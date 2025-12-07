"""Utilities for working with quantized checkpoints and unit-scale int8 states."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import torch


def to_cpu_float(tensor: torch.Tensor | np.ndarray) -> torch.Tensor:
    """Best-effort convert a possibly quantized tensor to a plain CPU float tensor."""

    base = tensor
    if hasattr(base, "dequantize"):
        try:
            base = base.dequantize()
        except Exception:
            pass
    elif hasattr(base, "to_dense"):
        try:
            base = base.to_dense()
        except Exception:
            pass
    return torch.as_tensor(base, device="cpu", dtype=torch.float32).detach()


def requantize_symmetric(tensor: torch.Tensor | np.ndarray) -> Tuple[np.ndarray, float]:
    """Symmetric int8 requantization.

    Returns (int8_numpy, scale). If tensor is all zeros, scale falls back to 1.0.
    """

    base = to_cpu_float(tensor)
    max_abs = float(base.abs().max())
    scale = max_abs / 127.0 if max_abs > 0 else 1.0
    int8_vals = torch.round(base / scale).clamp(-128, 127).to(torch.int8)
    return int8_vals.cpu().numpy(), scale


def unit_scale_state_dict(q_state: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
    """Convert a quantized state_dict to unit-scale int8 payloads (biases untouched)."""

    out: Dict[str, torch.Tensor] = {}
    for k, v in q_state.items():
        if "bias" in k:
            out[k] = to_cpu_float(v) if isinstance(v, torch.Tensor) else v
            continue
        int8_vals, _ = requantize_symmetric(v)
        out[k] = torch.from_numpy(int8_vals.astype(np.float32))
    return out


def load_model_state(ckpt_path: Path) -> Dict[str, torch.Tensor]:
    """Load a checkpoint and return its model_state (or raw state_dict)."""

    state = torch.load(ckpt_path, map_location="cpu")
    return state.get("model_state", state)
