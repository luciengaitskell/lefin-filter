#!/usr/bin/env python3
"""Simplified training entrypoint for traffic classification CNN.

Usage:
    uv run -m model.model train

The dataset definition lives in `data/dataset.py` and is imported here so the
chosen preprocessing config is versioned alongside the model code.
"""

from __future__ import annotations

import contextlib
import math
import os
from pathlib import Path
from typing import Dict, Literal, Tuple, cast

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.amp.autocast_mode import autocast
from torch.amp.grad_scaler import GradScaler
from torch.utils.data import DataLoader, TensorDataset
from tqdm.auto import tqdm
import typer
from pydantic import BaseModel, ConfigDict, Field

from model.dataset import (
    DEFAULT_CONFIG,
    DatasetConfig,
    ensure_preprocessed,
    load_split_arrays,
)
from model.util.quant import load_model_state, unit_scale_state_dict

app = typer.Typer(help="Train/evaluate the traffic CNN")


# -----------------------------------------------------------------------------
# Model
# -----------------------------------------------------------------------------


class EncryptTrafficCNN1D(nn.Module):
    def __init__(
        self,
        num_classes: int,
        arch: Literal["original", "gap", "gmp", "gapgmp"] = "gapgmp",
        input_len: int = 784,
        small_model: bool = True,
    ):
        super().__init__()
        self.small_model = small_model

        if self.small_model:
            self.conv1 = nn.Conv1d(1, 4, kernel_size=25)
            channels_out = self.conv1.out_channels
            conv1_len = max(1, input_len - self.conv1.kernel_size[0] + 1)
            flat_dim = conv1_len * channels_out  # no pooling in the small variant
        else:
            # Original two-conv variant (no padding) with max pools
            self.conv1 = nn.Conv1d(1, 32, kernel_size=25)
            self.pool1 = nn.MaxPool1d(kernel_size=3, stride=3, ceil_mode=True)
            self.conv2 = nn.Conv1d(32, 64, kernel_size=25)
            self.pool2 = nn.MaxPool1d(kernel_size=3, stride=3, ceil_mode=True)
            channels_out = self.conv2.out_channels
            conv1_len = max(1, input_len - self.conv1.kernel_size[0] + 1)
            pool1_k = (
                int(self.pool1.kernel_size)
                if isinstance(self.pool1.kernel_size, int)
                else int(self.pool1.kernel_size[0])
            )
            pool1_len = math.ceil(conv1_len / pool1_k)
            conv2_len = max(1, pool1_len - self.conv2.kernel_size[0] + 1)
            pool2_k = (
                int(self.pool2.kernel_size)
                if isinstance(self.pool2.kernel_size, int)
                else int(self.pool2.kernel_size[0])
            )
            pool2_len = math.ceil(conv2_len / pool2_k)
            input_len_reduced = pool2_len
            flat_dim = input_len_reduced * channels_out
        self.arch = arch.lower()

        if self.arch == "original":
            self.head = nn.Sequential(
                nn.Flatten(),
                nn.Linear(flat_dim, 1024),
                nn.ReLU(),
                nn.Dropout(p=0.5),
            )
            self.fc = nn.Linear(1024, num_classes)
        elif self.arch == "gap":
            self.pool = nn.AdaptiveAvgPool1d(1)
            self.fc = nn.Linear(channels_out, num_classes)
        elif self.arch == "gmp":
            self.pool = nn.AdaptiveMaxPool1d(1)
            self.fc = nn.Linear(channels_out, num_classes)
        elif self.arch == "gapgmp":
            self.head_gap = nn.AdaptiveAvgPool1d(1)
            self.head_gmp = nn.AdaptiveMaxPool1d(1)
            self.fc = nn.Linear(channels_out * 2, num_classes)
        else:
            raise ValueError(f"Unknown arch: {arch}")

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = F.relu(self.conv1(x))
        if not self.small_model:
            x = self.pool1(x)
            x = F.relu(self.conv2(x))
            x = self.pool2(x)

        if self.arch == "gapgmp":
            gap = self.head_gap(x).flatten(1)
            gmp = self.head_gmp(x).flatten(1)
            x = torch.cat([gap, gmp], dim=1)
            return self.fc(x)
        if self.arch == "gap" or self.arch == "gmp":
            x = self.pool(x).flatten(1)
            return self.fc(x)
        # original
        x = self.head(x)
        return self.fc(x)


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------

DATASET: DatasetConfig = DEFAULT_CONFIG.model_copy()


class TrainConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    dataset: DatasetConfig = Field(default_factory=lambda: DATASET)
    batch_size: int = 256
    epochs: int = 5
    eval_every_steps: int | None = None  # None means eval each epoch
    lr: float = 1e-3
    weight_decay: float = 0.0
    arch: Literal["original", "gap", "gmp", "gapgmp"] = "gapgmp"
    small_model: bool = True
    eval_unit_scale: bool = False
    amp: bool = False
    balance_classes: bool = True
    num_workers: int | None = None
    model_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent / "checkpoints"
    )
    group_by_dataset: bool = True
    export_int8: bool = False
    seed: int = 42
    overwrite: bool = False


# -----------------------------------------------------------------------------
# Data helpers
# -----------------------------------------------------------------------------


def _make_loader(
    x: np.ndarray,
    y: np.ndarray,
    batch_size: int,
    device: torch.device,
    shuffle: bool,
    num_workers: int | None,
) -> DataLoader:
    y_idx = y.astype(np.int64)
    x_t = torch.from_numpy(x).float().reshape(-1, 1, x.shape[1])
    y_t = torch.from_numpy(y_idx).long()
    pin = device.type == "cuda"
    worker_count = (
        num_workers
        if num_workers is not None
        else max(0, min(4, (os.cpu_count() or 2) - 1))
    )
    dl_kwargs = {
        "batch_size": batch_size,
        "shuffle": shuffle,
        "num_workers": worker_count,
        "pin_memory": pin,
    }
    if worker_count > 0:
        dl_kwargs["persistent_workers"] = True
        dl_kwargs["prefetch_factor"] = 2
    return DataLoader(TensorDataset(x_t, y_t), **dl_kwargs)


def evaluate(
    model: nn.Module, loader: DataLoader, device: torch.device
) -> Tuple[float, float]:
    model.eval()
    total = 0
    correct = 0
    loss_sum = 0.0
    criterion = nn.CrossEntropyLoss()
    with torch.no_grad():
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            logits = model(xb)
            loss = criterion(logits, yb)
            preds = logits.argmax(dim=1)
            loss_sum += loss.item() * xb.size(0)
            correct += (preds == yb).sum().item()
            total += xb.size(0)
    acc = correct / max(1, total)
    avg_loss = loss_sum / max(1, total)
    return acc, avg_loss


# -----------------------------------------------------------------------------
# Training
# -----------------------------------------------------------------------------


