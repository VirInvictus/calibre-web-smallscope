# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2018-2019 OzzieIsaacs, cervinko, jkrehm, bodybybuddha, ok11,
#                            andy29485, idalin, Kyosfonica, wuqi, Kennyl, lemmsh,
#                            falgh1, grunjol, csitko, ytils, xybydy, trasba, vrabe,
#                            ruben-herold, marblepebble, JackED42, SiphonSquirrel,
#                            apetresc, nanu-c, mutschler
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

import datetime
from urllib.parse import unquote_plus

from flask import Blueprint, request, render_template, make_response, abort, g, jsonify
from flask_babel import get_locale
from flask_babel import gettext as _


from sqlalchemy.sql.expression import func, text, or_, and_, true
from sqlalchemy.exc import InvalidRequestError, OperationalError

from . import logger, config, db, calibre_db, ub, isoLanguages, constants
from .usermanagement import requires_basic_auth_if_no_ano, auth
from .helper import get_download_link, get_book_cover
from .pagination import Pagination
from .web import render_read_books
from . import quarry_grid
from .library_cache import quarry


opds = Blueprint("opds", __name__)

log = logger.create()


def _int_param(name, default=0):
    """A query parameter as an int, or the default when absent or garbage.

    OPDS clients hand over offsets as arbitrary strings; a bad one used to
    escape `int()` as a 500 instead of degrading to the first page.
    Negative values clamp to 0 for the same reason.
    """
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return default


@opds.route("/opds/")
@opds.route("/opds")
@requires_basic_auth_if_no_ano
def feed_index():
    return render_xml_template("index.xml")


@opds.route("/opds/osd")
@requires_basic_auth_if_no_ano
def feed_osd():
    return render_xml_template("osd.xml", lang="en-EN")


# @opds.route("/opds/search", defaults={'query': ""})
@opds.route("/opds/search/<path:query>")
@requires_basic_auth_if_no_ano
def feed_cc_search(query):
    # Handle strange query from Libera Reader with + instead of spaces
    plus_query = unquote_plus(
        request.environ["RAW_URI"].split("/opds/search/")[1]
    ).strip()
    return feed_search(plus_query)


@opds.route("/opds/search", methods=["GET"])
@requires_basic_auth_if_no_ano
def feed_normal_search():
    return feed_search(request.args.get("query", "").strip())


@opds.route("/opds/books")
@requires_basic_auth_if_no_ano
def feed_booksindex():
    letters = _first_letters(
        row["title_sort"] or row["title"] for row in quarry().get_all_books()
    )
    return _letter_elements(letters, "opds.feed_letter_books")


