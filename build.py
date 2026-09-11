#!/usr/bin/env python3
"""Writes what is in locales/ into the repositories that serve it.

Nothing here runs on the server or in a browser: this builds the files the
other repos ship, and those files are committed there. A clone of the front
still renders without ever having seen this repo, which is the whole reason the
artifacts are checked in rather than built at deploy time.

  locales/site/<lang>.js     ->  SteamProfiler.Front  site/dict.<lang>.js
  locales/embed/<lang>.json  ->  SteamProfiler.Api    i18n_words.py

**One file per language, and the fallback is resolved here.** A reader used to
download every language in order to read in one of them. Now the browser is
served exactly one file, chosen from the `sp-lang` cookie by nginx, and by
serve.py in a local checkout, both answering at /dict.js. The dictionary costs
a third of what it did.

The price is that a missing string can no longer fall back at runtime: there is
nothing to fall back to in the file that arrived. So it falls back here
instead. Each language is built as the English file with the lines that
language has translated swapped in, which means an untranslated key reaches the
page as English rather than as a raw key, and a language that is 40% done still
answers for 100% of them. Every entry is one line, which is what makes the swap
a swap and not a parse.

`--check` builds everything in memory and compares it against what is on disk
in those repos, so the pre-push hook can refuse a push that would leave a
consumer holding last week's strings. Consumers that are not checked out beside
this one are skipped and named, because a translator has only this repo.
"""

import argparse
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SITE = HERE / 'locales' / 'site'
EMBED = HERE / 'locales' / 'embed'

ENTRY = re.compile(r"^ {4}'((?:[^'\\]|\\.)*)':")


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


def entries_of(path):
    """{key: the whole line it is written on}. Every entry is one line, which
    check.js enforces, so a translation is a line and merging is a swap."""
    out = {}
    for line in body_of(path):
        m = ENTRY.match(line)
        if m:
            out[m.group(1)] = line
    return out


def site_dict(lang):
    """One language, with English underneath it.

    The English file is the skeleton - its order, its section comments, its
    lines - and every key this language has translated replaces the English
    line in place. What is left untranslated stays English, which is the
    fallback that used to happen in the reader's browser."""
    mine = entries_of(SITE / f'{lang}.js') if lang != 'en' else {}
    out = [
        f'/* steamprofiler.org - every string on the site, in {lang}.',
        '',
        '   GENERATED from the SteamProfiler.i18n repository - do not edit here. A',
        '   fix to a string, or a language, is a pull request there; running its',
        '   build.py writes this file. Editing this copy works until the next build',
        '   and then quietly goes away.',
        '',
        '   One language per file, and a reader is served exactly one of them:',
        '   nginx picks it from the `sp-lang` cookie, serve.py does the same in a',
        '   local checkout, and both answer at /dict.js. So there is no fallback',
        '   left at runtime and none is needed - a key this language has not',
        '   translated is already sitting here in English.',
        '',
        '   Keys read as paths - `nav.*` chrome, `land.*` the landing page, `dash.*`',
        '   the dashboard, `g.*` the game pages, `msg.*` messages, `sup.*` support,',
        '   `err.*` anything a visitor can be told went wrong. The last groups',
        '   (`arma.*`, `gmod.*`, `pd2.*`, …) are the keys the API sends instead of',
        '   prose, so the server never has to know which language anyone reads. */',
        '',
        f"const DICT_LANG = '{lang}';",
        'const DICT = {',
    ]
    for line in body_of(SITE / 'en.js'):
        m = ENTRY.match(line)
        if m and m.group(1) in mine:
            line = mine[m.group(1)]
        out.append(line[2:] if line.startswith('  ') else line)
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


def targets():
    """(name, path under --root, what belongs in it). One dictionary per
    language, plus the words the API paints."""
    out = [('front', pathlib.Path(f'steamprofiler-front/site/dict.{lang}.js'),
            (lambda l: lambda: site_dict(l))(lang))
           for lang in langs(SITE, '.js')]
    out.append(('api', pathlib.Path('steamprofiler-api/i18n_words.py'), embed_words))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true',
                    help='compare instead of writing; exit 1 if a consumer has drifted')
    ap.add_argument('--root', default=str(HERE.parent), type=pathlib.Path,
                    help='folder the consumer repos sit in (default: beside this one)')
    args = ap.parse_args()

    drift, skipped = [], []
    for name, rel, render in targets():
        path = (args.root / rel).resolve()
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
