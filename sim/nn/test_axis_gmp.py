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
    long_torch_to_packed,
    packed_to_long_torch,
)


DATA_TYPE = torch.int8
NUM_ITER = 50


class GMPTestbench(AXIS_Testbench):
    def __init__(self, dut, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]
        self.layer = nn.AdaptiveMaxPool1d(1)  # 1 output (per channel): global max pool
        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.input_buffer = None

    def in_callback(self, raw_input):
        input_values = (
            packed_to_long_torch(
                raw_input,
                int(self.dut.BIT_WIDTH.value),
                int(self.dut.CHANNEL_COUNT.value) * int(self.dut.WIDTH.value),
            )
            .view(
                (
                    self.dut.CHANNEL_COUNT.value,
                    self.dut.WIDTH.value,
                )
            )
            .to(DATA_TYPE)
        )
        super().in_callback(input_values)

    def compare_fn(self, result):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False

        result = (
            packed_to_long_torch(
                result,
                int(self.dut.BIT_WIDTH.value),
                int(self.dut.CHANNEL_COUNT.value),
            )
            .view(
                (
                    self.dut.CHANNEL_COUNT.value,
                    1,
                )
            )
            .to(DATA_TYPE)
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

    def send_input(self, input_values: Tensor):
        # split input data into chunks of max WIDTH (channels left intact)
        width_chunks = input_values.split(int(self.dut.WIDTH.value), dim=1)
        packed_chunks = [
            long_torch_to_packed(
                chunk.flatten().to(torch.long), int(self.dut.BIT_WIDTH.value)
            )
            for chunk in width_chunks
        ]

        self.ind.append(
            {
                "type": "write_burst",
                "contents": {"data": packed_chunks},
            }
        )

        expected_result = self.layer(input_values.to(torch.float64)).to(DATA_TYPE)

        self.expected_data_out.append(expected_result)
        self.scoreboard_queue.append((input_values, expected_result))


@cocotb.test
async def test_a(dut):
    """cocotb test for AXI-Stream global max pool"""
    tb = GMPTestbench(dut)

    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    # feed the driver on the M Side:
    for i in range(NUM_ITER):
        x = torch.randint(
            torch.iinfo(DATA_TYPE).min,
            torch.iinfo(DATA_TYPE).max,
            (
                int(dut.CHANNEL_COUNT.value),
                int(dut.WIDTH.value) * random.randint(3, 9),
            ),
            dtype=DATA_TYPE,
        )
        tb.send_input(x)
        if random.randint(0, 2):
            tb.ind.append({"type": "pause", "duration": random.randint(1, 6)})

    # feed the driver on the S Side:
    # always be ready to receive data:
    tb.outd.append({"type": "read", "duration": NUM_ITER})

    await ClockCycles(dut.aclk, 3500)
    assert NUM_ITER == tb.outm.transactions, "Transaction Count doesn't match! :-/"
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
        hdl_toplevel="axis_gmp",
        sources=["nn/axis_gmp.sv"],
        includes=["nn"],
        parameters={
            "WIDTH": 4,
            "BIT_WIDTH": torch.iinfo(DATA_TYPE).bits,
            "CHANNEL_COUNT": 2,
        },
    )