@opds.route("/opds/books/letter/<book_id>")
@requires_basic_auth_if_no_ano
def feed_letter_books(book_id):
    # Phase 7: ids + paging through cquarry's grid (include_comments feeds
    # the content block; cc=[] skips the custom-column block until a cc
    # adapter exists).
    off = _int_param("offset")
    page = int(off / (int(config.config_books_per_page)) + 1)
    all_ids = quarry_grid.all_ids()
    if book_id != "00":
        rows = quarry().get_all_books()
        wanted = {
            row["id"]
            for row in rows
            if (row["title_sort"] or "").upper().startswith(book_id)
        }
        ids = sorted(wanted)
    else:
        ids = all_ids
    entries, pagination = quarry_grid.grid(page, ids, include_comments=True)
    cc = []
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/new")
@requires_basic_auth_if_no_ano
def feed_new():
    if not auth.current_user().check_visibility(constants.SIDEBAR_RECENT):
        abort(404)
    off = _int_param("offset")
    page = int(off / (int(config.config_books_per_page)) + 1)
    entries, pagination = quarry_grid.grid(
        page, None, sort=("timestamp",), descending=True, include_comments=True
    )
    cc = []
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/discover")
@requires_basic_auth_if_no_ano
def feed_discover():
    if not auth.current_user().check_visibility(constants.SIDEBAR_RANDOM):
        abort(404)
    import random as _random

    picks = _random.sample(
        quarry_grid.all_ids(),
        min(config.config_books_per_page, len(quarry_grid.all_ids())),
    )
    entries, pagination = quarry_grid.grid(1, picks, include_comments=True)
    cc = []
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/rated")
@requires_basic_auth_if_no_ano
def feed_best_rated():
    if not auth.current_user().check_visibility(constants.SIDEBAR_BEST_RATED):
        abort(404)
    off = _int_param("offset")
    page = int(off / (int(config.config_books_per_page)) + 1)
    ids = quarry_grid.ids_with("rating", 10)
    entries, pagination = quarry_grid.grid(
        page, ids, sort=("timestamp",), descending=True, include_comments=True
    )
    cc = []
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/hot")
@requires_basic_auth_if_no_ano
def feed_hot():
    if not auth.current_user().check_visibility(constants.SIDEBAR_HOT):
        abort(404)
    off = _int_param("offset")
    all_books = (
        ub.session.query(ub.Downloads, func.count(ub.Downloads.book_id))
        .order_by(func.count(ub.Downloads.book_id).desc())
        .group_by(ub.Downloads.book_id)
    )
    hot_books = all_books.offset(off).limit(config.config_books_per_page)
    entries = list()
    for book in hot_books:
        query = calibre_db.generate_linked_query(config.config_read_column, db.Books)
        download_book = (
            query.filter(calibre_db.common_filters())
            .filter(book.Downloads.book_id == db.Books.id)
            .first()
        )
        if download_book:
            entries.append(download_book)
        else:
            ub.delete_download(book.Downloads.book_id)
    num_books = entries.__len__()
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        num_books,
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/author")
@requires_basic_auth_if_no_ano
def feed_authorindex():
    if not auth.current_user().check_visibility(constants.SIDEBAR_AUTHOR):
        abort(404)
    letters = _first_letters(
        e["sort"] or e["name"] for e in quarry().get_entities("authors")
    )
    return _letter_elements(letters, "opds.feed_letter_author")


@opds.route("/opds/author/letter/<book_id>")
@requires_basic_auth_if_no_ano
def feed_letter_author(book_id):
    if not auth.current_user().check_visibility(constants.SIDEBAR_AUTHOR):
        abort(404)
    off = _int_param("offset")
    letter = (
        true() if book_id == "00" else func.upper(db.Authors.sort).startswith(book_id)
    )
    entries = (
        calibre_db.session.query(db.Authors)
        .join(db.books_authors_link)
        .join(db.Books)
        .filter(calibre_db.common_filters())
        .filter(letter)
        .group_by(text("books_authors_link.author"))
        .order_by(db.Authors.sort)
    )
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        entries.count(),
    )
    entries = entries.limit(config.config_books_per_page).offset(off).all()
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=entries,
        folder="opds.feed_author",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/author/<int:book_id>")
@requires_basic_auth_if_no_ano
def feed_author(book_id):
    return render_xml_dataset(db.Authors, book_id)


@opds.route("/opds/publisher")
@requires_basic_auth_if_no_ano
def feed_publisherindex():
    if not auth.current_user().check_visibility(constants.SIDEBAR_PUBLISHER):
        abort(404)
    off = _int_param("offset")
    entries = (
        calibre_db.session.query(db.Publishers)
        .join(db.books_publishers_link)
        .join(db.Books)
        .filter(calibre_db.common_filters())
        .group_by(text("books_publishers_link.publisher"))
        .order_by(db.Publishers.sort)
        .limit(config.config_books_per_page)
        .offset(off)
    )
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        len(calibre_db.session.query(db.Publishers).all()),
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=entries,
        folder="opds.feed_publisher",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/publisher/<int:book_id>")
@requires_basic_auth_if_no_ano
def feed_publisher(book_id):
    return render_xml_dataset(db.Publishers, book_id)


