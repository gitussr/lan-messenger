"""Modern Windows-11-style GUI for LAN Messenger, built with CustomTkinter.

Presentation only -- no socket or database code lives here, exactly like the
original ttk-based gui.py. The app layer (main.py) wires this window up to
NetworkManager/Storage/Discovery via the on_send_chat / on_send_file /
on_peer_selected callbacks, and pushes incoming data in through
display_message() / display_system() / set_peers() / load_history(). The
public surface main.py relies on:

    ChatWindow(username)
        .username                          -> str
        .current_peer                      -> Optional[str]
        .on_send_chat(peer_name, text)     -> callback set by app layer
        .on_send_file(peer_name, filepath) -> callback set by app layer
        .on_peer_selected(peer_name)       -> callback set by app layer
        .set_peers(names)                  -> replace the contact list
        .display_message(sender, text, timestamp=None) -> append a chat bubble
        .display_system(text)              -> append a system notice
        .load_history(rows)                -> replay (sender, text, ts) rows
        .run()                             -> start the Tk mainloop
        .schedule(delay_ms, callback)      -> run callback on the Tk thread

`peer_name` for on_send_chat/on_peer_selected may be `protocol.BROADCAST_PEER_ID`
when the user has the pinned "Broadcast to All" entry selected -- the app
layer is responsible for fanning that out to every discovered peer.

Tk (and by extension CustomTkinter, which is a themed layer on top of Tk) is
not thread-safe: network and discovery callbacks fire on background threads,
so any call into this window from those threads must go through schedule()
to run on the Tk main thread instead of touching widgets directly.

Requires the `customtkinter` package (pip install customtkinter) -- listed
in requirements.txt.
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

from protocol import BROADCAST_PEER_ID

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

# ---------------------------------------------------------------------------
# Visual system -- restrained Fluent/Win11 palette: neutral surfaces, hairline
# 1px borders on every card/control, a single accent color, and a modest
# corner radius (Win11 controls use ~4-8px, not the "pill" shapes of a mobile
# chat app). Spacing is expressed as named constants so blocks like the
# contact row keep identical padding on all four sides.
# ---------------------------------------------------------------------------

FONT = "Segoe UI"

RADIUS = 6
BORDER_W = 1

PAD_LG = 16
PAD_MD = 12
PAD_SM = 8

BUBBLE_RADIUS = 18

ACCENT = "#0F6CBD"          # Fluent "communication blue"
ACCENT_HOVER = "#115EA3"
ACCENT_PRESSED = "#0C4A80"
ACCENT_BORDER = "#0C4A80"

SENT_BUBBLE = ACCENT
SENT_TEXT = "#FFFFFF"
RECV_BUBBLE_L, RECV_BUBBLE_D = "#F3F3F3", "#2A2A2E"
RECV_TEXT_L, RECV_TEXT_D = "#1A1A1A", "#F2F2F5"

APP_BG_L, APP_BG_D = "#FFFFFF", "#181818"
SIDEBAR_L, SIDEBAR_D = "#F7F7F8", "#1F1F23"
CHAT_BG_L, CHAT_BG_D = "#FFFFFF", "#1B1B1D"
HEADER_L, HEADER_D = "#FBFBFC", "#202024"

BORDER_L, BORDER_D = "#E1E1E6", "#34343A"

SYSTEM_L, SYSTEM_D = "#6B6B70", "#9A9AA2"

SELECTED_TINT_L, SELECTED_TINT_D = "#E5F1FB", "#0F3554"
ROW_HOVER_L, ROW_HOVER_D = "#EDEDF0", "#2A2A2E"

ONLINE_DOT = "#0F7B0F"

AVATAR_PALETTE = [
    "#C42B1C", "#CA5010", "#986F0B", "#498205", "#038387",
    "#0078D4", "#8764B8", "#C239B3", "#005B70", "#767676",
]

BROADCAST_COLOR = "#8764B8"

EMOJI_SET = [
    "😀", "😂", "😍", "🙂", "😉", "😅", "😢", "😮", "😡", "👍",
    "👎", "🙏", "👏", "🎉", "🔥", "❤️", "✅", "❌", "🤔", "😴",
]


def _avatar_color(name: str) -> str:
    return AVATAR_PALETTE[hash(name) % len(AVATAR_PALETTE)]


def _initials(name: str) -> str:
    name = name.strip()
    if not name:
        return "?"
    parts = name.replace("_", " ").replace(".", " ").split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    return name[:2].upper()


class ChatWindow:
    def __init__(self, username: str):
        self.username = username
        self.current_peer: Optional[str] = None
        self.on_send_chat: Optional[Callable[[str, str], None]] = None
        self.on_send_file: Optional[Callable[[str, str], None]] = None
        self.on_peer_selected: Optional[Callable[[str], None]] = None

        self._all_peers: list[str] = []
        self._contact_rows: dict[str, "_ContactRow"] = {}
        self._broadcast_row: Optional["_ContactRow"] = None
        self._emoji_popup: Optional[ctk.CTkToplevel] = None

        self.root = ctk.CTk()
        self.root.title(f"LAN Messenger — {username}")
        self.root.geometry("1040x680")
        self.root.minsize(760, 520)
        self.root.configure(fg_color=(APP_BG_L, APP_BG_D))

        self._build_widgets()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        self.root.grid_columnconfigure(0, minsize=280)
        self.root.grid_columnconfigure(1, minsize=BORDER_W)
        self.root.grid_columnconfigure(2, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self._build_sidebar()

        ctk.CTkFrame(
            self.root, width=BORDER_W, corner_radius=0,
            fg_color=(BORDER_L, BORDER_D),
        ).grid(row=0, column=1, sticky="ns")

        self._build_chat_pane()

    def _build_sidebar(self) -> None:
        sidebar = ctk.CTkFrame(
            self.root, corner_radius=0, fg_color=(SIDEBAR_L, SIDEBAR_D),
        )
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(5, weight=1)

        # -- "Me" header -------------------------------------------------
        me_row = ctk.CTkFrame(sidebar, fg_color="transparent")
        me_row.grid(row=0, column=0, sticky="ew", padx=PAD_LG, pady=PAD_LG)
        me_row.grid_columnconfigure(1, weight=1)

        self._avatar(me_row, self.username, size=40).grid(row=0, column=0, rowspan=2)
        ctk.CTkLabel(
            me_row, text=self.username, anchor="w",
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
        ).grid(row=0, column=1, sticky="ew", padx=(PAD_SM + 2, 0))
        ctk.CTkLabel(
            me_row, text="Online on this LAN", anchor="w",
            font=ctk.CTkFont(family=FONT, size=11),
            text_color=(SYSTEM_L, SYSTEM_D),
        ).grid(row=1, column=1, sticky="ew", padx=(PAD_SM + 2, 0))

        ctk.CTkFrame(
            sidebar, height=BORDER_W, corner_radius=0,
            fg_color=(BORDER_L, BORDER_D),
        ).grid(row=1, column=0, sticky="ew")

        # -- Appearance + search ------------------------------------------
        controls = ctk.CTkFrame(sidebar, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=PAD_LG, pady=(PAD_MD, PAD_SM))
        controls.grid_columnconfigure(0, weight=1)

        self.appearance_switch = ctk.CTkSegmentedButton(
            controls, values=["Light", "System", "Dark"],
            command=self._on_appearance_change,
            corner_radius=RADIUS, font=ctk.CTkFont(family=FONT, size=11),
        )
        self.appearance_switch.set("System")
        self.appearance_switch.grid(row=0, column=0, sticky="ew")

        self.search_entry = ctk.CTkEntry(
            controls, placeholder_text="Search contacts", corner_radius=RADIUS,
            border_width=BORDER_W, border_color=(BORDER_L, BORDER_D),
            font=ctk.CTkFont(family=FONT, size=12),
        )
        self.search_entry.grid(row=1, column=0, sticky="ew", pady=(PAD_SM, 0))
        self.search_entry.bind("<KeyRelease>", lambda _e: self._filter_contacts())

        # -- Pinned "Broadcast to All" entry -------------------------------
        broadcast_holder = ctk.CTkFrame(sidebar, fg_color="transparent")
        broadcast_holder.grid(row=3, column=0, sticky="ew", padx=PAD_SM, pady=(PAD_MD, 0))
        broadcast_holder.grid_columnconfigure(0, weight=1)
        self._broadcast_row = _ContactRow(
            broadcast_holder, BROADCAST_PEER_ID,
            selected=False, on_click=self._select_peer,
            display_name="Broadcast to All", subtitle="Message everyone at once",
            avatar_text="📢", avatar_color=BROADCAST_COLOR,
        )
        self._broadcast_row.frame.grid(row=0, column=0, sticky="ew")

        # -- Contact list --------------------------------------------------
        ctk.CTkLabel(
            sidebar, text="CONTACTS", anchor="w",
            font=ctk.CTkFont(family=FONT, size=11, weight="bold"),
            text_color=(SYSTEM_L, SYSTEM_D),
        ).grid(row=4, column=0, sticky="ew", padx=PAD_LG + 2, pady=(PAD_LG, PAD_SM))

        self.contacts_frame = ctk.CTkScrollableFrame(
            sidebar, fg_color="transparent",
        )
        self.contacts_frame.grid(row=5, column=0, sticky="nsew", padx=PAD_SM, pady=0)
        self.contacts_frame.grid_columnconfigure(0, weight=1)

        self.empty_label = ctk.CTkLabel(
            self.contacts_frame,
            text="No peers found yet.\nWaiting for LAN discovery…",
            justify="center", text_color=(SYSTEM_L, SYSTEM_D),
            font=ctk.CTkFont(family=FONT, size=12),
        )
        self.empty_label.grid(row=0, column=0, pady=30)

        # -- Footer / attribution -------------------------------------------
        ctk.CTkFrame(
            sidebar, height=BORDER_W, corner_radius=0,
            fg_color=(BORDER_L, BORDER_D),
        ).grid(row=6, column=0, sticky="sew")

        ctk.CTkLabel(
            sidebar, text="Developed by Chiranjit Karmakar",
            font=ctk.CTkFont(family=FONT, size=10),
            text_color=(SYSTEM_L, SYSTEM_D),
        ).grid(row=7, column=0, pady=PAD_MD)

    def _build_chat_pane(self) -> None:
        chat_pane = ctk.CTkFrame(self.root, corner_radius=0, fg_color=(CHAT_BG_L, CHAT_BG_D))
        chat_pane.grid(row=0, column=2, sticky="nsew")
        chat_pane.grid_columnconfigure(0, weight=1)
        chat_pane.grid_rowconfigure(2, weight=1)

        # -- Header with selected peer ---------------------------------
        header = ctk.CTkFrame(chat_pane, height=64, corner_radius=0, fg_color=(HEADER_L, HEADER_D))
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)

        self.peer_avatar_holder = ctk.CTkFrame(header, fg_color="transparent")
        self.peer_avatar_holder.grid(row=0, column=0, padx=(PAD_LG, 0), pady=PAD_MD)
        self._current_avatar = self._avatar(self.peer_avatar_holder, "?", size=36)
        self._current_avatar.pack()

        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.grid(row=0, column=1, sticky="w", padx=PAD_SM + 2)
        self.peer_name_label = ctk.CTkLabel(
            title_box, text="Select a contact", anchor="w",
            font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
        )
        self.peer_name_label.pack(anchor="w")
        self.peer_status_label = ctk.CTkLabel(
            title_box, text="", anchor="w", font=ctk.CTkFont(family=FONT, size=11),
            text_color=(SYSTEM_L, SYSTEM_D),
        )
        self.peer_status_label.pack(anchor="w")

        ctk.CTkFrame(
            chat_pane, height=BORDER_W, corner_radius=0,
            fg_color=(BORDER_L, BORDER_D),
        ).grid(row=1, column=0, sticky="ew")

        # -- Scrollable message list ------------------------------------
        self.messages_frame = ctk.CTkScrollableFrame(
            chat_pane, fg_color="transparent",
        )
        self.messages_frame.grid(row=2, column=0, sticky="nsew", padx=PAD_SM, pady=PAD_SM)
        self.messages_frame.grid_columnconfigure(0, weight=1)
        self._message_row = 0

        ctk.CTkFrame(
            chat_pane, height=BORDER_W, corner_radius=0,
            fg_color=(BORDER_L, BORDER_D),
        ).grid(row=3, column=0, sticky="ew")

        # -- Input row ----------------------------------------------------
        input_bar = ctk.CTkFrame(chat_pane, fg_color="transparent")
        input_bar.grid(row=4, column=0, sticky="ew", padx=PAD_MD, pady=PAD_MD)
        input_bar.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            input_bar, text="📎", width=38, height=38, corner_radius=RADIUS,
            fg_color="transparent", hover_color=(ROW_HOVER_L, ROW_HOVER_D),
            border_width=BORDER_W, border_color=(BORDER_L, BORDER_D),
            text_color=("black", "white"), command=self._file_clicked,
        ).grid(row=0, column=0, padx=(0, PAD_SM))

        self.entry = ctk.CTkEntry(
            input_bar, placeholder_text="Type a message…",
            corner_radius=RADIUS, height=38,
            border_width=BORDER_W, border_color=(BORDER_L, BORDER_D),
            font=ctk.CTkFont(family=FONT, size=12),
        )
        self.entry.grid(row=0, column=1, sticky="ew")
        self.entry.bind("<Return>", lambda _e: self._send_clicked())

        ctk.CTkButton(
            input_bar, text="🙂", width=38, height=38, corner_radius=RADIUS,
            fg_color="transparent", hover_color=(ROW_HOVER_L, ROW_HOVER_D),
            border_width=BORDER_W, border_color=(BORDER_L, BORDER_D),
            text_color=("black", "white"), command=self._toggle_emoji_picker,
        ).grid(row=0, column=2, padx=PAD_SM)

        ctk.CTkButton(
            input_bar, text="Send", width=80, height=38, corner_radius=RADIUS,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            border_width=BORDER_W, border_color=ACCENT_BORDER,
            font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
            command=self._send_clicked,
        ).grid(row=0, column=3)

    # ------------------------------------------------------------------
    # Small building blocks
    # ------------------------------------------------------------------
    def _avatar(self, parent, name: str, size: int = 36, text: Optional[str] = None,
                color: Optional[str] = None) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            parent, text=text if text is not None else _initials(name),
            width=size, height=size,
            corner_radius=size // 2, fg_color=color or _avatar_color(name),
            text_color="white",
            font=ctk.CTkFont(family=FONT, size=max(10, size // 3), weight="bold"),
        )

    def _on_appearance_change(self, value: str) -> None:
        ctk.set_appearance_mode(value.lower())

    # ------------------------------------------------------------------
    # Contacts
    # ------------------------------------------------------------------
    def _filter_contacts(self) -> None:
        query = self.search_entry.get().strip().lower()
        visible = [p for p in self._all_peers if query in p.lower()]
        self._render_contacts(visible)

    def _render_contacts(self, names: list[str]) -> None:
        for row in self._contact_rows.values():
            row.frame.destroy()
        self._contact_rows.clear()

        if not names:
            self.empty_label.grid(row=0, column=0, pady=30)
            return
        self.empty_label.grid_forget()

        for i, name in enumerate(sorted(names)):
            row = _ContactRow(
                self.contacts_frame, name,
                selected=(name == self.current_peer),
                on_click=self._select_peer,
            )
            row.frame.grid(row=i, column=0, sticky="ew", pady=(0, PAD_SM))
            self._contact_rows[name] = row

    def set_peers(self, names: list[str]) -> None:
        self._all_peers = list(names)
        if self.current_peer not in names and self.current_peer != BROADCAST_PEER_ID:
            self.current_peer = None
        self._filter_contacts()
        if self.current_peer == BROADCAST_PEER_ID:
            self._update_broadcast_subtitle()

    def _update_broadcast_subtitle(self) -> None:
        count = len(self._all_peers)
        noun = "peer" if count == 1 else "peers"
        self.peer_status_label.configure(text=f"Delivers to {count} online {noun}")

    def _select_peer(self, name: str) -> None:
        self.current_peer = name
        for peer_name, row in self._contact_rows.items():
            row.set_selected(peer_name == name)
        if self._broadcast_row is not None:
            self._broadcast_row.set_selected(name == BROADCAST_PEER_ID)

        for widget in self.peer_avatar_holder.winfo_children():
            widget.destroy()

        if name == BROADCAST_PEER_ID:
            self._current_avatar = self._avatar(
                self.peer_avatar_holder, name, size=36,
                text="📢", color=BROADCAST_COLOR,
            )
            self._current_avatar.pack()
            self.peer_name_label.configure(text="Broadcast to All")
            self._update_broadcast_subtitle()
        else:
            self._current_avatar = self._avatar(self.peer_avatar_holder, name, size=36)
            self._current_avatar.pack()
            self.peer_name_label.configure(text=name)
            self.peer_status_label.configure(text="Online · LAN")

        if self.on_peer_selected:
            self.on_peer_selected(name)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------
    def _send_clicked(self) -> None:
        text = self.entry.get().strip()
        if not text or not self.current_peer:
            return
        self.entry.delete(0, "end")
        self.display_message(self.username, text)
        if self.on_send_chat:
            self.on_send_chat(self.current_peer, text)

    def _file_clicked(self) -> None:
        if not self.current_peer or self.current_peer == BROADCAST_PEER_ID:
            messagebox.showinfo("LAN Messenger", "Select an individual contact to send a file.")
            return
        path = filedialog.askopenfilename()
        if path and self.on_send_file:
            self.on_send_file(self.current_peer, path)

    def _toggle_emoji_picker(self) -> None:
        if self._emoji_popup is not None and self._emoji_popup.winfo_exists():
            self._emoji_popup.destroy()
            self._emoji_popup = None
            return

        popup = ctk.CTkToplevel(self.root)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        x = self.root.winfo_rootx() + self.root.winfo_width() - 260
        y = self.root.winfo_rooty() + self.root.winfo_height() - 140
        popup.geometry(f"240x160+{x}+{y}")
        frame = ctk.CTkFrame(
            popup, corner_radius=RADIUS,
            border_width=BORDER_W, border_color=(BORDER_L, BORDER_D),
        )
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        for i, emoji in enumerate(EMOJI_SET):
            ctk.CTkButton(
                frame, text=emoji, width=32, height=32, corner_radius=RADIUS,
                fg_color="transparent", hover_color=(ROW_HOVER_L, ROW_HOVER_D),
                command=lambda e=emoji: self._insert_emoji(e),
            ).grid(row=i // 5, column=i % 5, padx=2, pady=2)
        self._emoji_popup = popup

    def _insert_emoji(self, emoji: str) -> None:
        self.entry.insert("insert", emoji)
        self.entry.focus_set()

    # ------------------------------------------------------------------
    # Messages
    # ------------------------------------------------------------------
    def display_message(self, sender: str, text: str, timestamp: Optional[float] = None) -> None:
        mine = sender == self.username
        timestamp_str = time.strftime(
            "%H:%M", time.localtime(timestamp) if timestamp is not None else time.localtime()
        )

        row = ctk.CTkFrame(self.messages_frame, fg_color="transparent")
        row.grid(row=self._message_row, column=0, sticky="ew", pady=5)
        row.grid_columnconfigure(0, weight=1)

        bubble = ctk.CTkFrame(
            row, corner_radius=BUBBLE_RADIUS,
            fg_color=SENT_BUBBLE if mine else (RECV_BUBBLE_L, RECV_BUBBLE_D),
            border_width=BORDER_W,
            border_color=ACCENT_BORDER if mine else (BORDER_L, BORDER_D),
        )
        bubble.grid(row=0, column=0, sticky="e" if mine else "w", padx=12)

        if not mine:
            ctk.CTkLabel(
                bubble, text=sender, font=ctk.CTkFont(family=FONT, size=10, weight="bold"),
                text_color=ACCENT,
            ).pack(anchor="w", padx=16, pady=(10, 0))

        ctk.CTkLabel(
            bubble, text=text, wraplength=380, justify="left",
            font=ctk.CTkFont(family=FONT, size=12),
            text_color=SENT_TEXT if mine else (RECV_TEXT_L, RECV_TEXT_D),
        ).pack(anchor="w", padx=16, pady=(10 if mine else 6, 2))

        ctk.CTkLabel(
            bubble, text=timestamp_str, font=ctk.CTkFont(family=FONT, size=9),
            text_color=("#E5EEFF" if mine else SYSTEM_L, "#DCE7FF" if mine else SYSTEM_D),
        ).pack(anchor="e" if mine else "w", padx=16, pady=(0, 8))

        self._message_row += 1
        self._scroll_to_bottom()

    def display_system(self, text: str) -> None:
        row = ctk.CTkFrame(self.messages_frame, fg_color="transparent")
        row.grid(row=self._message_row, column=0, sticky="ew", pady=6)
        row.grid_columnconfigure(0, weight=1)

        pill = ctk.CTkLabel(
            row, text=text, corner_radius=RADIUS,
            fg_color=(RECV_BUBBLE_L, RECV_BUBBLE_D),
            border_width=BORDER_W, border_color=(BORDER_L, BORDER_D),
            text_color=(SYSTEM_L, SYSTEM_D),
            font=ctk.CTkFont(family=FONT, size=11), padx=10, pady=4,
        )
        pill.grid(row=0, column=0)

        self._message_row += 1
        self._scroll_to_bottom()

    def load_history(self, rows: list[tuple[str, str, float]]) -> None:
        """Replay persisted (sender, text, timestamp) rows, oldest first."""
        if not rows:
            return
        for sender, text, timestamp in rows:
            self.display_message(sender, text, timestamp=timestamp)
        self.display_system(f"— {len(rows)} earlier message(s) loaded —")

    def _scroll_to_bottom(self) -> None:
        self.messages_frame._parent_canvas.update_idletasks()
        self.messages_frame._parent_canvas.yview_moveto(1.0)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def run(self) -> None:
        self.root.mainloop()

    def schedule(self, delay_ms: int, callback: Callable[[], None]) -> None:
        self.root.after(delay_ms, callback)


class _ContactRow:
    """A single clickable contact entry in the sidebar list.

    Padding around the avatar/name/status content is identical (PAD_MD) on
    all four sides, and selection is shown as a tinted background plus an
    accent-colored 1px border rather than a solid color fill -- closer to
    how Windows 11 apps (Settings, Teams, Outlook) highlight a selected
    list item than a loud full-bleed accent block. (An earlier version
    added a 4px accent stripe as a child widget flush against the left
    edge; CustomTkinter clipped the frame's own left border underneath it,
    so every unselected row was missing its left hairline. Simpler card,
    no stripe, no clipping.)
    """

    def __init__(
        self, parent, key: str, selected: bool, on_click: Callable[[str], None],
        display_name: Optional[str] = None, subtitle: str = "● Online",
        avatar_text: Optional[str] = None, avatar_color: Optional[str] = None,
    ):
        self.key = key
        self._on_click = on_click
        self._selected = selected
        name = display_name if display_name is not None else key

        self.frame = ctk.CTkFrame(
            parent, corner_radius=RADIUS,
            border_width=BORDER_W,
            border_color=ACCENT if selected else (BORDER_L, BORDER_D),
            fg_color=(SELECTED_TINT_L, SELECTED_TINT_D) if selected else "transparent",
        )
        self.frame.grid_columnconfigure(0, weight=1)

        content = ctk.CTkFrame(self.frame, fg_color="transparent")
        content.grid(row=0, column=0, sticky="nsew", padx=PAD_MD, pady=PAD_MD)
        content.grid_columnconfigure(1, weight=1)

        avatar = ctk.CTkLabel(
            content, text=avatar_text if avatar_text is not None else _initials(name),
            width=34, height=34, corner_radius=17,
            fg_color=avatar_color or _avatar_color(key),
            text_color="white", font=ctk.CTkFont(family=FONT, size=12, weight="bold"),
        )
        avatar.grid(row=0, column=0, rowspan=2, padx=(0, PAD_SM + 2))

        self._default_name_color = ctk.ThemeManager.theme["CTkLabel"]["text_color"]
        self._name_label = ctk.CTkLabel(
            content, text=name, anchor="w",
            font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
            text_color=self._default_name_color,
        )
        self._name_label.grid(row=0, column=1, sticky="ew")

        self._status_label = ctk.CTkLabel(
            content, text=subtitle, anchor="w",
            font=ctk.CTkFont(family=FONT, size=10),
            text_color=(SYSTEM_L, SYSTEM_D) if avatar_text else ONLINE_DOT,
        )
        self._status_label.grid(row=1, column=1, sticky="ew")

        for widget in (self.frame, content, avatar, self._name_label, self._status_label):
            widget.bind("<Button-1>", lambda _e: self._on_click(self.key))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.frame.configure(
            fg_color=(SELECTED_TINT_L, SELECTED_TINT_D) if selected else "transparent",
            border_color=ACCENT if selected else (BORDER_L, BORDER_D),
        )


if __name__ == "__main__":
    # Standalone preview: run `python gui.py` to see the window with fake
    # peers and echoed messages, without wiring up any real networking.
    window = ChatWindow(username="alice")

    def fake_send_chat(peer_name: str, text: str) -> None:
        if peer_name == BROADCAST_PEER_ID:
            window.schedule(400, lambda: window.display_system(f"(fake) Broadcast delivered: {text}"))
            return
        window.schedule(400, lambda: window.display_message(peer_name, f"(echo) {text}"))

    def fake_send_file(peer_name: str, filepath: str) -> None:
        window.display_system(f"Pretending to send {filepath} to {peer_name}")

    window.on_send_chat = fake_send_chat
    window.on_send_file = fake_send_file
    window.set_peers(["bob", "carol", "dave_from_accounting"])
    window.load_history([
        ("bob", "hey, you around?", time.time() - 3600),
        ("alice", "yep, what's up", time.time() - 3500),
    ])
    window.display_system("Discovery started — found 3 peers on the LAN")
    window.run()
