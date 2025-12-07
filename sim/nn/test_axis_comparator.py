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
    packed_to_long_torch,
)

INPUT_ELT_WIDTH = 16

@cocotb.test()
async def axis_comparator_test(dut):
    """Test AXIS Comparator module"""

    # Create a clock
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())

    # Reset the DUT
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_TESTS = 10
    for i in range(NUM_TESTS):
        max_value =  2**(INPUT_ELT_WIDTH - 1) - 1  # signed
        min_value = -2**(INPUT_ELT_WIDTH - 1)
        input_a = random.randint(min_value, max_value)
        input_b = random.randint(min_value, max_value)
        # put input a in top half and input b in bottom half of packed input of 2*INPUT_ELT_WIDTH bits
        packed_input = (input_a & ((1 << INPUT_ELT_WIDTH) - 1)) << INPUT_ELT_WIDTH | (input_b & ((1 << INPUT_ELT_WIDTH) - 1))
        dut.s00_axis_tdata.value = packed_input
        dut.s00_axis_tlast.value = 1
        dut.s00_axis_tvalid.value = 1

        await ClockCycles(dut.aclk, 2)
        if (input_a >= input_b):
            assert dut.output_valid.value == 1, f"Test {i}: Expected output_valid to be 1 but got 0 for inputs {input_a}, {input_b}"
            assert dut.top_half_greater.value == 1, f"Test {i}: Expected top_half_greater to be 1 but got 0 for inputs {input_a}, {input_b}"
        else:
            assert dut.output_valid.value == 1, f"Test {i}: Expected output_valid to be 1 but got 0 for inputs {input_a}, {input_b}"
            assert dut.top_half_greater.value == 0, f"Test {i}: Expected top_half_greater to be 0 but got 1 for inputs {input_a}, {input_b}"

@cocotb.test()
async def axis_comparator_test_with_missing_tlast(dut):
    """Test AXIS Comparator module with missing tlast signal"""

    # Create a clock
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())

    # Reset the DUT
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_TESTS = 10
    for i in range(NUM_TESTS):
        max_value =  2**(INPUT_ELT_WIDTH - 1) - 1  # signed
        min_value = -2**(INPUT_ELT_WIDTH - 1)
        input_a = random.randint(min_value, max_value)
        input_b = random.randint(min_value, max_value)
        # put input a in top half and input b in bottom half of packed input of 2*INPUT_ELT_WIDTH bits
        packed_input = (input_a & ((1 << INPUT_ELT_WIDTH) - 1)) << INPUT_ELT_WIDTH | (input_b & ((1 << INPUT_ELT_WIDTH) - 1))
        dut.s00_axis_tdata.value = packed_input
        dut.s00_axis_tlast.value = 0  # Missing tlast
        dut.s00_axis_tvalid.value = 1

        await ClockCycles(dut.aclk, 2)
        # Since tlast is missing, output_valid should not be asserted
        assert dut.output_valid.value == 0, f"Test {i}: Expected output_valid to be 0 due to missing tlast for inputs {input_a}, {input_b}"

@cocotb.test()
async def axis_comparator_test_mixed_tlast(dut):
    """Test AXIS Comparator module with mixed tlast signals"""

    # Create a clock
    cocotb.start_soon(Clock(dut.aclk, 10, units="ns").start())

    # Reset the DUT
    await reset(dut.aclk, dut.aresetn, 2, 0)

    NUM_TESTS = 10
    for i in range(NUM_TESTS):
        max_value =  2**(INPUT_ELT_WIDTH - 1) - 1  # signed
        min_value = -2**(INPUT_ELT_WIDTH - 1)
        input_a = random.randint(min_value, max_value)
        input_b = random.randint(min_value, max_value)
        # put input a in top half and input b in bottom half of packed input of 2*INPUT_ELT_WIDTH bits
        packed_input = (input_a & ((1 << INPUT_ELT_WIDTH) - 1)) << INPUT_ELT_WIDTH | (input_b & ((1 << INPUT_ELT_WIDTH) - 1))
        dut.s00_axis_tdata.value = packed_input
        dut.s00_axis_tlast.value = random.choice([0, 1])  # Randomly choose tlast
        dut.s00_axis_tvalid.value = 1

        await ClockCycles(dut.aclk, 2)
        if dut.s00_axis_tlast.value == 1:
            if (input_a >= input_b):
                assert dut.output_valid.value == 1, f"Test {i}: Expected output_valid to be 1 but got 0 for inputs {input_a}, {input_b}"
                assert dut.top_half_greater.value == 1, f"Test {i}: Expected top_half_greater to be 1 but got 0 for inputs {input_a}, {input_b}"
            else:
                assert dut.output_valid.value == 1, f"Test {i}: Expected output_valid to be 1 but got 0 for inputs {input_a}, {input_b}"
                assert dut.top_half_greater.value == 0, f"Test {i}: Expected top_half_greater to be 0 but got 1 for inputs {input_a}, {input_b}"
        else:
            # Since tlast is not asserted, output_valid should not be asserted
            assert dut.output_valid.value == 0, f"Test {i}: Expected output_valid to be 0 due to missing tlast for inputs {input_a}, {input_b}"

if __name__ == "__main__":
    build_and_run_sim(
        __file__,
        hdl_toplevel="axis_comparator",
        parameters={
            "DATA_WIDTH": INPUT_ELT_WIDTH
        },
    )
