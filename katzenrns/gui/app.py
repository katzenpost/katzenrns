# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The desktop client: a Qt application around a session. The protocol
client runs on its own threads; its changes cross to the Qt thread as one
signal, and the window rebuilds what it shows from the session."""

from __future__ import annotations

import sys
import threading
from typing import Optional

from pigeonhole_protocols.katzenqt1 import engine as eng
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from ..core import Session, default_state_dir
from .dialogs import NameDialog
from .window import MainWindow


class Bridge(QObject):
    """Signals emitted from the client's threads, delivered on the Qt
    thread."""

    changed = Signal(object)
    connected = Signal(object)
    failed = Signal(str)


class App:
    def __init__(self, window: MainWindow, state_dir: str, name: Optional[str], backend_factory, epoch_poll_s: float = 60.0):
        self.window = window
        self.state_dir = state_dir
        self.name = name
        self.backend_factory = backend_factory
        self.epoch_poll_s = epoch_poll_s
        self.bridge = Bridge()
        self.bridge.changed.connect(self._changed)
        self.bridge.connected.connect(self._connected)
        self.bridge.failed.connect(window.failed)
        self.session: Optional[Session] = None

    def start(self) -> None:
        threading.Thread(target=self._connect, daemon=True).start()

    def _connect(self) -> None:
        try:
            self.bridge.connected.emit(self.backend_factory())
        except Exception as e:
            self.bridge.failed.emit(str(e))

    def _connected(self, backend) -> None:
        self.session = Session(self.state_dir, self.name or "", backend, on_change=self.bridge.changed.emit, epoch_poll_s=self.epoch_poll_s)
        self.window.attach(self.session)
        self.session.start()

    def _changed(self, changes: eng.Changes) -> None:
        self.window.refresh(changes)

    def close(self) -> None:
        if self.session is not None:
            self.session.close()
        self.window.clipboard.clear()


def run(args) -> int:
    import RNS

    from ..transport import MeshBackend

    qapp = QApplication.instance() or QApplication(sys.argv[:1])
    window = MainWindow()
    name = args.name
    if not name:
        # Asked once: the stored name wins over an empty prompt.
        from pigeonhole_protocols.katzenqt1.store import Store

        st = Store(args.state)
        row = st.db.execute("SELECT value FROM meta WHERE key='me'").fetchone()
        st.close()
        if row is None:
            d = NameDialog()
            if not d.exec():
                return 0
            name = d.value()
    app = App(window, args.state, name, lambda: MeshBackend.connect(args.config, args.box_size, loglevel=RNS.LOG_DEBUG if args.verbose else RNS.LOG_ERROR), epoch_poll_s=args.epoch_poll)
    window.show()
    app.start()
    qapp.aboutToQuit.connect(app.close)
    return qapp.exec()