def train_model(cfg: TrainConfig) -> None:
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    ensure_preprocessed(cfg.dataset)
    (x_train, y_train) = load_split_arrays(cfg.dataset, "train")
    (x_test, y_test) = load_split_arrays(cfg.dataset, "test")

    max_label = 0
    if y_train.size:
        max_label = max(max_label, int(y_train.max()))
    if y_test.size:
        max_label = max(max_label, int(y_test.max()))
    num_classes = max_label + 1
    input_len = x_train.shape[1]

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
        else "cpu"
    )

    model = EncryptTrafficCNN1D(
        num_classes=num_classes,
        arch=cfg.arch,
        input_len=input_len,
        small_model=cfg.small_model,
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay
    )

    if cfg.balance_classes:
        counts = np.bincount(y_train, minlength=num_classes)
        weights = 1.0 / np.maximum(counts, 1)
        weights = weights / weights.mean()
        class_weights = torch.tensor(weights, device=device, dtype=torch.float32)
    else:
        class_weights = None
    criterion = nn.CrossEntropyLoss(weight=class_weights)

    scaler = GradScaler("cuda", enabled=cfg.amp and device.type == "cuda")

    train_loader = _make_loader(
        x_train,
        y_train,
        cfg.batch_size,
        device,
        shuffle=True,
        num_workers=cfg.num_workers,
    )
    test_loader = _make_loader(
        x_test,
        y_test,
        cfg.batch_size,
        device,
        shuffle=False,
        num_workers=cfg.num_workers,
    )

    model_root = (
        cfg.model_dir / cfg.dataset.resolved_name
        if cfg.group_by_dataset
        else cfg.model_dir
    )
    tqdm.write(
        "Starting training: "
        f"dataset={cfg.dataset.resolved_name} layer={cfg.dataset.layer} "
        f"input_len={input_len} classes={num_classes} arch={cfg.arch} "
        f"small_model={cfg.small_model} "
        f"model_dir={model_root}"
    )
    tqdm.write(str(model))

    cfg.model_dir.mkdir(parents=True, exist_ok=True)
    model_root.mkdir(parents=True, exist_ok=True)
    best_model = model_root / "best.pt"
    ckpt_path = model_root / "checkpoint.pt"

    global_step = 0
    best_acc = 0.0
    start_epoch = 0

    if ckpt_path.exists() and not cfg.overwrite:
        ckpt = torch.load(ckpt_path, map_location=device)
        model.load_state_dict(ckpt.get("model_state", {}))
        optimizer.load_state_dict(ckpt.get("optimizer_state", {}))
        scaler.load_state_dict(ckpt.get("scaler_state", {}))
        global_step = int(ckpt.get("global_step", 0))
        best_acc = float(ckpt.get("best_acc", 0.0))
        start_epoch = int(ckpt.get("epoch", 0))
        tqdm.write(
            f"Resumed from checkpoint: epoch={start_epoch}, global_step={global_step}, best_acc={best_acc:.4f}"
        )
    elif ckpt_path.exists() and cfg.overwrite:
        tqdm.write("Overwrite enabled: starting fresh despite existing checkpoint")

    def save_checkpoint(epoch: int, best_acc_val: float):
        torch.save(
            {
                "model_state": model.state_dict(),
                "optimizer_state": optimizer.state_dict(),
                "scaler_state": scaler.state_dict(),
                "global_step": global_step,
                "best_acc": best_acc_val,
                "epoch": epoch,
                "arch": cfg.arch,
                "small_model": cfg.small_model,
            },
            ckpt_path,
        )

    for epoch in range(start_epoch, cfg.epochs):
        model.train()
        pbar = tqdm(
            train_loader,
            desc=f"epoch {epoch + 1}/{cfg.epochs}",
            leave=False,
            dynamic_ncols=True,
        )
        autocast_cm = (
            autocast("cuda", enabled=cfg.amp and device.type == "cuda")
            if device.type == "cuda"
            else contextlib.nullcontext()
        )
        running_loss = 0.0
        running_correct = 0
        running_total = 0

        for xb, yb in pbar:
            xb, yb = xb.to(device), yb.to(device)
            optimizer.zero_grad()
            with autocast_cm:
                logits = model(xb)
                loss = criterion(logits, yb)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()

            preds = logits.argmax(dim=1)
            running_correct += (preds == yb).sum().item()
            running_total += xb.size(0)
            running_loss += loss.item() * xb.size(0)

            global_step += 1
            avg_loss = running_loss / max(1, running_total)
            train_acc = running_correct / max(1, running_total)
            pbar.set_postfix(loss=avg_loss, acc=train_acc)

            if cfg.eval_every_steps and global_step % cfg.eval_every_steps == 0:
                val_acc, val_loss = evaluate(model, test_loader, device)
                best_acc, _ = _maybe_save(model, best_model, val_acc, best_acc)
                pbar.set_postfix(
                    loss=avg_loss, acc=train_acc, val_loss=val_loss, val_acc=val_acc
                )

        # End-of-epoch eval when eval_every_steps is None
        if cfg.eval_every_steps is None:
            val_acc, val_loss = evaluate(model, test_loader, device)
            best_acc, _ = _maybe_save(model, best_model, val_acc, best_acc)
            tqdm.write(
                f"epoch {epoch + 1}: train_loss={avg_loss:.4f} train_acc={train_acc:.4f} "
                f"val_loss={val_loss:.4f} val_acc={val_acc:.4f}"
            )
        save_checkpoint(epoch + 1, best_acc)

    final_acc, val_loss = evaluate(model, test_loader, device)
    best_acc, saved = _maybe_save(model, best_model, final_acc, best_acc)
    tqdm.write(
        f"final: val_acc={final_acc:.4f} val_loss={val_loss:.4f} best_acc={best_acc:.4f} saved={saved}"
    )
    tqdm.write(f"Checkpoints: latest={ckpt_path}, best={best_model}")

    if cfg.export_int8:
        if best_model.exists():
            state = torch.load(best_model, map_location="cpu").get("model_state", {})
            model.load_state_dict(state)
        int8_path = best_model.with_name("best_int8.pt")
        quant_model = _export_int8(
            model,
            cfg.arch,
            input_len,
            num_classes,
            int8_path,
            cfg.small_model,
        )
        if quant_model is not None:
            quant_model.to(device)
            q_acc, q_loss = evaluate(quant_model, test_loader, device)
            tqdm.write(
                f"int8 eval: val_acc={q_acc:.4f} val_loss={q_loss:.4f} saved_path={int8_path}"
            )
            if cfg.eval_unit_scale:
                unit_model = EncryptTrafficCNN1D(
                    num_classes=num_classes,
                    arch=cfg.arch,
                    input_len=input_len,
                    small_model=cfg.small_model,
                ).to(device)
                unit_state = unit_scale_state_dict(quant_model.state_dict())
                unit_model.load_state_dict(unit_state, strict=False)
                u_acc, u_loss = evaluate(unit_model, test_loader, device)
                tqdm.write(
                    f"unit-scale eval: val_acc={u_acc:.4f} val_loss={u_loss:.4f}"
                )


def _maybe_save(
    model: nn.Module, path: Path, acc: float, best_acc: float
) -> tuple[float, bool]:
    saved = False
    if acc >= best_acc:
        torch.save({"model_state": model.state_dict()}, path)
        best_acc = acc
        saved = True
    return best_acc, saved


