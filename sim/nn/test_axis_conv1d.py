import cocotb
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import torch
from torch import nn, Tensor
from sim.bus.axis import AXIS_Testbench
from sim.lib.sim import build_and_run_sim, reset
from sim.lib.torch import (
    int8_torch_to_packed,
    packed_to_int8_torch,
    packed_to_long_torch,
)


KERNEL_WIDTH = 5
C_S00_AXIS_TDATA_WIDTH = 32
INPUT_BIT_WIDTH = 8
CHANNEL_IN_COUNT = 1
CHANNEL_OUT_COUNT = 2
WRITE_ITER = 11


class Conv1dTestbench(AXIS_Testbench):
    def __init__(self, dut, layer, **kwargs):
        super().__init__(dut, monitor_kwargs=dict(include_metadata=True), **kwargs)
        self.scoreboard_queue: deque[tuple[dict, Tensor]]

        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.layer: nn.Conv1d = layer
        assert self.layer.in_channels == 1, "Only single channel supported"
        assert self.layer.stride[0] == 1, "Only stride 1 supported"
        assert self.layer.padding[0] == 0, "Only no padding supported"
        self.input_buffer = None

    def in_callback(self, input_and_metadata):
        raw_input = input_and_metadata["data"]
        input_values = packed_to_int8_torch(raw_input, self.dut.INPUT_WIDTH.value)
        super().in_callback(input_values)

        if self.input_buffer is not None:
            full_input = torch.cat((self.input_buffer, input_values), dim=0)
        else:
            full_input = input_values

        kernel_width = self.layer.kernel_size[0]
        num_parallel_convs = int(self.dut.NUM_PARALLEL_CONVS.value)

        if full_input.numel() >= kernel_width + num_parallel_convs - 1:
            conv_input = full_input.to(torch.float32).view(1, 1, -1)
            conv_output = self.layer(conv_input)
            conv_output = conv_output[0, :, :num_parallel_convs]
            expected_result = conv_output.round().to(torch.long)
            self.expected_data_out.append(expected_result)
            self.scoreboard_queue.append((input_and_metadata, expected_result))

        if full_input.numel() >= kernel_width - 1:
            self.input_buffer = full_input[-(kernel_width - 1) :]
        else:
            self.input_buffer = full_input

    def compare_fn(self, result_and_metadata):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False

        result = packed_to_long_torch(
            result_and_metadata["data"],
            int(self.dut.OUTPUT_BIT_WIDTH.value),
            int(self.dut.NUM_PARALLEL_CONVS.value)
            * int(self.dut.CHANNEL_OUT_COUNT.value),
        ).view(
            (
                self.dut.CHANNEL_OUT_COUNT.value,
                self.dut.NUM_PARALLEL_CONVS.value,
            )
        )

        input_and_metadata, expected_result = self.scoreboard_queue.popleft()
        input_vals = input_and_metadata["data"]
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

        def cascade_and(x: int, width: int) -> int:
            """Return integer whose bit i = AND of bits 0..i of x."""
            out = 0
            running = 1
            for i in range(width):
                running &= (x >> i) & 1
                out |= running << i
            return out

        metadata_okay = True
        expected_strb = cascade_and(
            input_and_metadata["strb"],
            int(self.dut.INPUT_WIDTH.value),
        )
        metadata_okay &= result_and_metadata["strb"] == expected_strb
        if not metadata_okay:
            self.scoreboard.errors += 1
            self.dut._log.error(
                f"Metadata mismatch! Got strb {result_and_metadata['strb']}, expected {expected_strb}"
            )

        return result_okay


@cocotb.test
async def test_a(dut):
    """cocotb test for AXI-Stream conv1d"""
    # Integer-like Conv1d: use float weights with integer values and integer inputs
    with torch.no_grad():
        layer = nn.Conv1d(
            in_channels=CHANNEL_IN_COUNT,
            out_channels=CHANNEL_OUT_COUNT,
            kernel_size=KERNEL_WIDTH,
            stride=1,
            padding=0,
            bias=False,
        )
        int_kernel = torch.tensor(
            [[[1, 0, 4, 0, 0]], [[0, 1, 0, -1, 0]]], dtype=torch.int8
        )
        int_biases = torch.tensor([1, -1], dtype=torch.int8)
        assert int_kernel.shape == (
            layer.out_channels,
            layer.in_channels,
            KERNEL_WIDTH,
        ), f"Kernel shape mismatch {int_kernel.shape} | {layer.weight.shape}"
        assert int_biases.shape == (layer.out_channels,), (
            f"Biases shape mismatch {int_biases.shape} | {(layer.out_channels,)}"
        )
        layer.weight.copy_(int_kernel.float().view_as(layer.weight))
        layer.bias = nn.Parameter(int_biases.float())
        dut.weights.value = int_kernel.tolist()
        dut.biases.value = int_biases.tolist()

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
        strb = (1 << int(dut.INPUT_WIDTH.value)) - 1
        # randomly zero out some strb bits (but always keep first byte valid)
        for bit_idx in range(1, dut.INPUT_WIDTH.value):
            if random.random() < 0.2:
                strb &= ~(1 << bit_idx)

        tb.ind.append(
            {
                "type": "write_single",
                "contents": {
                    "data": int8_torch_to_packed(x),
                    "strb": strb,
                    "last": 0,
                },
            }
        )
        if random.random() < 0.3:
            tb.ind.append({"type": "pause", "duration": random.randint(1, 6)})
    # tb.ind.append({"type": "write_burst", "contents": {"data": list(...)}})
    # tb.ind.append({"type": "pause", "duration": 2})  # end with pause

    # feed the driver on the S Side:
    # always be ready to receive data:
    initial_transactions = random.randint(1, (EXPECTED_READ_TRANSACTIONS * 2) // 3)
    tb.outd.append({"type": "read", "duration": initial_transactions})
    tb.outd.append({"type": "pause", "duration": random.randint(5, 15)})
    tb.outd.append(
        {"type": "read", "duration": EXPECTED_READ_TRANSACTIONS - initial_transactions}
    )

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


if __name__ == "__main__":
    build_and_run_sim(
        __file__,
        hdl_toplevel="axis_conv1d",
        parameters={
            "KERNEL_WIDTH": KERNEL_WIDTH,
            "C_S00_AXIS_TDATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
            "INPUT_BIT_WIDTH": INPUT_BIT_WIDTH,
            "CHANNEL_IN_COUNT": CHANNEL_IN_COUNT,
            "CHANNEL_OUT_COUNT": CHANNEL_OUT_COUNT,
        },
    )
