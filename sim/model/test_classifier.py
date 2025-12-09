import cocotb
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, ReadOnly
import numpy as np
import torch
from torch import nn, Tensor
from sim.bus.axis import AXIS_Testbench
from sim.lib.sim import build_and_run_sim, reset
from sim.lib.torch import (
    int8_torch_to_packed,
    packed_to_long_torch,
    long_torch_to_packed,
)
from model.dataset import (
    load_split_raw,
)
from sim.model.test_model import ModelTestbench
from model.model import load_unit_scale_model
from model.checkpoints import checkpoints_dir
from model import export_weights  # noqa: F401 - will run `add_safe_globals`


DATA_TYPE = torch.int8
NUM_ITER = 150
C_S00_AXIS_TDATA_WIDTH = 32


class ClassifierTestbench(ModelTestbench):
    def __init__(self, dut, **kwargs):
        super().__init__(dut, enable_out=False, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, int]]
        self.x_raw, self.y_raw = load_split_raw(self.dataset_cfg, "test")

    def in_callback(self, raw_input):
        input_values = (
            packed_to_long_torch(
                raw_input,
                int(self.dut.BIT_WIDTH.value),
                int(self.dut.WIDTH.value),
            )
            .view((self.dut.WIDTH.value,))
            .to(DATA_TYPE)
        )
        AXIS_Testbench.in_callback(self, input_values)

    def send_test_input(self):
        N = self.x_raw.shape[0]
        idx = np.random.randint(0, N)  # random test sample index

        x_one_raw = self.x_raw[idx]
        y_one = self.y_raw[idx]

        x_one = np.frombuffer(x_one_raw, dtype=np.uint8)
        x_one_t = torch.from_numpy(x_one)
        x_one_t_fixed_width = x_one_t[:784]
        if len(x_one_t) < 784:
            x_one_t_fixed_width = torch.nn.functional.pad(
                x_one_t_fixed_width, (0, 784 - len(x_one_t_fixed_width))
            )

        with torch.no_grad():
            logits = self.model(x_one_t_fixed_width.float().reshape(1, 1, -1))
            probs = torch.softmax(logits, dim=1)
            preds = probs.argmax(dim=1)

        print("preds:", preds.numpy())
        print("labels:", y_one)

        chunked_input_data = x_one_t.to(torch.int8).split(int(self.dut.WIDTH.value))
        packed_chunks = [int8_torch_to_packed(chunk) for chunk in chunked_input_data]
        chunk_lengths = [len(chunk) for chunk in chunked_input_data]
        chunk_tkeep = [(1 << length) - 1 for length in chunk_lengths]

        self.ind.append(
            {
                "type": "write_burst",
                "contents": {"data": packed_chunks, "keep": chunk_tkeep},
            }
        )

        expected_result = preds.item()

        self.expected_data_out.append(expected_result)
        self.scoreboard_queue.append((x_one_t, round(expected_result)))


@cocotb.test
async def test_a(dut):
    """cocotb test for AXI-Stream full model"""
    tb = ClassifierTestbench(dut)

    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    # feed the driver on the M Side:
    for i in range(NUM_ITER):
        tb.send_test_input()
        if random.randint(0, 2):
            tb.ind.append({"type": "pause", "duration": random.randint(1, 6)})

    while tb.scoreboard_queue:
        await RisingEdge(dut.model_classification_valid)
        await ReadOnly()
        raw_output = int(dut.model_classification_malware.value)
        input_vals, expected_result = tb.scoreboard_queue.popleft()
        result_okay = True
        result_okay &= raw_output == expected_result
        if not result_okay:
            tb.scoreboard.errors += 1
            dut._log.error(
                f"Mismatch! Got {raw_output}, expected {expected_result} for input: \n"
                f"{input_vals}, len {len(input_vals)}"
            )
        else:
            dut._log.info(
                f"Match! Got {raw_output}, expected {expected_result} for input\n"
                f"{input_vals}, len {len(input_vals)}"
            )

    await ClockCycles(dut.aclk, 3500)
    assert tb.scoreboard.errors == 0, (
        f"Scoreboard found {tb.scoreboard.errors} errors! :-/"
    )
    await ClockCycles(dut.aclk, 20)


if __name__ == "__main__":
    build_and_run_sim(
        __file__,
        hdl_toplevel="classifier",
        parameters={
            "C_S00_AXIS_TDATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
            "BIT_WIDTH": torch.iinfo(DATA_TYPE).bits,
        },
    )
