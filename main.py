"""Entry point: wires discovery, networking, storage, and the GUI together."""
from __future__ import annotations

import sys
import time
from typing import Optional

from discovery import Discovery, PeerInfo
from file_transfer import FileReceiver, send_file
from gui import ChatWindow
from network import NetworkManager
from protocol import BROADCAST_CHAT_ID, MSG_CHAT, MSG_FILE, MSG_PRESENCE
from storage import Storage


def prompt_username() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    name = input("Choose a username: ").strip()
    return name or "anonymous"


def main() -> None:
    username = prompt_username()

    storage = Storage(db_path=f"{username}_chat_history.db")
    network = NetworkManager(username=username)
    chat_port = network.start_server()

    discovery = Discovery(username=username, chat_port=chat_port)
    file_receiver = FileReceiver(download_dir=f"{username}_downloads")
    gui = ChatWindow(username=username)

    def refresh_peer_list() -> None:
        gui.set_peers(list(discovery.peers.keys()))

    def ensure_connected(peer_name: str) -> bool:
        if network.is_connected(peer_name):
            return True
        peer = discovery.peers.get(peer_name)
        if peer is None:
            gui.display_system(f"{peer_name} is no longer available.")
            return False
        try:
            network.connect_to_peer(peer.ip, peer.port, peer_name)
            return True
        except OSError as exc:
            gui.display_system(f"Could not reach {peer_name}: {exc}")
            return False

    def handle_chat(msg: dict, _peer_name: str) -> None:
        def apply() -> None:
            storage.save_message(BROADCAST_CHAT_ID, msg["sender"], msg["text"], msg["timestamp"])
            gui.display_message(msg["sender"], msg["text"])

        gui.schedule(0, apply)

    def handle_presence(msg: dict, _peer_name: str) -> None:
        gui.schedule(0, lambda: gui.display_system(f"{msg['user']} is {msg['status']}"))

    def handle_file(msg: dict, peer_name: str) -> None:
        file_receiver.handle_chunk(msg, peer_name)

    def on_file_received(sender: str, path: str) -> None:
        gui.schedule(0, lambda: gui.display_system(f"Received file from {sender}: {path}"))

    file_receiver.on_file_received = on_file_received
    network.register_handler(MSG_CHAT, handle_chat)
    network.register_handler(MSG_PRESENCE, handle_presence)
    network.register_handler(MSG_FILE, handle_file)

    def on_peer_update(_name: str, _info: Optional[PeerInfo]) -> None:
        gui.schedule(0, refresh_peer_list)

    discovery.on_peer_update = on_peer_update

    def on_send_chat(peer_name: str, text: str) -> None:
        if not ensure_connected(peer_name):
            return
        timestamp = time.time()
        network.send_message(
            peer_name,
            {
                "type": MSG_CHAT,
                "sender": username,
                "text": text,
                "chat_id": BROADCAST_CHAT_ID,
                "timestamp": timestamp,
            },
        )
        storage.save_message(BROADCAST_CHAT_ID, username, text, timestamp)

    def on_send_file(peer_name: str, filepath: str) -> None:
        if not ensure_connected(peer_name):
            return
        send_file(network, peer_name, filepath, sender_name=username)

    gui.on_send_chat = on_send_chat
    gui.on_send_file = on_send_file

    discovery.start()

    try:
        gui.run()
    finally:
        discovery.stop()
        network.stop()
        storage.close()


if __name__ == "__main__":
    main()
