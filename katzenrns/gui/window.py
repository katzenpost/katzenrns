# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The one window: groups on the left, the conversation in the middle with
the composer under it, members on the right. Notices are drawn in a style
and place a sender cannot produce; sender names sit in a column a message
cannot write into; every remote string is plain text that has been through
the session's sanitizer. Nothing a remote event does opens a dialog."""

from __future__ import annotations

import uuid
from typing import Optional

from pigeonhole_protocols.katzenqt1 import engine as eng
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFontMetrics, QPainter, QPalette, QTextDocument, QTextOption
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ..core import Session
from . import models
from .dialogs import AddMemberDialog, Clipboard, GroupNameDialog, StopReadingDialog, VoucherDialog, peek_voucher, plain_label

SENDER_COLUMN = 110
PAD = 6


class LineDelegate(QStyledItemDelegate):
    """A message: time, sender in its own column, text wrapped. A notice:
    one line in the palette's placeholder colour with a bar on the left,
    a shape no message can take."""

    def _doc(self, text: str, width: int, font) -> QTextDocument:
        d = QTextDocument()
        d.setDefaultFont(font)
        opt = QTextOption()
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        d.setDefaultTextOption(opt)
        d.setPlainText(text)
        d.setTextWidth(max(50, width))
        return d

    def sizeHint(self, option, index) -> QSize:
        fm = QFontMetrics(option.font)
        if index.data(models.NOTICE):
            return QSize(option.rect.width(), fm.height() + 2 * PAD)
        width = option.rect.width() - SENDER_COLUMN - 3 * PAD - 44
        d = self._doc(index.data(models.WHAT), width, option.font)
        return QSize(option.rect.width(), int(d.size().height()) + 2 * PAD)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        r = option.rect
        pal = option.palette
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(r, pal.color(QPalette.ColorRole.Highlight).lighter(170))
        fm = QFontMetrics(option.font)
        if index.data(models.NOTICE):
            painter.fillRect(QRect(r.left() + PAD, r.top() + PAD, 3, r.height() - 2 * PAD), pal.color(QPalette.ColorRole.Mid))
            painter.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            f = option.font
            f.setItalic(True)
            painter.setFont(f)
            painter.drawText(QRect(r.left() + 3 * PAD, r.top() + PAD, r.width() - 4 * PAD, fm.height()), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, index.data(models.WHAT))
            painter.restore()
            return
        x = r.left() + PAD
        painter.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
        painter.drawText(QRect(x, r.top() + PAD, 40, fm.height()), Qt.AlignmentFlag.AlignLeft, index.data(models.WHEN) or "")
        x += 44
        f = option.font
        f.setBold(True)
        painter.setFont(f)
        mine = index.data(models.MINE)
        painter.setPen(pal.color(QPalette.ColorRole.Link) if mine else pal.color(QPalette.ColorRole.Text))
        who = fm.elidedText(index.data(models.WHO), Qt.TextElideMode.ElideRight, SENDER_COLUMN)
        painter.drawText(QRect(x, r.top() + PAD, SENDER_COLUMN, fm.height()), Qt.AlignmentFlag.AlignRight, who)
        x += SENDER_COLUMN + PAD
        painter.setFont(option.font)
        painter.setPen(pal.color(QPalette.ColorRole.Text))
        width = r.right() - x - PAD - (30 if mine else 0)
        d = self._doc(index.data(models.WHAT), width, option.font)
        painter.translate(x, r.top() + PAD)
        d.drawContents(painter)
        painter.translate(-x, -(r.top() + PAD))
        if mine:
            painter.setPen(pal.color(QPalette.ColorRole.PlaceholderText))
            painter.drawText(QRect(r.right() - 30, r.top() + PAD, 26, fm.height()), Qt.AlignmentFlag.AlignRight, index.data(models.MARK) or "")
        painter.restore()


