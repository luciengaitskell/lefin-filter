import os
import sys
from pathlib import Path

from cocotb.triggers import ClockCycles
from cocotb_tools.runner import get_runner


async def reset(clk, rst, cycles_held=3, polarity=1):
    rst.value = polarity
    await ClockCycles(clk, cycles_held)
    rst.value = not polarity


def build_and_run_sim(
    test_file,
    *,
    hdl_toplevel: str,
    additional_sources: list[str] | None = None,
    includes: list[str] | None = None,
    parameters: dict | None = None,
):
    if parameters is None:
        parameters = {}

    sim = os.getenv("SIM", "verilator")
    runner = get_runner(sim)

    # https://docs.cocotb.org/en/v1.9.2/simulator_support.html#verilator
    build_test_args = [
        "-Wall",
        # Enable tracing and fst generation
        "--trace",
        "--trace-fst",
        "--trace-structs",
        # Enable non-blocking assignments
        "--timing",
    ]
    proj_path = Path(__file__).resolve().parent.parent.parent
    source_root = Path(proj_path / "hdl")
    source_paths = list(source_root.glob("**/*.sv"))
    if additional_sources:
        source_paths += [proj_path / "hdl" / source for source in additional_sources]
    includes_paths = [source_root / "model" / "includes"]
    includes_paths += [proj_path / "hdl" / inc for inc in includes] if includes else []

    sys.path.append(str(Path(test_file).resolve().parent))
    print("added to sys.path:", str(Path(test_file).resolve().parent))

    test_module = os.path.basename(test_file).replace(".py", "")

    runner.build(
        sources=source_paths,
        includes=includes_paths,
        hdl_toplevel=hdl_toplevel,
        always=True,
        build_dir=Path("sim_build") / hdl_toplevel,
        build_args=build_test_args,
        parameters=parameters,
        timescale=("1ns", "1ps"),
        waves=True,
    )
    run_test_args = []
    runner.test(
        hdl_toplevel=hdl_toplevel,
        test_module=test_module,
        test_args=run_test_args,
        waves=True,
    )
