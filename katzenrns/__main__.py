# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""katzenrns: group chat over Reticulum.

    katzenrns                      the desktop client
    katzenrns --headless --name bob   commands on stdin, for scripts

Both attach to the Reticulum instance ~/.reticulum describes: a running
rnsd shared instance, or one started here from that config."""

from __future__ import annotations

import argparse
import sys

import RNS

from .core import Session, default_state_dir
from .transport import MeshBackend


def arguments(argv=None):
    ap = argparse.ArgumentParser(prog="katzenrns", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headless", action="store_true", help="commands on standard input, no window")
    ap.add_argument("--config", help="Reticulum config directory (default ~/.reticulum)")
    ap.add_argument("--state", default=default_state_dir(), help="where this client keeps its state")
    ap.add_argument("--name", help="the name you show others (asked once)")
    ap.add_argument("--box-size", type=int, default=1000, help="the replicas' box plaintext size")
    ap.add_argument("--epoch-poll", type=float, default=60.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    a = arguments(argv)
    if a.headless:
        from .headless import Shell

        if not a.name:
            print("--name is needed in headless mode", file=sys.stderr)
            return 2
        try:
            backend = MeshBackend.connect(a.config, a.box_size, loglevel=RNS.LOG_DEBUG if a.verbose else RNS.LOG_ERROR)
        except Exception as e:
            print(e, file=sys.stderr)
            return 1
        shell = None
        session = Session(a.state, a.name, backend, on_change=lambda ch: shell.on_change(ch), epoch_poll_s=a.epoch_poll)
        shell = Shell(session)
        try:
            shell.run()
        finally:
            session.close()
        return 0
    from .gui.app import run

    return run(a)


if __name__ == "__main__":
    sys.exit(main())
