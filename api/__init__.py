"""EPOS Next service layer.

FastAPI application exposing the deterministic engines in ``src/`` over a REST API backed by
SQLite. The engines are never reimplemented here; this package only adapts persistence into
engine inputs and engine outputs into product language.
"""
