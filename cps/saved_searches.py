# -*- coding: utf-8 -*-

# Saved Searches as browse sections (Carrel spec extension, cquarry 1.1).
#
# Calibre stores named searches in metadata.db's preferences table under the
# `saved_searches` key. Since cquarry 1.1 the engine interpolates them
# directly (`search:"Name"`), which means the web search bar and a resolved
# sidebar entry can never disagree about what a saved search matches: both go
# through the same grammar evaluation as Wings.
#
# Same shape as wings.py: resolve once per library revision, cache on
# metadata.db's mtime, expose a sidebar list plus one route per search.

from flask import Blueprint, abort
from flask_babel import gettext as _

from . import logger
from .library_cache import LibraryCache, library_path
from . import quarry_grid
from .render_template import render_title_template
from .usermanagement import login_required_if_no_ano

saved_searches = Blueprint("saved_searches", __name__)
log = logger.create()


def _resolve_saved():
    from cquarry.db import CalibreDB

    with CalibreDB(library_path()) as quarry:
        names = quarry.get_saved_searches()
        resolved = {}
        for name in names:
            # Per-name fault isolation, same shape as wings.py: one entry
            # the grammar cannot evaluate (a name containing a quote breaks
            # the interpolation, a renamed target raises) is skipped and
            # logged instead of failing the whole rebuild on every request
            # and vanishing the entire Saved Searches section.
            try:
                resolved[name] = frozenset(quarry.search('search:"%s"' % name))
            except Exception as ex:
                log.error("Saved search %r failed to resolve, skipping: %s", name, ex)
    log.info("Saved-search cache rebuilt: %d searches", len(resolved))
    return resolved


_cache = LibraryCache(_resolve_saved)


def _saved_ids():
    """Saved-search name -> frozenset of book ids, rebuilt on library change."""
    return _cache.get()


@saved_searches.app_context_processor
def inject_saved_searches():
    try:
        resolved = _saved_ids()
    except Exception as ex:
        log.error("Saved searches unavailable: %s", ex)
        return {"saved_searches_list": []}
    return {
        "saved_searches_list": [
            {"name": name, "count": len(ids)} for name, ids in resolved.items()
        ]
    }


@saved_searches.route("/saved/<path:name>", defaults={"page": 1})
@saved_searches.route("/saved/<path:name>/page/<int:page>")
@login_required_if_no_ano
def show_saved(name, page):
    try:
        resolved = _saved_ids()
    except Exception as ex:
        log.error("Saved searches unavailable: %s", ex)
        resolved = {}
    # Case-insensitive like wings (Phase 13); the canonical spelling wins.
    key = next((k for k in resolved if k.lower() == name.lower()), None)
    if key is None:
        abort(404)
    # A saved search that currently matches nothing is still a real search:
    # render an empty page rather than 404 so the sidebar link keeps working.
    entries, pagination = quarry_grid.grid(page, resolved[key] or frozenset())
    return render_title_template(
        "index.html",
        random=None,
        entries=entries,
        pagination=pagination,
        title=_("Saved Search: %(name)s", name=key),
        page="saved_searches",
        wing_active=key,
    )