@opds.route("/opds/category")
@requires_basic_auth_if_no_ano
def feed_categoryindex():
    if not auth.current_user().check_visibility(constants.SIDEBAR_CATEGORY):
        abort(404)
    letters = _first_letters(e["name"] for e in quarry().get_entities("tags"))
    return _letter_elements(letters, "opds.feed_letter_category")


@opds.route("/opds/category/letter/<book_id>")
@requires_basic_auth_if_no_ano
def feed_letter_category(book_id):
    if not auth.current_user().check_visibility(constants.SIDEBAR_CATEGORY):
        abort(404)
    off = _int_param("offset")
    letter = true() if book_id == "00" else func.upper(db.Tags.name).startswith(book_id)
    entries = (
        calibre_db.session.query(db.Tags)
        .join(db.books_tags_link)
        .join(db.Books)
        .filter(calibre_db.common_filters())
        .filter(letter)
        .group_by(text("books_tags_link.tag"))
        .order_by(db.Tags.name)
    )
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        entries.count(),
    )
    entries = entries.offset(off).limit(config.config_books_per_page).all()
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=entries,
        folder="opds.feed_category",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/category/<int:book_id>")
@requires_basic_auth_if_no_ano
def feed_category(book_id):
    return render_xml_dataset(db.Tags, book_id)


@opds.route("/opds/series")
@requires_basic_auth_if_no_ano
def feed_seriesindex():
    if not auth.current_user().check_visibility(constants.SIDEBAR_SERIES):
        abort(404)
    letters = _first_letters(
        e["sort"] or e["name"] for e in quarry().get_entities("series")
    )
    return _letter_elements(letters, "opds.feed_letter_series")


@opds.route("/opds/series/letter/<book_id>")
@requires_basic_auth_if_no_ano
def feed_letter_series(book_id):
    if not auth.current_user().check_visibility(constants.SIDEBAR_SERIES):
        abort(404)
    off = _int_param("offset")
    letter = (
        true() if book_id == "00" else func.upper(db.Series.sort).startswith(book_id)
    )
    entries = (
        calibre_db.session.query(db.Series)
        .join(db.books_series_link)
        .join(db.Books)
        .filter(calibre_db.common_filters())
        .filter(letter)
        .group_by(text("books_series_link.series"))
        .order_by(db.Series.sort)
    )
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        entries.count(),
    )
    entries = entries.offset(off).limit(config.config_books_per_page).all()
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=entries,
        folder="opds.feed_series",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/series/<int:book_id>")
@requires_basic_auth_if_no_ano
def feed_series(book_id):
    off = _int_param("offset")
    page = int(off / (int(config.config_books_per_page)) + 1)
    ids = quarry_grid.ids_for_entity("series", book_id)
    entries, pagination = quarry_grid.grid(
        page, ids, sort=("series_index",), include_comments=True
    )
    cc = []
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/ratings")
@requires_basic_auth_if_no_ano
def feed_ratingindex():
    if not auth.current_user().check_visibility(constants.SIDEBAR_RATING):
        abort(404)
    off = _int_param("offset")
    entries = (
        calibre_db.session.query(
            db.Ratings,
            func.count("books_ratings_link.book").label("count"),
            (db.Ratings.rating / 2).label("name"),
        )
        .join(db.books_ratings_link)
        .join(db.Books)
        .filter(calibre_db.common_filters())
        .group_by(text("books_ratings_link.rating"))
        .order_by(db.Ratings.rating)
        .all()
    )

    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        len(entries),
    )
    element = list()
    for entry in entries:
        element.append(FeedObject(entry[0].id, _("{} Stars").format(entry.name)))
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=element,
        folder="opds.feed_ratings",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/ratings/<book_id>")
@requires_basic_auth_if_no_ano
def feed_ratings(book_id):
    return render_xml_dataset(db.Ratings, book_id)


