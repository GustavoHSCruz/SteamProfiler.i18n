#!/usr/bin/env python3
"""Writes what is in locales/ into the repositories that serve it.

Nothing here runs on the server or in a browser: this builds the files the
other repos ship, and those files are committed there. A clone of the front
still renders without ever having seen this repo, which is the whole reason the
artifacts are checked in rather than built at deploy time.

  locales/site/<lang>.js     ->  SteamProfiler.Front  site/dict.<lang>.js
                                                    next/src/i18n/<lang>.ts
  locales/embed/<lang>.json  ->  SteamProfiler.Api    i18n_words.py
  both of them, counted      ->  SteamProfiler.Front  site/coverage.js, next/src/i18n/coverage.ts

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

The third artifact is not strings but a count of them, and it is written from
here for the same reason the dictionaries are: once English is merged underneath
a language, the file that ships can no longer say which half was translated.
See coverage() - it is what the /translate page draws.

`--check` builds everything in memory and compares it against what is on disk
in those repos, so the pre-push hook can refuse a push that would leave a
consumer holding last week's strings. Consumers that are not checked out beside
this one are skipped and named, because a translator has only this repo.
"""

import argparse
import html
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
SITE = HERE / 'locales' / 'site'
EMBED = HERE / 'locales' / 'embed'
UI = HERE / 'locales' / 'ui'

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
    out += merged_lines(lang)
    out.append('};')
    return '\n'.join(out) + '\n'


def merged_lines(lang):
    """English as the skeleton, this language's lines swapped in, indented
    one level less than in locales/ because the built object sits at the top."""
    mine = entries_of(SITE / f'{lang}.js') if lang != 'en' else {}
    out = []
    for line in body_of(SITE / 'en.js'):
        m = ENTRY.match(line)
        if m and m.group(1) in mine:
            line = mine[m.group(1)]
        out.append(line[2:] if line.startswith('  ') else line)
    return out


def next_dict(lang):
    """The same dictionary as site_dict(), as a module the React front imports.

    Same merge, same lines, so the two fronts cannot say different things
    while both are served. What differs is the wrapper: a module has no
    global plural() to call, so each file gets one bound to its own language,
    and the build splits the five into chunks so a reader downloads one."""
    out = [
        f'/* steamprofiler.org - every string on the site, in {lang}.',
        '',
        '   GENERATED from the SteamProfiler.i18n repository - do not edit here.',
        '   Built from the same lines as site/dict.<lang>.js, with English',
        '   underneath, so a key this language has not translated is English. */',
        '',
        "import { pluralFor } from './plural';",
        "import type { Dict } from './plural';",
        '',
        f"const plural = pluralFor('{lang}');",
        '',
        'const DICT: Dict = {',
    ]
    out += merged_lines(lang)
    out += ['};', '', 'export default DICT;']
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


# ── The coverage panel ───────────────────────────────────────────────
# The site has a page that says how much of it each language has, and it is
# built here rather than fetched from anywhere: this is the only place that
# knows what a language has translated, because the dictionary it ships has
# English merged underneath and can no longer tell the two apart.
#
# The groups exist so the page can say where the weight is. A translator
# deciding whether to start sees that the game pages are two fifths of every
# string on the site, and that the rest of it is smaller than it looks. They
# are prefixes and not sections, because the section comments in en.js are
# prose for a person reading the file and were never meant to partition it.
#
# The labels are not here. They are `tr.grp_*` in the dictionary, like every
# other word a reader sees, so this writes the id and the page translates it.
GROUPS = (('g', 'games'), ('em', 'generator'), ('fx', 'franchises'),
          ('dash', 'dash'), ('priv', 'privacy'))


def group_of(key):
    prefix = key.split('.', 1)[0]
    for head, name in GROUPS:
        if prefix == head:
            return name
    return 'rest'


def coverage():
    """What each language has, counted against English.

    Deliberately has no timestamp in it. A date would make this file differ
    from itself every day, which would turn `--check` - the hook that refuses a
    push where a consumer has drifted - into an alarm that goes off on its own
    every morning."""
    english = entries_of(SITE / 'en.js')
    order = [name for _, name in GROUPS] + ['rest']
    weight = {name: 0 for name in order}
    for key in english:
        weight[group_of(key)] += 1

    languages = []
    for lang in langs(SITE, '.js'):
        mine = english if lang == 'en' else entries_of(SITE / f'{lang}.js')
        done = {name: 0 for name in order}
        for key in mine:
            # A key this language has that English does not is a key that was
            # renamed or deleted there. check.js refuses that; counting it
            # here would report 101% while it is being fixed.
            if key in english:
                done[group_of(key)] += 1
        languages.append({'code': lang, 'done': sum(done.values()),
                          'groups': done})

    embed_langs = langs(EMBED, '.json')
    words = json.loads((EMBED / 'en.json').read_text(encoding='utf-8'))
    # Heaviest first, because the list is read to decide where to start.
    # `rest` is pinned to the end wherever it lands: it is a residual and not
    # a topic, and a translator cannot choose to do it first.
    named = sorted((n for n in order if n != 'rest'),
                   key=lambda n: -weight[n])
    return {'keys': len(english),
            'groups': [{'id': name, 'keys': weight[name]}
                       for name in named + ['rest']],
            'languages': languages,
            'embed': {'words': len(words), 'languages': embed_langs}}


