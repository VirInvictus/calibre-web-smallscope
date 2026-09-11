# -*- coding: utf-8 -*-

# Single-user operation (Carrel spec 11).
#
# This instance has exactly one reader, so authentication is removed as a
# concept rather than merely bypassed: no credential is ever requested and the
# credential-management paths answer 404.
#
# The owner is authenticated on every request instead of stripping flask-login.
# Upstream has 154 @login_required decorators across 10 modules; rewriting them
# would turn every rebase onto a new upstream tag into a merge conflict, which
# spec section 3 explicitly protects against. Leaving them in place and always
# arriving authenticated makes them pass trivially.
#
# Deleting this module and its two lines in main.py restores stock behaviour.
#
# The server binds 0.0.0.0 (spec 11.3), so with authentication removed anything
# on the local network can read and download the whole library and reach the
# admin pane. That is recorded as a deliberate decision, not an oversight: the
# control is that the instance runs only in environments Brandon trusts, never
# the bind address. Somewhere untrusted, the honest fixes are deleting this
# module or fronting it with an authenticating reverse proxy.
#
# This comment previously claimed a localhost bind. It stopped being true when
# the server was rebound for phone access on 2026-07-24.

from flask import abort, request

# calibre-web vendors flask-login as cps.cw_login; importing the upstream
# package name fails in this venv.
from .cw_login import current_user, login_user

# Paths that exist only to manage credentials or to manage a user population
# that no longer exists, plus the admin machinery surfaces the credential seal
# never met (Phase 13): the updater pair can replace the checkout with an
# upstream release, which destroys the smallscope patches and stops the
# server; the user-management AJAX trio sits below the UI-layer seal, and
# deleting the owner bricks the room; /ajax/pathchooser is an arbitrary
# directory listing; /shutdown and /reconnect are one-request disruptions.
# Compared after stripping a trailing slash and lowercasing, so /login and
# /login/ are both sealed; _SEALED_PREFIXES covers the one route that takes
# a path parameter.
#
# /admin/user/<id> is deliberately NOT sealed: it is how the owner edits their
# own locale and sidebar preferences, which is ordinary configuration rather
# than user management.
_SEALED = frozenset(
    (
        "/login",
        "/logout",
        "/register",
        "/admin/user/new",
        "/admin/usertable",
        "/get_update_status",
        "/get_updater_status",
        "/ajax/listusers",
        "/ajax/deleteuser",
        "/ajax/pathchooser",
        "/shutdown",
        "/reconnect",
    )
)

_SEALED_PREFIXES = ("/ajax/editlistusers",)


def _owner():
    """The account every request runs as: the lowest-numbered admin."""
    from . import constants, ub

    return (
        ub.session.query(ub.User)
        .filter(ub.User.role.op("&")(constants.ROLE_ADMIN) == constants.ROLE_ADMIN)
        .order_by(ub.User.id)
        .first()
    )


def install(app):
    @app.before_request
    def _single_user():
        path = request.path.rstrip("/").lower()
        if path in _SEALED or path.startswith(_SEALED_PREFIXES):
            abort(404)
        if not current_user.is_authenticated:
            owner = _owner()
            if owner is not None:
                # remember=True so the session cookie carries it; the login is
                # re-established per request anyway if the cookie is missing or
                # the session-key check in load_user rejects it.
                login_user(owner, remember=True)
