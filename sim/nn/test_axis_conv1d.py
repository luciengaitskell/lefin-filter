import cocotb
import os
import sys
from pathlib import Path
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import (
    ClockCycles,
)
from cocotb_tools.runner import get_runner
from sim.bus.axis import AXIS_Testbench
import torch
from torch import nn, Tensor


test_file = os.path.basename(__file__).replace(".py", "")


async def reset(clk, rst, cycles_held=3, polarity=1):
    rst.value = polarity
    await ClockCycles(clk, cycles_held)
    rst.value = not polarity


KERNEL_WIDTH = 5
C_S00_AXIS_TDATA_WIDTH = 32
INPUT_BIT_WIDTH = 8
CHANNEL_OUT_COUNT = 2
WRITE_ITER = 11


def int8_torch_to_packed(value: Tensor) -> int:
    assert value.dtype == torch.int8, "Input tensor must be of dtype int8"
    packed = 0
    for i, v in enumerate(value):
        packed |= (int(v.item()) & 0xFF) << (i * 8)
    return packed


def packed_to_int8_torch(value: int, length: int) -> Tensor:
    values = []
    for i in range(length):
        byte = (value >> (i * 8)) & 0xFF
        if byte >= 0x80:
            byte -= 0x100
        values.append(byte)
    return torch.tensor(values, dtype=torch.int8)


def packed_to_long_torch(value: int, value_bit_width: int, length: int) -> Tensor:
    values = []
    for i in range(length):
        byte = (value >> (i * value_bit_width)) & ((1 << value_bit_width) - 1)
        sign_bit = 1 << (value_bit_width - 1)
        if byte & sign_bit:
            byte -= 1 << value_bit_width
        values.append(byte)
    return torch.tensor(values, dtype=torch.long)


class Conv1dTestbench(AXIS_Testbench):
    def __init__(self, dut, layer, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]

        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.layer: nn.Conv1d = layer
        assert self.layer.in_channels == 1, "Only single channel supported"
        assert self.layer.stride[0] == 1, "Only stride 1 supported"
        assert self.layer.padding[0] == 0, "Only no padding supported"
        self.input_buffer = None

    def in_callback(self, raw_input):
        input_values = packed_to_int8_torch(raw_input, self.dut.INPUT_WIDTH.value)
        super().in_callback(input_values)

        if self.input_buffer is not None:
            input_values = torch.cat((self.input_buffer, input_values), dim=0)
            conv_input = input_values.to(torch.float32).view(1, 1, -1)
            conv_output = self.layer(conv_input)
            conv_output = conv_output[0, :, : self.dut.NUM_PARALLEL_CONVS.value]
            expected_result = conv_output.round().to(torch.long)
            self.expected_data_out.append(expected_result)
            self.scoreboard_queue.append((input_values, expected_result))

        self.input_buffer = input_values[-(self.layer.kernel_size[0] - 1) :]

    def compare_fn(self, result):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False

        result = packed_to_long_torch(
            result,
            int(self.dut.OUTPUT_BIT_WIDTH.value),
            int(self.dut.NUM_PARALLEL_CONVS.value)
            * int(self.dut.CHANNEL_OUT_COUNT.value),
        ).view(
            (
                self.dut.CHANNEL_OUT_COUNT.value,
                self.dut.NUM_PARALLEL_CONVS.value,
            )
        )

        input_vals, expected_result = self.scoreboard_queue.popleft()
        result_okay = torch.isclose(result, expected_result, rtol=0.05, atol=0.1)
        if not result_okay.all():
            self.scoreboard.errors += 1
            self.dut._log.error(
                f"Mismatch! Got {result}, expected {expected_result} for input {input_vals}"
            )
        else:
            self.dut._log.info(
                f"Match! Got {result},expected {expected_result} for input {input_vals}"
            )
        return result_okay


