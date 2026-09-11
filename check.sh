#!/usr/bin/env bash
# The whole suite. Run from the repo root, and by .githooks/pre-push.
#
# Two halves: the strings have to be sound on their own, and the copies the
# other repositories ship have to match them. The second half is skipped, by
# name, when those repositories are not checked out beside this one.
set -u
cd "$(dirname "$0")"

fails=0
step() {
  local name="$1"; shift
  printf '\n== %s\n' "$name"
  if "$@"; then return 0; fi
  fails=$((fails + 1))
}

step "strings"        node check.js
step "built copies"   python3 build.py --check

printf '\n'
if [ "$fails" -ne 0 ]; then
  printf '%d step(s) failed\n' "$fails"
  exit 1
fi
printf 'all good\n'
