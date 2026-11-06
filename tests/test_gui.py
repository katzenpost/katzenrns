# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The desktop client offscreen: two windows over one simulated Pigeonhole
in virtual time. alice creates a group, bob joins by voucher, alice adds
him through the dialog's path, they talk, and the views show it."""

import base64
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from pigeonhole_protocols.katzenqt1 import engine as eng
from pigeonhole_protocols.katzenqt1.client import SyncClient
from pigeonhole_protocols.transport.sim import SimBackend
from PySide6.QtWidgets import QApplication

from katzenrns import core
from katzenrns.gui import models
from katzenrns.gui.dialogs import peek_voucher
from katzenrns.gui.window import MainWindow


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def make(tmp_path, name, sim, clock):
    w = MainWindow()
    s = core.Session(str(tmp_path / name), name, sim, client=SyncClient(str(tmp_path / name), name, sim, clock=clock))
    s.client.on_change = w.refresh
    w.attach(s)
    return w, s


def settle(sessions, qapp, ms=60_000, step=1000):
    for _ in range(ms // step):
        for s in sessions:
            s.client.run(step)
        qapp.processEvents()


def lines(w):
    m = w.lines_model
    return [(m.data(m.index(i, 0), models.WHO), m.data(m.index(i, 0), models.WHAT), m.data(m.index(i, 0), models.NOTICE)) for i in range(m.rowCount())]


def test_two_windows(qapp, tmp_path):
    sim, clock = SimBackend(max_plaintext=1000, real_vouchers=True), [0]  # peek_voucher reads a real payload
    aw, alice = make(tmp_path, "alice", sim, clock)
    bw, bob = make(tmp_path, "bob", sim, clock)
    assert aw.stack.currentIndex() == 0  # the empty screen

    alice.client.feed(eng.Create("g", "Family"))
    bob.client.feed(eng.Join("g", "Fam"))
    settle([alice, bob], qapp, 10_000)
    assert aw.stack.currentIndex() == 1 and aw.header.text().startswith("Family — joined")
    assert "waiting for the member" in bw.header.text()
    code = bob.voucher_code("g")
    assert code

    # What the Add dialog does: peek the claimed name off the network, then induct with a petname.
    claimed = peek_voucher(sim, base64.b64decode(code))
    assert claimed == "bob"
    aw._petname_for_next = "Robert"
    alice.client.feed(eng.Induct("g", code))
    settle([alice, bob], qapp, 60_000)
    bw.select("g")
    assert bw.header.text().startswith("Fam — joined")

    alice.client.feed(eng.Send("g", "hello"))
    settle([alice, bob], qapp, 60_000)
    bob.client.feed(eng.Send("g", "hey <b>there</b>\x1b[31m"))
    settle([alice, bob], qapp, 60_000)
    got = lines(aw)
    assert ("alice", "hello", False) in got
    assert ("Robert", "hey <b>there</b>[31m", False) in got  # petname shown, controls stripped, no markup
    assert ("~alice", "hello", False) in lines(bw)  # bob never named alice: a claim
    assert any(n for _, _, n in got)  # notices present
    # Members pane: alice sees Robert as her petname; bob sees ~alice as a claim.
    am = aw.members_model
    names = [am.data(am.index(i, 0)) for i in range(am.rowCount())]
    assert "alice (you)" in names and "Robert" in names
    bm = bw.members_model
    assert "~alice" in [bm.data(bm.index(i, 0)) for i in range(bm.rowCount())]
    alice.close()
    bob.close()


def test_app_logs_mesh_failure(qapp, tmp_path, capsys):
    from katzenrns.gui.app import App

    def no_mesh():
        raise RuntimeError("no Pigeonhole replica heard on the mesh")

    w = MainWindow()
    App(w, str(tmp_path), "alice", no_mesh)._connect()
    assert "katzenrns: the mesh could not be reached: no Pigeonhole replica heard on the mesh" in capsys.readouterr().err
    assert w.statusBar().currentMessage() == "Not on the mesh"
