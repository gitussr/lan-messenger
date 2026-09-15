# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Windows desktop LAN chat/messenger, in Python, that works entirely over the local network
with **no central server required** (peer-to-peer). Any two peers on the same LAN/subnet
discover each other, chat, share files, and see presence/status without any internet
dependency or dedicated server machine.

The design source is `Building a Windows LAN Messenger – System Design and Implementation.pdf`
in the repo root — consult it for the full rationale (protocol/GUI/serialization comparisons,
AWS-concept mapping, etc.) behind the choices below. The code in this repo is the
implementation of that blueprint, with a couple of correctness fixes over the doc's pseudocode
(see "Deviations from the design doc" below).

## Commands

There is no build step — this is a plain-stdlib Python app, run directly.

```
python main.py [username]          # launch a peer; shows a GUI dialog for a username if omitted
python -m pytest                   # run the test suite (tests/)
python -m pytest tests/test_storage.py -k round_trip   # run a single test
python -m py_compile *.py          # quick syntax check without running anything
```

Packaging as a Windows `.exe` (PyInstaller):
```
pip install pyinstaller
pyinstaller --onefile --windowed --collect-data customtkinter --collect-data pytablericons main.py
```
`--collect-data` bundles package data files that are read from disk at runtime: CustomTkinter's
theme files and pytablericons' SVG icons (it loads each icon from its package directory).
`--windowed` is required, not optional: the app is GUI-only end to end (the username prompt
is `gui.ask_username()`, a CustomTkinter dialog, not a console `input()` call), so a
console-attached build leaves a console window around for no reason, and closing that console
kills the whole process (Tk mainloop included) since it's the process's own window, not a
child. Output lands in `dist/main.exe`. Use `--add-data` for bundled resources (icons, etc.)
and `--hidden-import` if PyInstaller misses a dependency.

`requirements.txt` lists the runtime dependencies — `customtkinter` (the GUI's theming layer
over Tkinter) and `pytablericons` (GUI icons; pulls in Pillow and pygame) — plus dev/build
tooling (`pytest`, `pyinstaller`).

To manually test two peers on one machine, run `python main.py alice` and `python main.py bob`
in separate terminals; they'll discover each other over the loopback-reachable broadcast
address as long as Windows Firewall allows the UDP discovery port (37020) and the dynamically
chosen TCP chat port.

## Tech stack

- **Python 3.10+** (developed/tested on 3.13), targeting Windows.
- **Networking**: stdlib `socket` only — UDP broadcast for discovery, TCP for chat/file
  streams. No `asyncio`, no `zeroconf`; both are documented fallbacks in the design PDF if
  raw UDP broadcast proves unreliable on a given network (some LANs block it).
- **Message format**: JSON (stdlib `json`), newline-delimited for TCP framing — see
  "Deviations from the design doc".
- **GUI**: CustomTkinter (Fluent/Windows-11-styled theming layer over stdlib Tkinter), with
  icons from `pytablericons` rendered to images. Don't use emoji as UI icons: Tk 8.6 on
  Windows can't draw color emoji and renders them as near-invisible monochrome slivers.
  Both packages are listed in `requirements.txt`.
- **Storage**: SQLite via stdlib `sqlite3`, one DB file per peer (`<username>_chat_history.db`).
  No server-side or shared database — every peer stores its own history.
- **Testing**: `pytest`, via `tests/`.

## Architecture

Peer-to-peer over LAN — every running instance is simultaneously a client and a server. There
is no message broker; peers talk directly to each other over TCP once discovered. Discovery
happens via UDP broadcast. `main.py` is the composition root: it constructs one instance of
each module below and wires them together with plain callbacks — none of the other modules
import each other except `file_transfer.py`, which depends on `network.py`.

- **`protocol.py`** — the only place that defines the wire format: message type constants
  (`MSG_CHAT`, `MSG_PRESENCE`, `MSG_FILE`, `MSG_ACK`) and their dataclasses (`ChatMessage`,
  `PresenceUpdate`, `FileChunk`), plus `encode()`/`decode()` helpers. Construct/parse messages
  through this module rather than building JSON dicts ad hoc elsewhere.
