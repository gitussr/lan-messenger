"""UDP-broadcast peer discovery.

Implements the DISCOVER -> ANNOUNCE handshake described in the design doc: a
peer broadcasts a "discover" packet to the LAN broadcast address, and every
listening peer replies with an "announce" packet (name, port). Peers also
self-announce periodically so late joiners can find them, and stale entries
are reaped after PEER_TIMEOUT seconds of silence.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

DISCOVERY_PORT = 37020
BROADCAST_ADDR = "255.255.255.255"
ANNOUNCE_INTERVAL = 5.0
PEER_TIMEOUT = 15.0


@dataclass
class PeerInfo:
    name: str
    ip: str
    port: int
    last_seen: float


class Discovery:
    def __init__(self, username: str, chat_port: int, discovery_port: int = DISCOVERY_PORT):
        self.username = username
        self.chat_port = chat_port
        self.discovery_port = discovery_port
        self.peers: dict[str, PeerInfo] = {}

        self._lock = threading.Lock()
        self._sock: Optional[socket.socket] = None
        self._running = False

        # optional callback(name, PeerInfo | None) -- None means the peer expired
        self.on_peer_update: Optional[Callable[[str, Optional[PeerInfo]], None]] = None

    def start(self) -> None:
        self._running = True
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.bind(("", self.discovery_port))
        self._sock.settimeout(1.0)

        threading.Thread(target=self._listen_loop, daemon=True).start()
        threading.Thread(target=self._announce_loop, daemon=True).start()
        threading.Thread(target=self._reap_loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        if self._sock:
            self._sock.close()

    def discover_peers(self, timeout: float = 2.0) -> dict[str, PeerInfo]:
        """Actively broadcast a discovery request and wait `timeout` seconds for replies."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.5)
        try:
            self._send(sock, {"type": "discover"}, (BROADCAST_ADDR, self.discovery_port))
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                self._handle_packet(data, addr, reply_sock=sock)
        finally:
            sock.close()
        with self._lock:
            return dict(self.peers)

    def _announce_loop(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            while self._running:
                self._send(
                    sock,
                    {"type": "announce", "name": self.username, "port": self.chat_port},
                    (BROADCAST_ADDR, self.discovery_port),
                )
                time.sleep(ANNOUNCE_INTERVAL)
        finally:
            sock.close()

    def _listen_loop(self) -> None:
        while self._running:
            try:
                data, addr = self._sock.recvfrom(1024)
            except (socket.timeout, OSError):
                continue
            self._handle_packet(data, addr, reply_sock=self._sock)

    def _handle_packet(self, data: bytes, addr, reply_sock: socket.socket) -> None:
        try:
            msg = json.loads(data.decode("utf-8"))
        except ValueError:
            return
        msg_type = msg.get("type")
        if msg_type == "discover":
            self._send(
                reply_sock,
                {"type": "announce", "name": self.username, "port": self.chat_port},
                addr,
            )
        elif msg_type == "announce":
            self._register_peer(msg.get("name"), addr[0], msg.get("port"))

    def _reap_loop(self) -> None:
        while self._running:
            time.sleep(ANNOUNCE_INTERVAL)
            cutoff = time.time() - PEER_TIMEOUT
            expired: list[str] = []
            with self._lock:
                for name, info in list(self.peers.items()):
                    if info.last_seen < cutoff:
                        del self.peers[name]
                        expired.append(name)
            for name in expired:
                if self.on_peer_update:
                    self.on_peer_update(name, None)

    def _register_peer(self, name, ip, port) -> None:
        if not name or name == self.username or port is None:
            return
        with self._lock:
            info = PeerInfo(name=name, ip=ip, port=port, last_seen=time.time())
            is_new = name not in self.peers
            self.peers[name] = info
        if is_new and self.on_peer_update:
            self.on_peer_update(name, info)

    @staticmethod
    def _send(sock: socket.socket, payload: dict, addr) -> None:
        sock.sendto(json.dumps(payload).encode("utf-8"), addr)
