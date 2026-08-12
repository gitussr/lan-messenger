from protocol import ChatMessage, decode, encode


def test_chat_message_round_trips_through_json():
    msg = ChatMessage(sender="alice", text="hello", chat_id="broadcast", timestamp=123.0)

    raw = encode(msg)
    decoded = decode(raw.decode("utf-8").strip())

    assert decoded == {
        "sender": "alice",
        "text": "hello",
        "chat_id": "broadcast",
        "timestamp": 123.0,
        "type": "chat",
    }
