# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The dialogs: a name for ourselves, a new group, joining one, the voucher
to hand on, adding someone, stopping reading someone. Each states what the
act does before the user does it, names the act on its button, defaults to
the safe answer, and shows remote strings as plain text only."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from hpqc.voucher import stateless as voucher_stateless
from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ..core import MAX_NAME, display_name, parse_voucher

CLIPBOARD_SECONDS = 60


def plain_label(text: str, wrap: bool = True) -> QLabel:
    l = QLabel(text)
    l.setTextFormat(Qt.TextFormat.PlainText)
    l.setWordWrap(wrap)
    return l


class Clipboard:
    """One owner for secrets on the clipboard: a copy is cleared after a
    minute, and on quit, as katzenqt does."""

    def __init__(self):
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.clear)
        self.text: Optional[str] = None

    def copy_secret(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.text = text
        self.timer.start(CLIPBOARD_SECONDS * 1000)

    def clear(self) -> None:
        cb = QGuiApplication.clipboard()
        if self.text is not None and cb.text() == self.text:
            cb.clear()
        self.text = None


class NameDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("katzenrns")
        lay = QVBoxLayout(self)
        lay.addWidget(plain_label("The name you show others. Members of your groups see it next to what you say; you can be known by another name in each of their clients."))
        self.name = QLineEdit()
        self.name.setMaxLength(MAX_NAME)
        lay.addWidget(self.name)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self.name.textChanged.connect(lambda t: bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(display_name(t) != "unnamed")))
        bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

    def value(self) -> str:
        return display_name(self.name.text())


class GroupNameDialog(QDialog):
    """A name for a group here, for creating one or for joining someone's.
    The name is ours alone: other members call the group what they like."""

    def __init__(self, joining: bool, taken: Callable[[str], bool], parent=None):
        super().__init__(parent)
        self.taken = taken
        self.setWindowTitle("Join a group" if joining else "Create a group")
        lay = QVBoxLayout(self)
        if joining:
            lay.addWidget(plain_label("What will you call the group you are joining? The name is yours alone. Next you get a code to send to a member, who adds you."))
        else:
            lay.addWidget(plain_label("What will you call the new group? Nobody else is in it until you add them."))
        self.name = QLineEdit()
        lay.addWidget(self.name)
        self.hint = plain_label("")
        lay.addWidget(self.hint)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Join" if joining else "Create", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.name.textChanged.connect(self._check)
        self._check("")

    def _check(self, t: str) -> None:
        t = t.strip()
        if not t:
            self.ok.setEnabled(False)
            self.hint.setText("")
        elif self.taken(t):
            self.ok.setEnabled(False)
            self.hint.setText("You already have a group called %s." % t)
        else:
            self.ok.setEnabled(True)
            self.hint.setText("")

    def value(self) -> str:
        return self.name.text().strip()


class VoucherDialog(QDialog):
    """The code to hand to a member of the group, out of band."""

    def __init__(self, group: str, code: str, clipboard: Clipboard, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Your code for %s" % group)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(plain_label("Send this code to someone who is in the group. Whoever has it can add you to a group of theirs, once; after that it is spent."))
        self.code = QPlainTextEdit(code)
        self.code.setReadOnly(True)
        self.code.setMaximumHeight(60)
        lay.addWidget(self.code)
        row = QHBoxLayout()
        copy = QPushButton("Copy")
        self.copied = plain_label("")
        row.addWidget(copy)
        row.addWidget(self.copied)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addWidget(plain_label("Waiting for a member to add you. You can close this window; the group joins on its own when they do."))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)

        def do_copy():
            clipboard.copy_secret(code)
            self.copied.setText("Copied. The clipboard is cleared in %d seconds." % CLIPBOARD_SECONDS)

        copy.clicked.connect(do_copy)


class _Peek(QObject):
    done = Signal(object, object)  # (claimed name or None, error or None)


