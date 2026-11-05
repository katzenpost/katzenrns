# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The box client, with a query mode of "request" (Link requests and Resources), "channel"
(Channel messages, for replicas on Reticulum stacks without requests) or "auto": requests
first, Channel when a replica announcing it does not answer them, and the mode that answered
kept per replica."""

from __future__ import annotations

from typing import Dict, Optional

import RNS
from pigeonhole_rns.client import Client

MODES = ("auto", "request", "channel")


class Boxes(Client):
    # shortcut: overrides pigeonhole_rns's private _query; move "auto" into its Client when it grows one.
    def __init__(self, configdir: Optional[str], box_plaintext_size: int, loglevel: int = RNS.LOG_ERROR, mode: str = "auto"):
        if mode not in MODES:
            raise ValueError("mode must be one of %s" % ", ".join(MODES))
        super().__init__(configdir, box_plaintext_size, loglevel=loglevel, mode="request" if mode == "auto" else mode)
        self.auto = mode == "auto"
        self.modes: Dict[bytes, str] = {}

    def mode_of(self, dest: bytes) -> str:
        if not self.auto:
            return self.mode
        with self._mu:
            channel = dest in self.channel_replicas
        return self.modes.get(dest, "request") if channel else "request"

    def _ask(self, dest: bytes, mode: str, path: str, data: bytes) -> Optional[bytes]:
        if mode == "channel":
            return self.links.channel_request(dest, data)
        return self.links.request(dest, path, data)

    def _query(self, dest: bytes, path: str, data: bytes) -> Optional[bytes]:
        if not self.auto or path == "peek":
            return super()._query(dest, path, data)
        first = self.mode_of(dest)
        raw = self._ask(dest, first, path, data)
        if raw is not None:
            return raw
        with self._mu:
            if dest not in self.channel_replicas:
                return None
        other = "channel" if first == "request" else "request"
        raw = self._ask(dest, other, path, data)
        if raw is not None:
            RNS.log("replica %s answers in %s mode" % (dest.hex(), other), RNS.LOG_NOTICE)
            self.modes[dest] = other
        return raw
