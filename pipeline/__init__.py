"""Shared pipeline engine, called by both front doors (main.py CLI and
backend/bridge.py -- Flask GUI). Neither front door contains pipeline
logic itself; see docs/design/adr/0001-flask-waitress-react-over-pywebview.md
and docs/design/SYSTEM_DESIGN.md §4.
"""
