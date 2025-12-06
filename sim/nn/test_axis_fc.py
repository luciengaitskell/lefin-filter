import math
import cocotb
import random
from collections import deque
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
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

INPUT_BIT_WIDTH = 16
ELEMENTS_IN_COUNT = 16
OUTPUT_BIT_WIDTH = 36
ELEMENTS_OUT_COUNT = 2
WEIGHT_BIT_WIDTH = 16
BIAS_BIT_WIDTH = 16
assert OUTPUT_BIT_WIDTH >= INPUT_BIT_WIDTH + WEIGHT_BIT_WIDTH + math.ceil(math.log2(ELEMENTS_IN_COUNT)), f"OUTPUT_BIT_WIDTH is too small to hold the result of the FC layer, min is {INPUT_BIT_WIDTH + WEIGHT_BIT_WIDTH + math.ceil(math.log2(ELEMENTS_IN_COUNT))}"
C_S00_AXIS_TDATA_WIDTH = INPUT_BIT_WIDTH * ELEMENTS_IN_COUNT
C_M00_AXIS_TDATA_WIDTH = OUTPUT_BIT_WIDTH * ELEMENTS_OUT_COUNT


class FCTestbench(AXIS_Testbench):
    def __init__(self, dut, layer, **kwargs):
        super().__init__(dut, **kwargs)
        self.scoreboard_queue: deque[tuple[Tensor, Tensor]]

        self.expected_data_out = []  # contains list of expected outputs (Growing)
        self.input_buffer = None
        self.layer: nn.Linear = layer

    def in_callback(self, raw_input):
        print(f"Raw input received: {raw_input}")
        print(f"Input bit width: {int(self.dut.INPUT_BIT_WIDTH.value)}, Elements in count: {int(self.dut.ELEMENTS_IN_COUNT.value)}")
        input_values = packed_to_long_torch(raw_input, int(self.dut.INPUT_BIT_WIDTH.value), int(self.dut.ELEMENTS_IN_COUNT.value))
        print(f"Unpacked input values: {input_values}")
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
            int(self.dut.OUTPUT_BIT_WIDTH.value),
            int(self.dut.ELEMENTS_OUT_COUNT.value),
        )

        input_vals, expected_result = self.scoreboard_queue.popleft()
        result_ok = torch.equal(result, expected_result)
        if not result_ok:
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
            in_features=ELEMENTS_IN_COUNT,
            out_features=ELEMENTS_OUT_COUNT,
            bias=True,
        )
        max_of_weights = 2 ** (WEIGHT_BIT_WIDTH - 1) - 1
        max_of_bias = 2 ** (BIAS_BIT_WIDTH - 1) - 1
        min_of_weights = -max_of_weights - 1
        min_of_bias = -max_of_bias - 1
        int_weights = torch.randint( min_of_weights, max_of_weights + 1, fc_layer.weight.size(), dtype=torch.long )
        int_bias = torch.randint( min_of_bias, max_of_bias + 1, fc_layer.bias.size(), dtype=torch.long )
        fc_layer.weight.data = int_weights.to(torch.float32)
        fc_layer.bias.data = int_bias.to(torch.float32)

        dut._log.info(f"Weight: {int_weights}")
        dut._log.info(f"Bias: {int_bias}")
        dut.s_weights.value = int_weights.tolist()
        dut.s_biases.value = int_bias.tolist()


    tb = FCTestbench(
        dut,
        layer=fc_layer
    )

    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_ITER = 1000
    for _ in range(NUM_ITER):
        x = torch.randint(
            torch.iinfo(torch.int16).min,
            torch.iinfo(torch.int16).max,
            (ELEMENTS_IN_COUNT,),
            dtype=torch.long,
        )
        print(f"Input: {x}")
        tb.ind.append(
            {
                "type": "write_single",
                "contents": {"data": long_torch_to_packed(x, INPUT_BIT_WIDTH), "last": 0},
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

if __name__ == "__main__":
    build_and_run_sim(
        __file__,
        hdl_toplevel="axis_fc",
        includes=["nn"],
        parameters={
            "ELEMENTS_IN_COUNT": ELEMENTS_IN_COUNT,
            "INPUT_BIT_WIDTH": INPUT_BIT_WIDTH,
            "ELEMENTS_OUT_COUNT": ELEMENTS_OUT_COUNT,
            "OUTPUT_BIT_WIDTH": OUTPUT_BIT_WIDTH,
            "WEIGHT_BIT_WIDTH": WEIGHT_BIT_WIDTH,
            "BIAS_BIT_WIDTH": BIAS_BIT_WIDTH,
        },
    )
