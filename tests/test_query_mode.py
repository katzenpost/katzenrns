# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""--query-mode auto asks in requests first, falls back to Channel for a replica announcing
it, and keeps the mode that answered."""

import threading

from katzenrns.__main__ import arguments
from pigeonhole_protocols.transport.reticulum import Boxes

A, B = b"a" * 16, b"b" * 16


class Links:
    def __init__(self, request_ok, channel_ok):
        self.ok = {"request": request_ok, "channel": channel_ok}
        self.asked = []

    def request(self, dest, path, data):
        self.asked.append((dest, "request"))
        return b"r" if dest in self.ok["request"] else None

    def channel_request(self, dest, data):
        self.asked.append((dest, "channel"))
        return b"c" if dest in self.ok["channel"] else None


def boxes(mode, links, channel_replicas):
    b = Boxes.__new__(Boxes)
    b.mode = "request" if mode == "auto" else mode
    b.auto = mode == "auto"
    b.modes = {}
    b._mu = threading.Lock()
    b.channel_replicas = set(channel_replicas)
    b.links = links
    return b


def test_auto_prefers_requests():
    links = Links({A}, {A})
    b = boxes("auto", links, {A})
    assert b._query(A, "read", b"q") == b"r"
    assert links.asked == [(A, "request")]


def test_auto_falls_back_to_channel_and_keeps_it():
    links = Links(set(), {A})
    b = boxes("auto", links, {A})
    assert b._query(A, "write", b"q") == b"c"
    assert b._query(A, "read", b"q") == b"c"
    assert links.asked == [(A, "request"), (A, "channel"), (A, "channel")]
    assert b.mode_of(A) == "channel"


def test_auto_never_channels_to_a_replica_not_announcing_it():
    links = Links(set(), {B})
    b = boxes("auto", links, set())
    assert b._query(B, "read", b"q") is None
    assert links.asked == [(B, "request")]


def test_fixed_modes():
    links = Links({A}, {A})
    assert boxes("channel", links, {A})._query(A, "read", b"q") == b"c"
    assert boxes("request", links, {A})._query(A, "read", b"q") == b"r"


def test_query_mode_flag(tmp_path):
    assert arguments(["--state", str(tmp_path)]).query_mode == "auto"
    assert arguments(["--state", str(tmp_path), "--query-mode", "channel"]).query_mode == "channel"
