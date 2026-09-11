# -*- coding: utf-8 -*-

# Wings: Calibre virtual libraries as read-only browse sections
# (Carrel spec 8). Wing expressions live in metadata.db's
# preferences table and are evaluated by CalibreQuarry's stdlib port of
# Calibre's search grammar (including vl: cross-references, so the
# self-referential Unsorted wing parses). cquarry opens its own mode=ro
# connection; results are cached keyed on metadata.db's mtime, so any
# library change invalidates on the next request.

from flask import Blueprint, abort
from flask_babel import gettext as _

from . import logger
from .library_cache import LibraryCache, library_path
from . import quarry_grid
from .render_template import render_title_template
from .usermanagement import login_required_if_no_ano

wings = Blueprint("wings", __name__)
log = logger.create()


def _resolve_wings():
    from cquarry.db import CalibreDB

    with CalibreDB(library_path()) as quarry:
        names = quarry.get_virtual_libraries()
        # Mirror the Calibre GUI's own sidebar (cquarry 1.1): drop libraries
        # the user hid and follow the stored tab order; anything unknown to
        # that state keeps alphabetical order after the known ones.
        ui = quarry.get_vl_ui_state()
        hidden = {str(h).lower() for h in ui.get("hidden", [])}
        order = ui.get("order") or {}

        def sort_key(name):
            for key, pos in order.items():
                if str(key).lower() == name.lower():
                    try:
                        return (0, float(pos), name.lower())
                    except (TypeError, ValueError):
                        return (1, 0.0, name.lower())
            return (1, 0.0, name.lower())

        resolved = {}
        for name in sorted((n for n in names if n.lower() not in hidden), key=sort_key):
            # Per-name fault isolation: a wing whose expression cannot be
            # evaluated (a vl: target renamed or deleted in Calibre, a
            # corrupted preference) is skipped and logged. Before Phase 13
            # one broken wing raised out of the comprehension, which failed
            # the whole rebuild, which never updated the cache mtime, so
            # every page render re-paid the failure and the entire Wings
            # section vanished until the entry was fixed in Calibre.
            try:
                resolved[name] = frozenset(quarry.resolve_vl(name))
            except Exception as ex:
                log.error("Wing %r failed to resolve, skipping: %s", name, ex)
    log.info("Wings cache rebuilt: %d wings", len(resolved))
    return resolved


_cache = LibraryCache(_resolve_wings)


def _wing_ids():
    """Wing name -> frozenset of book ids, rebuilt when metadata.db changes."""
    return _cache.get()


@wings.app_context_processor
def inject_wings():
    try:
        resolved = _wing_ids()
    except Exception as ex:
        log.error("Wings unavailable: %s", ex)
        return {"wings_list": []}
    return {
        "wings_list": [
            {"name": name, "count": len(ids)} for name, ids in resolved.items()
        ]
    }


@wings.route("/wings/<path:name>", defaults={"page": 1})
@wings.route("/wings/<path:name>/page/<int:page>")
@login_required_if_no_ano
def show_wing(name, page):
    try:
        resolved = _wing_ids()
    except Exception as ex:
        log.error("Wings unavailable: %s", ex)
        resolved = {}
    # Wing URLs are case-insensitive like every surface beneath them
    # (Phase 13): the sidebar spells the wing its own way and the route
    # matches any casing. The canonical spelling drives the title and the
    # active marker so the sidebar highlights the real entry.
    key = next((k for k in resolved if k.lower() == name.lower()), None)
    if key is None:
        abort(404)
    entries, pagination = quarry_grid.grid(page, resolved[key])
    return render_title_template(
        "index.html",
        random=None,
        entries=entries,
        pagination=pagination,
        title=_("Wing: %(name)s", name=key),
        page="wings",
        wing_active=key,
    )
