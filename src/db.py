"""Database schema, connection management, and migrations for NotizieGeopolitica."""

import sqlite3
from contextlib import contextmanager
from src.config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    feed_url    TEXT NOT NULL,
    region      TEXT NOT NULL,
    country     TEXT,
    language    TEXT DEFAULT 'en',
    active      BOOLEAN DEFAULT 1
);

CREATE TABLE IF NOT EXISTS articles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    INTEGER NOT NULL REFERENCES sources(id),
    url          TEXT NOT NULL UNIQUE,
    title        TEXT NOT NULL,
    author       TEXT,
    published_at TIMESTAMP,
    fetched_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    content_raw  TEXT,
    summary      TEXT,
    keywords     TEXT,
    processed    BOOLEAN DEFAULT 0,
    matched      BOOLEAN DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source_id);
CREATE INDEX IF NOT EXISTS idx_articles_processed ON articles(processed);
CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);

CREATE TABLE IF NOT EXISTS story_clusters (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    summary     TEXT,
    main_topic  TEXT,
    event_date  DATE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published   BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cluster_articles (
    cluster_id  INTEGER NOT NULL REFERENCES story_clusters(id),
    article_id  INTEGER NOT NULL REFERENCES articles(id),
    PRIMARY KEY (cluster_id, article_id)
);

CREATE TABLE IF NOT EXISTS comparisons (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id      INTEGER NOT NULL REFERENCES story_clusters(id) UNIQUE,
    comparison_text TEXT NOT NULL,
    key_differences TEXT,
    key_agreements  TEXT,
    western_frame   TEXT,
    nonwestern_frame TEXT,
    omissions       TEXT,
    generated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db():
    """Create the database and all tables if they don't exist."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_connection():
    """Context manager for database connections with WAL mode and foreign keys."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_source(name, feed_url, region, country=None, language="en"):
    """Insert or update a source in the database."""
    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sources (name, feed_url, region, country, language)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   feed_url=excluded.feed_url,
                   region=excluded.region,
                   country=excluded.country,
                   language=excluded.language""",
            (name, feed_url, region, country, language),
        )


def get_active_sources():
    """Return all active sources."""
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM sources WHERE active=1"
        ).fetchall()


def article_exists(url):
    """Check if an article URL is already in the database."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM articles WHERE url=?", (url,)
        ).fetchone()
        return row is not None


def insert_article(source_id, url, title, author, published_at, content_raw):
    """Insert a new article. Returns the article id, or None if it already exists."""
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO articles (source_id, url, title, author, published_at, content_raw)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (source_id, url, title, author, published_at, content_raw),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None


def get_article_count_by_source():
    """Return article count per source for status reporting."""
    with get_connection() as conn:
        return conn.execute(
            """SELECT s.name, s.region, s.active, COUNT(a.id) as count
               FROM sources s
               LEFT JOIN articles a ON a.source_id = s.id
               GROUP BY s.id
               ORDER BY s.region, s.name"""
        ).fetchall()
