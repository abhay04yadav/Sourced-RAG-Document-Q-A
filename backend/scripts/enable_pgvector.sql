"""
Day 1: enable pgvector on your Supabase (or any Postgres) database.

Run this once in the Supabase SQL Editor, then verify with:

    SELECT * FROM pg_extension WHERE extname = 'vector';
"""

CREATE EXTENSION IF NOT EXISTS vector;
