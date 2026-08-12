"""Chunked file sending/receiving layered on top of NetworkManager.

Files are read in fixed-size chunks, base64-encoded into "file" messages
carrying an index, and terminated by an eof=True marker. The receiver
reassembles chunks by index (they may arrive out of order relative to how
the network delivers them within a single connection, though TCP itself
preserves order per-peer) and writes the completed file to disk.
"""
from __future__ import annotations

import base64
import os
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from network import NetworkManager

CHUNK_SIZE = 50 * 1024


def send_file(network: NetworkManager, peer_name: str, filepath: str, sender_name: str) -> None:
    filename = os.path.basename(filepath)
    with open(filepath, "rb") as f:
        index = 0
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            network.send_message(
                peer_name,
                {
                    "type": "file",
                    "sender": sender_name,
                    "filename": filename,
                    "index": index,
                    "data": base64.b64encode(chunk).decode("ascii"),
                    "eof": False,
                },
            )
            index += 1
    network.send_message(
        peer_name,
        {
            "type": "file",
            "sender": sender_name,
            "filename": filename,
            "index": index,
            "data": "",
            "eof": True,
        },
    )


@dataclass
class _IncomingFile:
    chunks: dict = field(default_factory=dict)


class FileReceiver:
    """Reassembles incoming file-chunk messages and writes completed files to disk."""

    def __init__(self, download_dir: str = "downloads"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
        self._transfers: dict[tuple[str, str], _IncomingFile] = {}
        self._lock = threading.Lock()

        # optional callback(sender, filepath)
        self.on_file_received: Optional[Callable[[str, str], None]] = None

    def handle_chunk(self, msg: dict, _peer_name: str) -> None:
        sender = msg["sender"]
        filename = self._safe_filename(msg["filename"])
        key = (sender, filename)

        with self._lock:
            transfer = self._transfers.setdefault(key, _IncomingFile())
            if not msg["eof"]:
                transfer.chunks[msg["index"]] = base64.b64decode(msg["data"])
                return
            ordered = [transfer.chunks[i] for i in sorted(transfer.chunks)]
            del self._transfers[key]

        dest_path = os.path.join(self.download_dir, filename)
        with open(dest_path, "wb") as f:
            for chunk in ordered:
                f.write(chunk)

        if self.on_file_received:
            self.on_file_received(sender, dest_path)

    @staticmethod
    def _safe_filename(filename: str) -> str:
        """Strip any path components to prevent path traversal into the download dir."""
        return os.path.basename(filename.replace("\\", "/"))
