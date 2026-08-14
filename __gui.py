"""Tkinter GUI for LAN Messenger.

Presentation only -- no socket or database code lives here. The app layer
(main.py) wires this window up to NetworkManager/Storage/Discovery via the
on_send_chat / on_send_file / on_peer_selected callbacks, and pushes incoming
data in through display_message()/set_peers().

Tk is not thread-safe: network and discovery callbacks fire on background
threads, so any call into this window from those threads must go through
schedule() to run on the Tk main thread instead of touching widgets directly.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional


class ChatWindow:
    def __init__(self, username: str):
        self.username = username
        self.current_peer: Optional[str] = None

        self.on_send_chat: Optional[Callable[[str, str], None]] = None
        self.on_send_file: Optional[Callable[[str, str], None]] = None
        self.on_peer_selected: Optional[Callable[[str], None]] = None

        self.root = tk.Tk()
        self.root.title(f"LAN Messenger — {username}")
        self.root.geometry("640x420")

        self._build_widgets()

    def _build_widgets(self) -> None:
        paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        contacts_frame = ttk.Frame(paned, width=160)
        self.contacts_list = tk.Listbox(contacts_frame)
        self.contacts_list.pack(fill=tk.BOTH, expand=True)
        self.contacts_list.bind("<<ListboxSelect>>", self._on_contact_selected)
        paned.add(contacts_frame, weight=1)

        chat_frame = ttk.Frame(paned)
        self.chat_text = tk.Text(chat_frame, state=tk.DISABLED, wrap=tk.WORD)
        self.chat_text.pack(fill=tk.BOTH, expand=True)

        input_row = ttk.Frame(chat_frame)
        input_row.pack(fill=tk.X)
        self.entry = ttk.Entry(input_row)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.entry.bind("<Return>", lambda _e: self._send_clicked())
        ttk.Button(input_row, text="Send", command=self._send_clicked).pack(side=tk.LEFT)
        ttk.Button(input_row, text="File...", command=self._file_clicked).pack(side=tk.LEFT)
        paned.add(chat_frame, weight=3)

    def _on_contact_selected(self, _event) -> None:
        selection = self.contacts_list.curselection()
        if not selection:
            return
        self.current_peer = self.contacts_list.get(selection[0])
        if self.on_peer_selected:
            self.on_peer_selected(self.current_peer)

    def _send_clicked(self) -> None:
        text = self.entry.get().strip()
        if not text or not self.current_peer:
            return
        self.entry.delete(0, tk.END)
        self.display_message(self.username, text)
        if self.on_send_chat:
            self.on_send_chat(self.current_peer, text)

    def _file_clicked(self) -> None:
        if not self.current_peer:
            messagebox.showinfo("LAN Messenger", "Select a contact first.")
            return
        path = filedialog.askopenfilename()
        if path and self.on_send_file:
            self.on_send_file(self.current_peer, path)

    def set_peers(self, names: list[str]) -> None:
        selected = self.current_peer
        self.contacts_list.delete(0, tk.END)
        for name in sorted(names):
            self.contacts_list.insert(tk.END, name)
        if selected in names:
            self.contacts_list.selection_set(sorted(names).index(selected))

    def display_message(self, sender: str, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.chat_text.configure(state=tk.NORMAL)
        self.chat_text.insert(tk.END, f"[{timestamp}] {sender}: {text}\n")
        self.chat_text.see(tk.END)
        self.chat_text.configure(state=tk.DISABLED)

    def display_system(self, text: str) -> None:
        self.display_message("*", text)

    def run(self) -> None:
        self.root.mainloop()

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        self.root.after(delay_ms, callback)
