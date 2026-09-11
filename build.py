#!/usr/bin/env python3
"""Writes what is in locales/ into the repositories that serve it.

Nothing here runs on the server or in a browser: this builds the two files the
other repos ship, and those files are committed there. A clone of the front
still renders without ever having seen this repo, which is the whole reason the
artifacts are checked in rather than built at deploy time.

  locales/site/<lang>.js     ->  SteamProfiler.Front  site/dict.js
  locales/embed/<lang>.json  ->  SteamProfiler.Api    i18n_words.py

`--check` builds both in memory and compares them against what is on disk in
those repos, so the pre-push hook can refuse a push that would leave a consumer
holding last week's strings. Consumers that are not checked out beside this one
are skipped and named, because a translator has only this repo.
"""

import argparse
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
SITE = HERE / 'locales' / 'site'
EMBED = HERE / 'locales' / 'embed'

# English first because it is the fallback, then the rest in alphabetical order.
def langs(folder, suffix):
    found = sorted(p.stem for p in folder.glob('*' + suffix))
    if 'en' not in found:
        sys.exit(f'{folder} has no en{suffix}, and English is the fallback')
    return ['en'] + [l for l in found if l != 'en']


def body_of(path):
    """The object literal inside locales/site/<lang>.js, spliced out whole.

    Verbatim on purpose - comments, order and the function-valued strings that
    call plural() all survive, which they would not if this parsed the file
    into data and printed it back."""
    lines = path.read_text(encoding='utf-8').split('\n')
    start = next(i for i, l in enumerate(lines) if l.rstrip().endswith('= {')) + 1
    end = len(lines) - 1
    while lines[end].strip() != '};':
        end -= 1
    return lines[start:end]


def site_dict():
    out = [
        '/* steamprofiler.org - every string on the site, in the languages it speaks.',
        '',
        '   GENERATED from the SteamProfiler.i18n repository - do not edit here. A',
        '   fix to a string, or a language, is a pull request there; running its',
        '   build.py writes this file. Editing this copy works until the next build',
        '   and then quietly goes away.',
        '',
        '   English is the source of truth and the fallback: a key missing from',
        '   another language falls back to en rather than to nothing.',
        '',
        '   Keys read as paths - `nav.*` chrome, `land.*` the landing page, `dash.*`',
        '   the dashboard, `g.*` the game pages, `msg.*` messages, `sup.*` support,',
        '   `err.*` anything a visitor can be told went wrong. The last groups',
        '   (`arma.*`, `gmod.*`, `pd2.*`, …) are the keys the API sends instead of',
        '   prose, so the server never has to know which language anyone reads. */',
        '',
        'const DICT = {',
    ]
    names = langs(SITE, '.js')
    for i, lang in enumerate(names):
        if i:
            out.append('')
        out.append(f'  {lang}: {{')
        out += body_of(SITE / f'{lang}.js')
        out.append('  },')
    out.append('};')
    return '\n'.join(out) + '\n'


def embed_words():
    out = [
        '"""The words the API paints into an image, in the languages the site speaks.',
        '',
        'GENERATED from the SteamProfiler.i18n repository - do not edit here.',
        '',
        'An image carries its own text, so unlike every other route on this service',
        'these strings cannot be left to the browser. Only the handful a chart needs;',
        'everything else the API answers with is a key the front translates.',
        '"""',
        '',
        'WORDS = {',
    ]
    for lang in langs(EMBED, '.json'):
        words = json.loads((EMBED / f'{lang}.json').read_text(encoding='utf-8'))
        out.append(f'    {json.dumps(lang)}: {{')
        for key, value in words.items():
            out.append(f'        {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},')
        out.append('    },')
    out.append('}')
    return '\n'.join(out) + '\n'


TARGETS = [
    ('front', pathlib.Path('steamprofiler-front/site/dict.js'), site_dict),
    ('api', pathlib.Path('steamprofiler-api/i18n_words.py'), embed_words),
]


def resolve(rel, root):
    return (root / rel).resolve()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true',
                    help='compare instead of writing; exit 1 if a consumer has drifted')
    ap.add_argument('--root', default=str(HERE.parent), type=pathlib.Path,
                    help='folder the consumer repos sit in (default: beside this one)')
    args = ap.parse_args()

    drift, skipped = [], []
    for name, rel, render in TARGETS:
        path = resolve(rel, args.root)
        if not path.parent.is_dir():
            skipped.append(f'{name}: {path.parent} is not checked out')
            continue
        built = render()
        if args.check:
            have = path.read_text(encoding='utf-8') if path.exists() else ''
            if have != built:
                drift.append(f'{name}: {rel} does not match locales/')
            else:
                print(f'ok    {rel}')
        else:
            changed = not path.exists() or path.read_text(encoding='utf-8') != built
            path.write_text(built, encoding='utf-8')
            print(f'{"wrote" if changed else "same "} {rel}')

    for note in skipped:
        print(f'skip  {note}')
    if drift:
        print('\n'.join(drift), file=sys.stderr)
        print('run ./build.py to bring them up to date', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
