# SteamProfiler.i18n

Every string steamprofiler.org shows a reader, in every language it speaks, and
the build that writes them into the two repositories that serve them.

The site is [SteamProfiler.Front](https://github.com/GustavoHSCruz/SteamProfiler.Front)
and the service behind it is private. Neither of them is where a translation is
written any more: they hold the built copy, this repository holds the source.

```
locales/site/<lang>.js     ->  SteamProfiler.Front   site/dict.js
locales/embed/<lang>.json  ->  SteamProfiler.Api     i18n_words.py
```

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
edit locales/                 node check.js      refuses a broken translation
  -> ./build.py               writes site/dict.js and i18n_words.py
  -> commit in all three      the built copies are checked in on purpose
  -> git push in front/api    which is what publishes (see those repos)
```

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

A key *missing* from a translation is not a failure. It falls back to English
by design, and `check.js` counts it so the report doubles as the todo list.

## Adding a language

Copy `locales/site/en.js` and `locales/embed/en.json` to the new code, translate,
run `node check.js` and `./build.py`. That is this repository done, and it is the
smaller half: a language is also a storefront, a currency and a date format, so
the two consumers need to be told it exists.

In `SteamProfiler.Front`:

- `site/i18n.js` - `LOCALES`, `STORES`, `MONEY`, `LANG_NAMES` and the browser
  sniffing in `pickLang()`. `STORES` is why the language picker is also the
  currency picker: Steam prices each region on its own, so the site asks the
  storefront that language belongs to instead of converting.
- `tools/check-html.py`, `tools/check-prices.js`, `tools/check-policy.js`,
  `tools/gen-policy.js` - each carries its own `LANGS`.
- `site/banned.html`, `appeal.html`, `appeal-sent.html`, `abuse.html` - the ban
  wall and the ticket form are served without the dictionary, so they spell all
  the languages out in the markup.

In the API: `meta.py` (`STORE_LANGUAGES`, `COUNTRIES`), `api.py` (`OG_LOCALE`)
and `blog.py` (`LANGS`, which decides how many translations a post gets).

## Running it

```
./check.sh          the whole suite: check.js, then build.py --check
./build.py          write the built files into the sibling repositories
./build.py --root ~/somewhere/else
```

Needs `python3` and `node`, both only to run these two scripts. The consumers
are found beside this checkout and skipped, by name, when they are not there,
because a translator has only this repository.

## Licence

MIT, same as the front. See `LICENSE`.
