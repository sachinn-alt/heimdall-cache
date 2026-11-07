import json
import sqlite3
import logging
import os
import tempfile
from pathlib import Path
from typing import Dict, Optional, List
from .models import CacheEntry, Claim

logger = logging.getLogger("heimdall.storage")

# Use /tmp on Vercel/serverless environments where app root is read-only
if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
    DB_PATH = Path(tempfile.gettempdir()) / "heimdall_cache.db"
else:
    DB_PATH = Path(__file__).resolve().parent.parent / "heimdall_cache.db"

class SQLiteVectorStorage:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = str(db_path)
        try:
            self._init_db()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite at {self.db_path}: {e}")

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache_vectors (
                    id TEXT PRIMARY KEY,
                    prompt TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    last_verified_at REAL NOT NULL,
                    hit_count INTEGER DEFAULT 0,
                    claims_json TEXT NOT NULL,
                    max_volatility TEXT NOT NULL,
                    overall_freshness REAL NOT NULL,
                    status TEXT NOT NULL
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operational_metrics (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_requests INTEGER DEFAULT 0,
                    cache_hits INTEGER DEFAULT 0,
                    cache_misses INTEGER DEFAULT 0,
                    stale_invalidations INTEGER DEFAULT 0,
                    tokens_saved INTEGER DEFAULT 0
                )
            """)
            cursor.execute("INSERT OR IGNORE INTO operational_metrics (id) VALUES (1)")
            conn.commit()

    def save_entry(self, entry: CacheEntry):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO cache_vectors (
                        id, prompt, response_text, embedding, created_at,
                        last_verified_at, hit_count, claims_json, max_volatility,
                        overall_freshness, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        prompt = excluded.prompt,
                        response_text = excluded.response_text,
                        embedding = excluded.embedding,
                        last_verified_at = excluded.last_verified_at,
                        hit_count = excluded.hit_count,
                        claims_json = excluded.claims_json,
                        max_volatility = excluded.max_volatility,
                        overall_freshness = excluded.overall_freshness,
                        status = excluded.status
                """, (
                    entry.id,
                    entry.prompt,
                    entry.response_text,
                    json.dumps(entry.embedding),
                    entry.created_at,
                    entry.last_verified_at,
                    entry.hit_count,
                    json.dumps([c.model_dump() for c in entry.claims]),
                    entry.max_volatility,
                    entry.overall_freshness,
                    entry.status
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error saving entry {entry.id} to SQLite: {e}")

    def load_all_entries(self) -> Dict[str, CacheEntry]:
        entries: Dict[str, CacheEntry] = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM cache_vectors")
                rows = cursor.fetchall()
                for r in rows:
                    claims_data = json.loads(r["claims_json"])
                    claims = [Claim(**c) for c in claims_data]
                    entry = CacheEntry(
                        id=r["id"],
                        prompt=r["prompt"],
                        response_text=r["response_text"],
                        embedding=json.loads(r["embedding"]),
                        created_at=r["created_at"],
                        last_verified_at=r["last_verified_at"],
                        hit_count=r["hit_count"],
                        claims=claims,
                        max_volatility=r["max_volatility"],
                        overall_freshness=r["overall_freshness"],
                        status=r["status"],
                    )
                    entries[entry.id] = entry
        except Exception as e:
            logger.error(f"Error loading entries from SQLite: {e}")
        return entries

    def delete_entry(self, entry_id: str):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM cache_vectors WHERE id = ?", (entry_id,))
                conn.commit()
        except Exception as e:
            logger.error(f"Error deleting entry {entry_id} from SQLite: {e}")

    def update_metrics(self, total: int, hits: int, misses: int, invalidations: int, tokens: int):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE operational_metrics
                    SET total_requests = ?, cache_hits = ?, cache_misses = ?,
                        stale_invalidations = ?, tokens_saved = ?
                    WHERE id = 1
                """, (total, hits, misses, invalidations, tokens))
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating metrics in SQLite: {e}")

    def load_metrics(self) -> Optional[dict]:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM operational_metrics WHERE id = 1")
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.error(f"Error loading metrics from SQLite: {e}")
        return None

db_storage = SQLiteVectorStorage()
