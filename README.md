# katzenrns

Group chat over a Reticulum mesh, on Pigeonhole boxes. katzenrns speaks the same katzenqt1
protocol as katzenqt does on the Katzenpost mixnet, so a group can have members on a mesh and
members on the mixnet, talking through a bridge replica without knowing it. The protocol is
[pigeonhole_protocols](https://github.com/katzenpost/pigeonhole_protocols) (its `py/`); the
mesh replicas and the mesh half of the bridge are [pigeonhole_rns](https://github.com/katzenpost/pigeonhole_rns),
the bridge socket on the mixnet replica is in the Katzenpost repository; the design is
the Pigeonhole over Reticulum specification on the Katzenpost website.

On the mesh, this client does the BACAP encryption itself with hpqc and sends sealed boxes to
the nearest replica it hears announce. There is no daemon between the client and the mesh. In
open mode, BACAP is the only protection; a closed mesh adds a Noise layer in the transport.

## Run

    pip install katzenrns
    rnsd &                      # or let katzenrns start its own Reticulum instance
    katzenrns                   # the desktop client
    katzenrns --headless --name bob     # commands on stdin, for scripts

The first launch of the desktop client asks for the name you show others. Then: **Create a
group**, or **Join a group**, which shows a voucher code to send to someone already in the
group; they paste it into **Add someone**. The code is the same text katzenqt uses, so a
katzenqt user can add you, and you them.

The headless shell takes `create g`, `join g`, `invite g CODE`, `send g text`, `show g`,
`members g`, `scan g`, `remove g NAME`, `leave g` and prints `READY`, `VOUCHER=...`,
`JOINED g` and `LINE g who: text` as things happen.

## Test

    pip install -e .[test]
    pytest
    python tests/e2e_mesh.py --run-dir /some/scratch/dir      # two replicas, two shells

With a docker mixnet up in a Katzenpost checkout (`make -C docker start wait`) and the mesh replica container up
(`pigeonhole_rns/tests/docker_bridge.sh start katzenpost/docker/mixnet-alpine`),
two scripts put a katzenrns shell on the mesh in one group with a mixnet client, through the
bridge, each founding once and joining once, and check that each reads and acknowledges the
other:

    scripts/interop.sh host ../katzenpost            # with pigeonhole_protocols' Go katzenqt1
    scripts/interop.sh guest ../katzenpost
    KATZENQT=../katzenqt/.venv/bin/katzenqt-headless scripts/interop-katzenqt.sh host ../katzenpost
    KATZENQT=../katzenqt/.venv/bin/katzenqt-headless scripts/interop-katzenqt.sh guest ../katzenpost

The interop workflow runs all four on every push.
