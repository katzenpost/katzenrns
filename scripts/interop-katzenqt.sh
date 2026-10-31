#!/bin/bash
# A katzenrns shell on the mesh and katzenqt's headless driver on the mixnet, in one group,
# through the bridge: as host, katzenrns founds the group and inducts katzenqt; as guest, katzenqt
# founds it and inducts katzenrns. Each sends, each reads the other, and each sees its first
# message acknowledged by the other, which proves the control messages crossed too.
#
# Needs a docker mixnet with the bridge running (in the katzenpost checkout:
# make -C docker start wait reticulum-start), katzenrns installed in the current Python, and
# katzenqt-headless on PATH or named by KATZENQT (katzenqt's .venv/bin/katzenqt-headless).
#
#   scripts/interop-katzenqt.sh host|guest KATZENPOST_DIR [WORK_DIR]
set -euo pipefail
role=${1:?host or guest}
katzenpost=${2:?path to the katzenpost checkout}
work=${3:-${WORK:-$PWD/interop-katzenqt-$role-$$}}
here=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$work"
work=$(cd "$work" && pwd) # katzenqt takes its state path as given, from its own data directory if relative
net="$katzenpost/docker/mixnet-alpine"
# The client daemon's address, from the testnet's thin client config: its port is drawn from a
# per-checkout seed.
daemon=${DAEMON:-$(sed -n 's/^ *Address *= *"\(.*\)"/\1/p' "$net/client/thinclient.toml" | sed 's/^localhost:/127.0.0.1:/')}
katzenqt=${KATZENQT:-katzenqt-headless}

step() { echo "== $(date +%T) $*"; }

# The mixnet's box size, from its Sphinx geometry; the mesh must use the same.
box=$(cd "$katzenpost" && go run "$here/scripts/boxsize.go" "$net/client/client.toml")
step "box size $box"

# The mesh side attaches to the bridge container's shared Reticulum instance on this host.
mkdir -p "$work/rns"
printf '[reticulum]\n  share_instance = Yes\n[logging]\n  loglevel = 3\n' > "$work/rns/config"

mkfifo "$work/rns.in"
python -m katzenrns --headless --config "$work/rns" --state "$work/rns-state" --name meshy --box-size "$box" --epoch-poll 30 < "$work/rns.in" > "$work/rns.out" 2> "$work/rns.err" &
rnspid=$!
trap 'kill $rnspid 2>/dev/null || true' EXIT
exec 4> "$work/rns.in"

# katzenqt's driver runs one verb per process over the same state; each verb's result tokens
# (CREATED, VOUCHER=, INDUCTED=, JOINED, SENT, RECV=) come on stderr, kept in kqt.log.
kqt() {
  KQT_STATE="$work/kqt" PYTHONUNBUFFERED=1 "$katzenqt" "$@" --address "$daemon" --network tcp 2>&1 | tee -a "$work/kqt.log"
}
kqt_local() { # verbs that need no daemon
  KQT_STATE="$work/kqt" PYTHONUNBUFFERED=1 "$katzenqt" "$@" 2>&1 | tee -a "$work/kqt.log"
}

wait_for() { # file pattern [seconds]
  local deadline=$(( $(date +%s) + ${3:-900} ))
  until grep -q -- "$2" "$1"; do
    if [ "$(date +%s)" -gt "$deadline" ]; then
      echo "FAIL: no '$2' in $1"; echo "--- $1"; cat "$1"; echo "--- rns.err"; tail -20 "$work/rns.err"; exit 1
    fi
    kill -0 $rnspid 2>/dev/null || { echo "katzenrns died"; cat "$work/rns.err"; exit 1; }
    sleep 2
  done
}
expect() { # output token
  grep -q -- "$2" <<< "$1" || { echo "FAIL: katzenqt gave no '$2'"; echo "$1"; exit 1; }
}

wait_for "$work/rns.out" READY 300
if [ "$role" = host ]; then
  step "katzenrns founds g; katzenqt mints a voucher"
  echo "create g" >&4
  expect "$(kqt create-conv g kqt)" CREATED
  out=$(kqt voucher-mint g kqt); expect "$out" "VOUCHER="
  code=$(sed -n 's/^VOUCHER=//p' <<< "$out" | tail -1)
  step "katzenrns inducts katzenqt (reads the voucher through the bridge)"
  echo "invite g $code" >&4
  expect "$(kqt voucher-await g)" JOINED
else
  step "katzenqt founds g; katzenrns mints a voucher"
  expect "$(kqt create-conv g kqt)" CREATED
  echo "join g" >&4
  wait_for "$work/rns.out" "VOUCHER="
  code=$(sed -n 's/^VOUCHER=//p' "$work/rns.out" | tail -1)
  step "katzenqt inducts katzenrns (reads the voucher through the bridge)"
  expect "$(kqt voucher-induct g meshy "$code")" "INDUCTED="
  wait_for "$work/rns.out" "JOINED g"
fi
step "each sends"
echo "send g from the mesh" >&4
expect "$(kqt send g "from the mixnet")" SENT
step "katzenqt reads katzenrns"
expect "$(kqt read g 600 "from the mesh")" "RECV=from the mesh"
step "katzenrns reads katzenqt"
wait_for "$work/rns.out" "LINE g .*: from the mixnet"
# Acknowledgements ride on the next message each side sends.
step "each sends again, carrying its acknowledgements"
echo "send g mesh read you" >&4
expect "$(kqt send g "mixnet read you")" SENT
expect "$(kqt read g 600 "mesh read you")" "RECV=mesh read you"
wait_for "$work/rns.out" "LINE g .*: mixnet read you"
step "each sees its first message acknowledged"
for i in $(seq 1 60); do
  echo "show g" >&4
  sleep 5
  grep -q "meshy ✓✓: from the mesh" "$work/rns.out" && break
done
grep -q "meshy ✓✓: from the mesh" "$work/rns.out" || { echo "FAIL: katzenrns saw no acknowledgement from katzenqt"; tail -30 "$work/rns.out"; exit 1; }
# katzenqt keeps whose acknowledgements it has accepted per conversation; the mesh member's
# must be among them.
info=$(kqt_local info)
grep -q '"name": "g".*"acked": {[^}]*"meshy"' <<< "$info" || { echo "FAIL: katzenqt accepted no acknowledgement from the mesh"; echo "$info"; exit 1; }
echo "quit" >&4
step "ok: katzenrns and katzenqt read and acknowledge each other through the bridge ($role)"
