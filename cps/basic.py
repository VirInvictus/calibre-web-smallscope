#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2018-2019 OzzieIsaacs, cervinko, jkrehm, bodybybuddha, ok11,
#                            andy29485, idalin, Kyosfonica, wuqi, Kennyl, lemmsh,
#                            falgh1, grunjol, csitko, ytils, xybydy, trasba, vrabe,
#                            ruben-herold, marblepebble, JackED42, SiphonSquirrel,
#                            apetresc, nanu-c, mutschler, carderne
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.


from flask import Blueprint, abort
from flask_babel import gettext as _
from flask_babel import get_locale
from flask import request, redirect, url_for

from . import logger, isoLanguages
from . import config
from . import calibre_db
from .usermanagement import login_required_if_no_ano
from .render_template import render_title_template

try:
    from natsort import natsorted as sort
except ImportError:
    sort = sorted  # Just use regular sort then, may cause issues with badly named pages in cbz/cbr files

basic = Blueprint("basic", __name__)

log = logger.create()


@basic.route("/basic", methods=["GET"])
@login_required_if_no_ano
def index():
    term = request.args.get("query", "")  # default to showing all books
    limit = 15
    page = int(request.args.get("page") or 1)
    # Phase 7 swap: the fallback page searches through cquarry's engine too
    # (spec 13's one-grammar rule applied to the last holdout) and pages via
    # quarry_grid. Fixed title-sort: the basic page has no sort header.
    from .carrel_search import LibraryUnavailable, SearchError, resolve
    from .quarry_grid import grid

    search_error = None
    try:
        ids = resolve(term) if term else None
    except SearchError as ex:
        ids, search_error = [], str(ex)
    except LibraryUnavailable:
        # The library cannot be read, which is not a bad query: answer the
        # instance's standard degraded status, like /statistics.
        abort(503)
    # ids=None (no query) pages the whole library; an empty set (query
    # matched nothing) pages nothing — grid keeps the two apart.
    entries, pagination = grid(page, ids, per_page=limit)
    result_count = pagination.total
    return render_title_template(
        "basic_index.html",
        searchterm=term,
        pagination=pagination,
        query=term,
        adv_searchterm=term,
        entries=entries,
        result_count=result_count,
        search_error=search_error,
        title=_("Search"),
        page="search",
    )


@basic.route("/basic_book/<int:book_id>")
@login_required_if_no_ano
def show_book(book_id):
    entries = calibre_db.get_book_read_archived(
        book_id, config.config_read_column, allow_show_archived=True
    )
    if entries:
        entry = entries[0]
        for lang_index in range(0, len(entry.languages)):
            entry.languages[lang_index].language_name = isoLanguages.get_language_name(
                get_locale(), entry.languages[lang_index].lang_code
            )
        entry.ordered_authors = calibre_db.order_authors([entry])

        return render_title_template(
            "basic_detail.html",
            entry=entry,
            is_xhr=request.headers.get("X-Requested-With") == "XMLHttpRequest",
            title=entry.title,
            page="book",
        )
    else:
        log.debug(
            "Selected book is unavailable. File does not exist or is not accessible"
        )
        return redirect(url_for("basic.index"))
