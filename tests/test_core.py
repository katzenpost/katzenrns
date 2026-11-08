# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The session and the headless shell over a simulated Pigeonhole, in
virtual time, and the sanitizer every remote string passes through."""

import io

from pigeonhole_protocols.katzenqt1 import engine as eng
from pigeonhole_protocols.katzenqt1 import wire
from pigeonhole_protocols.katzenqt1.client import SyncClient
from pigeonhole_protocols.transport.sim import SimBackend

from katzenrns import core
from katzenrns.headless import Shell


def test_display_text_strips_controls_and_bidi():
    assert core.display_text("hi\x1b[31m there‮!") == "hi[31m there!"
    assert core.display_text("a\nb\tc") == "a\nb\tc"
    assert core.display_text("x" * 20, limit=5) == "xxxxx [cut]"


def test_display_name_is_one_short_line():
    assert core.display_name("  bob\nsmith \x00 ") == "bob smith"
    assert core.display_name("") == "unnamed"
    assert len(core.display_name("n" * 100)) == core.MAX_NAME


def test_skeleton_merges_lookalikes():
    assert core.skeleton("al1ce") == core.skeleton("alice") == core.skeleton("ALICE")
    assert core.skeleton("аlice") == core.skeleton("alice")  # Cyrillic а
    assert core.mixed_script("аlice") and not core.mixed_script("alice")


def test_parse_voucher():
    import base64

    v = bytes(range(32))
    code = base64.b64encode(v).decode()
    assert core.parse_voucher(" " + code[:10] + "\n" + code[10:] + " ") == v
    assert core.parse_voucher("not a code") is None
    assert core.parse_voucher(base64.b64encode(b"short").decode()) is None


def make(tmp_path, name, sim, clock):
    out = io.StringIO()
    s = core.Session(str(tmp_path / name), name, sim, client=SyncClient(str(tmp_path / name), name, sim, clock=clock))
    shell = Shell(s, out)
    s.client.on_change = shell.on_change
    return s, shell, out


def settle(sessions, ms=120_000, step=1000):
    for _ in range(ms // step):
        for s in sessions:
            s.client.run(step)


def test_two_shells_talk(tmp_path):
    sim, clock = SimBackend(max_plaintext=1000), [0]
    alice, ash, aout = make(tmp_path, "alice", sim, clock)
    bob, bsh, bout = make(tmp_path, "bob", sim, clock)
    for sh in (ash, bsh):
        sh.run(inp=iter([]))  # start, print READY, no commands yet
    ash.command("create g")
    bsh.command("join g")
    settle([alice, bob], 10_000)
    code = [l for l in bout.getvalue().splitlines() if l.startswith("VOUCHER=")][0][len("VOUCHER="):]
    ash.command("invite g " + " ".join(code[i:i + 8] for i in range(0, len(code), 8)))  # spaced, as pasted from a chat
    settle([alice, bob], 60_000)
    assert "JOINED g" in bout.getvalue()
    ash.command("send g hello bob")
    settle([alice, bob], 60_000)
    assert "LINE g alice: hello bob" in bout.getvalue()
    bsh.command("send g hey")
    settle([alice, bob], 60_000)
    assert "LINE g bob: hey" in aout.getvalue()
    # Names: bob is shown by the name he claimed, marked as a claim, until alice names him.
    members = {m["name"]: m for m in alice.members(alice.client.chat_id("g"))}
    assert "bob" in members and not members["bob"]["petname"]
    alice.petnames.set(members["bob"]["key"], "Robert")
    assert alice.name_of(alice.client.chat_id("g"), members["bob"]["key"]) == "Robert"
    # The shell shows our own lines with marks.
    aout.truncate(0)
    aout.seek(0)
    ash.command("show g")
    shown = aout.getvalue()
    assert "alice ✓✓: hello bob" in shown and "Robert: hey" in shown
    # A message of a type this app does not know is shown as a notice.
    c = alice.client.state.chat(alice.client.chat_id("g"))
    raw = wire.Gcm(membership_hash=eng.membership(c.group), msg_type=13).encode()
    for o in c.group.compose(raw):
        c.jobs.append(eng.Job(c.fresh(), o.token, None, wire.frame(raw)))
    ash.command("send g after")
    settle([alice, bob], 60_000)
    assert "this app cannot show (type 13, version 5): update the app" in bout.getvalue()
    alice.close()
    bob.close()


def test_wire_version_reaches_the_engine(tmp_path):
    import pytest

    from katzenrns.__main__ import arguments

    assert arguments([]).wire_version == 4
    assert arguments(["--wire-version", "3"]).wire_version == 3
    with pytest.raises(SystemExit):
        arguments(["--wire-version", "6"])
    for v in (3, 4, 5):
        s = core.Session(str(tmp_path / str(v)), "a", SimBackend(max_plaintext=1000), wire_version=v)
        assert s.client.engine.wire_version == v
        s.close()
