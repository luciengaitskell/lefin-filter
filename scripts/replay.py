#!/usr/bin/env python3
"""Replay validation samples across a two-port link and measure pass/fail & latency.

Scenario: NIC with two interfaces connected via an inline filter appliance. We send
packets out `tx_iface`, listen on `rx_iface`, and check which validation samples
make it through. Packets are tagged with a small header containing sample_id and
label so we can match returns. Latency is measured using capture timestamps.

Usage examples:
  uv run replay_filter_eval.py run --tx eth0 --rx eth1 --count 5000
  uv run replay_filter_eval.py run --tx eth0 --rx eth1 --pps 5000 --count 20000

Notes:
- We build synthetic UDP packets: Ether/IP/UDP/Raw(tag + sample bytes).
- The tag is 5 bytes: 4-byte sample_id (uint32 LE) + 1-byte label.
- Validation samples come from the dataset test split.
- Best-effort timestamping: capture timestamps come from libpcap/OS. If your
  driver is configured for hardware timestamps, pcap will surface them; otherwise
  they are kernel/software timestamps. This keeps the script simple.
"""

from __future__ import annotations

import hashlib
import struct
import time
from pathlib import Path
from typing import Dict, Literal, Tuple

import numpy as np
import typer
from pydantic import BaseModel, Field
from scapy.all import AsyncSniffer, Raw, conf, sendp
from scapy.layers.inet import IP, UDP
from scapy.layers.l2 import Ether
from tqdm.auto import tqdm

from model.dataset import DEFAULT_CONFIG, DatasetConfig, load_metadata, load_split_raw

app = typer.Typer(
    help="Replay validation samples over two NIC ports and measure pass/fail & latency"
)


# ----------------------------------------------------------------------------
# Models
# ----------------------------------------------------------------------------


class ReplayConfig(BaseModel):
    dataset: DatasetConfig = Field(default_factory=lambda: DEFAULT_CONFIG.model_copy())
    tx_iface: str
    rx_iface: str
    dst_mac: str | None = None
    src_mac: str | None = None
    dst_ip: str | None = "198.18.0.2"
    src_ip: str | None = "198.18.0.1"
    dst_port: int | None = 5001
    pps: int | None = 5000
    count: int | None = 10000
    timeout: float = 30.0
    batch: int = 512
    snaplen: int = 2048
    promisc: bool = True
    out_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parent)
    max_len_bytes: int | None = 1514
    payload_layer: Literal["l2", "l3", "l7"] = (
        "l3"  # how dataset bytes should be injected on send
    )
    allowlist_file: Path | None = None
    denylist_file: Path | None = None
    specific_ids_file: Path | None = None
    benign_label_names: list[str] | None = None
    allowlist_label_names: list[str] | None = None
    debug: bool = False  # Enable debug mode with detailed packet ordering logs


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def _hash_bytes(data: bytes) -> int:
    """Return a stable 64-bit hash for arbitrary bytes.

    We use BLAKE2b with an 8-byte digest; collisions are vanishingly unlikely
    for the dataset sizes we care about and this works uniformly for l2/l3/l7.
    """

    h = hashlib.blake2b(data, digest_size=8)
    # Interpret as unsigned little-endian integer for easy dict keys
    return int.from_bytes(h.digest(), "little")


def _build_packet(sample_id: int, label: int, payload: bytes, cfg: ReplayConfig):
    tag = struct.pack("<IB", sample_id, label & 0xFF)
    raw = Raw(load=tag + payload)
    ether = Ether()
    if cfg.dst_mac:
        ether.dst = cfg.dst_mac
    if cfg.src_mac:
        ether.src = cfg.src_mac
    pkt = (
        ether
        / IP(src=cfg.src_ip or "198.18.0.1", dst=cfg.dst_ip or "198.18.0.2")
        / UDP(sport=1024 + (sample_id % 40000), dport=cfg.dst_port or 5001)
        / raw
    )
    return pkt