@opds.route("/opds/formats")
@requires_basic_auth_if_no_ano
def feed_formatindex():
    if not auth.current_user().check_visibility(constants.SIDEBAR_FORMAT):
        abort(404)
    off = _int_param("offset")
    entries = (
        calibre_db.session.query(db.Data)
        .join(db.Books)
        .filter(calibre_db.common_filters())
        .group_by(db.Data.format)
        .order_by(db.Data.format)
        .all()
    )
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        len(entries),
    )
    element = list()
    for entry in entries:
        element.append(FeedObject(entry.format, entry.format))
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=element,
        folder="opds.feed_format",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/formats/<book_id>")
@requires_basic_auth_if_no_ano
def feed_format(book_id):
    off = _int_param("offset")
    page = int(off / (int(config.config_books_per_page)) + 1)
    ids = quarry_grid.ids_with("formats", book_id.upper())
    entries, pagination = quarry_grid.grid(
        page, ids, sort=("timestamp",), descending=True, include_comments=True
    )
    cc = []
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/language")
@opds.route("/opds/language/")
@requires_basic_auth_if_no_ano
def feed_languagesindex():
    if not auth.current_user().check_visibility(constants.SIDEBAR_LANGUAGE):
        abort(404)
    off = _int_param("offset")
    # Phase 7: language facets from cquarry's entity rollup.
    if auth.current_user().filter_language() == "all":
        languages = [
            type("Lang", (), {"lang_code": e["name"], "name": e["name"]})()
            for e in quarry().get_entities("languages")
            if e["count"]
        ]
    else:
        languages = [
            type(
                "Lang",
                (),
                {
                    "lang_code": auth.current_user().filter_language(),
                    "name": isoLanguages.get_language_name(
                        get_locale(), auth.current_user().filter_language()
                    ),
                },
            )
        ]
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        len(languages),
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=languages,
        folder="opds.feed_languages",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/language/<int:book_id>")
@requires_basic_auth_if_no_ano
def feed_languages(book_id):
    off = _int_param("offset")
    entries, __, pagination = calibre_db.fill_indexpage(
        (int(off) / (int(config.config_books_per_page)) + 1),
        0,
        db.Books,
        db.Books.languages.any(db.Languages.id == book_id),
        [db.Books.timestamp.desc()],
        True,
        config.config_read_column,
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


@opds.route("/opds/shelfindex")
@requires_basic_auth_if_no_ano
def feed_shelfindex():
    if not (auth.current_user().is_authenticated or g.allow_anonymous):
        abort(404)
    off = _int_param("offset")
    shelf = (
        ub.session.query(ub.Shelf)
        .filter(
            or_(ub.Shelf.is_public == 1, ub.Shelf.user_id == auth.current_user().id)
        )
        .order_by(ub.Shelf.name)
        .all()
    )
    number = len(shelf)
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        number,
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml",
        listelements=shelf,
        folder="opds.feed_shelf",
        pagination=pagination,
        cc=cc,
    )


@opds.route("/opds/shelf/<int:book_id>")
@requires_basic_auth_if_no_ano
def feed_shelf(book_id):
    if not (auth.current_user().is_authenticated or g.allow_anonymous):
        abort(404)
    off = _int_param("offset")
    if auth.current_user().is_anonymous:
        shelf = (
            ub.session.query(ub.Shelf)
            .filter(ub.Shelf.is_public == 1, ub.Shelf.id == book_id)
            .first()
        )
    else:
        shelf = (
            ub.session.query(ub.Shelf)
            .filter(
                or_(
                    and_(
                        ub.Shelf.user_id == int(auth.current_user().id),
                        ub.Shelf.id == book_id,
                    ),
                    and_(ub.Shelf.is_public == 1, ub.Shelf.id == book_id),
                )
            )
            .first()
        )
    result = list()
    pagination = list()
    # user is allowed to access shelf
    if shelf:
        result, __, pagination = calibre_db.fill_indexpage(
            (int(off) / (int(config.config_books_per_page)) + 1),
            config.config_books_per_page,
            db.Books,
            ub.BookShelf.shelf == shelf.id,
            [ub.BookShelf.order.asc()],
            True,
            config.config_read_column,
            ub.BookShelf,
            ub.BookShelf.book_id == db.Books.id,
        )
        # delete shelf entries where book is not existent anymore, can happen if book is deleted outside calibre-web
        wrong_entries = (
            calibre_db.session.query(ub.BookShelf)
            .join(db.Books, ub.BookShelf.book_id == db.Books.id, isouter=True)
            .filter(db.Books.id == None)
            .all()
        )
        for entry in wrong_entries:
            log.info("Not existing book {} in {} deleted".format(entry.book_id, shelf))
            try:
                ub.session.query(ub.BookShelf).filter(
                    ub.BookShelf.book_id == entry.book_id
                ).delete()
                ub.session.commit()
            except (OperationalError, InvalidRequestError) as e:
                ub.session.rollback()
                log.error_or_exception("Settings Database error: {}".format(e))
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template("feed.xml", entries=result, pagination=pagination, cc=cc)


