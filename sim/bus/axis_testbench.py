from collections import deque

from cocotb_bus.scoreboard import Scoreboard

from .axis import M_AXIS_Driver, S_AXIS_Driver, AXIS_Monitor


class AXIS_Testbench:
    def __init__(self, dut, **kwargs):
        self.dut = dut
        self.scoreboard = Scoreboard(dut, fail_immediately=False)
        self.scoreboard_queue: deque = deque()
        self.data_in = []
        self.data_out = []

        self.inm = AXIS_Monitor(dut, "s00", dut.aclk, callback=self.in_callback)
        self.ind = M_AXIS_Driver(dut, "s00", dut.aclk)  # M driver for S port

        self.outm = AXIS_Monitor(dut, "m00", dut.aclk, callback=self.out_callback)
        self.outd = S_AXIS_Driver(dut, "m00", dut.aclk)  # S driver for M port

        self.scoreboard.add_interface(
            self.outm,
            self.scoreboard_queue,
            compare_fn=self.compare_fn,
        )

    def compare_fn(self, result):
        expected_result = self.scoreboard_queue.popleft()
        return result == expected_result

    def in_callback(self, data):
        self.data_in.append(data)

    def out_callback(self, result):
        self.data_out.append(result)