class MainWindow(QMainWindow):
    """Built before the session exists: ``attach`` wires one in once the
    mesh is reached."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("katzenrns")
        self.resize(960, 600)
        self.s: Optional[Session] = None
        self.clipboard = Clipboard()
        self.current: Optional[str] = None

        self.groups = QListView()
        self.groups.setMinimumWidth(160)
        self.lines = QListView()
        self.lines.setItemDelegate(LineDelegate(self.lines))
        self.lines.setWordWrap(True)
        self.lines.setResizeMode(QListView.ResizeMode.Adjust)
        self.lines.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.members = QListView()
        self.members.setMinimumWidth(160)
        self.members.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.members.customContextMenuRequested.connect(self._member_menu)

        self.header = plain_label("")
        self.header.setStyleSheet("QLabel { padding: 4px; }")
        self.composer = QLineEdit()
        self.composer.setPlaceholderText("Say something")
        self.composer.returnPressed.connect(self.send)
        self.send_button = QPushButton("Send")
        self.send_button.clicked.connect(self.send)

        centre = QWidget()
        cl = QVBoxLayout(centre)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.addWidget(self.header)
        cl.addWidget(self.lines, 1)
        row = QHBoxLayout()
        row.addWidget(self.composer, 1)
        row.addWidget(self.send_button)
        cl.addLayout(row)

        # The empty screen: two acts, nothing else.
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.addStretch(1)
        self.status = plain_label("Reaching the mesh…")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(self.status)
        self.create_button = QPushButton("Create a group")
        self.join_button = QPushButton("Join a group")
        for b in (self.create_button, self.join_button):
            b.setMinimumHeight(40)
            b.setEnabled(False)
            el.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        el.addWidget(plain_label("Joining gives you a code to send to a member of the group; they add you. Nothing is read until then."), 0, Qt.AlignmentFlag.AlignHCenter)
        el.addStretch(1)
        self.create_button.clicked.connect(self.create_group)
        self.join_button.clicked.connect(self.join_group)

        self.stack = QStackedWidget()
        self.stack.addWidget(empty)
        split = QSplitter()
        split.addWidget(self.groups)
        split.addWidget(centre)
        split.addWidget(self.members)
        split.setStretchFactor(1, 1)
        self.stack.addWidget(split)
        self.setCentralWidget(self.stack)

        tb = self.addToolBar("Groups")
        tb.setMovable(False)
        self.act_create = QAction("Create a group", self)
        self.act_join = QAction("Join a group", self)
        self.act_add = QAction("Add someone", self)
        self.act_scan = QAction("Look for missed messages", self)
        self.act_voucher = QAction("Show my code", self)
        self.act_leave = QAction("Leave this group", self)
        for a in (self.act_create, self.act_join, self.act_add, self.act_scan, self.act_voucher, self.act_leave):
            tb.addAction(a)
            a.setEnabled(False)
        self.act_create.triggered.connect(self.create_group)
        self.act_join.triggered.connect(self.join_group)
        self.act_add.triggered.connect(self.add_member)
        self.act_scan.triggered.connect(self.scan)
        self.act_voucher.triggered.connect(self.show_voucher)
        self.act_leave.triggered.connect(self.leave)
        self.statusBar().showMessage("Reaching the mesh…")

    # ---- wiring ----

    def attach(self, session: Session) -> None:
        self.s = session
        self.groups_model = models.GroupsModel(session, self)
        self.lines_model = models.LinesModel(session, self)
        self.members_model = models.MembersModel(session, self)
        self.groups.setModel(self.groups_model)
        self.lines.setModel(self.lines_model)
        self.members.setModel(self.members_model)
        self.groups.selectionModel().currentChanged.connect(lambda cur, _prev: self.select(self.groups_model.chat_id(cur.row())))
        for b in (self.create_button, self.join_button, self.act_create, self.act_join):
            b.setEnabled(True)
        self.status.setText("You are in no group yet.")
        self.statusBar().showMessage("On the mesh as %s" % session.me)
        self.setWindowTitle("katzenrns · %s" % session.me)
        self.refresh(None)
        if self.groups_model.rowCount():
            self.groups.setCurrentIndex(self.groups_model.index(0, 0))

    def failed(self, why: str) -> None:
        self.status.setText("The mesh could not be reached: %s" % why)
        self.statusBar().showMessage("Not on the mesh")

    def refresh(self, changes) -> None:
        """Something changed in the client: rebuild what is shown. Called
        on the main thread."""
        if self.s is None:
            return
        self._hooks()
        selected = self.current
        self.groups_model.refresh()
        self.stack.setCurrentIndex(1 if self.groups_model.rowCount() else 0)
        if selected is not None:
            row = self.groups_model.row_of(selected)
            if row < 0:
                self.select(None)
            else:
                if self.groups.currentIndex().row() != row:
                    self.groups.setCurrentIndex(self.groups_model.index(row, 0))
                at_end = self.lines.verticalScrollBar().value() >= self.lines.verticalScrollBar().maximum() - 4
                self.lines_model.refresh()
                self.members_model.refresh()
                self._header()
                if at_end:
                    self.lines.scrollToBottom()
        elif self.groups_model.rowCount():
            self.groups.setCurrentIndex(self.groups_model.index(0, 0))

    def select(self, chat: Optional[str]) -> None:
        self.current = chat
        self.lines_model.set_chat(chat)
        self.members_model.set_chat(chat)
        self._header()
        self.lines.scrollToBottom()

    def _chat(self) -> Optional[eng.Chat]:
        return self.s.client.state.chat(self.current) if self.s and self.current else None

    def _header(self) -> None:
        c = self._chat()
        joined = c is not None and c.group is not None
        self.act_add.setEnabled(joined)
        self.act_scan.setEnabled(joined)
        self.act_leave.setEnabled(c is not None)
        self.act_voucher.setEnabled(c is not None and c.joining is not None and bool(c.joining.code))
        self.composer.setEnabled(joined)
        self.send_button.setEnabled(joined)
        if c is None:
            self.header.setText("")
            return
        self.header.setText("%s — %s" % (c.name, models.group_state(c)))

    # ---- acts ----

    def _taken(self, name: str) -> bool:
        return self.s is not None and self.s.client.chat_id(name) is not None

    def create_group(self) -> None:
        d = GroupNameDialog(False, self._taken, self)
        if d.exec() and self.s:
            chat = uuid.uuid4().hex
            self.s.client.feed(eng.Create(chat, d.value()))
            self.current = chat

    def join_group(self) -> None:
        d = GroupNameDialog(True, self._taken, self)
        if d.exec() and self.s:
            chat = uuid.uuid4().hex
            self.s.client.feed(eng.Join(chat, d.value()))
            self.current = chat
            self._pending_voucher = chat

    def show_voucher(self) -> None:
        c = self._chat()
        if c is None or self.s is None:
            return
        code = self.s.voucher_code(c.id)
        if code:
            VoucherDialog(c.name, code, self.clipboard, self).exec()

    def add_member(self) -> None:
        c = self._chat()
        if c is None or self.s is None or c.group is None:
            return
        backend = self.s.backend
        d = AddMemberDialog(c.name, lambda v: peek_voucher(backend, v), self)
        if d.exec():
            voucher, petname = d.value()
            if voucher is None:
                return
            import base64

            self._petname_for_next = petname
            self.s.client.feed(eng.Induct(c.id, base64.b64encode(voucher).decode()))

    def send(self) -> None:
        c = self._chat()
        text = self.composer.text().strip()
        if c is None or self.s is None or c.group is None or not text:
            return
        self.composer.clear()
        self.s.client.feed(eng.Send(c.id, text))

    def scan(self) -> None:
        c = self._chat()
        if c is not None and self.s is not None:
            self.s.client.feed(eng.Scan(c.id))

    def leave(self) -> None:
        c = self._chat()
        if c is None or self.s is None:
            return
        d = StopReadingDialog(c.name, "everyone", self)
        d.setWindowTitle("Leave %s" % c.name)
        if d.exec():
            self.s.client.feed(eng.Leave(c.id))

    def _member_menu(self, pos) -> None:
        idx = self.members.indexAt(pos)
        c = self._chat()
        if not idx.isValid() or c is None or self.s is None:
            return
        m = self.members_model.member(idx.row())
        if m is None or m.get("me"):
            return
        menu = QMenu(self)
        name_act = menu.addAction("Call them something else…")
        stop_act = menu.addAction("Stop reading %s…" % m["name"])
        chosen = menu.exec(self.members.mapToGlobal(pos))
        if chosen is name_act:
            from PySide6.QtWidgets import QInputDialog

            name, ok = QInputDialog.getText(self, "Name", "What do you call them?", text=m["name"])
            if ok and name.strip():
                from ..core import display_name

                self.s.petnames.set(m["key"], display_name(name))
                self.refresh(None)
        elif chosen is stop_act:
            if StopReadingDialog(c.name, m["name"], self).exec():
                self.s.client.feed(eng.RemoveMember(c.id, m["key"]))

    # ---- what the window started, completed by the client ----

    def _hooks(self) -> None:
        """A voucher minted for a join the user began: show it. A member
        added through the dialog: the name the user chose there becomes
        their petname."""
        assert self.s is not None
        pending = getattr(self, "_pending_voucher", None)
        if pending is not None:
            c = self.s.client.state.chat(pending)
            code = self.s.voucher_code(pending)
            if c is not None and code:
                self._pending_voucher = None
                VoucherDialog(c.name, code, self.clipboard, self).show()
        pet = getattr(self, "_petname_for_next", None)
        if pet:
            seen = getattr(self, "_seen_added", set())
            for c in self.s.client.chats():
                if c.group is None:
                    continue
                for line in c.log:
                    if line.notice is not None and line.notice.kind == "added" and (c.id, line.id) not in seen:
                        seen.add((c.id, line.id))
                        # The member just added is the last one the chat learned a name for.
                        for key in reversed(list(c.names)):
                            if key in c.group.readers:
                                self.s.petnames.set(key, pet)
                                self._petname_for_next = None
                                break
            self._seen_added = seen
