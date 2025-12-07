import cocotb
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
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
    DEFAULT_CONFIG,
    DatasetConfig,
    ensure_preprocessed,
    load_split_arrays,
)
from model.model import load_unit_scale_model
from model.checkpoints import checkpoints_dir
from model import export_weights  # noqa: F401 - will run `add_safe_globals`


DATA_TYPE = torch.int8
NUM_ITER = 1
C_S00_AXIS_TDATA_WIDTH = 32


class ModelTestbench(AXIS_Testbench):
    def __init__(self, dut, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]
        self.layer = nn.AdaptiveMaxPool1d(1)  # 1 output (per channel): global max pool
        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.input_buffer = None
        self.dataset_cfg: DatasetConfig = DEFAULT_CONFIG.model_copy()
        self.dataset_cfg = self.dataset_cfg.model_copy(
            update={
                "name": "ustc_packet",
                "layer": "l2",
                "include_layer_suffix": True,
                "target_size": 784,
            }
        )
        ensure_preprocessed(self.dataset_cfg)
        x_test, y_test = load_split_arrays(self.dataset_cfg, "test")
        self.x_test = x_test
        self.y_test = y_test

        # 3) Load your unit-scale model
        self.model = load_unit_scale_model(
            checkpoints_dir / "ustc_packet_l2/best_int8.pt",
            arch="gmp",
            input_len=784,
            num_classes=2,
            small_model=True,
            device="cpu",
        )
        self.model.eval()

    def in_callback(self, raw_input):
        input_values = (
            packed_to_long_torch(
                raw_input,
                int(self.dut.INPUT_BIT_WIDTH.value),
                int(self.dut.INPUT_WIDTH.value),
            )
            .view((self.dut.INPUT_WIDTH.value,))
            .to(DATA_TYPE)
        )
        super().in_callback(input_values)

    def compare_fn(self, raw_result):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False

        result = (
            packed_to_long_torch(
                raw_result,
                int(self.dut.OUTPUT_BIT_WIDTH.value),
                2,
            )
            .view((1, 2))
            .to(torch.int64)
        )

        input_vals, expected_result = self.scoreboard_queue.popleft()
        result_okay = torch.isclose(result, expected_result, rtol=0.05, atol=0)
        if not result_okay.all():
            self.scoreboard.errors += 1
            expected_raw = long_torch_to_packed(
                expected_result.view(-1),
                int(self.dut.OUTPUT_BIT_WIDTH.value),
            )

            self.dut._log.error(
                f"Mismatch! Got {result}, expected {expected_result} for input: \n{input_vals}\nRaw 0x{raw_result:x} != expected 0x{expected_raw:x}"
            )
        else:
            self.dut._log.info(
                f"Match! Got {result},expected {expected_result} for input {input_vals}"
            )
        return result_okay

    def send_test_input(self):
        N = self.x_test.shape[0]
        idx = np.random.randint(0, N)  # random test sample index

        x_one = self.x_test[idx]  # shape (784,)
        y_one = self.y_test[idx]

        x_one_t = torch.from_numpy(x_one)

        with torch.no_grad():
            logits = self.model(x_one_t.float().reshape(1, 1, x_one.shape[0]))
            probs = torch.softmax(logits, dim=1)
            preds = probs.argmax(dim=1)

        print("preds:", preds.numpy())
        print("labels:", y_one)

        chunked_input_data = x_one_t.to(torch.int8).split(
            int(self.dut.INPUT_WIDTH.value)
        )
        packed_chunks = [int8_torch_to_packed(chunk) for chunk in chunked_input_data]
        chunk_lengths = [len(chunk) for chunk in chunked_input_data]
        chunk_tstrb = [(1 << length) - 1 for length in chunk_lengths]

        self.ind.append(
            {
                "type": "write_burst",
                "contents": {"data": packed_chunks, "strb": chunk_tstrb},
            }
        )

        expected_result = logits.to(torch.int64)

        self.expected_data_out.append(expected_result)
        self.scoreboard_queue.append((x_one_t, expected_result))


@cocotb.test
async def test_a(dut):
    """cocotb test for AXI-Stream full model"""
    tb = ModelTestbench(dut)

    cocotb.start_soon(Clock(dut.aclk, 10, unit="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    # feed the driver on the M Side:
    for i in range(NUM_ITER):
        tb.send_test_input()
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
        hdl_toplevel="model",
        parameters={
            "C_S00_AXIS_TDATA_WIDTH": C_S00_AXIS_TDATA_WIDTH,
            "INPUT_BIT_WIDTH": torch.iinfo(DATA_TYPE).bits,
        },
    )
