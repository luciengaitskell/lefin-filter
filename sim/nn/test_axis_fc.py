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

INPUT_BIT_WIDTH = 16
CHANNEL_IN_COUNT = 8
OUTPUT_BIT_WIDTH = 16
CHANNEL_OUT_COUNT = 2
C_S00_AXIS_TDATA_WIDTH = INPUT_BIT_WIDTH * CHANNEL_IN_COUNT
C_M00_AXIS_TDATA_WIDTH = OUTPUT_BIT_WIDTH * CHANNEL_OUT_COUNT

class FCTestbench(AXIS_Testbench):
    def __init__(self, dut, layer, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]

        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.input_buffer = None
        self.layer: nn.Linear = layer

    def in_callback(self, raw_input):
        input_values = packed_to_long_torch(raw_input, self.dut.INPUT_WIDTH.value, self.dut.NUM_VALUES.value)
        super().in_callback(input_values)

        weight = self.layer.weight.data.to(torch.long)
        bias = self.layer.bias.data.to(torch.long)
        expected_result = torch.matmul(input_values, weight.t()) + bias
        self.expected_data_out.append(expected_result)
        self.scoreboard_queue.append((input_values, expected_result))

    def compare_fn(self, result):
        """Compare the received transaction with the expected output."""
        if not self.scoreboard_queue:
            return False

        result = packed_to_long_torch(
            result,
            int(self.dut.OUTPUT_WIDTH.value),
            int(self.dut.NUM_OUTPUTS.value),
        )

        input_vals, expected_result = self.scoreboard_queue.popleft()
        result_ok = torch.equal(result, expected_result)
        if not result_ok.all():
            self.scoreboard.errors += 1 
            self.dut._log.error(f"FC Mismatch!\nInput: {input_vals}\nExpected: {expected_result}\nGot: {result}")
        else:
            self.dut._log.info(f"FC Match!\nInput: {input_vals}\nOutput: {result}")

        return result_ok

@cocotb.test()
async def test_a(dut):
    """Test FC layer"""
    with torch.no_grad():
        fc_layer = nn.Linear(
            in_features=CHANNEL_IN_COUNT,
            out_features=CHANNEL_OUT_COUNT,
            bias=True,
        )
        int_weights = torch.randint( -128, 127, fc_layer.weight.size(), dtype=torch.int16 )
        int_bias = torch.randint( -128, 127, fc_layer.bias.size(), dtype=torch.int16 )
        fc_layer.weight.data = int_weights.to(torch.float32)
        fc_layer.bias.data = int_bias.to(torch.float32)

        dut._log.info(f"Weight: {int_weights}")
        dut._log.info(f"Bias: {int_bias}")
        dut.weights.value = int_weights.flatten().tolist()
        dut.bias.value = int_bias.tolist()


    tb = FCTestbench(
        dut,
        layer=fc_layer
    )

    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_ITER = 20
    for _ in range(NUM_ITER):
        x = torch.randint(
            torch.iinfo(torch.int8).min,
            torch.iinfo(torch.int8).max,
            (CHANNEL_IN_COUNT,),
            dtype=torch.int8,
        )
        tb.ind.append(
            {
                "type": "write_single",
                "contents": {"data": int8_torch_to_packed(x), "last": 0},
            }
        )
        tb.ind.append({"type": "pause", "duration": random.randint(1, 6)})
    
    tb.outd.append({"type": "read", "duration": NUM_ITER*10})

    await ClockCycles(dut.aclk, NUM_ITER * 20)
    assert tb.inm.transactions == tb.outm.transactions, (
        "Transaction Count doesn't match! :-/"
    )
    dut._log.info(f"in transactions: {tb.inm.transactions}, out transactions: {tb.outm.transactions}")
    assert tb.scoreboard.errors == 0, (
        f"Test Failed with {tb.scoreboard.errors} errors!"
    ) 