"""Flask API app factory -- JSON API routes.

Full route set (folder pickers via dialogs.py, the status-polling contract
via bridge.py, per-book actions) is Epic 6 work -- see
docs/requirements/01-architecture.md §Status endpoint contract and
docs/BACKLOG.md Epic 6. This scaffold exists so launcher.py (Epic 0) has a
real WSGI app to serve, with a minimal health-check route proving the
wiring works end-to-end before any real route logic exists.
"""

from __future__ import annotations

from flask import Flask, Response, jsonify


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/api/health")
    def health() -> Response:
        return jsonify({"status": "ok"})

    return app
