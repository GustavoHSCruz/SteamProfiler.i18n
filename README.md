# SteamProfiler.i18n

Every string steamprofiler.org shows a reader, in every language it speaks, and
the build that writes them into the two repositories that serve them.

The site is [SteamProfiler.Front](https://github.com/GustavoHSCruz/SteamProfiler.Front)
and the service behind it is private. Neither of them is where a translation is
written any more: they hold the built copy, this repository holds the source.

```
locales/site/<lang>.js     ->  SteamProfiler.Front   site/dict.<lang>.js
locales/embed/<lang>.json  ->  SteamProfiler.Api     i18n_words.py
```

A reader is served exactly one dictionary. `/dict.js` is not a file: nginx
picks `dict.pt.js` or `dict.ru.js` from the `sp-lang` cookie, falling back to
`Accept-Language` and then to English, and `serve.py` does the same three steps
in a local checkout. That is what the split is for. The old single file carried
every language and cost 152 KB gzipped for a reader who could only read one of
them; Portuguese is 48 KB and Russian 58 KB.

The fallback moved here as a consequence. There is no second dictionary in the
browser to fall back to, so each language is built as the English file with the
lines that language has translated swapped in: an untranslated key arrives as
English text, and a language that is 40% done still answers for 100% of the
keys.

## The two stores, and why they are not one

**`locales/site/`** is the dictionary the browser loads: a little over two
thousand strings, one file per language. A value is either a string or a small
function, because some sentences count things and a language that has plurals
has to pick the form itself:

```js
'cd.cards': (v) => `${v.n} ${plural(v.raw, ['card', 'cards'])}`,
```

That is why these files are JavaScript and not JSON. `plural()` lives in the
front's `i18n.js` and takes the raw number, never the formatted one, because
`1,001` is plural and `1.0` is not.

**`locales/embed/`** is the handful of words the API paints into an image.
An image carries its own text, so those cannot be left to the browser; they
are plain strings with no markup and no interpolation, which is why they are
JSON. Everything else the API answers with is a key (`@err.rate|n=6`), resolved
by the front against the dictionary above, so the server never has to know
which language anybody reads.

## How a string reaches a reader

```
./release.sh
  |
  +-- node check.js        refuses a broken translation
  +-- git push             this repository, source before anything built from it
  +-- ./build.py           writes dict.<lang>.js and i18n_words.py
  +-- commit + push        in the front and in the api, which is what publishes
```

**Merging a pull request here publishes nothing.** The deploy watcher follows
`origin/main` of the front and of the api, and this repository is neither: the
strings reach a reader when the files built from them are committed over there.
`./release.sh` is that step, and it is the whole of it. Each consumer's own
pre-push hook still runs its own suite on the way out, so a bad string is
refused by the repository it would have broken.

It stops short of one thing, on purpose, and says so loudly: a new language is
a file *and* a line in the nginx map that chooses which file to serve, and an
entry in `LOCALES` that puts it in the picker. Without those the dictionary is
published and nobody can ask for it, so `release.sh` names both places and
exits 2.

The built files are committed rather than generated at deploy time so that a
clone of the front still renders without ever having seen this repository.
`./build.py --check` is the other half of that deal: it fails when a consumer
is holding strings older than the ones here, and the pre-push hook runs it.

## What the checks refuse

`node check.js`, run by `./check.sh` and by the hook:

- **a variable only one language reaches for.** `{n}` renamed to `{nn}` prints
  a sentence with the number missing and nothing anywhere says so. The
  languages are read against each other, not against English: a variable
  English does not use is ordinary, because Russian needs the raw number to
  pick a plural where English just writes the word.
- **an unbalanced tag.** Values carry `<b>`, `<span>` and `<br>`. One that
  opens a tag and never closes it swallows the element it was dropped into.
- **a key missing from `locales/embed/`.** The API falls back a whole language
  at a time there, so a missing word is a crash while an image is being drawn,
  not English text on a Russian chart.
- **a key that is no longer in English.** English is the source of truth: a key
  only the translations still have is one that was renamed and left behind.
- **a key written twice in one file.** The browser keeps the last one and says
  nothing, so the first is a string somebody wrote, translated, and will never
  see on a page. There was one, and in Russian the two lines disagreed.

A key *missing* from a translation is not a failure. It falls back to English
by design, and `check.js` counts it so the report doubles as the todo list.

## Adding a language

Copy `locales/site/en.js` and `locales/embed/en.json` to the new code, translate,
run `node check.js` and `./release.sh`. Untranslated keys need not be deleted or
kept: what is missing comes out as English in the built file either way. That is
this repository done, and it is the smaller half: a language is also a
storefront, a currency and a date format, so the two consumers need to be told
it exists.

In `SteamProfiler.Front`:

- `site/i18n.js` - `LOCALES`, `STORES`, `MONEY`, `LANG_NAMES` and the browser
  sniffing in `pickLang()`. A language missing from `LOCALES` is one the picker
  will not offer and `pickLang()` will never return, so its dictionary would be
  built and never served. `STORES` is why the language picker is also the
  currency picker: Steam prices each region on its own, so the site asks the
  storefront that language belongs to instead of converting.
- `tools/check-html.py`, `tools/check-prices.js`, `tools/check-policy.js`,
  `tools/gen-policy.js` - each carries its own `LANGS`.
- `site/banned.html`, `appeal.html`, `appeal-sent.html`, `abuse.html` - the ban
  wall and the ticket form are served without the dictionary, so they spell all
  the languages out in the markup.

- `serve.py` and, in the API repo, `nginx.conf` and `admin/server.py` - the
  three places that choose which dictionary to send. They read the languages
  off disk, so a new file is picked up on its own; what they do carry by hand
  is the `Accept-Language` guess for a first visit.

In the API: `meta.py` (`STORE_LANGUAGES`, `COUNTRIES`), `api.py` (`OG_LOCALE`)
and `blog.py` (`LANGS`, which decides how many translations a post gets).

## Running it

```
./release.sh            publish: check, push, build, commit and push the consumers
./release.sh --dry-run  say what that would do and touch nothing
./check.sh              the whole suite: check.js, then build.py --check
./check.sh --strings    only the strings, which is what the pre-push hook runs
./build.py              write the built files into the sibling repositories
./build.py --root ~/somewhere/else
```

Needs `python3` and `node`, both only to run these two scripts. The consumers
are found beside this checkout and skipped, by name, when they are not there,
because a translator has only this repository.

## Licence

MIT, same as the front. See `LICENSE`.