def coverage_js():
    body = json.dumps(coverage(), ensure_ascii=False, indent=2)
    return '\n'.join([
        '/* steamprofiler.org - how much of the site each language has.',
        '',
        '   GENERATED from the SteamProfiler.i18n repository - do not edit here.',
        '   Its build.py writes this file; /translate is the page that reads it.',
        '',
        '   Counted against English, which is the source of truth and therefore',
        '   always whole. A language is at less than 100% when keys of English',
        '   are missing from it, and those reach a reader as English rather than',
        '   as a raw key - which is why a translation can be published at 40% and',
        '   still answer for every string on the site. */',
        '',
        'const COVERAGE = ' + body + ';',
    ]) + '\n'


def coverage_ts():
    """The same counts for the React front, which imports them."""
    body = json.dumps(coverage(), ensure_ascii=False, indent=2)
    return '\n'.join([
        '/* steamprofiler.org - how much of the site each language has.',
        '',
        '   GENERATED from the SteamProfiler.i18n repository - do not edit here.',
        '   The same counts as site/coverage.js; /translate is the page that reads it. */',
        '',
        'const COVERAGE = ' + body + ';',
        '',
        'export default COVERAGE;',
    ]) + '\n'


def ui_docs(root):
    """Build an offline-capable documentation page from UI structure and i18n strings.

    English renders the static HTML and is the runtime fallback. All supported
    UI dictionaries ship inline so language switching also works from disk.
    """
    template = (root / 'steamprofiler-ui/docs/index.template.html').read_text(encoding='utf-8')
    dictionaries = {lang: json.loads((UI / f'{lang}.json').read_text(encoding='utf-8'))
                    for lang in langs(UI, '.json')}
    english = dictionaries['en']

    def replace(match):
        mode, key = match.groups()
        if key not in english:
            raise ValueError(f'UI template references unknown English key: {key}')
        return english[key] if mode == 'ui_html' else html.escape(english[key], quote=True)

    # Interpolate only the template; dictionary values are never interpreted as templates.
    built = re.sub(r'\{\{(ui_html|ui)\.([a-zA-Z0-9_.-]+)\}\}', replace, template)
    built = re.sub(r'\{\{ui_number\.(\d+)\}\}', lambda match: f'{int(match[1]):,}', built)
    payload = json.dumps(dictionaries, ensure_ascii=False, separators=(',', ':')).replace('<', r'\u003c')
    return '<!-- GENERATED from docs/index.template.html and SteamProfiler.i18n/locales/ui/. -->\n' + built.replace('{{UI_LOCALES}}', payload)


def targets(root=HERE.parent):
    """(name, path under --root, what belongs in it). One dictionary per
    language, the words the API paints, and the counts /translate draws."""
    out = [('front', pathlib.Path(f'steamprofiler-front/site/dict.{lang}.js'),
            (lambda l: lambda: site_dict(l))(lang))
           for lang in langs(SITE, '.js')]
    out += [('front', pathlib.Path(f'steamprofiler-front/next/src/i18n/{lang}.ts'),
             (lambda l: lambda: next_dict(l))(lang))
            for lang in langs(SITE, '.js')]
    out.append(('api', pathlib.Path('steamprofiler-api/i18n_words.py'), embed_words))
    out.append(('front', pathlib.Path('steamprofiler-front/site/coverage.js'), coverage_js))
    out.append(('front', pathlib.Path('steamprofiler-front/next/src/i18n/coverage.ts'), coverage_ts))
    if (root / 'steamprofiler-ui/docs/index.template.html').exists():
        out.append(('ui', pathlib.Path('steamprofiler-ui/index.html'), lambda: ui_docs(root)))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check', action='store_true',
                    help='compare instead of writing; exit 1 if a consumer has drifted')
    ap.add_argument('--root', default=str(HERE.parent), type=pathlib.Path,
                    help='folder the consumer repos sit in (default: beside this one)')
    ap.add_argument('--consumer', choices=['front', 'api', 'ui'],
                    help='build or check only this consumer')
    args = ap.parse_args()

    drift, skipped = [], []
    for name, rel, render in targets(args.root):
        if args.consumer and args.consumer != name:
            continue
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
