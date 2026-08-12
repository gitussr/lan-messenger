"""Wire message definitions shared by every peer.

All other modules construct/parse messages through this module instead of
building JSON dicts ad hoc, so the wire format stays centralized in one place.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

MSG_CHAT = "chat"
MSG_PRESENCE = "presence"
MSG_FILE = "file"
MSG_ACK = "ack"

STATUS_ONLINE = "online"
STATUS_AWAY = "away"
STATUS_BUSY = "busy"
STATUS_OFFLINE = "offline"

BROADCAST_CHAT_ID = "broadcast"


@dataclass
class ChatMessage:
    sender: str
    text: str
    chat_id: str = BROADCAST_CHAT_ID
    timestamp: float = field(default_factory=time.time)
    type: str = MSG_CHAT

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PresenceUpdate:
    user: str
    status: str
    type: str = MSG_PRESENCE

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileChunk:
    sender: str
    filename: str
    index: int
    data: str  # base64-encoded chunk bytes; "" for the EOF marker
    eof: bool
    type: str = MSG_FILE

    def to_dict(self) -> dict:
        return asdict(self)


def encode(message) -> bytes:
    """Serialize a protocol dataclass (or plain dict) to newline-delimited JSON."""
    payload = message.to_dict() if hasattr(message, "to_dict") else message
    return (json.dumps(payload) + "\n").encode("utf-8")


def decode(raw: str) -> dict:
    return json.loads(raw)
