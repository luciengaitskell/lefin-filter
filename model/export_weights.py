#!/usr/bin/env python3
"""Export quantized weights to a SystemVerilog header (.svh).

This script loads the TorchAO int8 weight-only checkpoint (``best_int8.pt``)
and emits a .svh with a ``localparam`` array per tensor (conv1/conv2/fc weights
and biases). We quantize to symmetric int8 with a per-tensor scale so hardware
can reconstruct floats as needed.

Example:
    uv run -m model.export_weights --ckpt model/checkpoints/ustc_packet_l2/best_int8.pt \
        --out hdl/model/includes/model_params.svh
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Dict, List, Tuple

import numpy as np
import torch
import typer
from torch.serialization import add_safe_globals
from model.util.quant import load_model_state, requantize_symmetric

# TorchAO checkpoints store AffineQuantizedTensor in state_dict
try:  # pragma: no cover - optional dependency
    from torchao.dtypes.affine_quantized_tensor import AffineQuantizedTensor

    add_safe_globals([AffineQuantizedTensor])
except Exception:
    AffineQuantizedTensor = None  # type: ignore

app = typer.Typer(
    help="Export int8 quantized weights and model params as SystemVerilog localparams"
)


def _quantize_int8(t: torch.Tensor) -> Tuple[np.ndarray, float]:
    """Symmetric int8 quantization with per-tensor scale."""

    q, scale = requantize_symmetric(t)
    return q.astype(np.int8, copy=False), float(scale)


def _format_nested(values: np.ndarray) -> str:
    """Format an ndarray into SystemVerilog nested brace initialization.

    Uses SV array literal syntax with a leading quote on each brace level, e.g.
    `'{1, -2}` for 1-D and `'{ '{1,2}, '{3,4} }` for 2-D.
    """

    if values.ndim == 1:
        return "'{" + ", ".join(str(int(v)) for v in values) + "}"
    return "'{" + ", ".join(_format_nested(v) for v in values) + "}"


def _bit_width(values: np.ndarray) -> int:
    """Return the bit width of a numpy array dtype (e.g., int8 -> 8)."""

    return int(values.dtype.itemsize * 8)


def _layer_name(prefix: str, kind: str) -> str:
    """Return canonical layer base name (e.g., conv1 -> CONV1D_1, fc1 -> FC_1)."""

    if kind == "conv1d":
        m = re.match(r"conv(\d+)", prefix)
        if m:
            return f"CONV1D_{m.group(1)}"
        return prefix.upper()
    if kind == "linear":
        m = re.match(r"fc(\d+)", prefix)
        if m:
            return f"FC_{m.group(1)}"
        return prefix.upper()
    return prefix.upper()


def _sort_key(name: str) -> Tuple[int, str]:
    """Natural sort: by numeric suffix when present, otherwise lexicographic."""

    m = re.search(r"(\d+)$", name)
    return (int(m.group(1)) if m else 0, name)


def _format_localparam(
    name: str,
    values: np.ndarray,
    scale: float,
    shape: Tuple[int, ...],
    dim_exprs: Tuple[str, ...] | None = None,
    scale_name: str | None = None,
    comment_name: str | None = None,
    bit_width: int | None = None,
    bit_width_name: str | None = None,
    include_scale: bool = True,
) -> str:
    init = _format_nested(values)
    dims = "".join(dim_exprs) if dim_exprs else "".join(f"[0:{d - 1}]" for d in shape)
    scale_ident = scale_name or f"{name}_SCALE"
    bit_width_ident = bit_width_name or (
        f"{name}_BIT_WIDTH" if bit_width is not None else None
    )
    comment = comment_name or name
    bit_width_line = (
        f"localparam int {bit_width_ident} = {bit_width};" if bit_width_ident else ""
    )
    scale_line = (
        f"localparam real {scale_ident} = {scale:.8f};" if include_scale else ""
    )

    lines = [f"  // {comment} shape={shape} scale={scale}"]
    if scale_line:
        lines.append(f"  {scale_line}")
    if bit_width_line:
        lines.append(f"  {bit_width_line}")
    lines.append(f"  localparam signed [WEIGHT_BIT_WIDTH-1:0] {name} {dims} = {init};")
    return "\n".join(lines) + "\n\n"


def export_svh(
    ckpt_path: Path,
    out_path: Path,
    emit_scales: bool = False,
    package_name: str = "model_params",
) -> None:
    model_state: Dict[str, torch.Tensor] = load_model_state(ckpt_path)
    # Discover layers from weight tensors so emission is data-driven
    layers = {}
    for key, tensor in model_state.items():
        if not key.endswith("weight"):
            continue
        prefix = key.split(".")[0]
        if tensor.ndim == 3:
            kind = "conv1d"
        elif tensor.ndim == 2:
            kind = "linear"
        else:
            typer.echo(f"Skipping unsupported tensor rank for {key}: {tensor.shape}")
            continue
        base = _layer_name(prefix, kind)
        layers[prefix] = {
            "base": base,
            "kind": kind,
            "weight_key": key,
            "bias_key": f"{prefix}.bias" if f"{prefix}.bias" in model_state else None,
            "weight_tensor": tensor,
        }

    # Emit header
    sections = [
        "// Auto-generated from int8 checkpoint",
        f"// source: {ckpt_path}",
        "// verilog_format: off",
        "`ifndef MODEL_WEIGHTS_SVH",
        "`define MODEL_WEIGHTS_SVH",
        "",
        f"package {package_name};",
        "",
    ]

    # Architecture params inferred from shapes
    for _, layer in sorted(layers.items(), key=lambda item: _sort_key(item[1]["base"])):
        base = layer["base"]
        tensor = layer["weight_tensor"]
        if layer["kind"] == "conv1d":
            co, ci, kw = tensor.shape
            sections.append(f"localparam int {base}_CHANNEL_OUT_COUNT = {co};")
            sections.append(f"localparam int {base}_CHANNEL_IN_COUNT  = {ci};")
            sections.append(f"localparam int {base}_KERNEL_WIDTH     = {kw};")
            sections.append(f"localparam int {base}_STRIDE           = 1;")
            sections.append("")
        elif layer["kind"] == "linear":
            out_dim, in_dim = tensor.shape
            sections.append(f"localparam int {base}_IN_DIM  = {in_dim};")
            sections.append(f"localparam int {base}_OUT_DIM = {out_dim};")
            sections.append("")

    # Prepare tensor specs for emission (weights and biases)
    tensor_specs: List[Dict[str, Any]] = []
    for _, layer in sorted(layers.items(), key=lambda item: _sort_key(item[1]["base"])):
        base = layer["base"]
        weight = layer["weight_tensor"]
        if layer["kind"] == "conv1d":
            tensor_specs.append(
                {
                    "key": layer["weight_key"],
                    "name": f"{base}_WEIGHT",
                    "shape": (weight.shape[0], weight.shape[1], weight.shape[2]),
                    "dim_exprs": (
                        f"[0:{base}_CHANNEL_OUT_COUNT-1]",
                        f"[0:{base}_CHANNEL_IN_COUNT-1]",
                        f"[0:{base}_KERNEL_WIDTH-1]",
                    ),
                }
            )
            if layer["bias_key"]:
                tensor_specs.append(
                    {
                        "key": layer["bias_key"],
                        "name": f"{base}_BIAS",
                        "shape": (weight.shape[0],),
                        "dim_exprs": (f"[0:{base}_CHANNEL_OUT_COUNT-1]",),
                    }
                )
        elif layer["kind"] == "linear":
            tensor_specs.append(
                {
                    "key": layer["weight_key"],
                    "name": f"{base}_WEIGHT",
                    "shape": (weight.shape[0], weight.shape[1]),
                    "dim_exprs": (f"[0:{base}_OUT_DIM-1]", f"[0:{base}_IN_DIM-1]"),
                }
            )
            if layer["bias_key"]:
                tensor_specs.append(
                    {
                        "key": layer["bias_key"],
                        "name": f"{base}_BIAS",
                        "shape": (weight.shape[0],),
                        "dim_exprs": (f"[0:{base}_OUT_DIM-1]",),
                    }
                )

    # Quantize tensors and emit localparams
    data_sections: List[str] = []
    global_bit_width: int | None = None
    for spec in tensor_specs:
        key = str(spec["key"])
        if key not in model_state:
            typer.echo(f"Warning: missing {key} in checkpoint; skipping")
            continue
        tensor = model_state[key]
        q, scale = _quantize_int8(tensor)
        bit_width = _bit_width(q)
        if global_bit_width is None:
            global_bit_width = bit_width
        shape: Tuple[int, ...] = tuple(int(x) for x in spec["shape"])  # type: ignore[arg-type]
        dim_exprs: Tuple[str, ...] = tuple(spec["dim_exprs"])  # type: ignore[arg-type]
        name = str(spec["name"])
        data_sections.append(
            _format_localparam(
                name,
                q.reshape(shape),
                scale,
                shape,
                dim_exprs=dim_exprs,
                scale_name=f"{name}_SCALE",
                comment_name=name,
                bit_width=bit_width,
                bit_width_name=f"{name}_BIT_WIDTH",
                include_scale=emit_scales,
            )
        )

    if global_bit_width is None:
        global_bit_width = 8
    sections.append(f"  localparam int WEIGHT_BIT_WIDTH = {global_bit_width};\n")
    sections.extend(data_sections)
    sections.append(f"endpackage : {package_name}\n")
    sections.append("`endif // MODEL_WEIGHTS_SVH")
    sections.append("// verilog_format: on\n")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(sections))
    typer.echo(f"Wrote {out_path}")


@app.command()
def main(
    ckpt: Path = typer.Option(
        ..., help="Path to torchao int8 checkpoint (best_int8.pt)"
    ),
    out: Path = typer.Option(..., help="Output .svh path"),
    emit_scales: bool = typer.Option(
        False,
        help="Emit per-tensor scale localparams alongside quantized weights/biases",
    ),
    package_name: str = typer.Option(
        "model_params",
        help="SystemVerilog package name to wrap the emitted params",
    ),
):
    export_svh(ckpt, out, emit_scales=emit_scales, package_name=package_name)


if __name__ == "__main__":
    app()
