#!/usr/bin/env python3
"""Dataset builder/loader for traffic classification.

Goals:
- Single place to preprocess PCAPs into a fixed train/test split.
- Simple API for training/inference scripts to load data.
- Minimal CLI: `uv run dataset.py preprocess`.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Sequence, Tuple

import numpy as np
import typer
from pydantic import BaseModel, ConfigDict, Field
from scapy.all import IP, TCP, UDP, rdpcap
from tqdm.auto import tqdm

app = typer.Typer(help="Preprocess PCAPs and load cached splits")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _default_pcap_root() -> Path:
    """Find the USTC-TFC2016 dataset relative to this file."""
    here = Path(__file__).resolve()
    candidate = here.parent / "datasets" / "USTC-TFC2016"
    if candidate.exists() and (candidate / "Benign").exists():
        return candidate
    raise FileNotFoundError("Could not find USTC-TFC2016 with Benign/ and Malware/")


def get_flow_key(packet, bidirectional: bool = True) -> Tuple:
    if not packet.haslayer(IP):
        raise ValueError("Packet does not have an IP layer")
    ip = packet[IP]
    src_ip, dst_ip, proto = ip.src, ip.dst, ip.proto
    src_port = (
        packet[TCP].sport
        if packet.haslayer(TCP)
        else packet[UDP].sport
        if packet.haslayer(UDP)
        else 0
    )
    dst_port = (
        packet[TCP].dport
        if packet.haslayer(TCP)
        else packet[UDP].dport
        if packet.haslayer(UDP)
        else 0
    )
    if bidirectional and (src_ip, src_port) > (dst_ip, dst_port):
        return (dst_ip, src_ip, dst_port, src_port, proto)
    return (src_ip, dst_ip, src_port, dst_port, proto)


def get_session_key(packet) -> Tuple:
    return get_flow_key(packet, bidirectional=True)


def extract_payload(packet, layer: Literal["l3", "l7", "l2"] = "l3") -> bytes:
    if layer == "l2":
        # Full frame, including Ethernet header when present
        return bytes(packet)
    if not packet.haslayer(IP):
        return b""
    if layer == "l7":
        if packet.haslayer(TCP):
            return bytes(packet[TCP].payload)
        if packet.haslayer(UDP):
            return bytes(packet[UDP].payload)
        return b""
    # l3: IP and above
    return bytes(packet[IP])


def pad_or_trim(payload: bytes, target_size: int) -> np.ndarray:
    buf = np.zeros(target_size, dtype=np.uint8)
    take = min(len(payload), target_size)
    if take:
        buf[:take] = np.frombuffer(payload[:take], dtype=np.uint8)
    return buf


# -----------------------------------------------------------------------------
# Config and metadata
# -----------------------------------------------------------------------------


class DatasetConfig(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = "ustc_packet"
    pcap_root: Path = Field(default_factory=_default_pcap_root)
    output_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parent / "datasets" / "out"
    )
    mode: Literal["packet", "session", "flow"] = "packet"
    layer: Literal["l3", "l7", "l2"] = "l3"
    include_layer_suffix: bool = True
    target_size: int = 784
    test_size: float = 0.1
    seed: int = 42
    dedupe: bool = True
    min_bytes: int = 1
    max_samples_per_label: int | None = None
    label_names: List[str] | None = None

    @property
    def resolved_name(self) -> str:
        if self.include_layer_suffix:
            return f"{self.name}_{self.layer}"
        return self.name

    @property
    def dataset_dir(self) -> Path:
        return self.output_dir / self.resolved_name

    @property
    def metadata_path(self) -> Path:
        return self.dataset_dir / "metadata.json"


class DatasetSummary(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    label_names: List[str]
    counts: Dict[str, int]
    per_label: Dict[str, int]
    train_counts: Dict[str, int]
    test_counts: Dict[str, int]
    config: DatasetConfig


DEFAULT_CONFIG = DatasetConfig()


# -----------------------------------------------------------------------------
# Core processing
# -----------------------------------------------------------------------------


def process_pcap_file(
    pcap_path: Path,
    mode: Literal["session", "flow", "packet"],
    layer: Literal["l3", "l7", "l2"],
) -> Dict[Tuple, bytes]:
    sessions: Dict[Tuple, bytearray] = {}
    packets = rdpcap(str(pcap_path))
    for idx, pkt in enumerate(packets):
        if mode == "session":
            key = get_session_key(pkt)
        elif mode == "flow":
            key = get_flow_key(pkt)
        else:
            key = ("packet", idx)
        if key is None:
            continue
        payload = extract_payload(pkt, layer)
        if not payload:
            continue
        if mode == "packet":
            # store as bytes
            sessions[key] = bytearray(
                payload if isinstance(payload, (bytes, bytearray)) else bytes(payload)
            )
        else:
            if key not in sessions:
                sessions[key] = bytearray()
            sessions[key].extend(payload)
    return {
        k: (v if isinstance(v, bytes) else bytes(v))
        for k, v in sessions.items()
        if len(v) > 0
    }


def _iter_pcaps(root: Path, labels: Sequence[str]):
    for label in labels:
        for pcap in sorted((root / label).glob("*.pcap")):
            yield label, pcap


def preprocess(config: DatasetConfig = DEFAULT_CONFIG) -> DatasetSummary:
    rng = np.random.default_rng(config.seed)
    label_names = config.label_names or sorted(
        [p.name for p in config.pcap_root.iterdir() if p.is_dir()]
    )
    if not label_names:
        raise ValueError(f"No label folders found under {config.pcap_root}")

    config.dataset_dir.mkdir(parents=True, exist_ok=True)
    samples: List[np.ndarray] = []
    raw_samples: List[bytes] = []
    labels: List[int] = []
    dedupe_hashes = set()
    deduped_count = 0
    per_label_counts: Dict[str, int] = {name: 0 for name in label_names}

    total_pcaps = sum(
        len(list((config.pcap_root / label).glob("*.pcap"))) for label in label_names
    )
    pcap_bar = tqdm(total=total_pcaps, desc="pcaps", unit="pcap", dynamic_ncols=True)

    try:
        for label_idx, label in enumerate(label_names):
            capped = 0
            pcaps = sorted((config.pcap_root / label).glob("*.pcap"))
            sample_bar = tqdm(
                desc=f"{label} samples", unit="", dynamic_ncols=True, leave=False
            )
            for pcap in pcaps:
                pcap_bar.set_postfix(label=label, file=pcap.name)
                payloads = process_pcap_file(pcap, config.mode, config.layer)
                for payload in payloads.values():
                    if len(payload) < config.min_bytes:
                        continue
                    arr = pad_or_trim(payload, config.target_size)
                    if config.dedupe:
                        digest = hashlib.md5(arr.tobytes()).hexdigest()
                        if digest in dedupe_hashes:
                            deduped_count += 1
                            continue
                        dedupe_hashes.add(digest)
                    samples.append(arr)
                    raw_samples.append(
                        payload if isinstance(payload, bytes) else bytes(payload)
                    )
                    labels.append(label_idx)
                    per_label_counts[label] += 1
                    capped += 1
                    sample_bar.update(1)
                    if (
                        config.max_samples_per_label
                        and capped >= config.max_samples_per_label
                    ):
                        break
                pcap_bar.update(1)
                if (
                    config.max_samples_per_label
                    and capped >= config.max_samples_per_label
                ):
                    break
            sample_bar.close()
    finally:
        pcap_bar.close()

    if not samples:
        raise ValueError("No samples were produced; check input directory and filters")

    images = np.stack(samples, axis=0).astype(np.uint8)
    label_arr = np.array(labels, dtype=np.int64)

    # Raw variable-length payloads are stored alongside the fixed-size arrays
    # as a simple NumPy object array so we can reuse the exact bytes later
    # (e.g., for replay scripts that need full L2/L3/L7 payloads).
    raw_arr = np.array(raw_samples, dtype=object)

    perm = rng.permutation(len(images))
    n_test = int(round(len(images) * config.test_size))
    if len(images) > 1:
        n_test = min(max(n_test, 1), len(images) - 1)
    else:
        n_test = 0
    test_idx = perm[:n_test]
    train_idx = perm[n_test:]

    train_x, train_y = images[train_idx], label_arr[train_idx]
    test_x, test_y = images[test_idx], label_arr[test_idx]

    train_raw = raw_arr[train_idx]
    test_raw = raw_arr[test_idx]

    config.dataset_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(config.dataset_dir / "train.npz", x=train_x, y=train_y)
    np.savez_compressed(config.dataset_dir / "test.npz", x=test_x, y=test_y)

    # Save parallel raw payload splits for consumers that need the original
    # variable-length bytes (e.g., replay over a NIC). These are kept separate
    # from the fixed-size tensors used for training.
    np.savez_compressed(
        config.dataset_dir / "train_raw.npz", payloads=train_raw, y=train_y
    )
    np.savez_compressed(
        config.dataset_dir / "test_raw.npz", payloads=test_raw, y=test_y
    )

    train_counts = {
        label: int((train_y == idx).sum()) for idx, label in enumerate(label_names)
    }
    test_counts = {
        label: int((test_y == idx).sum()) for idx, label in enumerate(label_names)
    }
    summary = DatasetSummary(
        name=config.resolved_name,
        label_names=label_names,
        counts={"total": len(images), "train": len(train_y), "test": len(test_y)},
        per_label=per_label_counts,
        train_counts=train_counts,
        test_counts=test_counts,
        config=config,
    )

    metadata = summary.model_dump()
    metadata["config"] = config.model_dump()
    config.metadata_path.write_text(json.dumps(metadata, indent=2, default=str))
    typer.echo(
        f"Saved dataset to: {config.dataset_dir} (train.npz, test.npz, train_raw.npz, test_raw.npz, metadata.json)"
    )
    typer.echo(f"Dedupe stats: removed {deduped_count} duplicates prior to split")
    return summary


# -----------------------------------------------------------------------------
# Loading helpers
# -----------------------------------------------------------------------------


def load_split_arrays(
    config: DatasetConfig = DEFAULT_CONFIG, split: Literal["train", "test"] = "train"
) -> Tuple[np.ndarray, np.ndarray]:
    path = config.dataset_dir / f"{split}.npz"
    if not path.exists():
        raise FileNotFoundError(f"Split not found: {path}. Run preprocess first.")
    data = np.load(path)
    return data["x"], data["y"]


def load_split_raw(
    config: DatasetConfig = DEFAULT_CONFIG, split: Literal["train", "test"] = "train"
) -> Tuple[np.ndarray, np.ndarray]:
    """Load variable-length raw payloads and labels for a split.

    This mirrors `load_split_arrays` but returns the original bytes sequences
    (stored as an object array) instead of fixed-size, padded tensors.
    """

    path = config.dataset_dir / f"{split}_raw.npz"
    if not path.exists():
        raise FileNotFoundError(
            f"Raw split not found: {path}. Run preprocess with an updated dataset module."
        )
    data = np.load(path, allow_pickle=True)
    return data["payloads"], data["y"]


def load_metadata(config: DatasetConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """Load dataset metadata produced by :func:`preprocess`.

    This provides access to fields like ``label_names`` without callers
    needing to know about the on-disk JSON layout.
    """

    if not config.metadata_path.exists():
        raise FileNotFoundError(
            f"Metadata not found: {config.metadata_path}. Run preprocess first."
        )
    with config.metadata_path.open("r") as f:
        return json.load(f)


def load_splits(
    config: DatasetConfig = DEFAULT_CONFIG,
) -> Tuple[Tuple[np.ndarray, np.ndarray], Tuple[np.ndarray, np.ndarray]]:
    return load_split_arrays(config, "train"), load_split_arrays(config, "test")


def ensure_preprocessed(
    config: DatasetConfig = DEFAULT_CONFIG, force: bool = False
) -> DatasetSummary | None:
    if force or not (config.dataset_dir / "train.npz").exists():
        return preprocess(config)
    return None


# -----------------------------------------------------------------------------
# CLI
# -----------------------------------------------------------------------------


@app.command()
def preprocess_cmd(
    name: str = typer.Option(DEFAULT_CONFIG.name, help="Dataset name (output folder)"),
    mode: Literal["packet", "session", "flow"] = typer.Option(
        DEFAULT_CONFIG.mode, help="Grouping granularity"
    ),
    layer: Literal["l3", "l7", "l2"] = typer.Option(
        DEFAULT_CONFIG.layer,
        help="Payload to extract: l3=IP+, l7=application only, l2=full Ethernet frame",
    ),
    target_size: int = typer.Option(
        DEFAULT_CONFIG.target_size, help="Bytes per sample (28x28 default)"
    ),
    test_size: float = typer.Option(
        DEFAULT_CONFIG.test_size, help="Test split fraction"
    ),
    dedupe: bool = typer.Option(True, help="Drop duplicate payloads"),
    max_samples_per_label: int | None = typer.Option(
        None, help="Optional cap per label"
    ),
    include_layer_suffix: bool = typer.Option(
        True, help="Append _<layer> to the dataset folder name"
    ),
    output_dir: Path | None = typer.Option(None, help="Override output root"),
    pcap_root: Path | None = typer.Option(None, help="Override PCAP root"),
    seed: int = typer.Option(DEFAULT_CONFIG.seed, help="Random seed"),
):
    cfg = DatasetConfig(
        name=name,
        mode=mode,
        layer=layer,
        include_layer_suffix=include_layer_suffix,
        target_size=target_size,
        test_size=test_size,
        dedupe=dedupe,
        max_samples_per_label=max_samples_per_label,
        output_dir=output_dir or DEFAULT_CONFIG.output_dir,
        pcap_root=pcap_root or DEFAULT_CONFIG.pcap_root,
        seed=seed,
    )
    summary = preprocess(cfg)
    typer.echo(f"✓ Preprocessed dataset '{summary.name}'")
    typer.echo(
        f"  Total samples: {summary.counts['total']} (train {summary.counts['train']}, test {summary.counts['test']})"
    )
    typer.echo(f"  Labels: {', '.join(summary.label_names)}")


if __name__ == "__main__":
    app()
