# Carrel (calibre-web fork)

A fork of [calibre-web](https://github.com/janeczku/calibre-web) turned into a
single-user reading room for one curated Calibre library.

A carrel is a private desk in a library. That is the whole design brief: no
accounts, no sharing, no dashboard. One reader, 7,000 books, and an interface
that gets out of the way.

**This repository holds the code.** The contract, the theme source, and the
roadmap live in the companion repo,
[Carrel](https://github.com/VirInvictus/Carrel). Read its `spec.md` before
changing semantics here.

![The library grid](docs/screenshots/browse.png)

## What is different from upstream

**No login.** `cps/single_user.py` authenticates the owner on every request, so
upstream's 154 `@login_required` decorators pass untouched and rebases onto new
tags stay clean. `/login`, `/logout`, `/register` and user management answer
404. Deleting that one module restores stock behaviour exactly.

**The library is read-only, structurally.** `metadata.db` is attached with
`?mode=ro` at every connection site and the read-status toggle refuses writes.
No code path can modify the library, and the tests prove it by checksumming the
database around the attempts.

**Calibre's search grammar.** Upstream has none: it lowercases the term and
hands it to FTS5 as a phrase, so every field-prefixed query matches as literal
text and finds nothing. Carrel evaluates through
[CalibreQuarry](https://github.com/VirInvictus/cquarry)'s stdlib port of
Calibre's expression parser. Measured against the live library:

| query | upstream | Carrel |
| --- | --- | --- |
| `author:"King"` | 0 | 55 |
| `title:Dune` | 0 | 11 |
| `tags:Fic.Fantasy` | 0 | 1368 |
| `rating:>=4` | 0 | 130 |
| `#audience:Rin` | 0 | 244 |
| `author:King AND title:Tower` | 0 | 1 |

Field prefixes, boolean logic, grouping, hierarchical tags, custom columns and
`vl:` references all behave as they do in Calibre. A malformed query reports
the grammar's own message rather than quietly returning nothing.

**Wings.** Calibre virtual libraries surfaced as browse sections, evaluated
through the same engine, so a wing in the sidebar and a `vl:` search agree by
construction.

**Saved Searches.** Calibre’s named searches join them as a second sidebar section (`/saved/<name>`), resolved through cquarry 1.1’s `search:"Name"` interpolation with cycle detection — so the sidebar, the search bar and the desktop Calibre GUI can never disagree about what a saved search matches.

**Calibre-exact wing layout.** The sidebar follows the ordering stored in Calibre’s own preferences (`virt_libs_order`) and hides what Calibre hides (`virt_libs_hidden`), so the web room arranges wings exactly as the desktop does.

**Reader state.** The detail page shows where you are in a book (latest-device progress from `last_read_positions`) and how many highlights it holds (from `annotations`) — both read through cquarry’s extractors, never guessed.

**A category browser over the dot taxonomy.** Only leaf tags are assigned in
this library (`Fic.Fantasy.Epic.Gods` exists; `Fic.Fantasy` does not), so every
path prefix becomes a browsable node that accumulates its descendants. The
counts match the search engine exactly: Fic 3440, Fic.Fantasy 1368, NonFic
3004.

**Ctrl-K.** A fuzzy jumper over every wing, author, series, category and page,
6,975 destinations for this library, cached on the database's mtime. Type
something that is not a destination and it offers to search for it instead, so
one keystroke reaches both.

![The command palette](docs/screenshots/palette.png)

**Statistics** computed live from `metadata.db`. Axes with a real distribution
get ranked ledgers; degenerate ones (2% rated, 98% unread, 96% one source) get
a single readout line each, because a chart of one slice looks broken.

![Statistics](docs/screenshots/stats.png)

**Series awareness.** The detail page states where a book sits, how many of the
series you hold, and which numbers are missing. It never claims how long a
series is, because the library cannot know that.

**Keyboard.** `j`/`k` walk the grid, `g`/`G` jump to the ends, Enter opens, `/`
focuses search, Ctrl-K opens the palette.

| The category tree | On a phone |
| :---: | :---: |
| <img src="docs/screenshots/categories.png" width="290" alt="The category tree, expanded"> | <img src="docs/screenshots/mobile.png" width="290" alt="Carrel on a phone"> |

**Removed:** uploads, shelves, metadata editing, Kobo sync, Goodreads, email,
registration, public sharing, the task queue, advanced search, Discover, Hot
Books and Top Rated. Routes are disabled rather than deleted, so the diff
against upstream stays small and rebase-friendly.

## Running it

The venv holds the dependencies; the `calibreweb` wheel is uninstalled and the
fork runs from source (the 0.6.26 tree has no `src/` layout, so an editable
install is not possible).

```sh
CALIBRE_DBPATH=~/.calibre-web ~/.local/share/carrel/venv/bin/python cps.py -i 0.0.0.0
```

or `just serve` from the Carrel repo, which is the same command.

> **The bind address matters.** There is no authentication. Binding anything
> other than `127.0.0.1` means every device on the network can read the whole
> library and reach the admin pane. That is a deliberate choice for a trusted
> home network run on demand, and the wrong one for an always-on host. See
> spec §11.3.

## Tests

```sh
~/.local/share/carrel/venv/bin/python -m unittest discover -s tests
```

108 collected tests in about a second (60 unique test methods; the quarry
extensions inherit the base fixtures), against a fixture library built from a real Calibre
schema dump. They cover the enum read column and all four status badges, write
refusal with checksum proof, the read-only attachment, the disabled routes,
wing membership, category roll-up, the search grammar, the statistics metrics,
the currently-reading shelf,
and that every palette destination lands on the thing it names.

The harness does not log in. That is deliberate: every assertion doubles as a
regression guard on the single-user shim.

## Layout

New code lives in new modules, so the diff against upstream stays legible.

| file | what it does |
| --- | --- |
| `cps/single_user.py` | authenticates the owner; seals the credential routes |
| `cps/smallscope.py` | disables blueprints and the cut browse surfaces |
| `cps/carrel_search.py` | resolves a query through cquarry's engine |
| `cps/quarry_grid.py` | the cquarry data layer: build_detail, entity id sets, search sorts, pagination |
| `cps/reading_shelf.py` | the currently-reading shelf |
| `cps/library_cache.py` | mtime + UUID keyed caches over cquarry reads |
| `cps/page_count.py` | cached page counts for progress fractions |
| `cps/wings.py` | virtual libraries as browse sections |
| `cps/saved_searches.py` | Calibre saved searches as browse sections |
| `cps/reader_state.py` | per-book progress and highlights on the detail page |
| `cps/categories.py` | the dot-taxonomy tree and its roll-up |
| `cps/palette.py` | the Ctrl-K index |
| `cps/series_info.py` | series position, holdings and gaps |
| `cps/stats.py` | headless metrics for the statistics surfaces |
| `cps/static/js/` | `palette.js`, `cattree.js`, `keynav.js`, all vanilla |

`cps/static/css/kanagawa-dragon.css` is **vendored** from the Carrel repo via
`just sync-theme`. Never edit it here.

## Working on this fork

Work only on the `smallscope` branch, cut from upstream tag `0.6.26`. `master`
tracks upstream and is never committed to. Rebases onto new upstream tags are
deliberate events, not routine pulls.

Upstream code style applies inside upstream files: this is GPL-3.0 third-party
code, so match what is there rather than imposing personal conventions.

![A book](docs/screenshots/detail.png)

## Licence

GPL-3.0, inherited from calibre-web. Upstream's documentation, issue tracker
and community live at
[janeczku/calibre-web](https://github.com/janeczku/calibre-web). This fork is a
personal instance and is not a place to report upstream bugs.

### support

if any of this is useful to you and you'd like to chip in:

- liberapay · [liberapay.com/bdkl](https://liberapay.com/bdkl/)
- bitcoin
  ```
  bc1qkge6zr45tzqfwfmvma2ylumt6mg7wlwmhr05yv
  ```
