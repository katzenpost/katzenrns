# katzenrns

katzenrns is a group chat client for a Reticulum mesh, on Pigeonhole boxes. It speaks
the katzenqt1 protocol that katzenqt and hushphone speak on the Katzenpost mixnet, so one group
can have members on a mesh and members on the mixnet, joined by a bridge replica.

<p>
  <img src="docs/hushphone-interop.png" alt="katzenrns on the desktop: Alice Cryptwalker on a Reticulum mesh in a group with Bobby Lobby, a hushphone user on the mixnet, greeting each other, with read receipts" width="640">
</p>

The client does the BACAP encryption itself with hpqc and sends sealed boxes to the nearest
replica it hears announce; there is no daemon between it and the mesh. In open mode BACAP is
the only protection; a closed mesh adds a Noise layer in the transport. katzenrns is only a
client: the mesh replicas and the mesh half of the bridge are
[pigeonhole_rns](https://github.com/katzenpost/pigeonhole_rns), and the protocol is
[pigeonhole_protocols](https://github.com/katzenpost/pigeonhole_protocols). To chat only on
the mixnet, use [katzenqt](https://github.com/katzenpost/katzenqt) or
[hushphone](https://github.com/katzenpost/hushphone).

## Quick start

Python 3.10 or newer:

    pip install git+https://github.com/katzenpost/katzenrns
    katzenrns --replica 162.220.11.225:4242

That reaches the namenlos bridge replica over TCP from a Reticulum instance private to
katzenrns. The status bar reads "On the mesh" once the replica announces. Then **Create a
group**, or **Join a group** and send the voucher code it shows to someone already in it. Each
[release](https://github.com/katzenpost/katzenrns/releases) also has a single-file Linux
executable. [docs/usage.md](docs/usage.md) covers your own rnsd, the options, and the headless
shell (`--headless`) for scripts.

## In this repository

- [katzenrns/__main__.py](katzenrns/__main__.py): the command line and the Reticulum mesh backend.
- [katzenrns/core.py](katzenrns/core.py): the session, its state, petnames, vouchers and the sanitizer for remote text.
- [katzenrns/gui/](katzenrns/gui): the Qt desktop client.
- [katzenrns/headless.py](katzenrns/headless.py): the shell, commands on stdin and events on stdout.
- [tests/](tests): unit tests, the desktop client offscreen, and a two-replica local mesh.
- [scripts/](scripts): interop runs against a docker mixnet, a mixnet box-size probe, and release build helpers.
- [docs/](docs): [usage](docs/usage.md) and [testing and releases](docs/development.md).

## Status and compatibility

Version 0.1.0. katzenrns reads katzenqt1 wire versions 3, 4 and 5 and writes 4 by default;
`--wire-version` picks another. katzenqt, jam and frank_chat read 3 and 4. Voucher codes are
the text katzenqt uses, also shown as the same QR code. The
[interop workflow](.github/workflows/interop.yml) puts a katzenrns shell in one group with
pigeonhole_protocols' Go katzenqt1 client and with katzenqt, through a bridge replica on a
docker mixnet, in both directions.

## Testing and licence

    pip install -e .[test]
    pytest
    python tests/e2e_mesh.py --run-dir /some/scratch/dir

The mixnet interop runs are in [docs/development.md](docs/development.md). katzenrns is
licensed AGPL-3.0-only.