class AddMemberDialog(QDialog):
    """Paste a code; read the voucher; name the member; add them. The paste
    is the user's act of designation, and the dialog says what it grants
    before the button that grants it."""

    def __init__(self, group: str, peek: Callable[[bytes], str], parent=None):
        """``peek`` reads a voucher's payload off the network and returns
        the name its holder claims; it raises when it cannot."""
        super().__init__(parent)
        self.group = group
        self.peek = peek
        self.voucher: Optional[bytes] = None
        self.setWindowTitle("Add someone to %s" % group)
        self.setMinimumWidth(460)
        self.lay = QVBoxLayout(self)
        self.lay.addWidget(plain_label("Paste the code they sent you."))
        self.code = QPlainTextEdit()
        self.code.setMaximumHeight(60)
        self.lay.addWidget(self.code)
        self.status = plain_label("")
        self.lay.addWidget(self.status)
        self.form = QFormLayout()
        self.petname = QLineEdit()
        self.petname.setMaxLength(MAX_NAME)
        self.form.addRow("What you call them", self.petname)
        self.lay.addLayout(self.form)
        self.consequence = plain_label("")
        self.lay.addWidget(self.consequence)
        bb = QDialogButtonBox()
        self.ok = bb.addButton("Read the code", QDialogButtonBox.ButtonRole.AcceptRole)
        bb.addButton(QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._go)
        bb.rejected.connect(self.reject)
        self.lay.addWidget(bb)
        self.petname.setVisible(False)
        self.form.labelForField(self.petname).setVisible(False)
        self.code.textChanged.connect(self._check)
        self._signals = _Peek()
        self._signals.done.connect(self._peeked)
        self._check()

    def _check(self) -> None:
        if self.voucher is not None:
            return
        v = parse_voucher(self.code.toPlainText())
        self.ok.setEnabled(v is not None)
        self.status.setText("" if v is not None or not self.code.toPlainText().strip() else "That is not a code.")

    def _go(self) -> None:
        if self.voucher is None:
            v = parse_voucher(self.code.toPlainText())
            if v is None:
                return
            self.voucher = v
            self.code.setReadOnly(True)
            self.ok.setEnabled(False)
            self.status.setText("Reading the code on the mesh…")
            threading.Thread(target=self._peek_thread, args=(v,), daemon=True).start()
            return
        self.accept()

    def _peek_thread(self, v: bytes) -> None:
        try:
            self._signals.done.emit(self.peek(v), None)
        except Exception as e:
            self._signals.done.emit(None, e)

    def _peeked(self, claimed, error) -> None:
        if error is not None:
            self.status.setText("The code could not be read yet: %s. You can try again later." % error)
            self.voucher = None
            self.code.setReadOnly(False)
            self._check()
            return
        claimed = display_name(claimed or "")
        self.status.setText('The code was made by someone who calls themselves "%s".' % claimed)
        self.petname.setText(claimed)
        self.petname.setVisible(True)
        self.form.labelForField(self.petname).setVisible(True)
        self.ok.setEnabled(True)

        def update():
            name = display_name(self.petname.text())
            self.consequence.setText("%s will read everything said in %s from now on, and what you send later. You can stop reading them, but you cannot take this back." % (name, self.group))
            self.ok.setText("Add %s to %s" % (name, self.group))

        self.petname.textChanged.connect(lambda _t: update())
        update()
        self.adjustSize()

    def value(self) -> tuple:
        return self.voucher, display_name(self.petname.text())


class StopReadingDialog(QDialog):
    def __init__(self, group: str, name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Stop reading %s" % name)
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.addWidget(plain_label(
            "Stop reading %s in %s and delete what they sent? This cannot be undone here. "
            "%s keeps their key and still reads everything said in %s; the other members are not told." % (name, group, name, group)
        ))
        bb = QDialogButtonBox()
        stop = bb.addButton("Stop reading %s" % name, QDialogButtonBox.ButtonRole.DestructiveRole)
        keep = bb.addButton("Keep reading", QDialogButtonBox.ButtonRole.RejectRole)
        keep.setDefault(True)
        stop.clicked.connect(self.accept)
        keep.clicked.connect(self.reject)
        lay.addWidget(bb)


def peek_voucher(backend, voucher: bytes) -> str:
    """The name a voucher's holder claims, read from the voucher stream's
    first box; raises when the box is not there yet."""
    from pigeonhole_protocols.katzenqt1.engine import DATA

    _, read_cap = backend.voucher_derive_stream(voucher)
    r = backend.read_box(read_cap, read_cap[32:])
    if r.kind != DATA:
        raise RuntimeError("the code has not been published on the mesh yet")
    return voucher_stateless.parse_and_verify_payload(voucher, r.plaintext).display_name
