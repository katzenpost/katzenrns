# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""Qt item models over the session. Each holds a plain list it rebuilds
from the session when told something changed; nothing is read from the
protocol client while painting. Every string a model hands a view has
been through the session's sanitizer."""

from __future__ import annotations

import time
from typing import List, Optional

from pigeonhole_protocols.katzenqt1 import engine as eng
from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from ..core import Session

WHO = Qt.ItemDataRole.UserRole + 1
WHAT = Qt.ItemDataRole.UserRole + 2
NOTICE = Qt.ItemDataRole.UserRole + 3
MARK = Qt.ItemDataRole.UserRole + 4
WHEN = Qt.ItemDataRole.UserRole + 5
MINE = Qt.ItemDataRole.UserRole + 6
KEY = Qt.ItemDataRole.UserRole + 7
STATE = Qt.ItemDataRole.UserRole + 8
CLAIM = Qt.ItemDataRole.UserRole + 9
DETAIL = Qt.ItemDataRole.UserRole + 10


def group_state(c: eng.Chat) -> str:
    """The group's standing, in task terms: what the user holds."""
    if c.group is None:
        if c.joining is not None and c.joining.code:
            return "not joined: waiting for the member you gave the code to"
        if c.joining is not None:
            return "not joined: minting a voucher"
        return "not joined"
    parts = ["joined"]
    if c.inducting is not None:
        parts.append("adding a member")
    if c.jobs:
        parts.append("%d to send" % len(c.jobs))
    return ", ".join(parts)


class GroupsModel(QAbstractListModel):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.s = session
        self.rows: List[eng.Chat] = []
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self.rows = self.s.client.chats()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        c = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return c.name
        if role == STATE:
            return group_state(c)
        if role == KEY:
            return c.id
        if role == Qt.ItemDataRole.ToolTipRole:
            return group_state(c)
        return None

    def chat_id(self, row: int) -> Optional[str]:
        return self.rows[row].id if 0 <= row < len(self.rows) else None

    def row_of(self, chat: str) -> int:
        for i, c in enumerate(self.rows):
            if c.id == chat:
                return i
        return -1


class LinesModel(QAbstractListModel):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.s = session
        self.chat: Optional[str] = None
        self.rows: list = []

    def set_chat(self, chat: Optional[str]) -> None:
        self.chat = chat
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self.rows = []
        if self.chat is not None:
            c = self.s.client.state.chat(self.chat)
            for line in self.s.client.lines(self.chat):
                who, what = self.s.line_text(self.chat, line)
                mine = c is not None and c.group is not None and line.sender == c.group.me
                mark = ""
                if mine:
                    mark = "…" if line.status == eng.PENDING else ("✓✓" if c.acknowledged(line) else "✓")
                when = time.strftime("%H:%M", time.localtime(line.time / 1000)) if line.time else ""
                self.rows.append((who, what, line.notice is not None, mark, when, mine))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        who, what, notice, mark, when, mine = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return what if notice else "%s: %s" % (who, what)
        if role == WHO:
            return who
        if role == WHAT:
            return what
        if role == NOTICE:
            return notice
        if role == MARK:
            return mark
        if role == WHEN:
            return when
        if role == MINE:
            return mine
        return None


class MembersModel(QAbstractListModel):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self.s = session
        self.chat: Optional[str] = None
        self.rows: list = []

    def set_chat(self, chat: Optional[str]) -> None:
        self.chat = chat
        self.refresh()

    def refresh(self) -> None:
        self.beginResetModel()
        self.rows = []
        if self.chat is not None:
            c = self.s.client.state.chat(self.chat)
            if c is not None and c.group is not None:
                self.rows.append({"key": c.group.me, "name": self.s.me, "petname": True, "claimed": None, "acked": None, "ambiguous": False, "mixed_script": False, "me": True})
            for m in self.s.members(self.chat):
                m["me"] = False
                self.rows.append(m)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        m = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            name = m["name"] if (m["petname"] or m["me"]) else "~" + m["name"]
            if m["ambiguous"] or m["mixed_script"]:
                name += " [%s]" % m["key"][:4].hex()
            return name + (" (you)" if m["me"] else "")
        if role == CLAIM:
            return not (m["petname"] or m["me"])
        if role == KEY:
            return m["key"]
        if role == DETAIL or role == Qt.ItemDataRole.ToolTipRole:
            if m["me"]:
                return "You. Everyone listed here can read what you send."
            bits = []
            bits.append("Can read everything said in this group.")
            if not m["petname"]:
                bits.append('"%s" is the name they chose; you have not named them.' % (m["claimed"] or m["key"][:4].hex()))
            if m["mixed_script"]:
                bits.append("Their name mixes alphabets, as look-alike names do.")
            if m["ambiguous"]:
                bits.append("Another member's name looks the same; the key fragment tells them apart.")
            bits.append("Has read your messages." if m["acked"] is not None else "Has not yet acknowledged anything you sent.")
            return " ".join(bits)
        return None

    def member(self, row: int) -> Optional[dict]:
        return self.rows[row] if 0 <= row < len(self.rows) else None
