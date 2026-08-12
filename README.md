# LAN Messenger

A peer-to-peer Windows desktop chat app that works entirely over the local network —
no internet connection and no dedicated server required. Peers discover each other via
UDP broadcast, then chat and share files directly over TCP.

See `Building a Windows LAN Messenger – System Design and Implementation.pdf` for the full
design rationale, and `CLAUDE.md` for architecture notes if you're developing on this repo.

## Requirements

- Python 3.10+ (developed/tested on 3.13)
- No third-party runtime dependencies — only the standard library (`socket`, `json`,
  `sqlite3`, `tkinter`)
- Windows (Tkinter ships with the standard Windows Python installer; on other OSes it may
  need to be installed separately)

## Setup

Clone the repo and, optionally, create a virtual environment for the dev/build tooling
(`pytest`, `pyinstaller`) listed in `requirements.txt` — the app itself needs nothing
installed to run:

```
git clone https://github.com/gitussr/lan-messenger.git
cd lan-messenger
pip install -r requirements.txt   # only needed for running tests / building the .exe
```

## Running

```
python main.py [username]
```

If you omit the username, you'll be prompted for one. Each running instance opens its own
window and is simultaneously a client and a server — there's nothing else to start.

To try it on one machine with two peers, open two terminals:

```
python main.py alice
python main.py bob
```

Give it a few seconds for discovery (peers re-announce every 5s); each window's contact
list should then show the other. Select a contact, type a message, and press Enter or
Send. Use the "File..." button to send a file — it lands in `<username>_downloads/`.

Chat history is stored locally per user in `<username>_chat_history.db` (SQLite) and is
never shared with other peers.

### Firewall

Windows Firewall may prompt to allow Python network access the first time you run this —
allow it on your private/home network profile. The app uses:

- UDP port `37020` for peer discovery
- A dynamically assigned TCP port per instance for chat/file transfer

## Testing

```
python -m pytest
```

Run a single test:

```
python -m pytest tests/test_storage.py -k round_trip
```

## Building a standalone .exe

```
pip install pyinstaller
pyinstaller --onefile main.py
```

The executable is produced at `dist/main.exe` and can run on a machine without Python
installed.
