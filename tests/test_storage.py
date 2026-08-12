import os
import tempfile

from storage import Storage


def test_save_and_get_history_round_trip():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        storage = Storage(db_path=path)
        storage.save_message("broadcast", "alice", "hi", 1.0)
        storage.save_message("broadcast", "bob", "hey", 2.0)

        history = storage.get_history("broadcast")

        assert history == [("alice", "hi", 1.0), ("bob", "hey", 2.0)]
        storage.close()
    finally:
        os.remove(path)
