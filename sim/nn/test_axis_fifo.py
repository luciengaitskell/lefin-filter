import math
import cocotb
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge
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

C_S00_AXIS_TDATA_WIDTH = 32
C_S00_AXIS_TSTRB_WIDTH = 4
C_S00_AXIS_TKEEP_WIDTH = 4

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

    def assert_stuff(self):
        assert self.inm.transactions == self.outm.transactions, (
            f"Transaction Count doesn't match! :-/ In: {self.inm.transactions}, Out: {self.outm.transactions}"
        )
        print(
            f"in transactions: {self.inm.transactions}, out transactions: {self.outm.transactions}"
        )
        assert self.scoreboard.errors == 0, (
            f"Scoreboard found {self.scoreboard.errors} errors! :-/"
        )

@cocotb.test()
async def test_fifos_basic(dut):
    """Test basic funcitonality of fifo, should pass data through unchanged
    after a dump signal until
    Simulate good data being passed through fifo as a burst with tlast
    dump_valid is raised after tlast sent
    goes fill_only -> nfill_ndrain -> drain_only  (done)-> fill_only
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_ITER = 5
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    data_in = [random.randint(0, max_data_value) for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in}
        })
    # tb.ind.append({"type": "write_single", "contents": {"data": 0XAFAFAFAF}})
    # tb.ind.append({"type": "write_single", "contents": {"data": 0X55555555, "last": 1}})
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    await ClockCycles(dut.aclk, NUM_ITER*5)  # wait a bit before starting
    dut.read_enable.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.read_enable.value = 0
    await ClockCycles(dut.aclk, NUM_ITER*5)

    tb.assert_stuff()

@cocotb.test()
async def test_fifos_basic2(dut):
    """ basic test but goes fill_only -> fill_and_drain -> drain_only -> fill_only
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_ITER = 5
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    data_in = [random.randint(0, max_data_value) for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in}
        })
    # tb.ind.append({"type": "write_single", "contents": {"data": 0XAFAFAFAF}})
    # tb.ind.append({"type": "write_single", "contents": {"data": 0X55555555, "last": 1}})
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    await ClockCycles(dut.aclk, NUM_ITER//2)  # wait a bit before starting but before a tlast is sent
    dut.read_enable.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.read_enable.value = 0
    await ClockCycles(dut.aclk, NUM_ITER*5)

    tb.assert_stuff()


@cocotb.test()
async def test_fifos_basic3(dut):
    """ test that goes from fill_only directly to drain_only (a read_enable and tlast at same time)
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_ITER = 5
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    for _ in range(NUM_ITER):
        data_in = random.randint(0, max_data_value)
        tb.ind.append({
            "type": "write_single",
            "contents": {"data": data_in}
            })
    tb.ind.append({"type": "write_single", "contents": {"data": 0X55555555, "last": 1}})
    for _ in range(NUM_ITER + 1):
        await FallingEdge(dut.aclk)
    dut.read_enable.value = 1             #should come with tlast
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})
    await ClockCycles(dut.aclk, NUM_ITER)  # wait a bit before starting but before a tlast is sent
    # tb.ind.append({"type": "write_single", "contents": {"data": 0X55555555, "last": 1}})
    await ClockCycles(dut.aclk, 1)
    dut.read_enable.value = 0
    await ClockCycles(dut.aclk, NUM_ITER*5)

    tb.assert_stuff()

@cocotb.test()
async def test_fifos_backpressure(dut):
    """Test fifo with inconsistent read enables to simulate backpressure
    should still pass data through correctly
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_ITER = 10
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    for i in range(NUM_ITER):
        data_in = random.randint(0, max_data_value)
        if i == NUM_ITER - 1:
            tb.ind.append({
                "type": "write_single",
                "contents": {"data": data_in, "last": 1}
            })
        else:
            tb.ind.append({
                "type": "write_single",
                "contents": {"data": data_in, "last": 0}
            })
        
    for _ in range(NUM_ITER*5):
        tb.outd.append({"type": "read", "duration": random.randint(1, 3)})
        tb.outd.append({"type": "pause", "duration": random.randint(1, 3)})
    await ClockCycles(dut.aclk, NUM_ITER)  # wait a bit before starting
    dut.read_enable.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.read_enable.value = 0
    await ClockCycles(dut.aclk, NUM_ITER*5)
    
    tb.assert_stuff()

@cocotb.test()
async def test_fifos_pause_sendside(dut):
    """ test that sends in a burst but has some cycles in between where master sends no data
    should still pass data through correctly
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_ITER = 10
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    for _ in range(NUM_ITER):
        data_in = random.randint(0, max_data_value)
        tb.ind.append({
            "type": "write_single",
            "contents": {"data": data_in}
            })
        tb.ind.append({"type": "pause", "duration": random.randint(1, 3)})

    tb.ind.append({
        "type": "write_single",
        "contents": {"data": random.randint(0, max_data_value), "last": 1}
        })
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    await ClockCycles(dut.aclk, NUM_ITER*5)  # wait a bit before starting
    dut.read_enable.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.read_enable.value = 0
    await ClockCycles(dut.aclk, NUM_ITER*5)

    tb.assert_stuff()


@cocotb.test()
async def test_fifos_vary_m_s_pauses(dut):
    """ test that has pauses on both master and slave side at varying intervals
    should still pass data through correctly
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_ITER = 10
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    for _ in range(NUM_ITER):
        data_in = random.randint(0, max_data_value)
        tb.ind.append({
            "type": "write_single",
            "contents": {"data": data_in}
            })
        tb.ind.append({"type": "pause", "duration": random.randint(1, 3)})

    tb.ind.append({
        "type": "write_single",
        "contents": {"data": random.randint(0, max_data_value), "last": 1}
        })
    
    for _ in range(NUM_ITER*5):
        tb.outd.append({"type": "read", "duration": random.randint(1, 3)})
        tb.outd.append({"type": "pause", "duration": random.randint(1, 3)})

    await ClockCycles(dut.aclk, NUM_ITER*5)  # wait a bit before starting
    dut.read_enable.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.read_enable.value = 0
    await ClockCycles(dut.aclk, NUM_ITER*5)

    tb.assert_stuff()

@cocotb.test()
async def test_fifos_multiple_bursts_no_pause(dut):
    """ test that sends multiple bursts of data separated no pauses
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_BURSTS = 3
    BURST_SIZE = 5
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    for _ in range(NUM_BURSTS):
        data_in = [random.randint(0, max_data_value) for _ in range(BURST_SIZE)]
        tb.ind.append({
            "type": "write_burst",
            "contents": {"data": data_in}
            })
        
    tb.outd.append({"type": "read", "duration": NUM_BURSTS * BURST_SIZE * 10})

    for _ in range(NUM_BURSTS):
        await ClockCycles(dut.aclk, BURST_SIZE*5)  # wait a bit before starting
        dut.read_enable.value = 1
        await ClockCycles(dut.aclk, 1)
        dut.read_enable.value = 0
    await ClockCycles(dut.aclk, BURST_SIZE*5)

    tb.assert_stuff()

@cocotb.test()
async def test_fifos_multiple_bursts_with_pause(dut):
    """ test that sends multiple bursts of data separated by pauses
    """
    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_BURSTS = 3
    BURST_SIZE = 5
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    for _ in range(NUM_BURSTS):
        data_in = [random.randint(0, max_data_value) for _ in range(BURST_SIZE)]
        tb.ind.append({
            "type": "write_burst",
            "contents": {"data": data_in}
            })
        tb.ind.append({"type": "pause", "duration": 50})
        
    tb.outd.append({"type": "read", "duration": NUM_BURSTS * BURST_SIZE * 10})

    for _ in range(NUM_BURSTS):
        await ClockCycles(dut.aclk, BURST_SIZE*5)  # wait a bit before starting
        dut.read_enable.value = 1
        await ClockCycles(dut.aclk, 1)
        dut.read_enable.value = 0
    await ClockCycles(dut.aclk, BURST_SIZE*5)

    tb.assert_stuff()

@cocotb.test()
async def test_fifos_random_multi_burst(dut):
    """ vary burst sizes, pauses, and read enables randomly
    """

    tb = FIFOsTestbench(dut)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_BURSTS = 20
    MAX_BURST_SIZE = 700
    max_data_value = 2 ** C_S00_AXIS_TDATA_WIDTH - 1
    for _ in range(NUM_BURSTS):
        burst_size = random.randint(1, MAX_BURST_SIZE)
        data_in = [random.randint(0, max_data_value) for _ in range(burst_size)]
        tb.ind.append({
            "type": "write_burst",
            "contents": {"data": data_in}
            })
        if random.random() < 0.5:
            tb.ind.append({"type": "pause", "duration": random.randint(10, 100)})
        else:
            pass  # no pause

    #randomize read enables and pauses on read side
    for _ in range(NUM_BURSTS * MAX_BURST_SIZE):
        read_duration = random.randint(1, 5)
        tb.outd.append({"type": "read", "duration": read_duration})
        if random.random() < 0.5:
            tb.outd.append({"type": "pause", "duration": random.randint(10, 100)})
        else:
            pass  # no pause
    
    # randomize read_enable timing
    for _ in range(NUM_BURSTS * 5): # possible to have multiple read enables per burst
        time_till_next_enable = random.randint(1, MAX_BURST_SIZE*2)
        await ClockCycles(dut.aclk, time_till_next_enable)
        dut.read_enable.value = 1
        await ClockCycles(dut.aclk, 1 * random.randint(1,3))
        dut.read_enable.value = 0
        await ClockCycles(dut.aclk, MAX_BURST_SIZE)
    await ClockCycles(dut.aclk, NUM_BURSTS * MAX_BURST_SIZE*3)

    tb.assert_stuff()

        



if __name__ == "__main__":
    build_and_run_sim(
        __file__,
        hdl_toplevel="axis_fifo",
        includes=["nn"],
        parameters={
            "DATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
            "DEPTH": 700,
        },
    )






        