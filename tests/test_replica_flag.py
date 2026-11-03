# SPDX-FileCopyrightText: © 2026 David Stainton
# SPDX-License-Identifier: AGPL-3.0-only
"""--replica HOST:PORT writes a Reticulum config of katzenrns's own under
the state directory, with one TCP link to that replica."""

import pytest

from katzenrns.__main__ import arguments, replica_config


def test_replica_writes_a_config_under_the_state(tmp_path):
    a = arguments(["--state", str(tmp_path), "--replica", "162.220.11.225:4242"])
    assert a.config == str(tmp_path / "reticulum")
    text = (tmp_path / "reticulum" / "config").read_text()
    assert "type = TCPClientInterface" in text
    assert "target_host = 162.220.11.225" in text
    assert "target_port = 4242" in text
    assert "share_instance = No" in text
    assert a.box_size == 1549


def test_replica_rewrites_for_a_new_address(tmp_path):
    replica_config(str(tmp_path), "10.0.0.1:4242")
    replica_config(str(tmp_path), "10.0.0.2:5000")
    text = (tmp_path / "reticulum" / "config").read_text()
    assert "target_host = 10.0.0.2" in text and "target_port = 5000" in text
    assert "10.0.0.1" not in text


def test_replica_wants_host_and_port(tmp_path):
    with pytest.raises(SystemExit):
        replica_config(str(tmp_path), "no-port")


def test_replica_and_config_exclude_each_other(tmp_path):
    with pytest.raises(SystemExit):
        arguments(["--state", str(tmp_path), "--replica", "h:1", "--config", str(tmp_path)])
