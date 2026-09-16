#!/usr/bin/env bash
# Publishes what is in locales/ - the one command that makes a translation real.
#
# Merging a pull request here changes nothing on the site. The deploy watcher
# follows origin/main of the front and of the api, and this repository is
# neither: the strings only reach a reader when the files built from them are
# committed over there. That gap is what this closes.
#
#   pull here -> check the strings -> build -> commit and push each consumer
#
# The push is what publishes, exactly as it is in every other repository here,
# and each consumer's own pre-push hook runs its own suite on the way out. This
# script never deploys anything itself.
#
# It also says when a language cannot reach anyone yet. A dictionary is a file;
# a *language* is also a line in the nginx map that chooses which file to serve
# and an entry in LOCALES that puts it in the picker. Build a fourth language
# without those and the file is published, downloaded by nobody, and everything
# looks fine.
#
#   ./release.sh              pull, build, commit, push
#   ./release.sh --dry-run    say what it would do, touch nothing
#   ./release.sh --root DIR   look for the consumer repos in DIR
#
# Exit codes: 0 published (or nothing to publish), 1 refused, 2 published but a
# language still does not reach anyone.
set -uo pipefail
cd "$(dirname "$0")"

DRY=0
ROOT="$(cd .. && pwd)"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --root) shift; ROOT="$(cd "${1:?--root wants a directory}" && pwd)" ;;
    *) echo "unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

FRONT="$ROOT/steamprofiler-front"
API="$ROOT/steamprofiler-api"
UI="$ROOT/steamprofiler-ui"

die() { printf '\n%s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
run() { [ "$DRY" -eq 1 ] && { printf '       would: %s\n' "$*"; return 0; }; "$@"; }

# ── This repository has to be clean and current ──────────────────────
[ -z "$(git status --porcelain)" ] \
  || die "there is uncommitted work here. Commit or stash it: a release publishes
what is committed, and half a translation is worse than none."

git fetch -q origin || die "could not reach origin"
if [ -n "$(git rev-parse --abbrev-ref '@{u}' 2>/dev/null)" ]; then
  behind="$(git rev-list --count HEAD..'@{u}')"
  ahead="$(git rev-list --count '@{u}'..HEAD)"
  if [ "$behind" -gt 0 ] && [ "$ahead" -eq 0 ]; then
    say "== pulling $behind commit(s) merged here"
    run git pull -q --ff-only || die "the pull did not fast-forward"
  elif [ "$behind" -gt 0 ]; then
    die "this branch and origin/main have both moved. Sort that out first."
  fi
fi

# ── The strings themselves ───────────────────────────────────────────
say "== checking the strings"
node check.js || die "the strings did not pass. Nothing was published."

# ── This repository goes out first ───────────────────────────────────
# The commit that lands in each consumer names the sha these strings came from,
# and a sha nobody else has is a receipt pointing at nothing. So the source is
# published before the files built from it, never after.
mine="$(git rev-list --count '@{u}'..HEAD 2>/dev/null || echo 0)"
if [ "$mine" -gt 0 ]; then
  say ""
  say "== pushing $mine commit(s) of strings"
  git log --oneline '@{u}'..HEAD | sed 's/^/       /'
  run git push -q || die "the push was refused. Read what the checks said:
nothing was published anywhere."
fi

# ── Each consumer has to be somewhere a commit can land ──────────────
consumers=""
[ -d "$FRONT/.git" ] && consumers="$consumers front"
[ -d "$API/.git" ]   && consumers="$consumers api"
[ -d "$UI/.git" ] && [ -f "$UI/docs/index.template.html" ] && consumers="$consumers ui"
[ -d "$FRONT/.git" ] || die "$FRONT is not a checkout, and the site dictionary lives there."

for name in $consumers; do
  case "$name" in front) repo="$FRONT" ;; api) repo="$API" ;; ui) repo="$UI" ;; esac
  branch="$(git -C "$repo" rev-parse --abbrev-ref HEAD)"
  [ "$branch" = "main" ] || die "$name is on '$branch', not main."
  git -C "$repo" fetch -q origin || die "$name: could not reach origin"
  behind="$(git -C "$repo" rev-list --count HEAD..'@{u}')"
  ahead="$(git -C "$repo" rev-list --count '@{u}'..HEAD)"
  if [ "$ahead" -gt 0 ]; then
    say ""
    git -C "$repo" log --oneline '@{u}'..HEAD
    die "$name has commits of its own that were never pushed. Push or drop them
