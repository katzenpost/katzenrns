# Testing and releasing katzenrns

## Tests

    pip install -e .[test]
    pytest
    python tests/e2e_mesh.py --run-dir /some/scratch/dir      # two replicas, two shells

`tests/test_gui.py` drives the desktop client; without a display, run it with
`QT_QPA_PLATFORM=offscreen`, as CI does.

## Interop with the mixnet

With a docker mixnet up in a Katzenpost checkout (`make -C docker start wait`) and the mesh
replica container up (`pigeonhole_rns/tests/docker_bridge.sh start katzenpost/docker/mixnet-alpine`),
two scripts put a katzenrns shell on the mesh in one group with a mixnet client, through the
bridge, each founding once and joining once, and check that each reads and acknowledges the
other:

    scripts/interop.sh host ../katzenpost            # with pigeonhole_protocols' Go katzenqt1
    scripts/interop.sh guest ../katzenpost
    KATZENQT=../katzenqt/.venv/bin/katzenqt-headless scripts/interop-katzenqt.sh host ../katzenpost
    KATZENQT=../katzenqt/.venv/bin/katzenqt-headless scripts/interop-katzenqt.sh guest ../katzenpost

The interop workflow runs all four on pushes to main, daily, and on pull requests that change the
code or these scripts.

## Releases

To cut a release, set the version in `pyproject.toml` and push the matching tag,
`git tag vX.Y.Z && git push origin vX.Y.Z`; the release workflow builds, smoke tests and
publishes it. Running that workflow by hand builds the same files as workflow artifacts and
publishes nothing.
