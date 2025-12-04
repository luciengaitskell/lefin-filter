import math
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
    long_torch_to_packed,
    packed_to_long_torch,
)

C_S00_AXIS_TDATA_WIDTH = 64
C_S00_AXIS_TSTRB_WIDTH = 8
C_S00_AXIS_TKEEP_WIDTH = 8

class FIFOsTestbench(AXIS_Testbench):
    def __init__(self, dut, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]

        self.expected_data_out = []  # contains list of expected outputs (Growing)

    def in_callback(self, input_value):
        super().in_callback(input_value)
        self.expected_data_out.append(input_value)
        self.scoreboard_queue.append((input_value, input_value))

    def compare_fn(self, result):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False
        
        inp, expected_output = self.scoreboard_queue.popleft()
        okay = result == expected_output
        if not okay:
            print(f"Mismatch! Input: {inp}, Expected: {expected_output}, Got: {result}")
        else:
            print(f"Match! Input: {inp}, Output: {result}")

        return okay

@cocotb.test()
async def test_fifos_basic(dut):
    """Test basic funcitonality of fifo, should pass data through unchanged
    after a dump signal until
    Simulate good data being passed through fifo as a burst with tlast
    dump_valid is raised after tlast sent
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut, dut.aclk, 2, 0)

    NUM_ITER = 10
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    data_in = [random.randint(0, max_data_value) for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in}
        })
    
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    await ClockCycles(dut.aclk, NUM_ITER*2)  # wait a bit before starting

    assert tb.inm.transactions == tb.outm.transactions, (
        "Transaction Count doesn't match! :-/"
    )
    print(
        f"in transactions: {tb.inm.transactions}, out transactions: {tb.outm.transactions}"
    )
    assert tb.scoreboard.errors == 0, (
        f"Scoreboard found {tb.scoreboard.errors} errors! :-/"
    )

if __name__ == "__main__":
    build_and_run_sim(
        __file__,
        hdl_toplevel="axis_fifos",
        source=["nn/axis_fc.sv"],
        includes=["nn"],
        parameters={
            "C_S00_AXIS_TDATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
            "C_S00_AXIS_TSTRB_WIDTH": C_S00_AXIS_TSTRB_WIDTH,
            "C_S00_AXIS_TKEEP_WIDTH": C_S00_AXIS_TKEEP_WIDTH,
        },
    )






        