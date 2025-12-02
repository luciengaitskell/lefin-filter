import cocotb
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import torch
from torch import nn, Tensor
from sim.bus.axis import AXIS_Testbench
from sim.util.sim import build_and_run_sim, reset
from sim.util.torch import (
    int8_torch_to_packed,
    packed_to_int8_torch,
    packed_to_long_torch,
)


C_S00_AXIS_TDATA_WIDTH = 32
BIT_WIDTH = 8
CHANNEL_COUNT = 2
NUM_ITER = 11


class ReLUTestbench(AXIS_Testbench):
    def view_tensor(self, tensor: Tensor) -> Tensor:
        return tensor.view(
            (
                self.dut.CHANNEL_COUNT.value,
                self.dut.WIDTH.value,
            )
        )

    def __init__(self, dut, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]

        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.input_buffer = None

    def in_callback(self, raw_input):
        input_values = self.view_tensor(
            packed_to_int8_torch(raw_input, self.dut.NUM_VALUES.value)
        )
        super().in_callback(input_values)

        expected_result = nn.functional.relu(input_values).to(torch.long)

        self.expected_data_out.append(expected_result)
        self.scoreboard_queue.append((input_values, expected_result))

    def compare_fn(self, result):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False

        result = self.view_tensor(
            packed_to_long_torch(
                result,
                int(self.dut.BIT_WIDTH.value),
                int(self.dut.CHANNEL_COUNT.value) * int(self.dut.WIDTH.value),
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
    """cocotb test for AXI-Stream relu"""
    # Integer-like Conv1d: use float weights with integer values and integer inputs

    tb = ReLUTestbench(dut)

    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    # feed the driver on the M Side:
    for i in range(NUM_ITER):
        x = torch.randint(
            torch.iinfo(torch.int8).min,
            torch.iinfo(torch.int8).max,
            (dut.NUM_VALUES.value,),
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
    tb.outd.append({"type": "read", "duration": NUM_ITER})

    await ClockCycles(dut.aclk, 3500)
    assert tb.inm.transactions == tb.outm.transactions, (
        "Transaction Count doesn't match! :-/"
    )
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
        hdl_toplevel="axis_relu",
        sources=["nn/axis_relu.sv"],
        includes=["nn"],
        parameters={
            "C_S00_AXIS_TDATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
            "BIT_WIDTH": BIT_WIDTH,
            "CHANNEL_COUNT": CHANNEL_COUNT,
        },
    )
