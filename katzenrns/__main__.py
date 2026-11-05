# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""katzenrns: group chat over Reticulum.

    katzenrns                      the desktop client
    katzenrns --headless --name bob   commands on stdin, for scripts

Both attach to the Reticulum instance ~/.reticulum describes: a running
rnsd shared instance, or one started here from that config. With --replica
HOST:PORT, katzenrns instead starts its own instance with one TCP link to
that replica, from a config it writes under its state directory, so no
Reticulum config is needed to reach a bridge on the internet."""

from __future__ import annotations

import argparse
import os
import sys

import RNS

from .core import Session, default_state_dir
from .mesh import MODES, Boxes
from pigeonhole_protocols.transport.reticulum import MeshBackend


def arguments(argv=None):
    ap = argparse.ArgumentParser(prog="katzenrns", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--headless", action="store_true", help="commands on standard input, no window")
    ap.add_argument("--config", help="Reticulum config directory (default ~/.reticulum)")
    ap.add_argument("--replica", metavar="HOST:PORT", help="reach this replica over TCP from an instance of katzenrns's own, instead of ~/.reticulum")
    ap.add_argument("--state", default=default_state_dir(), help="where this client keeps its state")
    ap.add_argument("--name", help="the name you show others (asked once)")
    ap.add_argument("--box-size", type=int, default=1549, help="the replicas' box plaintext size (default: namenlos's)")
    ap.add_argument("--wire-version", type=int, choices=(3, 4), default=4, help="the katzenqt1 wire version written and minted: 3 (map form, long vouchers) or 4 (compact; default)")
    ap.add_argument("--query-mode", choices=MODES, default="auto", help="how queries reach a replica: request (Link requests and Resources), channel (Channel messages), or auto (default): requests, falling back to Channel per replica")
    ap.add_argument("--epoch-poll", type=float, default=60.0)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.replica:
        if a.config:
            ap.error("--replica and --config are two ways to reach the mesh; give one")
        a.config = replica_config(a.state, a.replica)
    return a


def replica_config(state_dir: str, replica: str) -> str:
    """Write the Reticulum config for one TCP link to ``replica`` under the
    state directory, and return its directory. Written on every start, so
    a changed address takes effect; the identity and storage beside it stay."""
    host, sep, port = replica.rpartition(":")
    if not sep or not host or not port.isdigit():
        raise SystemExit("--replica wants HOST:PORT, got %r" % replica)
    d = os.path.join(state_dir, "reticulum")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "config"), "w") as f:
        f.write(
            "# written by katzenrns --replica; edit the flag, not this file\n"
            "[reticulum]\n  enable_transport = No\n  share_instance = No\n"
            "[interfaces]\n  [[replica]]\n    type = TCPClientInterface\n    enabled = yes\n"
            "    target_host = %s\n    target_port = %s\n" % (host.strip("[]"), port)
        )
    return d


def main(argv=None) -> int:
    a = arguments(argv)
    if a.headless:
        from .headless import Shell

        if not a.name:
            print("--name is needed in headless mode", file=sys.stderr)
            return 2
        try:
            backend = MeshBackend.wait_for(Boxes(a.config, a.box_size, loglevel=RNS.LOG_DEBUG if a.verbose else RNS.LOG_ERROR, mode=a.query_mode))
        except Exception as e:
            print(e, file=sys.stderr)
            return 1
        shell = None
        session = Session(a.state, a.name, backend, on_change=lambda ch: shell.on_change(ch), epoch_poll_s=a.epoch_poll, wire_version=a.wire_version)
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
