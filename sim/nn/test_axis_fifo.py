import math
import cocotb
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge
import torch
from torch import nn, Tensor
from sim.bus.axis import AXIS_Testbench
from sim.lib.sim import build_and_run_sim, reset
from sim.lib.torch import (
    int8_torch_to_packed,
    packed_to_int8_torch,
    long_torch_to_packed,
    packed_to_long_torch,
)

C_S00_AXIS_TDATA_WIDTH = 32
C_S00_AXIS_TSTRB_WIDTH = 4
C_S00_AXIS_TKEEP_WIDTH = 4

class FIFOsTestbench(AXIS_Testbench):
    def __init__(self, dut, ignore_scoreboard=False, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]

        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.ignore_scoreboard = ignore_scoreboard
    def in_callback(self, input_value):
        super().in_callback(input_value)
        self.expected_data_out.append(input_value)
        self.scoreboard_queue.append((input_value, input_value))

    def compare_fn(self, result):
        """Compare the received transaction with the expected output."""
        if self.ignore_scoreboard:
            okay = True
        else:
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
    dut.packet_input_valid.value = 1
    dut.packet_input_good.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0
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
    dut.packet_input_valid.value = 1
    dut.packet_input_good.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0
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
    dut.packet_input_valid.value = 1             #should come with tlast
    dut.packet_input_good.value = 1
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})
    await ClockCycles(dut.aclk, NUM_ITER)  # wait a bit before starting but before a tlast is sent
    # tb.ind.append({"type": "write_single", "contents": {"data": 0X55555555, "last": 1}})
    await ClockCycles(dut.aclk, 1)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0
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
    dut.packet_input_valid.value = 1
    dut.packet_input_good.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0
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
    dut.packet_input_valid.value = 1
    dut.packet_input_good.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0
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
    dut.packet_input_valid.value = 1
    dut.packet_input_good.value = 1
    await ClockCycles(dut.aclk, 1)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0
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
        dut.packet_input_valid.value = 1
        dut.packet_input_good.value = 1
        await ClockCycles(dut.aclk, 1)
        dut.packet_input_valid.value = 0
        dut.packet_input_good.value = 0
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
        dut.packet_input_valid.value = 1
        dut.packet_input_good.value = 1
        await ClockCycles(dut.aclk, 1)
        dut.packet_input_valid.value = 0
        dut.packet_input_good.value = 0
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
        dut.packet_input_valid.value = 1
        dut.packet_input_good.value = 1
        await ClockCycles(dut.aclk, 1 * random.randint(1,3))
        dut.packet_input_valid.value = 0
        dut.packet_input_good.value = 0
        await ClockCycles(dut.aclk, MAX_BURST_SIZE)
    await ClockCycles(dut.aclk, NUM_BURSTS * MAX_BURST_SIZE*3)

    tb.assert_stuff()


@cocotb.test()
async def test_fifos_drop_packet(dut):
    """ test that drops a packet in the fifo
    """
    tb = FIFOsTestbench(dut, ignore_scoreboard=True)
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
    dut.packet_input_valid.value = 1
    dut.packet_input_good.value = 0   # drop packet
    await ClockCycles(dut.aclk, 1)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0
    await ClockCycles(dut.aclk, NUM_ITER*5)

    assert len(tb.data_in) == NUM_ITER, f"Should have recieved all input data, but got: {len(tb.data_in)} instead"
    assert len(tb.data_out) == 0, f"Should have recieved no output data, but got: {len(tb.data_out)} instead"

async def pulse_dut_packet_signal(dut, good: bool):
    """ helper function to pulse the packet_input_valid and good signals for 1 cycle
    """
    await FallingEdge(dut.aclk)
    dut.packet_input_valid.value = 1
    dut.packet_input_good.value = 1 if good else 0
    await FallingEdge(dut.aclk)
    dut.packet_input_valid.value = 0
    dut.packet_input_good.value = 0

@cocotb.test()
async def test_fifos_drop_packet_with_good(dut):
    """ test that drops a packet in the fifo but has good packet after
    """
    tb = FIFOsTestbench(dut, ignore_scoreboard=True)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_ITER = 3
    # bad packet before
    data_in1 = [0x11111111 for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in1}
        })
    #pause for a bit
    tb.ind.append({"type": "pause", "duration": 3})
    # good packet after
    data_in2 = [0x22222222 for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in2}
        })
    #pause for a bit
    tb.ind.append({"type": "pause", "duration": 3})

    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    #schedule good/bad packet pulses
    await ClockCycles(dut.aclk, NUM_ITER-1)  # wait a bit
    await pulse_dut_packet_signal(dut, good=False)  # bad packet
    await ClockCycles(dut.aclk, 3)  # wait a bit
    await pulse_dut_packet_signal(dut, good=True)  # good packet
    await ClockCycles(dut.aclk, NUM_ITER*5)

    assert len(tb.data_in) == NUM_ITER*2, f"Should have recieved all input data, but got: {len(tb.data_in)} instead"
    assert len(tb.data_out) == NUM_ITER, f"Should have recieved only good output data, but got: {len(tb.data_out)} instead"
    for data in tb.data_out:
        assert data == 0x22222222, f"Output data should only contain good packet data, got: {data} instead"