@opds.route("/opds/download/<book_id>/<book_format>/")
@requires_basic_auth_if_no_ano
def opds_download_link(book_id, book_format):
    if not auth.current_user().role_download():
        return abort(401)
    client = "kobo" if "Kobo" in request.headers.get("User-Agent") else ""
    return get_download_link(book_id, book_format.lower(), client)


@opds.route("/ajax/book/<string:uuid>/<library>")
@opds.route("/ajax/book/<string:uuid>", defaults={"library": ""})
@requires_basic_auth_if_no_ano
def get_metadata_calibre_companion(uuid, library):
    entry = (
        calibre_db.session.query(db.Books)
        .filter(db.Books.uuid.like("%" + uuid + "%"))
        .first()
    )
    if entry is not None:
        js = render_template("json.txt", entry=entry)
        response = make_response(js)
        response.headers["Content-Type"] = "application/json; charset=utf-8"
        return response
    else:
        return ""


@opds.route("/opds/stats")
@requires_basic_auth_if_no_ano
def get_database_stats():
    # Phase 7: counts from cquarry's cached rows.
    stat = dict()
    stat["books"] = len(quarry().get_all_books())
    stat["authors"] = len(quarry().get_entities("authors"))
    stat["categories"] = len(quarry().get_entities("tags"))
    stat["series"] = len(quarry().get_entities("series"))
    return make_response(jsonify(stat))


@opds.route("/opds/thumb_240_240/<book_id>")
@opds.route("/opds/cover_240_240/<book_id>")
@opds.route("/opds/cover_90_90/<book_id>")
@opds.route("/opds/cover/<book_id>")
@requires_basic_auth_if_no_ano
def feed_get_cover(book_id):
    return get_book_cover(book_id)


