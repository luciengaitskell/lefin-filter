import os
from collections import deque
from cocotb.triggers import (
    RisingEdge,
    FallingEdge,
    ReadOnly,
    ReadWrite,
)
from cocotb_bus.drivers import BusDriver
from cocotb_bus.monitors import BusMonitor
from cocotb_bus.scoreboard import Scoreboard

test_file = os.path.basename(__file__).replace(".py", "")


class AXIS_Monitor(BusMonitor):
    """
    monitors axi streaming bus
    """

    transactions = 0  # use this variable to track good ready/valid handshakes

    def __init__(self, dut, name, clk, callback=None, *, include_metadata=False):
        self._signals = [
            "axis_tvalid",
            "axis_tready",
            "axis_tlast",
            "axis_tdata",
            "axis_tstrb",
            "axis_tkeep",
        ]
        BusMonitor.__init__(self, dut, name, clk, callback=callback)
        self.clock = clk
        self.transactions = 0
        self.dut = dut
        self.include_metadata = include_metadata

    async def _monitor_recv(self):
        """
        Monitor receiver
        """
        rising_edge = RisingEdge(self.clock)  # make these coroutines once and reuse
        falling_edge = FallingEdge(self.clock)
        read_only = ReadOnly()  # This is
        while True:
            # await rising_edge #can either wait for just edge...
            # or you can also wait for falling edge/read_only (see note in lab)
            await falling_edge  # sometimes see in AXI shit
            await read_only  # readonly (the postline)
            valid = self.bus.axis_tvalid.value
            ready = self.bus.axis_tready.value
            last = self.bus.axis_tlast.value
            data = self.bus.axis_tdata.value
            if valid and ready:
                self.transactions += 1
                all_data = dict(
                    data=data.to_unsigned(),
                    last=last,
                    name=self.name,
                    count=self.transactions,
                )

                optional_bus_fields = dict(
                    strb=self.bus.axis_tstrb,
                    keep=self.bus.axis_tkeep,
                )
                for field_name, signal in optional_bus_fields.items():
                    if signal is not None:
                        all_data[field_name] = signal.value.to_unsigned()

                self.dut._log.info(f"{self.name}: {all_data}")
                if self.include_metadata:
                    self._recv(all_data)
                else:
                    self._recv(data.to_unsigned())


class AXIS_Driver(BusDriver):
    def __init__(self, dut, name, clk, role="M"):
        self._signals = [
            "axis_tvalid",
            "axis_tready",
            "axis_tlast",
            "axis_tdata",
            "axis_tstrb",
            "axis_tkeep",
        ]
        BusDriver.__init__(self, dut, name, clk)
        self.clock = clk
        self.dut = dut


class M_AXIS_Driver(AXIS_Driver):
    def __init__(self, dut, name, clk):
        super().__init__(dut, name, clk)
        self.bus.axis_tdata.value = 0
        self.bus.axis_tlast.value = 0
        self.bus.axis_tvalid.value = 0

        self.rising_edge = RisingEdge(self.clock)
        self.falling_edge = FallingEdge(self.clock)
        self.read_only = ReadOnly()

    async def wait_for_write_region(self):
        if self.clock.value:
            await self.falling_edge

    async def wait_for_transaction(self):
        await self.rising_edge  # transaction happens here

        ## DO NOT go to ReadOnly, as we want state right before clock edge
        # await self.read_only  # make sure everything is stable

        if not self.bus.axis_tready.value:
            # wait for ready from subordinate
            await RisingEdge(self.bus.axis_tready)
            await self.rising_edge  # transaction happens here
        await self.falling_edge  # deassert valid after transaction

    async def _driver_send(self, value, sync=True):
        if value.get("type") == "pause":
            await self.falling_edge
            self.bus.axis_tvalid.value = 0  # set to 0 and be done.
            self.bus.axis_tlast.value = 0  # set to 0 and be done.
            for i in range(value.get("duration", 1)):
                await self.rising_edge

        elif value.get("type") == "write_single":
            contents = value.get("contents", {})
            data = contents.get("data", 0)
            last = contents.get("last", 0)
            await self.wait_for_write_region()
            self.bus.axis_tdata.value = data
            self.bus.axis_tlast.value = last
            self.bus.axis_tvalid.value = 1
            await self.wait_for_transaction()
            self.bus.axis_tvalid.value = 0
            self.bus.axis_tlast.value = 0
        elif value.get("type") == "write_burst":
            contents = value.get("contents", {})
            data = contents.get("data", [0])
            strb: list | None = contents.get("strb", None)
            keep: list | None = contents.get("keep", None)
            await self.wait_for_write_region()
            for i, value in enumerate(data):
                self.bus.axis_tdata.value = int(value)
                if i == (len(data) - 1):
                    self.bus.axis_tlast.value = 1
                else:
                    self.bus.axis_tlast.value = 0
                self.bus.axis_tvalid.value = 1
                if strb is not None:
                    self.bus.axis_tstrb.value = int(strb[i])
                if keep is not None:
                    self.bus.axis_tkeep.value = int(keep[i])
                await self.wait_for_transaction()
                self.bus.axis_tvalid.value = 0
                self.bus.axis_tlast.value = 0
        else:
            raise ValueError(f"Unknown command {value}")


class S_AXIS_Driver(BusDriver):
    def __init__(self, dut, name, clk):
        self._signals = [
            "axis_tvalid",
            "axis_tready",
            "axis_tlast",
            "axis_tdata",
            "axis_tstrb",
        ]
        AXIS_Driver.__init__(self, dut, name, clk)
        self.bus.axis_tready.value = 0

        self.rising_edge = RisingEdge(self.clock)
        self.falling_edge = FallingEdge(self.clock)
        self.read_only = ReadOnly()

    async def wait_for_write_region(self):
        if self.clock.value:
            await self.falling_edge

    async def _driver_send(self, value, sync=True):
        if value.get("type") == "pause":
            await self.wait_for_write_region()
            self.bus.axis_tready.value = 0  # set to 0 and be done.
            for i in range(value.get("duration", 1)):
                await self.rising_edge
        elif value.get("type") == "read":
            await self.wait_for_write_region()
            self.bus.axis_tready.value = 1
            # wait for `duration` number of read transactions

            duration = value.get("duration", 1)
            # await self.rising_edge
            ## FIXME: maybe add some prints and see where they line up in script output
            for i in range(duration):
                await self.read_only
                while not self.bus.axis_tvalid.value:
                    # async efficient wait for valid on transaction
                    await RisingEdge(self.bus.axis_tvalid)
                    await self.rising_edge  # transaction happens here
                print(f"Read transaction {i + 1}/{duration} occurred")
                await self.falling_edge
            self.bus.axis_tready.value = 0
        else:
            raise ValueError(f"Unknown command {value}")

class AXIS_Testbench:
    def __init__(self, dut, *, monitor_kwargs=None):
        self.dut = dut
        self.scoreboard = Scoreboard(dut, fail_immediately=False)
        self.scoreboard_queue: deque = deque()
        self.data_in = []
        self.data_out = []
        monitor_kwargs = monitor_kwargs or {}

        self.inm = AXIS_Monitor(
            dut,
            "s00",
            dut.aclk,
            callback=self.in_callback,
            **monitor_kwargs,
        )
        self.ind = M_AXIS_Driver(dut, "s00", dut.aclk)  # M driver for S port

        self.outm = AXIS_Monitor(
            dut,
            "m00",
            dut.aclk,
            callback=self.out_callback,
            **monitor_kwargs,
        )
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