@cocotb.test()
async def test_fifos_sandwich_drop(dut):
    """ test that has good packet, bad packet, good packet in sequence
    """
    tb = FIFOsTestbench(dut, ignore_scoreboard=True)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_ITER = 3
    # good packet before
    data_in1 = [0x11111111 for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in1}
        })
    #pause for a bit
    tb.ind.append({"type": "pause", "duration": 3})
    # bad packet in middle
    data_in2 = [0x22222222 for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in2}
        })
    #pause for a bit
    tb.ind.append({"type": "pause", "duration": 3})
    # good packet after
    data_in3 = [0x33333333 for _ in range(NUM_ITER)]
    tb.ind.append({
        "type": "write_burst",
        "contents": {"data": data_in3}
        })
    #pause for a bit
    tb.ind.append({"type": "pause", "duration": 3})

    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    #schedule good/bad packet pulses
    await ClockCycles(dut.aclk, NUM_ITER-1)  # wait a bit
    await pulse_dut_packet_signal(dut, good=True)  # good packet
    await ClockCycles(dut.aclk, 3)  # wait a bit
    await pulse_dut_packet_signal(dut, good=False)  # bad packet
    await ClockCycles(dut.aclk, 3)  # wait a bit
    await pulse_dut_packet_signal(dut, good=True)  # good packet
    await ClockCycles(dut.aclk, NUM_ITER*5)

    expected_output = data_in1 + data_in3
    assert len(tb.data_in) == NUM_ITER*3, f"Should have recieved all input data, but got: {len(tb.data_in)} instead"
    assert len(tb.data_out) == NUM_ITER*2, f"Should have recieved only good output data, but got: {len(tb.data_out)} instead"
    for i, data in enumerate(tb.data_out):
        assert data == expected_output[i], f"Output data should only contain good packet data, got: {data} instead"

@cocotb.test
async def test_fifos_drop_with_pauses_in_sending(dut):
    """ test that drops packet but that packet is sent individually rather than in a burst
    """

    tb = FIFOsTestbench(dut, ignore_scoreboard=True)
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)    

    NUM_ITER = 6
    # packet to drop
    for _ in range(NUM_ITER-1):
        data_in = 0xBEEFBEEF
        tb.ind.append({
            "type": "write_single",
            "contents": {"data": data_in}
            })
        tb.ind.append({"type": "pause", "duration": 1})
    tb.ind.append({"type": "write_single", "contents": {"data": 0xBEEFBEEF, "last": 1}})
    
    # good packet after
    for _ in range(NUM_ITER-1):
        data_in = 0xAAAAAAAA
        tb.ind.append({
            "type": "write_single",
            "contents": {"data": data_in}
            })
        tb.ind.append({"type": "pause", "duration": 1})
    tb.ind.append({"type": "write_single", "contents": {"data": 0xAAAAAAAA, "last": 1}})

    # bad packet finally
    for _ in range(NUM_ITER-1):
        data_in = 0xFEEDFEED
        tb.ind.append({
            "type": "write_single",
            "contents": {"data": data_in}
            })
        tb.ind.append({"type": "pause", "duration": 1})
    tb.ind.append({"type": "write_single", "contents": {"data": 0xFEEDFEED, "last": 1}})

    # read
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    await ClockCycles(dut.aclk, 2*NUM_ITER-1)  # for first packet
    await pulse_dut_packet_signal(dut, good=False)  # bad packet
    await ClockCycles(dut.aclk, 3*NUM_ITER+2)
    await pulse_dut_packet_signal(dut, good=True)  # good packet
    await ClockCycles(dut.aclk, 2*NUM_ITER-1)
    await pulse_dut_packet_signal(dut, good=False)  # bad packet
    await ClockCycles(dut.aclk, NUM_ITER*5)

    #print hex values of data in and out for debugging in one line
    assert len(tb.data_in) == NUM_ITER*3, f"Should have recieved all input data, but got: {len(tb.data_in)} instead"
    assert len(tb.data_out) == NUM_ITER, f"Should have recieved only good output data, but got: {len(tb.data_out)} instead"
    for data in tb.data_out:
        assert data == 0xAAAAAAAA, f"Output data should only contain good packet data, got: {data} instead"




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






        