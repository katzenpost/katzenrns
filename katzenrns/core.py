# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""A session: the protocol client over a backend, with what both the shell
and the desktop client need and neither Qt nor a terminal: where state
lives, the one sanitizer every remote string passes through, petnames,
and the voucher code format."""

from __future__ import annotations

import base64
import os
import sqlite3
import unicodedata
from typing import Callable, Dict, List, Optional, Tuple

from pigeonhole_protocols.katzenqt1 import engine as eng
from pigeonhole_protocols.katzenqt1.client import Client
from pigeonhole_protocols.transport.base import Backend

MAX_NAME = 30
MAX_TEXT = 16 * 1024


def default_state_dir() -> str:
    base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    return os.path.join(base, "katzenrns")


# ---- the trusted path: one sanitizer ----

_BIDI = {0x061C, 0x200E, 0x200F, 0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069}


def display_text(s: str, limit: int = MAX_TEXT) -> str:
    """A remote string as the client shows it: control characters and
    bidi overrides removed, length capped, the cut marked. Every remote
    string, name or message, goes through here before it reaches a widget
    or a terminal."""
    out = []
    for ch in s:
        o = ord(ch)
        if o < 0x20 and ch not in "\n\t":
            continue
        if 0x7F <= o <= 0x9F or o in _BIDI:
            continue
        if unicodedata.category(ch) == "Cf":
            continue
        out.append(ch)
    t = "".join(out)
    if len(t) > limit:
        t = t[:limit] + " [cut]"
    return t


def display_name(s: str) -> str:
    """A name as shown: one line, no controls, at most MAX_NAME characters,
    never empty."""
    t = display_text(s.replace("\n", " ").replace("\t", " "), MAX_NAME + 1)
    t = " ".join(t.split())[:MAX_NAME]
    return t or "unnamed"


def skeleton(name: str) -> str:
    """A crude confusable skeleton: NFKC, case folded, a few look-alikes
    merged. Two names with one skeleton are shown apart."""
    t = unicodedata.normalize("NFKC", name).casefold()
    for a, b in (("0", "o"), ("1", "l"), ("i", "l"), ("|", "l"), ("5", "s"), ("а", "a"), ("е", "e"), ("о", "o"), ("р", "p"), ("с", "c"), ("х", "x")):
        t = t.replace(a, b)
    return "".join(ch for ch in t if not ch.isspace())


def mixed_script(name: str) -> bool:
    scripts = set()
    for ch in name:
        if not ch.isalpha():
            continue
        n = unicodedata.name(ch, "")
        scripts.add(n.split(" ")[0] if n else "?")
    return len(scripts) > 1


def fingerprint(key: bytes) -> str:
    return key[:4].hex()


# ---- vouchers ----


def parse_voucher(text: str) -> Optional[bytes]:
    """The 32 bytes a voucher code names, or None. Whitespace around and
    inside the pasted text is ignored."""
    t = "".join(text.split())
    try:
        v = base64.b64decode(t, validate=True)
    except Exception:
        return None
    return v if len(v) == 32 else None


# ---- the session ----


class Petnames:
    """Names the user assigned to members, by key, kept beside the protocol
    state. A member's claimed name is a claim; a petname is the user's."""

    def __init__(self, state_dir: str):
        self.db = sqlite3.connect(os.path.join(state_dir, "katzenrns.sqlite"), check_same_thread=False, isolation_level=None)
        self.db.execute("CREATE TABLE IF NOT EXISTS petnames (key BLOB PRIMARY KEY, name TEXT NOT NULL)")

    def get(self, key: bytes) -> Optional[str]:
        row = self.db.execute("SELECT name FROM petnames WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set(self, key: bytes, name: str) -> None:
        self.db.execute("INSERT OR REPLACE INTO petnames VALUES (?, ?)", (key, name))

    def close(self) -> None:
        self.db.close()


class Session:
    """The client, open on a state directory, over a backend."""

    def __init__(self, state_dir: str, name: str, backend: Backend, on_change: Optional[Callable[[eng.Changes], None]] = None, epoch_poll_s: float = 60.0, client: Optional[Client] = None, wire_version: int = 5):
        """``client`` replaces the threaded client, for tests in virtual time."""
        os.makedirs(state_dir, exist_ok=True)
        self.state_dir = state_dir
        self.backend = backend
        self.client = client or Client(state_dir, name, backend, epoch_poll_s=epoch_poll_s, on_change=on_change, wire_version=wire_version)
        if client is not None and on_change is not None:
            self.client.on_change = on_change
        self.petnames = Petnames(state_dir)

    @property
    def me(self) -> str:
        return self.client.state.me

    def start(self) -> None:
        self.client.start()

    def close(self) -> None:
        self.client.close()
        self.petnames.close()
        close = getattr(self.backend, "close", None)
        if close:
            close()

    # ---- names ----

    def name_of(self, chat: str, key: bytes, mark_claim: bool = True) -> str:
        """Who a key is, as shown: the user's petname, else the name the
        member claimed, marked as a claim with a leading ~ unless
        ``mark_claim`` is off; our own name for ourselves."""
        c = self.client.state.chat(chat)
        if c is not None and c.group is not None and c.group.me == key:
            return self.me
        pet = self.petnames.get(key)
        if pet:
            return pet
        claimed = c.names.get(key) if c is not None else None
        shown = display_name(claimed) if claimed else fingerprint(key)
        return ("~" + shown) if mark_claim else shown

    def members(self, chat: str) -> List[Dict]:
        """Each member read in a group: key, shown name, whether the name is
        a petname or a claim, how far they acknowledged our stream (the
        Idx64 of the last box of ours they read, or None), and a key
        fragment when two shown names collide."""
        c = self.client.state.chat(chat)
        if c is None or c.group is None:
            return []
        rows = []
        for key in c.group.readers:
            pet = self.petnames.get(key)
            claimed = c.names.get(key)
            rows.append({
                "key": key,
                "name": pet or display_name(claimed or "") if (pet or claimed) else fingerprint(key),
                "petname": bool(pet),
                "claimed": display_name(claimed) if claimed else None,
                "acked": c.group.ledger.acked_by.get(key),
                "mixed_script": mixed_script(claimed or ""),
            })
        seen: Dict[str, int] = {}
        for r in rows:
            seen[skeleton(r["name"])] = seen.get(skeleton(r["name"]), 0) + 1
        for r in rows:
            r["ambiguous"] = seen[skeleton(r["name"])] > 1
        return rows

    # ---- lines ----

    def line_text(self, chat: str, line: eng.Line, mark_claim: bool = True) -> Tuple[str, str]:
        """(who, what) for a line, sanitized; who is "" for a notice."""
        if line.notice is not None:
            return "", eng.plain(line.notice)
        return self.name_of(chat, line.sender, mark_claim), display_text(line.text)

    def voucher_code(self, chat: str) -> Optional[str]:
        c = self.client.state.chat(chat)
        return c.joining.code if c is not None and c.joining is not None and c.joining.code else None
