import cocotb
import random
from collections import deque
from itertools import islice
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
import torch
from sim.bus.axis import AXIS_Testbench
from sim.util.sim import build_and_run_sim, reset
from sim.util.torch import int8_torch_to_packed


C_S00_AXIS_TDATA_WIDTH = 32
BIT_WIDTH = 8
MAXIMUM_INPUT_BYTES = 64

NUM_ITER = 11


class ModelInterfaceTestbench(AXIS_Testbench):
    def __init__(self, dut, **kwargs):
        super().__init__(dut, monitor_kwargs=dict(include_metadata=True), **kwargs)
        self.scoreboard_queue: deque

        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.input_buffer = None

    def in_callback(self, raw_input):
        super().in_callback(raw_input)

    def compare_fn(self, result):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False

        print(result)
        input_vals = self.scoreboard_queue.popleft()

        result_okay = True
        result_okay &= result["strb"] == input_vals["keep"]
        result_okay &= result["data"] == input_vals["data"]

        if not result_okay:
            self.scoreboard.errors += 1
            self.dut._log.error(f"Mismatch! Got {result}, for input {input_vals}")
        else:
            self.dut._log.info(f"Match! Got {result}, for input {input_vals}")
        return result_okay

    def send_input(self, input_values: torch.Tensor) -> int:
        chunked_input_data = input_values.split(int(self.dut.WIDTH.value))
        packed_chunks = [int8_torch_to_packed(chunk) for chunk in chunked_input_data]
        chunk_lengths = [len(chunk) for chunk in chunked_input_data]
        chunk_tkeeps = [(1 << length) - 1 for length in chunk_lengths]

        self.ind.append(
            {
                "type": "write_burst",
                "contents": {"data": packed_chunks, "keep": chunk_tkeeps},
            }
        )
        self.scoreboard_queue.extend(
            {"data": packed, "keep": tkeep}
            for packed, tkeep in islice(
                zip(packed_chunks, chunk_tkeeps), int(self.dut.MAXIMUM_CYCLES.value)
            )
        )

        expected_read_transactions = min(
            len(packed_chunks), int(self.dut.MAXIMUM_CYCLES.value)
        )
        self.outd.append(
            {
                "type": "read",
                "duration": expected_read_transactions,
            }
        )
        return expected_read_transactions


@cocotb.test
async def test_a(dut):
    """cocotb test for AXI-Stream model interface."""

    tb = ModelInterfaceTestbench(dut)

    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    test_lengths = [
        *(random.randint(1, MAXIMUM_INPUT_BYTES - 1) for _ in range(3)),
        *(MAXIMUM_INPUT_BYTES for _ in range(3)),
        *(
            random.randint(1 + MAXIMUM_INPUT_BYTES, 3 * MAXIMUM_INPUT_BYTES)
            for _ in range(3)
        ),
    ]
    random.shuffle(test_lengths)

    total_expected_read_transactions = 0
    for data_length in test_lengths:
        full_input_data = torch.randint(
            torch.iinfo(torch.int8).min,
            torch.iinfo(torch.int8).max,
            (data_length,),
            dtype=torch.int8,
        )
        total_expected_read_transactions += tb.send_input(full_input_data)
        if random.randint(0, 2):
            tb.ind.append({"type": "pause", "duration": random.randint(1, 6)})

    await ClockCycles(dut.aclk, 1000)
    assert total_expected_read_transactions == tb.outm.transactions, (
        f"Transaction count ({tb.outm.transactions}) not as "
        f"expected ({total_expected_read_transactions}) :-/"
    )

    await ClockCycles(dut.aclk, 1000)
    tb.outd.append(
        {
            "type": "read",
            "duration": 10,
        }
    )
    assert total_expected_read_transactions == tb.outm.transactions, (
        f"Transaction count changed from {total_expected_read_transactions} "
        f"to {tb.outm.transactions} after extra reads!"
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
        hdl_toplevel="model_interface",
        parameters={
            "C_S00_AXIS_TDATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
            "BIT_WIDTH": BIT_WIDTH,
            "MAXIMUM_INPUT_BYTES": MAXIMUM_INPUT_BYTES,
        },
    )
