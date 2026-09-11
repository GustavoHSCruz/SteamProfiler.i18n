/* Fails if a translation would break a page, and reports what is still
   untranslated without failing for it.

   The checks exist because of what each kind of mistake does to a reader:

     placeholders   a string that renames `{n}` prints a sentence with the
                    number missing - "you have  games" - and nothing anywhere
                    says so. The languages are read against each other rather
                    than against English: a variable only one of them reaches
                    for is a typo, while one that English does not use is
                    ordinary, because Russian needs the raw number to pick a
                    plural where English just writes the word.

     tag balance    values carry <b>, <span> and <br>. One that opens a tag and
                    does not close it swallows the rest of the element, which
                    is how a string breaks a layout it is not even near.

     the api words  embed.py falls back a whole language at a time, not a key
                    at a time: words(lang) returns the language's table, and a
                    key missing from it is a KeyError while an image is being
                    drawn. So parity there is a hard failure, unlike the site.

     site parity    the opposite: a key missing from pt falls back to English
                    by design, so it is counted and listed, not refused. What
                    is refused is a key no longer in English, because that is a
                    key that was renamed or deleted and left behind here.

   Run: node check.js */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const SITE = path.join(__dirname, 'locales', 'site');
const EMBED = path.join(__dirname, 'locales', 'embed');
const VOID = new Set(['br', 'hr', 'img', 'input', 'wbr']);

const fail = [];
const note = [];

/** English first: it is the fallback, and every other language is read against it. */
function languages(dir, ext) {
  const found = fs.readdirSync(dir).filter((f) => f.endsWith(ext)).map((f) => f.slice(0, -ext.length));
  if (!found.includes('en')) { fail.push(`${dir}: no en${ext}`); return []; }
  return ['en', ...found.filter((l) => l !== 'en').sort()];
}

/** A key written twice in the same file. The browser keeps the last one and
 *  says nothing, so the first is a string somebody wrote, translated, and will
 *  never see on a page. Invisible to the evaluated object, which is why this
 *  reads the source. */
function duplicates(lang) {
  const seen = new Set();
  const twice = [];
  for (const line of fs.readFileSync(path.join(SITE, `${lang}.js`), 'utf8').split('\n')) {
    const m = line.match(/^ {4}'([^']+)':/);
    if (!m) continue;
    if (seen.has(m[1])) twice.push(m[1]);
    seen.add(m[1]);
  }
  return twice;
}

/** One locale file, evaluated the way the browser will evaluate it. plural() is
 *  stubbed because it lives in the front's i18n.js, not here. */
function load(lang) {
  const file = path.join(SITE, `${lang}.js`);
  const ctx = { plural: (n, forms) => forms[0] };
  vm.createContext(ctx);
  try {
    vm.runInContext(fs.readFileSync(file, 'utf8') + `;globalThis.__D=DICT_${lang.toUpperCase()};`, ctx);
  } catch (e) {
    fail.push(`locales/site/${lang}.js did not load: ${e.message}`);
    return null;
  }
  return ctx.__D;
}

/** What a value prints, and which variables it asked for. A function-valued
 *  string is called with a Proxy so the names it reaches for are recorded
 *  rather than guessed from its source. */
function sample(value, where) {
  if (typeof value !== 'function') {
    return { text: String(value), vars: new Set([...String(value).matchAll(/\{(\w+)\}/g)].map((m) => m[1])) };
  }
  const vars = new Set();
  const spy = new Proxy({}, { get: (_, prop) => { if (typeof prop === 'string') vars.add(prop); return '1'; } });
  try {
    return { text: String(value(spy)), vars };
  } catch (e) {
    fail.push(`${where}: threw when called - ${e.message}`);
    return { text: '', vars };
  }
}

/** Tags a value opens and does not close, or closes and never opened. */
function tagTrouble(text) {
  const stack = [];
  for (const m of text.matchAll(/<(\/?)([a-zA-Z][a-zA-Z0-9]*)[^>]*?(\/?)>/g)) {
    const [, closing, tag, selfClosing] = m;
    const name = tag.toLowerCase();
    if (VOID.has(name) || selfClosing) continue;
    if (closing) {
      if (stack.pop() !== name) return `</${name}> with no <${name}> open`;
    } else {
      stack.push(name);
    }
  }
  return stack.length ? `<${stack[stack.length - 1]}> left open` : null;
}

// ── The site dictionary ──────────────────────────────────────────────
const siteLangs = languages(SITE, '.js');
const dicts = {};
for (const lang of siteLangs) dicts[lang] = load(lang);

if (dicts.en) {
  const english = Object.keys(dicts.en);
  const users = new Map();   // key -> variable -> the languages that reach for it

  for (const lang of siteLangs) {
    const dict = dicts[lang];
    if (!dict) continue;
    const keys = Object.keys(dict);
    const twice = duplicates(lang);
    if (twice.length) {
      fail.push(`${lang}: written twice, and only the last one is ever read: ${twice.join(', ')}`);
    }
    const gone = keys.filter((k) => !(k in dicts.en));
    if (gone.length) {
      fail.push(`${lang}: ${gone.length} key(s) not in English - renamed or deleted there: ${gone.slice(0, 8).join(', ')}`);
    }
    if (lang !== 'en') {
      const missing = english.filter((k) => !(k in dict));
      const done = english.length - missing.length;
      note.push(`${lang}: ${done}/${english.length} strings translated` +
        (missing.length ? ` · ${missing.length} still fall back to English` : ''));
    }
    for (const key of keys) {
      const here = sample(dict[key], `${lang} ${key}`);
      if (!users.has(key)) users.set(key, new Map());
      for (const name of here.vars) {
        const seen = users.get(key);
        seen.set(name, [...(seen.get(name) || []), lang]);
      }
      const trouble = tagTrouble(here.text);
      if (trouble) fail.push(`${lang} ${key}: ${trouble}`);
    }
  }

  /* A variable exactly one language asks for, where more than one language has
     the string. Nobody passes `v.doneRow` on purpose. */
  for (const [key, seen] of users) {
    const holders = siteLangs.filter((l) => dicts[l] && key in dicts[l]);
    if (holders.length < 2) continue;
    for (const [name, langs] of seen) {
      if (langs.length === 1) {
        fail.push(`${key}: only ${langs[0]} reaches for {${name}} - the other ${holders.length - 1} do not, so it is a misspelt name`);
      }
    }
  }
}

// ── The words the API paints ─────────────────────────────────────────
const embedLangs = languages(EMBED, '.json');
const tables = {};
for (const lang of embedLangs) {
  try {
    tables[lang] = JSON.parse(fs.readFileSync(path.join(EMBED, `${lang}.json`), 'utf8'));
  } catch (e) {
    fail.push(`locales/embed/${lang}.json did not parse: ${e.message}`);
  }
}
if (tables.en) {
  for (const lang of embedLangs) {
    if (!tables[lang]) continue;
    const missing = Object.keys(tables.en).filter((k) => !(k in tables[lang]));
    const extra = Object.keys(tables[lang]).filter((k) => !(k in tables.en));
    if (missing.length) fail.push(`embed ${lang}: missing ${missing.join(', ')} - embed.py falls back a whole language at a time, so this is a crash, not English text`);
    if (extra.length) fail.push(`embed ${lang}: ${extra.join(', ')} not in English`);
  }
  note.push(`embed: ${Object.keys(tables.en).length} words × ${embedLangs.length} languages`);
}

for (const line of note) console.log(line);
if (fail.length) {
  console.error('\n' + fail.join('\n'));
  console.error(`\n${fail.length} problem(s)`);
  process.exit(1);
}
console.log('strings ok');
