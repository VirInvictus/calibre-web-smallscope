#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2022 OzzieIsaacs
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


from flask import Blueprint, abort, request, redirect, url_for
from flask_babel import gettext as _

from . import logger
from .usermanagement import login_required_if_no_ano
from .render_template import render_title_template


search = Blueprint("search", __name__)

log = logger.create()


@search.route("/search", methods=["GET"])
@login_required_if_no_ano
def simple_search():
    term = request.args.get("query")
    if term:
        return redirect(
            url_for(
                "web.books_list", data="search", sort_param="stored", query=term.strip()
            )
        )
    else:
        return render_title_template(
            "search.html",
            searchterm="",
            result_count=0,
            title=_("Search"),
            page="search",
        )


def render_search_results(term, offset=None, order=None, limit=None, sort_param=None):
    # Carrel (spec 13): the bar evaluates through cquarry's Calibre-parity
    # engine instead of upstream's FTS5 phrase match, which had no grammar and
    # returned nothing for every field-prefixed query.
    from .carrel_search import LibraryUnavailable, SearchError, resolve

    search_error = None
    if term:
        try:
            ids = resolve(term)
        except SearchError as ex:
            ids, search_error = [], str(ex)
        except LibraryUnavailable:
            # The library cannot be read, which is not a bad query: answer
            # the instance's standard degraded status, like /statistics.
            abort(503)
        result_count = len(ids)
        page = (int(offset) // int(limit) + 1) if (offset and limit) else 1
        # Carrel: honour the sort header, now through cquarry's list_books
        # (Phase 7 swap; the ORM query builders are off this page). The
        # token→keys mapping carries the authaz/authza tie-break shape.
        from . import quarry_grid

        keys, descending = quarry_grid.search_sort(sort_param)
        entries, pagination = quarry_grid.grid(
            page, ids, sort=keys, descending=descending
        )
    else:
        entries = list()
        order = [None, None]
        pagination = result_count = None

    return render_title_template(
        "search.html",
        search_error=search_error,
        searchterm=term,
        pagination=pagination,
        query=term,
        adv_searchterm=term,
        entries=entries,
        result_count=result_count,
        title=_("Search"),
        page="search",
        order=order[1],
    )