def load_unit_scale_model(
    ckpt_path: Path,
    arch: Literal["original", "gap", "gmp", "gapgmp"],
    input_len: int,
    num_classes: int,
    small_model: bool,
    device: torch.device | str = "cpu",
) -> nn.Module:
    """Load a unit-scale int8 model from a TorchAO checkpoint."""

    state = load_model_state(ckpt_path)
    unit_state = unit_scale_state_dict(state)
    model = EncryptTrafficCNN1D(
        num_classes=num_classes,
        arch=arch,
        input_len=input_len,
        small_model=small_model,
    ).to(device)
    model.load_state_dict(unit_state, strict=False)
    model.eval()
    return model


def _export_int8(
    model: nn.Module,
    arch: str,
    input_len: int,
    num_classes: int,
    path: Path,
    small_model: bool,
):
    try:
        from torchao.quantization import Int8WeightOnlyConfig, quantize_
    except Exception as exc:  # pragma: no cover - optional dependency
        tqdm.write(f"torchao not available, skipping int8 export: {exc}")
        return None

    arch_literal = cast(Literal["original", "gap", "gmp", "gapgmp"], arch)
    export_model = EncryptTrafficCNN1D(
        num_classes=num_classes,
        arch=arch_literal,
        input_len=input_len,
        small_model=small_model,
    )
    export_model.load_state_dict(model.state_dict())
    export_model.cpu()
    quantize_(export_model, Int8WeightOnlyConfig())
    torch.save({"model_state": export_model.state_dict()}, path)
    tqdm.write(f"Saved int8 weight-only model to {path}")
    return export_model


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


@app.command()
def train(
    epochs: int = typer.Option(5, help="Number of epochs"),
    batch_size: int = typer.Option(256, help="Batch size"),
    lr: float = typer.Option(1e-3, help="Learning rate"),
    eval_every_steps: int = typer.Option(
        0, help="Evaluate every N steps; 0 to eval each epoch"
    ),
    dataset_name: str = typer.Option(
        DEFAULT_CONFIG.name, help="Dataset base name (folder inside output_dir)"
    ),
    dataset_layer: Literal["l2", "l3", "l7"] = typer.Option(
        DEFAULT_CONFIG.layer, help="Payload layer L to train on"
    ),
    include_layer_suffix: bool = typer.Option(
        True, help="Append _<layer> to dataset folder when resolving paths"
    ),
    dataset_output_dir: Path | None = typer.Option(
        None, help="Override dataset output root"
    ),
    arch: Literal["original", "gap", "gmp", "gapgmp"] = typer.Option(
        "gmp", help="Model head"
    ),
    small_model: bool = typer.Option(
        True,
        help="Use smaller 1-conv variant; disable for original 2-conv + maxpool",
    ),
    amp: bool = typer.Option(False, help="Use CUDA AMP if available"),
    balance_classes: bool = typer.Option(
        True, help="Weight classes to address imbalance"
    ),
    weight_decay: float = typer.Option(0.0, help="Weight decay"),
    model_dir: Path | None = typer.Option(None, help="Where to store checkpoints"),
    group_by_dataset: bool = typer.Option(
        True, help="Place checkpoints under a dataset-specific subfolder"
    ),
    quantize_int8: bool = typer.Option(
        False, help="Also export an int8 weight-only model using torchao (best_int8.pt)"
    ),
    eval_unit_scale: bool = typer.Option(
        False,
        help="After int8 export, eval with quantized int weights using unit scale (sanity check)",
    ),
    seed: int = typer.Option(42, help="Random seed"),
    overwrite: bool = typer.Option(
        False, help="Ignore existing checkpoints and start fresh"
    ),
):
    eval_steps = eval_every_steps if eval_every_steps > 0 else None
    dataset_cfg = DATASET.model_copy(
        update={
            "name": dataset_name,
            "layer": dataset_layer,
            "include_layer_suffix": include_layer_suffix,
            "output_dir": dataset_output_dir or DATASET.output_dir,
        }
    )
    cfg = TrainConfig(
        dataset=dataset_cfg,
        epochs=epochs,
        batch_size=batch_size,
        lr=lr,
        eval_every_steps=eval_steps,
        arch=arch,
        small_model=small_model,
        amp=amp,
        balance_classes=balance_classes,
        weight_decay=weight_decay,
        model_dir=model_dir or TrainConfig().model_dir,
        group_by_dataset=group_by_dataset,
        export_int8=quantize_int8,
        eval_unit_scale=eval_unit_scale,
        seed=seed,
        overwrite=overwrite,
    )
    train_model(cfg)


if __name__ == "__main__":
    app()
