"""Persistência comercial mínima para leads, conversas e previews temporários."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


UTC = timezone.utc
DEFAULT_DB_PATH = os.getenv("LEADS_DB_PATH", "/data/leads.db")


class LeadsEngine:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        try:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Render usa /data persistente; em sandbox local, use um fallback gravável.
            self.db_path = Path("/tmp/humanos-digitais-data/leads.db")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    phone_number TEXT UNIQUE,
                    name TEXT,
                    email TEXT,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    source TEXT NOT NULL DEFAULT 'website',
                    status TEXT NOT NULL DEFAULT 'new',
                    city TEXT,
                    state TEXT,
                    country TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lead_id INTEGER,
                    session_id TEXT,
                    direction TEXT NOT NULL,
                    message TEXT NOT NULL,
                    avatar_id TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads(id)
                );
                CREATE TABLE IF NOT EXISTS previews (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    lead_id INTEGER,
                    knowledge_text TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    FOREIGN KEY (lead_id) REFERENCES leads(id)
                );
                CREATE INDEX IF NOT EXISTS idx_leads_created_at ON leads(created_at);
                CREATE INDEX IF NOT EXISTS idx_previews_expires_at ON previews(expires_at);
                """
            )

    @staticmethod
    def now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value or {}, ensure_ascii=False, default=str)

    def capture_lead(
        self,
        phone_number: str,
        name: str = "",
        email: str = "",
        tenant_id: str = "default",
        source: str = "website",
        metadata: Optional[dict[str, Any]] = None,
        geo: Optional[dict[str, Any]] = None,
        status: str = "new",
    ) -> dict[str, Any]:
        phone = re.sub(r"\D", "", phone_number or "")
        if len(phone) < 10:
            raise ValueError("phone_number inválido")
        now = self.now()
        geo = geo or {}
        with self._connect() as conn:
            existing = conn.execute("SELECT * FROM leads WHERE phone_number = ?", (phone,)).fetchone()
            if existing:
                conn.execute(
                    """UPDATE leads SET name=COALESCE(NULLIF(?, ''), name), email=COALESCE(NULLIF(?, ''), email),
                    tenant_id=?, source=?, city=COALESCE(NULLIF(?, ''), city), state=COALESCE(NULLIF(?, ''), state),
                    country=COALESCE(NULLIF(?, ''), country), metadata_json=?, updated_at=? WHERE phone_number=?""",
                    (name, email, tenant_id or "default", source, geo.get("city", ""), geo.get("state", ""), geo.get("country", ""), self._json(metadata), now, phone),
                )
                lead_id = existing["id"]
                created = False
            else:
                cur = conn.execute(
                    """INSERT INTO leads(phone_number,name,email,tenant_id,source,status,city,state,country,metadata_json,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (phone, name, email, tenant_id or "default", source, status, geo.get("city", ""), geo.get("state", ""), geo.get("country", ""), self._json(metadata), now, now),
                )
                lead_id = cur.lastrowid
                created = True
            row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        return {"created": created, "lead": dict(row)}

    def add_conversation(self, lead_id: Optional[int], session_id: str, direction: str, message: str, avatar_id: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO conversations(lead_id,session_id,direction,message,avatar_id,created_at) VALUES(?,?,?,?,?,?)",
                (lead_id, session_id, direction, message[:4000], avatar_id, self.now()),
            )

    def list_leads(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM leads ORDER BY created_at DESC LIMIT ? OFFSET ?", (min(max(limit, 1), 1000), max(offset, 0))).fetchall()
        return [dict(row) for row in rows]

    def export_csv(self) -> str:
        rows = self.list_leads(limit=1000)
        output = io.StringIO()
        fields = ["id", "phone_number", "name", "email", "tenant_id", "source", "status", "city", "state", "country", "created_at", "updated_at"]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})
        return output.getvalue()

    def create_preview(self, tenant_id: str = "default", knowledge_text: str = "", lead_id: Optional[int] = None) -> dict[str, Any]:
        preview_id = f"preview_{uuid.uuid4().hex}"
        created = datetime.now(UTC)
        expires = created + timedelta(hours=24)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO previews(id,tenant_id,lead_id,knowledge_text,created_at,expires_at) VALUES(?,?,?,?,?,?)",
                (preview_id, tenant_id or "default", lead_id, knowledge_text[:200000], created.isoformat(), expires.isoformat()),
            )
        return self.get_preview(preview_id) or {}

    def get_preview(self, preview_id: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM previews WHERE id = ?", (preview_id,)).fetchone()
        return dict(row) if row else None

    def increment_preview_messages(self, preview_id: str) -> int:
        with self._connect() as conn:
            conn.execute("UPDATE previews SET message_count = message_count + 1 WHERE id = ?", (preview_id,))
            row = conn.execute("SELECT message_count FROM previews WHERE id = ?", (preview_id,)).fetchone()
        return int(row["message_count"]) if row else 0

    def convert_preview(self, preview_id: str, phone_number: str, name: str = "", email: str = "") -> dict[str, Any]:
        preview = self.get_preview(preview_id)
        if not preview:
            raise KeyError("preview_not_found")
        lead = self.capture_lead(phone_number, name, email, preview["tenant_id"], "avatar_preview", status="hot")
        with self._connect() as conn:
            conn.execute("UPDATE leads SET status='hot', updated_at=? WHERE id=?", (self.now(), lead["lead"]["id"]))
            conn.execute("UPDATE previews SET status='converted', lead_id=? WHERE id=?", (lead["lead"]["id"], preview_id))
        return {"preview": self.get_preview(preview_id), "lead": lead["lead"]}

    def cleanup_expired_previews(self) -> int:
        now = self.now()
        with self._connect() as conn:
            cur = conn.execute("UPDATE previews SET status='expired' WHERE status='active' AND expires_at <= ?", (now,))
        return cur.rowcount