@opds.route("/opds/readbooks")
@requires_basic_auth_if_no_ano
def feed_read_books():
    if not (
        auth.current_user().check_visibility(constants.SIDEBAR_READ_AND_UNREAD)
        and not auth.current_user().is_anonymous
    ):
        return abort(403)
    off = _int_param("offset")
    result, pagination = render_read_books(
        int(off) / (int(config.config_books_per_page)) + 1, True, True
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template("feed.xml", entries=result, pagination=pagination, cc=cc)


@opds.route("/opds/unreadbooks")
@requires_basic_auth_if_no_ano
def feed_unread_books():
    if not (
        auth.current_user().check_visibility(constants.SIDEBAR_READ_AND_UNREAD)
        and not auth.current_user().is_anonymous
    ):
        return abort(403)
    off = _int_param("offset")
    result, pagination = render_read_books(
        int(off) / (int(config.config_books_per_page)) + 1, False, True
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template("feed.xml", entries=result, pagination=pagination, cc=cc)


class FeedObject:
    def __init__(self, rating_id, rating_name):
        self.rating_id = rating_id
        self.rating_name = rating_name

    @property
    def id(self):
        return self.rating_id

    @property
    def name(self):
        return self.rating_name


def feed_search(term):
    if term:
        # Phase 7: the OPDS search speaks the same grammar as the bar.
        # Phase 13: an unparseable query is an empty feed, not a 500 (the
        # web bar and /basic degrade the same way; OPDS users type stray
        # quotes), and the feed is capped at the configured books-per-page
        # with the template's existing rel="next" carrying readers onward,
        # instead of rendering every match in one unbounded response.
        from .carrel_search import LibraryUnavailable, SearchError, resolve

        try:
            ids = resolve(term)
        except (SearchError, LibraryUnavailable):
            ids = []
        page = _int_param("offset") // (config.config_books_per_page or 60) + 1
        entries, pagination = quarry_grid.grid(page, ids, include_comments=True)
        cc = []
        return render_xml_template(
            "feed.xml",
            searchterm=term,
            entries=entries,
            pagination=pagination,
            cc=cc,
        )
    else:
        return render_xml_template("feed.xml", searchterm="")


def render_xml_template(*args, **kwargs):
    # ToDo: return time in current timezone similar to %z
    currtime = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S+00:00")
    xml = render_template(
        current_time=currtime,
        instance=config.config_calibre_web_title,
        constants=constants.sidebar_settings,
        *args,
        **kwargs,
    )
    response = make_response(xml)
    response.headers["Content-Type"] = "application/atom+xml; charset=utf-8"
    return response


_DATASET_KINDS = {
    db.Authors: "authors",
    db.Publishers: "publishers",
    db.Tags: "tags",
    db.Ratings: "ratings",
}


def render_xml_dataset(data_table, book_id):
    # Phase 7: entity id sets resolve rows-side via quarry_grid.
    off = _int_param("offset")
    page = int(off / (int(config.config_books_per_page)) + 1)
    ids = quarry_grid.ids_for_entity(_DATASET_KINDS[data_table], book_id)
    entries, pagination = quarry_grid.grid(
        page, ids, sort=("timestamp",), descending=True, include_comments=True
    )
    cc = []
    return render_xml_template(
        "feed.xml", entries=entries, pagination=pagination, cc=cc
    )


def _first_letters(values):
    return sorted({v[:1].upper() for v in values if v})


def _letter_elements(letters, folder):
    """Letter facets for the index feeds, computed in Python (Phase 7):
    the SQL group-bys over entity columns are gone. "00" (All) leads,
    offsets slice letters, and the cc list is empty on cquarry-backed
    feeds until a cc adapter exists."""
    off = _int_param("offset")
    elements = []
    shift = 0
    if off == 0 and letters:
        elements.append({"id": "00", "name": _("All")})
        shift = 1
    for letter in letters[
        off + shift - 1 : int(off + int(config.config_books_per_page) - shift)
    ]:
        elements.append({"id": letter, "name": letter})
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        len(letters) + 1,
    )
    cc = []
    return render_xml_template(
        "feed.xml",
        letterelements=elements,
        folder=folder,
        pagination=pagination,
        cc=cc,
    )


def render_element_index(database_column, linked_table, folder):
    shift = 0
    off = _int_param("offset")
    entries = calibre_db.session.query(
        func.upper(func.substr(database_column, 1, 1)).label("id"), None, None
    )
    # query = calibre_db.generate_linked_query(config.config_read_column, db.Books)
    if linked_table is not None:
        entries = entries.join(linked_table).join(db.Books)
    entries = (
        entries.filter(calibre_db.common_filters())
        .group_by(func.upper(func.substr(database_column, 1, 1)))
        .all()
    )
    elements = []
    if off == 0 and entries:
        elements.append({"id": "00", "name": _("All")})
        shift = 1
    for entry in entries[
        off + shift - 1 : int(off + int(config.config_books_per_page) - shift)
    ]:
        elements.append({"id": entry.id, "name": entry.id})
    pagination = Pagination(
        (int(off) / (int(config.config_books_per_page)) + 1),
        config.config_books_per_page,
        len(entries) + 1,
    )
    cc = calibre_db.get_cc_columns(config, filter_config_custom_read=True)
    return render_xml_template(
        "feed.xml", letterelements=elements, folder=folder, pagination=pagination, cc=cc
    )