def _extract_tag(pkt) -> Tuple[int | None, int | None]:
    """Extract (sample_id, label) from a received packet.

    For strict L2 tests where the appliance acts as a loopback and does not
    modify frames, we rely on a hash of the full on-wire bytes and treat that
    hash as the sample_id (label is set to -1).

    For L7 runs we prefer the explicit 5-byte tag at the start of the Raw
    payload. As a generic fallback for other cases, we also try a payload hash
    so that we can still count passes when headers or ports differ.
    """

    # If we can reconstruct the full wire bytes, use that for hashing
    try:
        raw_bytes = bytes(pkt)
        if raw_bytes:
            sid = _hash_bytes(raw_bytes)
            return sid, -1
    except Exception:
        pass

    # Preferred path for tagged L7: explicit tag at the start of Raw payload
    if pkt.haslayer(Raw):
        data = bytes(pkt[Raw].load)
        if len(data) >= 5:
            sample_id = struct.unpack_from("<I", data, 0)[0]
            label = data[4]
            return sample_id, label

    # Fallback: hash just the Raw payload if present
    if pkt.haslayer(Raw):
        data = bytes(pkt[Raw].load)
        if data:
            sid = _hash_bytes(data)
            return sid, -1

    return None, None


# ----------------------------------------------------------------------------
# Core logic
# ----------------------------------------------------------------------------


