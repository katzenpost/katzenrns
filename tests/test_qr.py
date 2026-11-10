# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""The voucher QR must be the symbol hushphone, the T-Deck and katzenqt
show. HUSHPHONE_MATRIX is what hushphone's qrcodegen 1.8.0 (Rust) printed
for CODE, as katzenqt's test_voucher_qr.py has it."""

import base64
import os
import shutil
import subprocess

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
import shiboken6
from PySide6.QtWidgets import QApplication

from katzenrns.core import QUIET, parse_voucher, voucher_qr, voucher_qr_text
from katzenrns.gui.dialogs import Clipboard, VoucherDialog, voucher_qr_image

CODE = base64.b64encode(bytes(range(7, 39))).decode()
HUSHPHONE_MATRIX = (
    "#######.##..##.######.....#######",
    "#.....#.#.#.##....#.#####.#.....#",
    "#.###.#..#.#....##..###.#.#.###.#",
    "#.###.#.#.#...#.#...###.#.#.###.#",
    "#.###.#..##.#.#.....#..#..#.###.#",
    "#.....#..#.........####.#.#.....#",
    "#######.#.#.#.#.#.#.#.#.#.#######",
    "........###.#.#..#..#..##........",
    "#.##.###...##...####...#..#..#.##",
    ".#..#.....#...###.#.##.......####",
    "##.#..#.#.#.#.#..#..#..#.#.##.###",
    "..#..#..#..#.####.#.#.......##.#.",
    ".#.#.##.#...#..#..#..#...#.#....#",
    ".##.....#.####..###...#....#.###.",
    "#.#######.##.#.###......#.####...",
    "##.###..###.#...#..####.##.####.#",
    "#.....##..##.#.#.###..#.######..#",
    "..#.##...#.##..#.#####..##.###.#.",
    "###.####..#.##.###..#.#.#.#.##.#.",
    "...#.#.##.##..###...##.###.#...##",
    "##.#..#.####...#..###...#........",
    "###.....##.#...#.##..#........#..",
    "..##..#.#..#..#.##...#.#####...##",
    ".####..#.#.###..#.##...#.#...#.#.",
    "#.###.##.####.##....###.#####..##",
    "........#..#...###......#...###..",
    "#######.###...#.#..#..###.#.#.#..",
    "#.....#.#.####.......##.#...###..",
    "#.###.#...#.###..#.##..#######..#",
    "#.###.#.#..#......###..#......###",
    "#.###.#.#.####...#.#.##.##....#..",
    "#.....#..#...#.#####..#....##...#",
    "#######.###....#..#.##.#.##.#....",
)
N = len(HUSHPHONE_MATRIX) + 2 * QUIET
WANT = ["." * N] * QUIET + ["." * QUIET + r + "." * QUIET for r in HUSHPHONE_MATRIX] + ["." * N] * QUIET


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def text_modules(text):
    """The module rows a terminal QR draws: blocks are light, so '#' is a blank half."""
    top = {"█": "..", "▀": ".#", "▄": "#.", " ": "##"}
    rows = []
    for line in text.split("\n"):
        halves = [top[ch] for ch in line]
        rows += ["".join(h[0] for h in halves), "".join(h[1] for h in halves)]
    return rows


def zbar(path):
    return subprocess.run(["zbarimg", "--raw", "-q", str(path)], capture_output=True, text=True, check=True).stdout.strip()


def test_matches_hushphone_module_for_module():
    qr = voucher_qr(CODE)
    got = ["".join("#" if qr.get_module(x, y) else "." for x in range(-QUIET, qr.get_size() + QUIET)) for y in range(-QUIET, qr.get_size() + QUIET)]
    assert got == WANT


def test_terminal_qr_draws_the_same_modules():
    rows = text_modules(voucher_qr_text(CODE))
    assert rows[:N] == WANT
    assert rows[N:] == ["." * N]  # an odd row count: the last half row is more quiet zone


def test_image_draws_the_same_modules(qapp):
    img = voucher_qr_image(CODE, scale=6)
    assert img.width() == img.height() == N * 6
    got = ["".join("#" if img.pixelColor(x * 6 + 3, y * 6 + 3).lightness() < 128 else "." for x in range(N)) for y in range(N)]
    assert got == WANT


@pytest.mark.skipif(shutil.which("zbarimg") is None, reason="zbarimg is not installed")
def test_zbar_reads_both_back(qapp, tmp_path):
    png = tmp_path / "voucher.png"
    assert voucher_qr_image(CODE).save(str(png))
    assert zbar(png) == CODE
    # The terminal QR, drawn back out as a picture of what the terminal shows.
    rows = text_modules(voucher_qr_text(CODE))
    scale = 6
    pgm = tmp_path / "terminal.pgm"
    pixels = bytes(0 if ch == "#" else 255 for r in rows for _ in range(scale) for ch in r for _ in range(scale))
    pgm.write_bytes(b"P5 %d %d 255\n" % (len(rows[0]) * scale, len(rows) * scale) + pixels)
    out = zbar(pgm)
    assert out == CODE and parse_voucher(out) == bytes(range(7, 39))


def test_dialog_shows_the_qr_beside_the_text(qapp):
    clip = Clipboard()
    d = VoucherDialog("g", CODE, clip)
    assert d.code.toPlainText() == CODE
    shown = d.qr.pixmap().toImage()
    assert shown == voucher_qr_image(CODE).convertToFormat(shown.format())
    # Unparented: delete now, not at interpreter exit after QApplication, which crashed CI.
    shiboken6.delete(d)
    shiboken6.delete(clip.timer)
