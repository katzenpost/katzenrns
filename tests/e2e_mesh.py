# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""End to end: two Pigeonhole replica processes (pigeonhole_rns, from the
Katzenpost repository) on a local Reticulum network and two katzenrns
headless shells. alice founds a group, bob joins through a voucher alice
inducts, and they talk.

    python tests/e2e_mesh.py --run-dir /path/to/scratch

Not collected by pytest: it spawns processes and binds a TCP port."""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import subprocess
import sys
import threading
import time


HUB_PORT = 42111
# A voucher payload is about 450 bytes and the sealed reply to it more; the mixnet uses boxes of a kilobyte or two.
BOX = 1000

HUB_CONFIG = """[reticulum]
  enable_transport = Yes
  share_instance = No
[logging]
  loglevel = 3
[interfaces]
  [[Hub]]
    type = TCPServerInterface
    enabled = yes
    listen_ip = 127.0.0.1
    listen_port = %d
""" % HUB_PORT

LEAF_CONFIG = """[reticulum]
  enable_transport = No
  share_instance = No
[logging]
  loglevel = 3
[interfaces]
  [[ToHub]]
    type = TCPClientInterface
    enabled = yes
    target_host = 127.0.0.1
    target_port = %d
""" % HUB_PORT


def write_config(d: str, text: str) -> str:
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "config"), "w") as f:
        f.write(text)
    return d


class Proc:
    """A chat client process: lines in, lines out."""

    def __init__(self, name: str, args: list, env: dict, cwd: str, log):
        self.name = name
        self.p = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, env=env, cwd=cwd, text=True, bufsize=1)
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.seen: list = []
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.p.stdout is not None
        for line in self.p.stdout:
            line = line.rstrip("\n")
            print("  %s> %s" % (self.name, line), flush=True)
            self.lines.put(line)

    def say(self, cmd: str) -> None:
        print("%s< %s" % (self.name, cmd), flush=True)
        assert self.p.stdin is not None
        self.p.stdin.write(cmd + "\n")
        self.p.stdin.flush()

    def expect(self, needle: str, timeout: float) -> str:
        deadline = time.time() + timeout
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise TimeoutError("%s: no line containing %r" % (self.name, needle))
            try:
                line = self.lines.get(timeout=min(left, 1.0))
            except queue.Empty:
                continue
            self.seen.append(line)
            if needle in line:
                return line

    def close(self) -> None:
        try:
            self.say("quit")
            self.p.wait(timeout=15)
        except Exception:
            self.p.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--settle", type=float, default=10.0)
    ap.add_argument("--katzenrns", help="run this katzenrns executable instead of the installed module")
    a = ap.parse_args()

    run = os.path.abspath(a.run_dir)
    if os.path.isdir(run):
        shutil.rmtree(run)
    os.makedirs(run)
    here = os.path.dirname(os.path.abspath(__file__))
    pkg_root = os.path.dirname(here)
    env = dict(os.environ)

    procs = []
    chats = []
    try:
        for name, cfg in (("a", HUB_CONFIG), ("b", LEAF_CONFIG)):
            cfgdir = write_config(os.path.join(run, "rns-" + name), cfg)
            log = open(os.path.join(run, "replica-%s.log" % name), "w")
            procs.append(
                subprocess.Popen(
                    [sys.executable, "-m", "pigeonhole_rns.cli", "--config", cfgdir, "--box-size", str(BOX), "-v",
                     "replica", "--storage", os.path.join(run, "store-" + name), "--announce-interval", "3"],
                    stdout=log, stderr=subprocess.STDOUT, env=env, cwd=pkg_root,
                )
            )
            time.sleep(2.0)
        time.sleep(a.settle)

        def chat(name: str) -> Proc:
            cfgdir = write_config(os.path.join(run, "rns-" + name), LEAF_CONFIG)
            log = open(os.path.join(run, "chat-%s.log" % name), "w")
            c = Proc(
                name,
                ([a.katzenrns] if a.katzenrns else [sys.executable, "-m", "katzenrns"]) + ["--headless", "--config", cfgdir, "--state", os.path.join(run, "chat-" + name),
                 "--name", name, "--box-size", str(BOX), "--epoch-poll", "5"],
                env, pkg_root, log,
            )
            chats.append(c)
            return c

        alice, bob = chat("alice"), chat("bob")
        time.sleep(a.settle)

        alice.expect("READY", 120)
        bob.expect("READY", 120)
        alice.say("create g")
        alice.expect("a new group", 60)
        bob.say("join g")
        code = bob.expect("VOUCHER=", 120).split("VOUCHER=", 1)[1].strip()
        alice.say("invite g " + code)
        alice.expect("added ~bob", 180)
        bob.expect("JOINED g", 180)

        alice.say("send g hello bob, you coming to the party later tonight?")
        bob.expect("LINE g alice: hello bob, you coming to the party later tonight?", 180)
        bob.say("send g yo what up? yes")
        alice.expect("LINE g bob: yo what up? yes", 180)

        bob.say("members g")
        bob.expect("~alice", 10)
        print("PASS")
        return 0
    except Exception as e:
        print("FAIL:", e, file=sys.stderr)
        return 1
    finally:
        for c in chats:
            c.close()
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    sys.exit(main())