def run_replay(cfg: ReplayConfig):
    # Load dataset metadata to obtain label names for eval without callers
    # needing to know anything about the on-disk JSON structure.
    metadata = load_metadata(cfg.dataset)
    label_names = metadata.get("label_names", [])

    # Load validation split using raw (variable-length) payloads so that
    # replay uses the exact original bytes rather than the fixed-width,
    # zero-padded tensors used for training.
    x_raw, y_test = load_split_raw(cfg.dataset, "test")
    if x_raw.size == 0:
        raise RuntimeError("Test raw split is empty; run preprocessing first")

    total = cfg.count if cfg.count else len(x_raw)
    total = min(total, len(x_raw))
    ids = np.arange(total, dtype=np.int64)

    if cfg.specific_ids_file is not None:
        text = cfg.specific_ids_file.read_text().strip().splitlines()
        raw_ids = [int(line) for line in text if line.strip()]
        ids = np.array(
            sorted({i for i in raw_ids if 0 <= i < len(x_raw)}), dtype=np.int64
        )

    if cfg.allowlist_file is not None:
        text = cfg.allowlist_file.read_text().strip().splitlines()
        allowed = {int(line) for line in text if line.strip()}
        ids = np.array(sorted([i for i in ids if i in allowed]), dtype=np.int64)

    if cfg.denylist_file is not None:
        text = cfg.denylist_file.read_text().strip().splitlines()
        denied = {int(line) for line in text if line.strip()}
        ids = np.array(sorted([i for i in ids if i not in denied]), dtype=np.int64)

    # Optional label-name allowlist: only keep indices whose label name is in
    # the configured set. This uses label_names from metadata and y_test.
    if cfg.allowlist_label_names:
        label_allow = set(cfg.allowlist_label_names)
        filtered = []
        for i in ids:
            idx = int(i)
            if idx >= len(y_test):
                continue
            lbl_idx = int(y_test[idx])
            if 0 <= lbl_idx < len(label_names):
                if label_names[lbl_idx] in label_allow:
                    filtered.append(idx)
        ids = np.array(sorted(set(filtered)), dtype=np.int64)

    if ids.size == 0:
        raise RuntimeError("No sample indices to replay after applying filters")

    total = len(ids)

    # Prep sniffer (filter only when using l7 wrapper)
    conf.sniff_promisc = cfg.promisc
    bpf = None
    if cfg.payload_layer == "l7" and cfg.dst_port:
        bpf = f"udp and port {cfg.dst_port}"
    sniffer = AsyncSniffer(
        iface=cfg.rx_iface,
        filter=bpf,
        store=True,
        prn=None,
        count=0,
        promisc=cfg.promisc,
        monitor=False,
    )

    sniffer.start()
    time.sleep(0.2)  # let capture warm up

    sent_times: Dict[int, float] = {}
    labels: Dict[int, int] = {}
    sent_packets: Dict[int, bytes] = {}  # Maps sample_id -> raw packet bytes
    # Maps sample_id -> dataset index (sid) so we can
    # later export both hash IDs and dataset indices for misses.
    sample_to_idx: Dict[int, int] = {}
    skipped_dataset_ids: list[int] = []

    # Debug mode: track packet sequence and order
    send_sequence: list[Tuple[int, int, int]] = []  # (send_order, sample_id, label)
    recv_sequence: list[Tuple[int, int, int]] = []  # (recv_order, sample_id, label)
    debug_log_path = None
    debug_log_file = None
    if cfg.debug:
        debug_log_path = cfg.out_dir / "replay_debug_packet_order.txt"
        debug_log_file = debug_log_path.open("w")
        debug_log_file.write("=== PACKET ORDERING DEBUG LOG ===\n")
        debug_log_file.write(
            f"Layer: {cfg.payload_layer}, Benign labels: {cfg.benign_label_names}\n\n"
        )

    pbar = tqdm(total=total, desc="sending", unit="pkt", dynamic_ncols=True)
    batch = cfg.batch
    inter = None
    if cfg.pps and cfg.pps > 0:
        inter = 1.0 / cfg.pps

    send_order = 0

    for start in range(0, total, batch):
        end = min(start + batch, total)
        pkts = []
        for i in range(start, end):
            sid = int(ids[i])
            payload = bytes(x_raw[sid])

            # Skip packets that exceed the configured maximum length.
            if cfg.max_len_bytes is not None and len(payload) > cfg.max_len_bytes:
                skipped_dataset_ids.append(sid)
                continue
            label = int(y_test[sid]) if sid < len(y_test) else 0
            if cfg.payload_layer == "l2":
                # Treat payload as pre-built L2 frame (already padded/trimmed)
                pkt = Ether(payload)
            elif cfg.payload_layer == "l3":
                # Stored bytes already contain IP header; wrap with Ethernet only
                ether = Ether()
                if cfg.dst_mac:
                    ether.dst = cfg.dst_mac
                if cfg.src_mac:
                    ether.src = cfg.src_mac
                pkt = ether / Raw(payload)
            else:  # l7
                if not cfg.dst_ip or not cfg.src_ip:
                    raise ValueError("dst_ip and src_ip are required for l7 replay")
                # Stored bytes are application payload; wrap with Ether/IP/UDP and prepend tag
                pkt = _build_packet(sid, label, payload, cfg)

            # Use dataset index as sample_id and store raw bytes for comparison
            pkt_bytes = bytes(pkt)
            sample_id = sid

            pkts.append(pkt)
            sent_times[sample_id] = time.time()
            labels[sample_id] = label
            sent_packets[sample_id] = pkt_bytes
            sample_to_idx[sample_id] = sid

            # Debug: track send order
            if cfg.debug:
                send_sequence.append((send_order, sample_id, label))
                send_order += 1
        if pkts:
            sendp(pkts, iface=cfg.tx_iface, inter=inter, verbose=False)
            pbar.update(len(pkts))
    pbar.close()

    print("Waiting for capture to complete...")
    time.sleep(1)
    sniffer.stop()
    sniffer.join(timeout=cfg.timeout)
    captured = sniffer.results or []

    # Match captures by comparing raw bytes
    seen: Dict[int, float] = {}
    recv_packets: Dict[int, bytes] = {}  # Maps sample_id -> received raw bytes
    recv_order = 0
    for pkt in captured:
        pkt_bytes = bytes(pkt)

        # Try to find matching sent packet by comparing bytes
        matched_sid = None
        for sent_sid, sent_bytes in sent_packets.items():
            if pkt_bytes == sent_bytes:
                matched_sid = sent_sid
                break

        if matched_sid is not None:
            seen[matched_sid] = getattr(pkt, "time", time.time())
            recv_packets[matched_sid] = pkt_bytes
            # Debug: track receive order
            if cfg.debug:
                recv_label = labels.get(matched_sid, -1)
                recv_sequence.append((recv_order, matched_sid, recv_label))
                recv_order += 1

    passed: list[int] = []
    missed: list[int] = []
    latencies = []
    for sid, send_ts in sent_times.items():
        if sid in seen:
            rtt = (seen[sid] - send_ts) * 1e3  # ms
            latencies.append(rtt)
            passed.append(sid)
        else:
            missed.append(sid)

    pass_rate = len(passed) / max(1, len(sent_times))
    tqdm.write(
        f"Results: sent={len(sent_times)} received={len(passed)} missed={len(missed)} pass_rate={pass_rate:.4f}"
    )
    if latencies:
        arr = np.array(latencies)
        tqdm.write(
            f"Latency ms: p50={np.percentile(arr, 50):.3f} p90={np.percentile(arr, 90):.3f} p95={np.percentile(arr, 95):.3f} max={arr.max():.3f}"
        )

    # Per-label stats
    per_label = {}
    for sid in passed:
        lbl = labels.get(sid, -1)
        per_label[lbl] = per_label.get(lbl, 0) + 1
    tqdm.write(f"Received per label: {per_label}")

    # Eval: benign vs malicious accuracy using label names from the dataset.
    if cfg.benign_label_names:
        benign_set = set(cfg.benign_label_names)

        benign_total = 0
        benign_pass = 0
        malicious_total = 0
        malicious_drop = 0

        # We iterate over all sent sample_ids and check if they were received.
        for sample_id, send_ts in sent_times.items():
            ds_idx = sample_to_idx.get(sample_id)
            if ds_idx is None or ds_idx >= len(y_test):
                continue
            lbl_idx = int(y_test[ds_idx])
            if 0 <= lbl_idx < len(label_names):
                lbl_name = label_names[lbl_idx]
            else:
                lbl_name = str(lbl_idx)

            is_benign = lbl_name in benign_set
            seen_pass = sample_id in seen

            if is_benign:
                benign_total += 1
                if seen_pass:
                    benign_pass += 1
            else:
                malicious_total += 1
                if not seen_pass:
                    malicious_drop += 1

        if benign_total + malicious_total > 0:
            benign_pass_rate = benign_pass / max(1, benign_total)
            malicious_drop_rate = malicious_drop / max(1, malicious_total)
            overall_correct = benign_pass + malicious_drop
            overall_total = benign_total + malicious_total
            overall_acc = overall_correct / overall_total if overall_total else 0.0

            tqdm.write(
                "Eval (using benign_label_names): "
                f"benign_pass_rate={benign_pass_rate:.4f} "
                f"malicious_drop_rate={malicious_drop_rate:.4f} "
                f"overall_accuracy={overall_acc:.4f} "
                f"(benign_total={benign_total}, malicious_total={malicious_total})"
            )

    # Dump misses for inspection: write dataset indices.
    if missed:
        miss_idxs = sorted(set(missed))

        miss_idx_path = cfg.out_dir / "replay_missed_dataset_ids.txt"
        miss_idx_path.write_text("\n".join(str(i) for i in miss_idxs))

        tqdm.write(
            f"Missed {len(missed)} packets; dataset indices written to {miss_idx_path}"
        )

    # Dump skipped oversized payload dataset indices for inspection
    if skipped_dataset_ids:
        skip_idxs = sorted(set(skipped_dataset_ids))
        skip_path = cfg.out_dir / "replay_skipped_oversize_dataset_ids.txt"
        skip_path.write_text("\n".join(str(s) for s in skip_idxs))
        tqdm.write(
            f"Skipped {len(skipped_dataset_ids)} oversized samples; "
            f"dataset indices written to {skip_path}"
        )

    # Debug mode: write packet ordering and byte comparison analysis
    if cfg.debug and debug_log_file:
        debug_log_file.write(f"\n=== SEND SEQUENCE (first 50) ===\n")
        debug_log_file.write("order | sample_id | label | pkt_bytes_len | status\n")
        for order, sid, lbl in send_sequence[:50]:
            status = "RECV" if sid in seen else "MISS"
            pkt_len = len(sent_packets.get(sid, b""))
            debug_log_file.write(
                f"{order:5} | {sid:9} | {lbl:5} | {pkt_len:13} | {status}\n"
            )

        debug_log_file.write(f"\n=== RECEIVE SEQUENCE (first 50) ===\n")
        debug_log_file.write(
            "order | sample_id | label | pkt_bytes_len | match_status\n"
        )
        for order, sid, lbl in recv_sequence[:50]:
            pkt_len = len(recv_packets.get(sid, b""))
            sent_bytes = sent_packets.get(sid, b"")
            recv_bytes = recv_packets.get(sid, b"")
            match_status = "MATCH" if sent_bytes == recv_bytes else "DIFFER"
            debug_log_file.write(
                f"{order:5} | {sid:9} | {lbl:5} | {pkt_len:13} | {match_status}\n"
            )

        # Analyze reordering by comparing sequences
        if send_sequence and recv_sequence:
            send_sids = [sid for _, sid, _ in send_sequence]
            recv_sids = [sid for _, sid, _ in recv_sequence]

            # Check if packets are reordered
            debug_log_file.write(f"\n=== ORDERING ANALYSIS ===\n")
            debug_log_file.write(f"Total sent: {len(send_sequence)}\n")
            debug_log_file.write(f"Total received: {len(recv_sequence)}\n")

            # Check for monotonic increase (no reordering)
            is_monotonic = (
                all(recv_sids[i] <= recv_sids[i + 1] for i in range(len(recv_sids) - 1))
                if len(recv_sids) > 1
                else True
            )
            debug_log_file.write(f"Packets in order: {is_monotonic}\n")

            # Count how many received packets match send position
            in_order_count = 0
            for recv_idx, recv_sid in enumerate(recv_sids[:50]):
                if recv_idx < len(send_sids) and send_sids[recv_idx] == recv_sid:
                    in_order_count += 1
            debug_log_file.write(
                f"Packets in correct position (first 50): {in_order_count}/50\n"
            )

            # Byte comparison analysis
            debug_log_file.write(f"\n=== BYTE COMPARISON (first 20) ===\n")
            bytes_match = 0
            bytes_differ = 0
            for sample_id in recv_sids[:20]:
                sent_bytes = sent_packets.get(sample_id, b"")
                recv_bytes = recv_packets.get(sample_id, b"")
                if sent_bytes == recv_bytes:
                    bytes_match += 1
                    debug_log_file.write(
                        f"sample_id={sample_id}: MATCH (len={len(sent_bytes)})\n"
                    )
                else:
                    bytes_differ += 1
                    debug_log_file.write(
                        f"sample_id={sample_id}: DIFFER sent_len={len(sent_bytes)} recv_len={len(recv_bytes)}\n"
                    )
                    # Show first difference
                    for i, (sb, rb) in enumerate(zip(sent_bytes, recv_bytes)):
                        if sb != rb:
                            debug_log_file.write(
                                f"  First difference at byte {i}: sent=0x{sb:02x} recv=0x{rb:02x}\n"
                            )
                            break
            debug_log_file.write(
                f"\nBytes match: {bytes_match}, Bytes differ: {bytes_differ}\n"
            )

            # Show benign vs malicious breakdown
            if cfg.benign_label_names:
                benign_set = set(cfg.benign_label_names)
                send_benign = sum(
                    1
                    for _, sid, lbl in send_sequence
                    if lbl in benign_set
                    or (0 <= lbl < len(label_names) and label_names[lbl] in benign_set)
                )
                recv_benign = sum(
                    1
                    for _, sid, lbl in recv_sequence
                    if lbl in benign_set
                    or (0 <= lbl < len(label_names) and label_names[lbl] in benign_set)
                )
                debug_log_file.write(
                    f"\nBenign sent: {send_benign}, Benign received: {recv_benign}\n"
                )

        debug_log_file.close()
        tqdm.write(f"Debug packet ordering written to {debug_log_path}")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------


