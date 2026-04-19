#!/usr/bin/env bash
# Run ChromaDB as a standalone HTTP server.
# Use this when running both the FastAPI backend AND the embedding worker;
# it prevents multi-process SQLite corruption (e.g. "similarities" disappearing).
#
# Then set CHROMA_HTTP_URL=http://localhost:8100 in .env
#
cd "$(dirname "$0")/.."
chroma run --path ./chroma_data --port 8100 --host localhost