@cocotb.test
async def test_a(dut):
    """cocotb test for AXI-Stream conv1d"""
    # Integer-like Conv1d: use float weights with integer values and integer inputs
    with torch.no_grad():
        layer = nn.Conv1d(
            in_channels=1,
            out_channels=CHANNEL_OUT_COUNT,
            kernel_size=KERNEL_WIDTH,
            stride=1,
            padding=0,
            bias=False,
        )
        int_kernel = torch.tensor([[1, 0, 4, 0, 0], [0, 1, 0, -1, 0]], dtype=torch.int8)
        assert int_kernel.shape == (layer.out_channels, KERNEL_WIDTH), (
            f"Kernel shape mismatch {int_kernel.shape} | {layer.weight.shape}"
        )
        layer.weight.copy_(int_kernel.float().view_as(layer.weight))
        dut.weights.value = int_kernel.tolist()

    tb = Conv1dTestbench(dut, layer=layer)

    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    EXPECTED_READ_TRANSACTIONS = WRITE_ITER - (
        (KERNEL_WIDTH - 1) / int(dut.INPUT_WIDTH.value)
    )
    assert EXPECTED_READ_TRANSACTIONS.is_integer(), (
        f"Expected read transactions must be integer, got {EXPECTED_READ_TRANSACTIONS}"
    )
    EXPECTED_READ_TRANSACTIONS = int(EXPECTED_READ_TRANSACTIONS)

    # feed the driver on the M Side:
    for i in range(WRITE_ITER):
        x = torch.randint(
            torch.iinfo(torch.int8).min,
            torch.iinfo(torch.int8).max,
            (dut.INPUT_WIDTH.value,),
            dtype=torch.int8,
        )
        tb.ind.append(
            {
                "type": "write_single",
                "contents": {"data": int8_torch_to_packed(x), "last": 0},
            }
        )
        tb.ind.append({"type": "pause", "duration": random.randint(1, 6)})
    # tb.ind.append({"type": "write_burst", "contents": {"data": list(...)}})
    # tb.ind.append({"type": "pause", "duration": 2})  # end with pause

    # feed the driver on the S Side:
    # always be ready to receive data:
    tb.outd.append({"type": "read", "duration": EXPECTED_READ_TRANSACTIONS})

    await ClockCycles(dut.aclk, 3500)
    assert tb.inm.transactions == tb.outm.transactions + int(
        dut.CYCLES_TO_FILL_PREVIOUS_INPUTS.value
    ), "Transaction Count doesn't match! :-/"
    print(
        f"in transactions: {tb.inm.transactions}, out transactions: {tb.outm.transactions}"
    )
    assert tb.scoreboard.errors == 0, (
        f"Scoreboard found {tb.scoreboard.errors} errors! :-/"
    )
    await ClockCycles(dut.aclk, 20)


def conv1d_runner():
    # https://docs.cocotb.org/en/v1.9.2/simulator_support.html#verilator
    sim = os.getenv("SIM", "verilator")
    build_test_args = [
        "-Wall",
        # Enable tracing and fst generation
        "--trace",
        "--trace-fst",
        "--trace-structs",
        # Enable non-blocking assignments
        "--timing",
    ]
    proj_path = Path(__file__).resolve().parent.parent.parent
    sources = [proj_path / "hdl" / "nn" / "axis_conv1d.sv"]
    parameters = {
        "KERNEL_WIDTH": KERNEL_WIDTH,
        "C_S00_AXIS_TDATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
        "INPUT_BIT_WIDTH": INPUT_BIT_WIDTH,
        "CHANNEL_OUT_COUNT": CHANNEL_OUT_COUNT,
    }
    sys.path.append(str(proj_path / "sim" / "nn"))
    runner = get_runner(sim)
    hdl_toplevel = "axis_conv1d"
    runner.build(
        sources=sources,
        includes=[proj_path / "hdl" / "nn"],
        hdl_toplevel=hdl_toplevel,
        always=True,
        build_args=build_test_args,
        parameters=parameters,
        timescale=("1ns", "1ps"),
        waves=True,
    )
    run_test_args = []
    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module=test_file,
        test_args=run_test_args,
        waves=True,
    )


if __name__ == "__main__":
    conv1d_runner()
