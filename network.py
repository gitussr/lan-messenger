"""TCP connection management: accepts peer connections, sends/receives messages.

Purely I/O -- message *interpretation* lives in the handlers registered by the
application layer (main.py), not here. Messages are framed as newline-delimited
JSON so a single TCP stream can carry many messages without ambiguity about
where one ends and the next begins.
"""
from __future__ import annotations

import json
import socket
import threading
from typing import Callable, Optional

Handler = Callable[[dict, str], None]


class NetworkManager:
    def __init__(self, username: str, listen_port: int = 0):
        self.username = username
        self.listen_port = listen_port

        self._server_socket: Optional[socket.socket] = None
        self._peer_sockets: dict[str, socket.socket] = {}
        self._handlers: dict[str, Handler] = {}
        self._lock = threading.Lock()
        self._running = False

        self.on_peer_connected: Optional[Callable[[str], None]] = None
        self.on_peer_disconnected: Optional[Callable[[str], None]] = None

    def register_handler(self, msg_type: str, handler: Handler) -> None:
        self._handlers[msg_type] = handler

    def is_connected(self, peer_name: str) -> bool:
        with self._lock:
            return peer_name in self._peer_sockets

    def start_server(self) -> int:
        """Start listening for incoming peer connections; returns the bound port."""
        self._running = True
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(("", self.listen_port))
        self._server_socket.listen()
        self.listen_port = self._server_socket.getsockname()[1]
        threading.Thread(target=self._accept_loop, daemon=True).start()
        return self.listen_port

    def stop(self) -> None:
        self._running = False
        if self._server_socket:
            self._server_socket.close()
        with self._lock:
            sockets = list(self._peer_sockets.values())
            self._peer_sockets.clear()
        for sock in sockets:
            sock.close()

    def connect_to_peer(self, ip: str, port: int, name: str) -> None:
        if name in self._peer_sockets:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((ip, port))
        sock.sendall((self.username + "\n").encode("utf-8"))
        self._register_peer(name, sock)

    def send_message(self, peer_name: str, msg_dict: dict) -> None:
        with self._lock:
            sock = self._peer_sockets.get(peer_name)
        if sock is None:
            raise ConnectionError(f"no connection to peer '{peer_name}'")
        sock.sendall((json.dumps(msg_dict) + "\n").encode("utf-8"))

    def _accept_loop(self) -> None:
        while self._running:
            try:
                client_sock, _addr = self._server_socket.accept()
            except OSError:
                break
            threading.Thread(target=self._handshake_and_listen, args=(client_sock,), daemon=True).start()

    def _handshake_and_listen(self, sock: socket.socket) -> None:
        name_line = self._readline(sock)
        if name_line is None:
            sock.close()
            return
        self._register_peer(name_line.strip(), sock)

    def _register_peer(self, name: str, sock: socket.socket) -> None:
        with self._lock:
            self._peer_sockets[name] = sock
        if self.on_peer_connected:
            self.on_peer_connected(name)
        threading.Thread(target=self._recv_loop, args=(name, sock), daemon=True).start()

    @staticmethod
    def _readline(sock: socket.socket) -> Optional[str]:
        buf = bytearray()
        while True:
            chunk = sock.recv(1)
            if not chunk:
                return None
            if chunk == b"\n":
                return buf.decode("utf-8")
            buf += chunk

    def _recv_loop(self, peer_name: str, sock: socket.socket) -> None:
        buf = b""
        try:
            while self._running:
                data = sock.recv(65536)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except ValueError:
                        continue
                    handler = self._handlers.get(msg.get("type"))
                    if handler:
                        handler(msg, peer_name)
        except OSError:
            pass
        finally:
            with self._lock:
                self._peer_sockets.pop(peer_name, None)
            sock.close()
            if self.on_peer_disconnected:
                self.on_peer_disconnected(peer_name)
