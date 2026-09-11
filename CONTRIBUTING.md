# Contributing

Translations and fixes are welcome, including a language that is not here yet.
This is a hobby project, so review may take a few days.

## Running it

```
git config core.hooksPath .githooks   # once, per checkout
./check.sh
```

The first line points git at the versioned pre-push hook, which runs the checks
before anything leaves your machine.

You do not need the site checked out to translate. `check.sh` validates this
repository on its own and tells you which consumers it could not find. If the
other repositories *are* beside this one, `./build.py` writes the built files
into them and `./build.py --check` says whether they have drifted.

To see a string in place, clone
[SteamProfiler.Front](https://github.com/GustavoHSCruz/SteamProfiler.Front)
next to this one, run `./build.py`, then `python3 serve.py` there. It forwards
`/api/` to the live site, so a fresh checkout renders real profiles.

## House style

**No em dashes.** Use a spaced hyphen. This holds in every language and across
the whole codebase.

**English is the source of truth.** A key must exist in `en`; everything else
is optional and falls back to it. A `pt` or `ru` that is only a copy of the
English is worse than leaving the key out, because the fallback is invisible
and a copy looks translated.

**Translate the sentence, not the words.** The site talks like a person who
plays games, not like a dialog box. Where English is dry, the translation is
allowed to be dry in its own way rather than in English's way.

**Count with `plural()`, not with `if`.** It takes the raw number and the forms
for the language, and Russian passes three:

```js
'cd.cards': (v) => `${v.n} ${plural(v.raw, ['карточка', 'карточки', 'карточек'])}`,
```

`v.n` is the formatted number, which is what the reader sees. `v.raw` is the
number itself, which is what decides the form: `1,001` is plural and `1.0` is
not.

**Keep the markup.** A value that carries `<b>` or `<br>` carries it in every
language, in the place that language would put the emphasis.

**Leave the key alone.** Keys are addresses (`dash.badges_count`), not text.
Renaming one is a change in the front, not a translation.

## Before opening a PR

```
./check.sh
```

It refuses a renamed variable, an unbalanced tag, a word missing from
`locales/embed/`, and a key that is no longer in English. A key you have not
translated yet is counted, not refused, so the output doubles as what is left
to do.

You do not need to build anything for a pull request: the files the other
repositories ship are written on release, by `./release.sh`, after the merge.
Change `locales/` and leave the rest alone.

Russian is the one to eyeball for length: a layout that fits in English and
overflows in Russian is the common failure here.

## Adding a language

See the README. The short version is that this repository is the small half:
copy `en`, translate, and expect a follow-up pull request on the front for the
storefront, the currency and the date format.
