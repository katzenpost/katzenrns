#!/bin/bash
# A katzenrns shell on the mesh and pigeonhole_protocols' katzenqt1 on the mixnet, in one group,
# through the bridge: as host, katzenrns founds the group and inducts katzenqt1; as guest,
# katzenqt1 founds it and inducts katzenrns. Each sends, each reads the other, and each sees its
# message acknowledged by the other, which proves the control messages crossed too.
#
# Needs a docker mixnet with the bridge running (in the katzenpost checkout:
# make -C docker start wait, then pigeonhole_rns/tests/docker_bridge.sh start docker/mixnet-alpine), the Go client on PATH as katzenqt1, and katzenrns
# installed in the current Python.
#
#   scripts/interop.sh host|guest KATZENPOST_DIR [WORK_DIR]
set -euo pipefail
role=${1:?host or guest}
katzenpost=${2:?path to the katzenpost checkout}
work=${3:-${WORK:-$PWD/interop-$role-$$}}
here=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$work"
net="$katzenpost/docker/mixnet-alpine"
# The client daemon's address, from the testnet's thin client config: its port is drawn from a
# per-checkout seed.
daemon=${DAEMON:-$(sed -n 's/^ *Address *= *"\(.*\)"/\1/p' "$net/client/thinclient.toml" | sed 's/^localhost:/127.0.0.1:/')}

step() { echo "== $(date +%T) $*"; }

# The mixnet's box size, from its Sphinx geometry; the mesh must use the same.
box=$(cd "$katzenpost" && go run "$here/scripts/boxsize.go" "$net/client/client.toml")
step "box size $box"

# The mesh side attaches to the bridge container's shared Reticulum instance on this host.
mkdir -p "$work/rns"
printf '[reticulum]\n  share_instance = Yes\n[logging]\n  loglevel = 3\n' > "$work/rns/config"

mkfifo "$work/go.in" "$work/rns.in"
katzenqt1 -daemon "$daemon" -state "$work/go" -name gopher -log "$work/go.log" < "$work/go.in" > "$work/go.out" 2> "$work/go.err" &
gopid=$!
python -m katzenrns --headless --config "$work/rns" --state "$work/rns-state" --name meshy --box-size "$box" --epoch-poll 30 < "$work/rns.in" > "$work/rns.out" 2> "$work/rns.err" &
rnspid=$!
trap 'kill $gopid $rnspid 2>/dev/null || true' EXIT
exec 3> "$work/go.in"
exec 4> "$work/rns.in"

wait_for() { # file pattern [seconds]
  local deadline=$(( $(date +%s) + ${3:-900} ))
  until grep -q -- "$2" "$1"; do
    if [ "$(date +%s)" -gt "$deadline" ]; then
      echo "FAIL: no '$2' in $1"; echo "--- $1"; cat "$1"; echo "--- go.err"; tail -20 "$work/go.err"; echo "--- rns.err"; tail -20 "$work/rns.err"; exit 1
    fi
    kill -0 $gopid 2>/dev/null || { echo "katzenqt1 died"; cat "$work/go.err"; exit 1; }
    kill -0 $rnspid 2>/dev/null || { echo "katzenrns died"; cat "$work/rns.err"; exit 1; }
    sleep 2
  done
}

wait_for "$work/go.out" READY 300
wait_for "$work/rns.out" READY 300
if [ "$role" = host ]; then
  step "katzenrns founds g; katzenqt1 mints a voucher"
  echo "create g" >&4
  echo "join g" >&3
  wait_for "$work/go.out" "VOUCHER="
  code=$(sed -n 's/^VOUCHER=//p' "$work/go.out" | tail -1)
  step "katzenrns inducts katzenqt1 (reads the voucher through the bridge)"
  echo "invite g $code" >&4
  wait_for "$work/go.out" "JOINED g"
else
  step "katzenqt1 founds g; katzenrns mints a voucher"
  echo "create g" >&3
  echo "join g" >&4
  wait_for "$work/rns.out" "VOUCHER="
  code=$(sed -n 's/^VOUCHER=//p' "$work/rns.out" | tail -1)
  step "katzenqt1 inducts katzenrns (reads the voucher through the bridge)"
  echo "invite g $code" >&3
  wait_for "$work/rns.out" "JOINED g"
fi
step "each sends"
echo "send g from the mesh" >&4
echo "send g from the mixnet" >&3
step "katzenqt1 reads katzenrns"
wait_for "$work/go.out" "LINE g .*: from the mesh"
step "katzenrns reads katzenqt1"
wait_for "$work/rns.out" "LINE g .*: from the mixnet"
# Acknowledgements ride on the next message each side sends.
step "each sends again, carrying its acknowledgements"
echo "send g mesh read you" >&4
echo "send g mixnet read you" >&3
wait_for "$work/go.out" "LINE g .*: mesh read you"
wait_for "$work/rns.out" "LINE g .*: mixnet read you"
step "each sees its first message acknowledged"
for i in $(seq 1 90); do
  echo "show g" >&3
  echo "show g" >&4
  sleep 5
  grep -q "me ✓✓: from the mixnet" "$work/go.out" && grep -q "meshy ✓✓: from the mesh" "$work/rns.out" && break
done
grep -q "me ✓✓: from the mixnet" "$work/go.out" || { echo "FAIL: katzenqt1 saw no acknowledgement from the mesh"; tail -30 "$work/go.out"; exit 1; }
grep -q "meshy ✓✓: from the mesh" "$work/rns.out" || { echo "FAIL: katzenrns saw no acknowledgement from the mixnet"; tail -30 "$work/rns.out"; exit 1; }
echo "quit" >&3
echo "quit" >&4
step "ok: katzenrns and katzenqt1 read and acknowledge each other through the bridge ($role)"
