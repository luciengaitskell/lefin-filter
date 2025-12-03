import cocotb
import random
from collections import deque
from cocotb.triggers import ReadOnly
from cocotb.triggers import Timer
import torch
from torch import nn, Tensor
from sim.util.torch import list_to_bitpacked
from sim.util.sim import build_and_run_sim


NUM_INPUTS = 4
INPUT_BIT_WIDTH = 16

@cocotb.test()
async def test_tree_adder(dut):
    """Test the Tree Adder module."""
    # DUT is purely combinational (no clock/reset required)
    NUM_TESTS = 20
    for _ in range(NUM_TESTS):
        input_tensor = torch.randint(
            low=-(1 << (INPUT_BIT_WIDTH - 1)),
            high=(1 << (INPUT_BIT_WIDTH - 1)) - 1,
            size=(NUM_INPUTS,),
            dtype=torch.int16,
        )
        # print how these are stored in list
        print (f"Input Tensor: {input_tensor.tolist()}")
        # ensure we're in the simulator write phase, then set dut inputs
        await Timer(1, 'ns')
        dut.inputs.value = input_tensor.tolist()
        # wait for combinational logic to settle (read-only phase)
        await ReadOnly()
        # calculate expected output
        expected_output = torch.sum(input_tensor).item()
        dut_output = dut.sum.value.to_signed()
        assert (dut_output == expected_output), (
            f"Tree Adder output mismatch: expected {expected_output}, got {dut_output}"
        )
        print(f"Test passed: expected {expected_output}, got {dut_output}")

if __name__ == "__main__":
    build_and_run_sim(
        __file__,
        hdl_toplevel="tree_adder",
        includes=["util"],
        sources=["util/tree_adder.sv"],
        parameters={
            "NUM_INPUTS": 4,
            "INPUT_BIT_WIDTH": 16,
        }
    )