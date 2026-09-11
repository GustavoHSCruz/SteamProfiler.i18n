#!/usr/bin/env bash
# The whole suite. Run from the repo root.
#
# Two halves: the strings have to be sound on their own, and the copies the
# other repositories ship have to match them. The second half is skipped, by
# name, when those repositories are not checked out beside this one.
#
# `--strings` runs only the first half, and it is what the pre-push hook uses.
# The second half asks whether the consumers are up to date, which is a
# question about something release.sh is on its way to do: gating a push here
# on it would mean publishing the built files before the source they came from,
# and the two would sit waiting for each other forever.
set -u
cd "$(dirname "$0")"

ONLY_STRINGS=0
[ "${1:-}" = "--strings" ] && ONLY_STRINGS=1

fails=0
step() {
  local name="$1"; shift
  printf '\n== %s\n' "$name"
  if "$@"; then return 0; fi
  fails=$((fails + 1))
}

step "strings"        node check.js
[ "$ONLY_STRINGS" -eq 0 ] && step "built copies"   python3 build.py --check

printf '\n'
if [ "$fails" -ne 0 ]; then
  printf '%d step(s) failed\n' "$fails"
  exit 1
fi
printf 'all good\n'