@app.command()
def run(
    tx: str = typer.Option(..., "--tx", help="Transmit interface"),
    rx: str = typer.Option(..., "--rx", help="Receive interface"),
    dataset_name: str = typer.Option(
        DEFAULT_CONFIG.name, help="Dataset base name (folder inside output_dir)"
    ),
    include_layer_suffix: bool = typer.Option(
        True, help="Append _<layer> to dataset folder when resolving paths"
    ),
    dataset_output_dir: Path | None = typer.Option(
        None, help="Override dataset output root"
    ),
    dst_mac: str | None = typer.Option(None, help="Destination MAC to set (optional)"),
    src_mac: str | None = typer.Option(None, help="Source MAC to set (optional)"),
    dst_ip: str | None = typer.Option(
        None,
        help="Destination IP (required for l7 replay; optional/ignored for l2/l3)",
    ),
    src_ip: str | None = typer.Option(
        None,
        help="Source IP (required for l7 replay; optional/ignored for l2/l3)",
    ),
    dst_port: int | None = typer.Option(
        None, help="UDP destination port (used only for l7 replay)"
    ),
    pps: int = typer.Option(5000, help="Packets per second (0 = as fast as possible)"),
    count: int = typer.Option(
        10000, help="Number of validation packets to send (<= test set)"
    ),
    batch: int = typer.Option(512, help="Batch size for sendp"),
    timeout: float = typer.Option(30.0, help="Capture timeout seconds"),
    promisc: bool = typer.Option(True, help="Enable promiscuous mode on RX"),
    max_len_bytes: int = typer.Option(
        1514,
        help="Maximum payload length in bytes to send; larger samples are skipped",
    ),
    payload_layer: Literal["l2", "l3", "l7"] = typer.Option(
        DEFAULT_CONFIG.layer,
        help="Layer to interpret dataset bytes: l2=send raw frame, l3=add Ether only, l7=wrap Ether/IP/UDP with tag",
    ),
    allowlist_file: Path | None = typer.Option(
        None,
        help="Optional file with one index per line; only these indices are eligible (applied after specific-ids-file)",
    ),
    denylist_file: Path | None = typer.Option(
        None,
        help="Optional file with one index per line; these indices are excluded",
    ),
    specific_ids_file: Path | None = typer.Option(
        None,
        help="Optional file with one index per line; when set, only these indices are replayed (overrides count)",
    ),
    benign_labels: str | None = typer.Option(
        None,
        help="Comma-separated list of label names that should be treated as benign for eval (others are treated as malicious)",
    ),
    allowlist_labels: str | None = typer.Option(
        None,
        help="Comma-separated list of label names; only samples with these labels are replayed",
    ),
    debug: bool = typer.Option(
        False,
        help="Enable debug mode: writes detailed packet ordering to replay_debug_packet_order.txt",
    ),
):
    dataset_cfg = DEFAULT_CONFIG.model_copy(
        update={
            "name": dataset_name,
            "layer": payload_layer,
            "include_layer_suffix": include_layer_suffix,
            "output_dir": dataset_output_dir or DEFAULT_CONFIG.output_dir,
        }
    )
    cfg = ReplayConfig(
        dataset=dataset_cfg,
        tx_iface=tx,
        rx_iface=rx,
        dst_mac=dst_mac,
        src_mac=src_mac,
        dst_ip=dst_ip,
        src_ip=src_ip,
        dst_port=dst_port,
        pps=pps if pps > 0 else None,
        count=count,
        batch=batch,
        timeout=timeout,
        promisc=promisc,
        max_len_bytes=max_len_bytes,
        payload_layer=payload_layer,
        allowlist_file=allowlist_file,
        denylist_file=denylist_file,
        specific_ids_file=specific_ids_file,
        benign_label_names=[s.strip() for s in benign_labels.split(",")]
        if benign_labels
        else None,
        allowlist_label_names=[s.strip() for s in allowlist_labels.split(",")]
        if allowlist_labels
        else None,
        debug=debug,
    )
    run_replay(cfg)


if __name__ == "__main__":
    app()
