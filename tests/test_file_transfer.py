import base64

from file_transfer import FileReceiver


def test_receiver_reassembles_out_of_order_chunks_and_strips_path(tmp_path):
    receiver = FileReceiver(download_dir=str(tmp_path))
    received = {}
    receiver.on_file_received = lambda sender, path: received.setdefault(sender, path)

    chunk0 = base64.b64encode(b"hello ").decode()
    chunk1 = base64.b64encode(b"world").decode()

    # Chunks arrive out of order and with a path-traversal filename.
    receiver.handle_chunk(
        {"sender": "alice", "filename": "../../evil.txt", "index": 1, "data": chunk1, "eof": False},
        "alice",
    )
    receiver.handle_chunk(
        {"sender": "alice", "filename": "../../evil.txt", "index": 0, "data": chunk0, "eof": False},
        "alice",
    )
    receiver.handle_chunk(
        {"sender": "alice", "filename": "../../evil.txt", "index": 2, "data": "", "eof": True},
        "alice",
    )

    dest = tmp_path / "evil.txt"
    assert dest.exists()
    assert dest.read_bytes() == b"hello world"
    assert received["alice"] == str(dest)