- **`discovery.py`** (`Discovery`) — UDP broadcast peer discovery on port `37020`. Implements
  the DISCOVER → ANNOUNCE handshake: broadcast a `discover` packet to `255.255.255.255`,
  listening peers reply `announce` (name, port); the sender's IP is read off the UDP packet.
  Runs an announce loop, a listener loop, and a reap loop (drops peers silent for
  `PEER_TIMEOUT` seconds) as daemon threads. `discovery.peers: dict[str, PeerInfo]` is the
  live registry; `on_peer_update(name, info_or_None)` fires on join/expiry.
- **`network.py`** (`NetworkManager`) — owns all TCP socket I/O: accepting incoming
  connections, connecting out to discovered peers, and the send/receive loops. The first line
  sent on a new connection is a plaintext username handshake. Incoming messages are dispatched
  by `type` to callbacks registered via `register_handler()` — this module never interprets
  message contents, keeping it pure transport.
- **`gui.py`** (`ChatWindow`) — Tkinter, presentation only, no socket/DB code. Exposes
  `on_send_chat` / `on_send_file` / `on_peer_selected` callback slots that `main.py` fills in,
  and `display_message()` / `set_peers()` for pushing data in. Because Tk is single-threaded,
  anything called from a `network.py`/`discovery.py` background thread must go through
  `gui.schedule(delay_ms, fn)` (wraps `root.after`) rather than touching widgets directly —
  `main.py`'s handlers all do this.
- **`storage.py`** (`Storage`) — SQLite persistence (`messages`, `users` tables), one DB file
  per peer. `save_message()` on every send/receive; `get_history()` to load a chat.
- **`file_transfer.py`** (`send_file`, `FileReceiver`) — chunked file transfer on top of
  `network.py.send_message`. Files are read in 50KB chunks, base64-encoded into `type:"file"`
  messages with an `index`, terminated by an `eof:true` marker; `FileReceiver` buffers chunks
  by `(sender, filename)` and writes the reassembled file to `<username>_downloads/` once EOF
  arrives. Filenames are passed through `_safe_filename()` (strips any path component) before
  touching disk, so a malicious peer can't path-traverse out of the download directory.

Data flow: GUI → NetworkManager.send_message → LAN → peer's NetworkManager._recv_loop →
dispatch by `type` → registered handler (`main.py`) → Storage + `gui.schedule(...)`.

### Deviations from the design doc

The PDF's pseudocode has two bugs that the real implementation fixes — worth knowing so you
don't "fix" them back to the doc's version:

- **TCP message framing**: the doc's `_recv_loop` does one `sock.recv(4096)` per message,
  which breaks as soon as a message exceeds 4096 bytes or two messages arrive in the same
  TCP segment. The real `NetworkManager` frames messages as **newline-delimited JSON** and
  buffers partial reads, so `json.dumps(...)` output must never itself contain a literal
  newline (it won't, under standard `json.dumps`).
- **Discovery socket reuse**: the doc's `discover_peers()` binds a second socket to the same
  `DISCOVERY_PORT` already bound by the listener, which fails on Windows. `Discovery` uses an
  unbound ephemeral-port socket for outbound `discover` broadcasts instead, and reuses the
  bound listener socket to reply when it receives someone else's `discover`.

### Design decisions worth preserving

- **P2P, not client-server**: chosen specifically so the app works with no dedicated
  always-on server machine. Don't reintroduce a central relay/server as the primary
  architecture without revisiting this decision.
- **JSON over protobuf/MessagePack**: deliberate simplicity tradeoff at this scale (≤ a few
  hundred LAN peers). Reconsider only if message throughput/size actually becomes a problem.
- **Discovery is UDP broadcast to `255.255.255.255`**, with periodic re-announce/reap so stale
  peer entries expire. Some enterprise LANs disable broadcast/multicast — `zeroconf`-based
  mDNS discovery is the documented fallback, not yet implemented.
- **No encryption/auth yet**: if added, the doc recommends AES-256 (GCM/EAX) via
  `cryptography`/`PyCryptodome` for payload confidentiality, and scoping the Windows Firewall
  to only the discovery UDP port and the chosen chat TCP port. Filename sanitization for file
  transfer is already implemented (see `file_transfer._safe_filename`).
- **Username entry is GUI-only**: `main.py.prompt_username()` falls back to `gui.ask_username()`
  (a CustomTkinter dialog), never `input()`. This is what makes `--windowed` packaging possible
  at all — a console `input()` call would have nothing to read from in a windowed build. Don't
  reintroduce a console prompt here.
