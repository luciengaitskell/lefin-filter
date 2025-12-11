#!/usr/bin/env python3
import errno
import select
import socket
import struct
import time
from typing import Tuple

import typer

app = typer.Typer(
    help="One-way latency over DAC using AF_PACKET + HW TX/RX timestamping"
)

# ---- Fallback constants for older Python builds ----
SO_TIMESTAMPING = getattr(
    socket, "SO_TIMESTAMPING", 37
)  # SOL_SOCKET option 37 [web:139]
MSG_ERRQUEUE = getattr(socket, "MSG_ERRQUEUE", 0x2000)

# Custom Ethertype for our test frames
ETH_P_CUSTOM = 0x88B5

# SO_TIMESTAMPING flag bits (from linux/net_tstamp.h)
SOF_TIMESTAMPING_TX_HARDWARE = 1 << 0
SOF_TIMESTAMPING_TX_SOFTWARE = 1 << 1
SOF_TIMESTAMPING_RX_HARDWARE = 1 << 2
SOF_TIMESTAMPING_RX_SOFTWARE = 1 << 3
SOF_TIMESTAMPING_RAW_HARDWARE = 1 << 6


def mac_bytes_to_str(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in b[:6])


def enable_timestamping(sock: socket.socket) -> None:
    flags = (
        SOF_TIMESTAMPING_TX_HARDWARE
        | SOF_TIMESTAMPING_TX_SOFTWARE
        | SOF_TIMESTAMPING_RX_HARDWARE
        | SOF_TIMESTAMPING_RX_SOFTWARE
        | SOF_TIMESTAMPING_RAW_HARDWARE
    )
    sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPING, flags)


def parse_scm_timestamping(cdata: bytes):
    """
    Parse struct scm_timestamping (3 * timespec).
    Returns (kind, sec, nsec) preferring hw_raw -> hw_system -> sw.
    """
    if len(cdata) < 48:
        return None
    sec0, nsec0, sec1, nsec1, sec2, nsec2 = struct.unpack("qqqqqq", cdata[:48])
    # [0]=software, [1]=hw->system, [2]=raw hw per kernel docs. [web:37][web:57]
    if sec2 or nsec2:
        return ("hw_raw", sec2, nsec2)
    if sec1 or nsec1:
        return ("hw_system", sec1, nsec1)
    if sec0 or nsec0:
        return ("sw", sec0, nsec0)
    return None


def recv_with_timestamp(sock: socket.socket, timeout: float):
    """Receive one Ethernet frame and extract its timestamp."""
    r, _, _ = select.select([sock], [], [], timeout)
    if not r:
        raise TimeoutError("RX timeout")

    frame, ancdata, flags, addr = sock.recvmsg(2048, 512)
    ts = None
    for level, ctype, cdata in ancdata:
        if level == socket.SOL_SOCKET and ctype == SO_TIMESTAMPING:
            ts = parse_scm_timestamping(cdata)
    return frame, addr, ts


def get_tx_timestamp(sock: socket.socket, timeout: float):
    """Read one TX timestamp from the socket error queue."""
    deadline = time.time() + timeout
    while True:
        try:
            data, ancdata, msg_flags, addr = sock.recvmsg(2048, 512, MSG_ERRQUEUE)
        except OSError as e:
            if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                if time.time() > deadline:
                    raise TimeoutError("TX timestamp timeout")
                time.sleep(0.001)
                continue
            raise

        for level, ctype, cdata in ancdata:
            if level == socket.SOL_SOCKET and ctype == SO_TIMESTAMPING:
                ts = parse_scm_timestamping(cdata)
                if ts is not None:
                    return ts


def make_af_packet_socket(iface: str) -> Tuple[socket.socket, bytes]:
    """
    Create AF_PACKET raw socket on iface for ETH_P_CUSTOM and return (sock, local_mac).
    """
    proto = socket.htons(ETH_P_CUSTOM)
    s = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, proto)
    s.setblocking(False)
    s.bind((iface, proto))  # filter to our ethertype on that interface
    enable_timestamping(s)

    # Local MAC from AF_PACKET getsockname()[4] (first 6 bytes).
    sn = s.getsockname()
    local_mac = sn[4][:6]
    return s, local_mac


@app.command()
def oneway(
    tx_iface: str = typer.Option(..., help="Transmit interface (e.g. ens1f0)"),
    rx_iface: str = typer.Option(..., help="Receive interface (e.g. ens1f1)"),
    count: int = typer.Option(10, help="Number of probes"),
    interval: float = typer.Option(0.5, help="Seconds between probes"),
):
    """
    Measure one-way latency from tx_iface -> device -> rx_iface using NIC HW timestamps.
    """
    tx_sock, tx_mac = make_af_packet_socket(tx_iface)
    rx_sock, rx_mac = make_af_packet_socket(rx_iface)

    dest_mac = rx_mac  # send directly to the other port's MAC

    typer.echo(
        f"TX iface={tx_iface} MAC={mac_bytes_to_str(tx_mac)}, "
        f"RX iface={rx_iface} MAC={mac_bytes_to_str(rx_mac)}"
    )

    eth_type = struct.pack("!H", ETH_P_CUSTOM)

    for seq in range(count):
        # Payload: magic + sequence number
        payload = b"OWD" + struct.pack("!I", seq)

        # Ethernet frame: dst MAC (rx port), src MAC (tx port), ethertype, payload
        frame = dest_mac + tx_mac + eth_type + payload

        # Send on TX port
        tx_sock.send(frame)

        # TX timestamp
        try:
            kind_tx, sec_tx, nsec_tx = get_tx_timestamp(tx_sock, timeout=1.0)
        except TimeoutError:
            typer.echo(f"[{seq}] TX timestamp timeout")
            time.sleep(interval)
            continue

        # Wait for matching frame on RX port
        try:
            while True:
                rx_frame, addr, ts_rx = recv_with_timestamp(rx_sock, timeout=1.0)
                if len(rx_frame) < 14 + 7:
                    continue

                dst = rx_frame[0:6]
                src = rx_frame[6:12]
                rx_type = rx_frame[12:14]
                rx_payload = rx_frame[14:]

                # Filter: our ethertype, magic, sequence, and MACs
                if rx_type != eth_type:
                    continue
                if rx_payload[:3] != b"OWD":
                    continue
                rx_seq = struct.unpack("!I", rx_payload[3:7])[0]
                if rx_seq != seq:
                    continue
                if dst != rx_mac or src != tx_mac:
                    continue

                if ts_rx is None:
                    typer.echo(f"[{seq}] RX frame but no RX timestamp")
                    break

                kind_rx, sec_rx, nsec_rx = ts_rx
                # One-way delay in seconds using two NIC/PHC-based timestamps. [web:37][web:57]
                owd_sec = (sec_rx - sec_tx) + (nsec_rx - nsec_tx) / 1e9
                typer.echo(
                    f"[{seq}] OWD={owd_sec * 1e6:.3f} us "
                    f"(TX {kind_tx} {sec_tx}.{nsec_tx:09d}, "
                    f"RX {kind_rx} {sec_rx}.{nsec_rx:09d})"
                )
                break
        except TimeoutError:
            typer.echo(f"[{seq}] RX timeout (no matching frame)")

        time.sleep(interval)


if __name__ == "__main__":
    app()
