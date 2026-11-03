#!/bin/sh
# Smoke test a built katzenrns executable: help, headless start, the GUI offscreen,
# and the two-replica mesh test with the executable as both shells.
#     scripts/smoke-binary.sh dist/katzenrns-VERSION-linux-x86_64 SCRATCH_DIR
set -eu
bin=$(realpath "$1")
run=$2
rm -rf "$run" && mkdir -p "$run"

timeout 60 "$bin" --help | grep -q "group chat over Reticulum"

# No replica listens on port 9: Reticulum starts from the config written under the
# state directory, retries the TCP link, and the shell gives up after its 60 s wait.
rc=0
timeout 120 "$bin" --headless --name smoke --state "$run/headless" --replica 127.0.0.1:9 </dev/null 2>"$run/headless.err" || rc=$?
cat "$run/headless.err"
[ "$rc" = 1 ]
grep -q "no Pigeonhole replica heard" "$run/headless.err"
grep -q "TCPInterface\[replica/127.0.0.1:9\]" "$run/headless.err"
test -f "$run/headless/reticulum/storage/transport_identity"

# The window stays up waiting for a replica; timeout's 124 means it was still running.
rc=0
QT_QPA_PLATFORM=offscreen timeout 20 "$bin" --name smoke --state "$run/gui" --replica 127.0.0.1:9 2>"$run/gui.err" || rc=$?
cat "$run/gui.err"
[ "$rc" = 124 ]
grep -q "reaching the mesh" "$run/gui.err"
! grep -q Traceback "$run/gui.err"

timeout 900 python "$(dirname "$0")/../tests/e2e_mesh.py" --run-dir "$run/mesh" --katzenrns "$bin"
echo "smoke: ok"
