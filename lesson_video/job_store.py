"""Durable, private metadata for the single-machine lesson prototype.

The random upload nonce makes retries safe; the separate per-job capability
controls all reads and generation. Neither capability is an account system.
"""

from contextlib import contextmanager
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid


ACTIVE_STATES = ("queued_read", "reading", "queued", "rendering")


class RequestConflict(ValueError):
    """An upload nonce was reused with different content."""


class JobStore:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self.path = self.root / "jobs.sqlite3"
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                request_id TEXT UNIQUE NOT NULL,
                payload_hash TEXT NOT NULL,
                access_token TEXT NOT NULL,
                status TEXT NOT NULL,
                character_json TEXT NOT NULL,
                review_json TEXT,
                error TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )""")
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        result = dict(row)
        result["character"] = json.loads(result.pop("character_json"))
        raw_review = result.pop("review_json")
        result["review"] = json.loads(raw_review) if raw_review else None
        return result

    def recover_interrupted(self):
        """A new server cannot resume a half-finished model or encoder call."""
        with self.connection() as db:
            return db.execute(
                "UPDATE jobs SET status='failed', error=?, updated_at=? "
                "WHERE status IN (?,?,?,?)",
                ("The server restarted before this lesson finished. Upload the picture again to retry.",
                 time.time(), *ACTIVE_STATES),
            ).rowcount

    def create(self, request_id, payload_hash, character):
        """Atomically create once; concurrent retries receive the same job."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE request_id=?", (request_id,)).fetchone()
            if row is not None:
                if not hmac.compare_digest(row["payload_hash"], payload_hash):
                    raise RequestConflict("This upload request was already used for a different picture or character.")
                return self._decode(row), False
            job_id = uuid.uuid4().hex
            now = time.time()
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
                (job_id, request_id, payload_hash, secrets.token_urlsafe(32), "queued_read",
                 json.dumps(character, sort_keys=True), None, None, now, now),
            )
            return self._decode(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()), True

    def get(self, job_id, token=None):
        with self.connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            return None
        if token is not None and not hmac.compare_digest(row["access_token"], token):
            return None
        return self._decode(row)

    def transition(self, job_id, expected, status, *, review=None, error=None):
        """Compare-and-set prevents duplicate workers and duplicate Generate clicks."""
        expected = (expected,) if isinstance(expected, str) else tuple(expected)
        if not expected:
            return False
        placeholders = ",".join("?" for _ in expected)
        with self.connection() as db:
            return bool(db.execute(
                f"UPDATE jobs SET status=?, updated_at=?, error=?, "
                f"review_json=COALESCE(?,review_json) WHERE id=? AND status IN ({placeholders})",
                (status, time.time(), error,
                 json.dumps(review, ensure_ascii=False) if review is not None else None,
                 job_id, *expected),
            ).rowcount)

    def job_dir(self, job_id):
        """Only call with the UUID obtained from a stored job."""
        return self.root / job_id
