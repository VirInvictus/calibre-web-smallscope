# CLAUDE.md (Carrel-calibre-web)

Fork of janeczku/calibre-web carrying the code side of Carrel, a single-user
reading room for Brandon's curated Calibre library. **The contract lives in the
companion repo:** `~/.gitrepos/Carrel/` (`spec.md`, `roadmap.md`, `CLAUDE.md`).
Read those before changing anything here.

## Hard rules

- Work only on the `smallscope` branch (cut from tag `0.6.26`). `master`
  tracks upstream; never commit to it. The branch and `cps/smallscope.py` keep
  their original names on purpose: renaming them would churn the upstream diff
  for no benefit.
- `metadata.db` is attached read-only by design and must stay that way. No code
  path may write the library, and no test may touch `~/docs/Calibre Library/`.
  Tests use the fixture DB in `tests/`.
- `cps/static/css/kanagawa-dragon.css` is VENDORED from `Carrel/theme/` via
  `just sync-theme`; edit it there, not here.
- Keep the diff rebase-friendly: disable routes rather than delete files, put
  new code in new modules. (The one deletion is the dead ORM behind the
  sealed advsearch, 0.6.36: deliberate, patchnoted, and amended into
  Carrel's spec 6.2 on 2026-09-11.)
- Upstream code style applies in upstream files (GPL-3.0 third-party code;
  match what is there, not the personal conventions).
- A formatter hook once reformatted Python touched via agent Edit/Write
  tools, churning whole upstream files and poisoning rebases; the hook's
  registration was removed on 2026-09-05, but if one is ever re-registered
  the hazard returns. **Patch upstream `.py` files via shell (python
  heredoc) regardless**; the rebase-cleanliness motive stands on its own.
  Templates, CSS, and our own new modules are fine to edit normally.

## The modules that are ours

Everything Carrel adds lives in its own file, so the upstream diff stays small.

| file | what it does |
| --- | --- |
| `cps/single_user.py` | authenticates the owner per request; seals the credential paths (`/login`, `/logout`, `/register`, `/admin/user/new`, `/admin/usertable`) and, since 0.6.40, the admin machinery (`/get_update_status`, `/get_updater_status`, the user AJAX trio, `/ajax/pathchooser`, `/shutdown`, `/reconnect`) |
| `cps/smallscope.py` | `trim()` disables blueprints; `seal_browse_surfaces()` 404s `/hot`, `/rated`, `/discover`, `/advsearch`, `/table`, `/ajax/listbooks`, `/ajax/table_settings` by path prefix |
| `cps/carrel_search.py` | resolves the search bar through cquarry's engine |
| `cps/wings.py` | Calibre virtual libraries as browse sections |
| `cps/saved_searches.py` | Calibre saved searches as browse sections (cquarry `search:"Name"` interpolation) |
| `cps/reader_state.py` | detail-page progress + highlights via cquarry extractors |
| `cps/categories.py` | the dot taxonomy as a tree, with descendant roll-up |
| `cps/palette.py` | the Ctrl-K index, emitted as JS |
| `cps/quarry_grid.py` | the cquarry-backed grid: entry adapters + pagination shim over `list_books()`; also backs the /search results page (SEARCH_SORTS maps the sort header) and the /basic fallback search |
| `cps/reading_shelf.py` | the front page's Currently Reading shelf |
| `cps/series_info.py` | series position, holdings, gaps |
| `cps/stats.py` | headless metrics plus the `/statistics` route |
| `cps/static/js/` | `palette.js`, `cattree.js`, `keynav.js`, vanilla and self-contained |

All of them cache on `metadata.db`'s mtime **and the library's UUID**, the
idiom `wings.py` established and the cquarry 1.3 adoption generalized
(mtime-only is the documented degraded mode).

## Rebase posture

Against upstream tag `0.6.26`, four files carry the fork's mass and will
conflict on any upstream touch: `web.py` (~2000 changed lines),
`helper.py` (~1000), `opds.py` (~700), and the advsearch deletion in
`search.py` (~450 lines gone). Budget a session for those. The done-right
counterexamples: `main.py` (+32 lines, all registrations and seals),
`constants.py` (one line), `admin.py` (6), `db.py` (36, the two attach
sites and the enum branch). Rebases onto new upstream tags are deliberate
events (Carrel spec 3), not routine pulls.

## Things that will bite you

- **calibre-web has two URL shapes.** Overview pages are bare (`/author`,
  `/series`, `/category`); an individual entity is `/<data>/<sort_param>/<id>`.
  Getting it wrong does **not** 404: the id lands in `sort_param` and `book_id`
  silently defaults to 1, so the page renders fine and shows the wrong thing.
  This shipped once and was only caught by a human noticing that Stephen King
  opened Troy Denning.
- **Only leaf tags are assigned in this library.** `Fic.Fantasy.Epic.Gods`
  exists; `Fic.Fantasy` does not. Anything walking the taxonomy has to
  synthesise the intermediate nodes from path prefixes.
- **`index.html`'s sort header builds `web.books_list` URLs.** Any custom page
  reusing that template must be excluded from the header, or it 500s on a
  `BuildError`. Wings and categories both hit this.
- **Jinja macros do not see the template context** unless imported
  `with context`. The category tree failed silently this way: no error, nothing
  expanded.
- **Specificity, repeatedly.** Stock `style.css` and Bootstrap both carry
  selectors longer than the obvious override (`.container-fluid .book .cover
  span img` is 0-3-2, `.btn-primary.active` is 0-2-0, `.navbar-brand` uses
  `!important`). Source order does not save you.
- **The library cannot know how long a series is.** Calibre's highest index is
  what is held, not the length. Never render it as "of N".
- **flask-login is vendored as `cps.cw_login`.** The upstream package name does
  not resolve in this venv.

## Running and testing

```sh
# run (no login; -i binds the LAN deliberately, see spec 11.3)
CALIBRE_DBPATH=~/.calibre-web ~/.local/share/carrel/venv/bin/python cps.py -i 0.0.0.0
# or: just serve   (from the Carrel repo)

~/.local/share/carrel/venv/bin/python -m unittest discover -s tests
```

The test harness mirrors `main()`'s blueprint registration and **must be kept
in sync with it**. It has drifted twice: once when `seal_browse_surfaces` was
added to `main.py` but not the harness, so the Phase 8 route cuts were never
actually exercised. If you register something in `main.py`, register it there
too.

The harness does not log in. Every assertion therefore doubles as a regression
guard on `single_user.py`; commenting the shim out fails most of the suite.

## Screenshots

`docs/screenshots/` feeds the README. Regenerate after visual changes: warm the
cover cache first (the grid lazy-loads, so a cold headless shot photographs
empty tiles) and disable `dom.image-lazy-loading.enabled` in the capture
profile.