first: this script would carry them along with the strings, and they are not
part of this translation."
  fi
  if [ "$behind" -gt 0 ]; then
    say "== $name is $behind commit(s) behind, pulling"
    run git -C "$repo" pull -q --ff-only || die "$name: the pull did not fast-forward"
  fi
done

# ── Build ────────────────────────────────────────────────────────────
say ""
say "== building"
python3 build.py --root "$ROOT" || die "the build failed"

# ── Commit and push what actually changed ────────────────────────────
here_sha="$(git rev-parse --short HEAD)"
here_subject="$(git log -1 --pretty=%s)"
published=0

for name in $consumers; do
  case "$name" in
    front) repo="$FRONT"; paths=('site/dict.*.js' 'site/coverage.js') ;;
    api)   repo="$API";   paths=('i18n_words.py') ;;
    ui)    repo="$UI";    paths=('index.html') ;;
  esac
  # An array, because the front has two kinds of built file now: the
  # dictionaries and the coverage counts /translate draws. One string with a
  # space in it would have been a single pathspec containing a space, which
  # matches nothing and would have published the dictionaries while quietly
  # leaving the counts behind.
  #
  # Each element quoted, so the glob is git's and is resolved inside that
  # repository rather than against whatever happens to sit next to this script.
  changed="$(git -C "$repo" status --porcelain -- "${paths[@]}")"
  if [ -z "$changed" ]; then
    say "== $name already has these strings"
    continue
  fi
  say ""
  say "== $name"
  printf '%s\n' "$changed" | sed 's/^/       /'
  message="$(printf 'Atualiza os textos a partir do repo de idiomas\n\nSteamProfiler.i18n em %s, "%s".\nArquivo gerado pelo build.py de lá; não editar aqui.\n' "$here_sha" "$here_subject")"
  # add before commit, because a language that is new here is a file git has
  # never seen, and a pathspec commit does not pick up what is untracked. The
  # pathspec on the commit is what keeps unrelated work in that repository out
  # of it.
  run git -C "$repo" add -- "${paths[@]}" || die "$name: could not stage the files"
  run git -C "$repo" commit -q -m "$message" -- "${paths[@]}" || die "$name: the commit failed"
  run git -C "$repo" push -q || die "$name: the push was refused. Its own checks
run on the way out, so read what they said - nothing was published for $name."
  published=1
  say "       pushed"
done

# ── A language that cannot reach anybody ─────────────────────────────
# Built, committed, and served to nobody: nginx chooses the file from a map
# with one line per language, and the picker only offers what LOCALES names.
stranded=""
for file in locales/site/*.js; do
  lang="$(basename "$file" .js)"
  missing=""
  grep -q "'$lang':" "$FRONT/site/i18n.js" \
    || missing="$missing
       $FRONT/site/i18n.js: add '$lang' to LOCALES, STORES, MONEY, LANG_NAMES and pickLang()"
  if [ -d "$API/.git" ]; then
    grep -q "sp-lang=$lang" "$API/nginx.conf" \
      || missing="$missing
       $API/nginx.conf: add the sp-lang=$lang line to the map, and to the Accept-Language guess"
  else
    missing="$missing
       (the api is not checked out here, so its nginx map could not be checked)"
  fi
  [ -n "$missing" ] && stranded="$stranded
  $lang reaches nobody yet:$missing"
done

say ""
if [ -n "$stranded" ]; then
  say "PUBLISHED, BUT NOT SERVED$stranded"
  say ""
  say "The dictionary is on the site and no reader can ask for it until those"
  say "lines exist. Both files are in the repositories named above."
  exit 2
fi

if [ "$published" -eq 1 ]; then
  say "published. The deploy watcher takes it from here."
else
  say "nothing to publish: every consumer already had these strings."
fi
