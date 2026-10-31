# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The headless shell: commands on standard input, lines as they arrive on
standard output, for scripts and interop tests. The markers a script waits
on are those of pigeonhole_protocols' Go client: READY once a replica is
heard, VOUCHER=<code> once minted, JOINED <group>, and LINE <group>
<who>: <text> for each line delivered.

    create GROUP            start a group
    join GROUP              mint a voucher to join someone's group
    invite GROUP CODE       add the member whose voucher code this is
    send GROUP TEXT...
    show GROUP              every line, with ✓ marks on our own
    members GROUP
    scan GROUP
    rename GROUP NEW
    remove GROUP NAME       stop reading a member
    leave GROUP
    quit
"""

from __future__ import annotations

import sys
import threading
import uuid
from typing import Dict, Set

from pigeonhole_protocols.katzenqt1 import engine as eng

from .core import Session


class Shell:
    def __init__(self, session: Session, out=sys.stdout):
        self.s = session
        self.out = out
        self.lock = threading.Lock()
        self.shown: Dict[str, Set[int]] = {}
        self.joined: Set[str] = set()
        self.minted: Set[str] = set()

    def say(self, line: str) -> None:
        with self.lock:
            print(line, file=self.out, flush=True)

    def on_change(self, ch: eng.Changes) -> None:
        for chat in list(ch.lines) + list(ch.chats):
            c = self.s.client.state.chat(chat)
            if c is None:
                continue
            if c.group is not None and chat not in self.joined:
                self.joined.add(chat)
                self.say("JOINED %s" % c.name)
            code = self.s.voucher_code(chat)
            if code and chat not in self.minted:
                self.minted.add(chat)
                self.say("VOUCHER=%s" % code)
            seen = self.shown.setdefault(chat, set())
            for line in self.s.client.lines(chat):
                if line.id in seen:
                    continue
                seen.add(line.id)
                who, what = self.s.line_text(chat, line, mark_claim=False)
                if who:
                    self.say("LINE %s %s: %s" % (c.name, who, what))
                else:
                    self.say("NOTE %s — %s" % (c.name, what))

    def show(self, chat: str, group: str) -> None:
        c = self.s.client.state.chat(chat)
        for line in self.s.client.lines(chat):
            who, what = self.s.line_text(chat, line, mark_claim=False)
            if not who:
                self.say("— " + what)
                continue
            mark = ""
            if c is not None and c.group is not None and line.sender == c.group.me:
                mark = " …" if line.status == eng.PENDING else (" ✓✓" if c.acknowledged(line) else " ✓")
            self.say("%s%s: %s" % (who, mark, what))

    def command(self, raw: str) -> bool:
        """One command; False to quit."""
        words = raw.strip().split(None, 2)
        if not words:
            return True
        cmd = words[0]
        if cmd == "quit":
            return False
        if len(words) < 2:
            self.say("? %s GROUP ..." % cmd)
            return True
        group = words[1]
        rest = words[2] if len(words) > 2 else ""
        chat = self.s.client.chat_id(group)
        if cmd == "create":
            self.s.client.feed(eng.Create(uuid.uuid4().hex, group))
        elif cmd == "join":
            self.s.client.feed(eng.Join(uuid.uuid4().hex, group))
        elif chat is None:
            self.say("? no group called %s" % group)
        elif cmd in ("invite", "induct"):
            self.s.client.feed(eng.Induct(chat, rest.strip()))
        elif cmd == "send":
            self.s.client.feed(eng.Send(chat, rest))
        elif cmd == "show":
            self.show(chat, group)
        elif cmd == "members":
            for m in self.s.members(chat):
                self.say("~%s %s%s" % (m["name"], m["key"].hex()[:16], "" if m["petname"] else " (as they call themselves)"))
        elif cmd == "scan":
            self.s.client.feed(eng.Scan(chat))
        elif cmd == "rename":
            self.s.client.feed(eng.Rename(chat, rest.strip()))
        elif cmd == "remove":
            who = [m["key"] for m in self.s.members(chat) if m["name"] == rest.strip()]
            if who:
                self.s.client.feed(eng.RemoveMember(chat, who[0]))
            else:
                self.say("? no member called %s" % rest.strip())
        elif cmd == "leave":
            self.s.client.feed(eng.Leave(chat))
        else:
            self.say("? unknown command %s" % cmd)
        return True

    def run(self, inp=sys.stdin) -> None:
        for c in self.s.client.chats():
            self.shown[c.id] = {l.id for l in c.log}
            if c.group is not None:
                self.joined.add(c.id)
            if self.s.voucher_code(c.id):
                self.minted.add(c.id)
        self.s.start()
        self.say("READY")
        for raw in inp:
            if not self.command(raw):
                break
