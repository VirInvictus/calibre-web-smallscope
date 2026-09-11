# -*- coding: utf-8 -*-

# Calibre-parity search (Carrel spec 13).
#
# Stock calibre-web has no expression grammar: search_query() lowercases the
# term and hands it to FTS5 as a phrase, so every Calibre-style query matches
# as literal text and returns nothing. Measured against the live library,
# author:"King" returned 0 where Calibre returns 55, and tags:Fic.Fantasy
# returned 0 where Calibre returns 1368.
#
# So the bar evaluates through cquarry's SearchEngine, the same engine wings.py
# already uses for virtual-library expressions. Field prefixes, boolean logic,
# grouping, hierarchical tags, custom columns (#audience:Rin) and vl:
# references all behave as they do in Calibre, including cquarry's documented
# deviations (stdlib re rather than regex, unicodedata rather than ICU,
# anchored tags:).
#
# A bare term keeps Calibre's semantics: substring across title, authors,
# author_sort, series, publisher, tags and comments. That is why a search for
# "King" matches "sorcerer-king" and equally "making" inside a description.
# It is faithful, and it is the cost of parity.

import sqlite3

from . import logger
from .library_cache import LibraryCache, library_path

log = logger.create()


class SearchError(Exception):
    """A query the grammar could not parse. Carries the engine's own message."""


class LibraryUnavailable(Exception):
    """The library behind the engine could not be opened or queried."""


def _open_quarry():
    from cquarry.db import CalibreDB

    log.info("Search engine rebound to metadata.db")
    return CalibreDB(library_path())


# The superseded connection is closed only once its replacement exists, so a
# failed rebuild leaves the working engine in place rather than a closed one.
_cache = LibraryCache(_open_quarry, dispose=lambda quarry: quarry.close())


def _quarry():
    """A cquarry CalibreDB, rebuilt when metadata.db changes.

    cquarry opens its own mode=ro connection, so this never widens the
    read-only guarantee in spec 7.
    """
    return _cache.get()


def resolve(term):
    """Query string -> list of book ids.

    Raises SearchError on a query the grammar cannot parse (a user error the
    callers render as a message) and LibraryUnavailable when the library
    itself cannot be read (a degraded instance, answered 503 like
    /statistics, not phrased as a bad query). Anything else is a bug and
    propagates.
    """
    from cquarry.search import ParseException

    try:
        return list(_quarry().search(term))
    except ParseException as ex:
        raise SearchError(str(ex)) from ex
    except (sqlite3.Error, OSError) as ex:
        # A vanished or unreadable metadata.db must not surface as "could
        # not parse that search" (Phase 13): the two failure classes get
        # different answers everywhere else in the fork, so they get
        # different exceptions here.
        log.error("Library unavailable for search %r: %s", term, ex)
        raise LibraryUnavailable(str(ex)) from ex
