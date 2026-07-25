import sqlite3
from datetime import datetime
from contextlib import contextmanager
from typing import List, Dict, Optional, Any


class Database:
    EMAIL_STATUS_SENT = "sent"
    EMAIL_STATUS_FAILED = "failed"
    EMAIL_STATUS_REPLIED = "replied"
    EMAIL_STATUS_ACKNOWLEDGED = "acknowledged"
    EMAIL_STATUS_NO_REPLY = "no_reply"
    EMAIL_STATUS_RETARGETED = "retargeted"

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    company TEXT,
                    context_tag TEXT,
                    extra_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS emails_sent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id INTEGER NOT NULL,
                    email_address TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    message_id TEXT,
                    attempt_number INTEGER DEFAULT 1,
                    is_retarget INTEGER DEFAULT 0,
                    sent_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (client_id) REFERENCES clients(id)
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_email_id INTEGER,
                    from_address TEXT NOT NULL,
                    subject TEXT,
                    body TEXT,
                    reply_message_id TEXT,
                    in_reply_to TEXT,
                    replied_at TIMESTAMP,
                    is_acknowledgment INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (original_email_id) REFERENCES emails_sent(id)
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_status ON emails_sent(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_email ON emails_sent(email_address)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails_sent(message_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_replies_in_reply_to ON email_replies(in_reply_to)
            """)
            conn.commit()

    # ---------- Client operations ----------

    def upsert_client(self, email: str, name: str = None, company: str = None,
                      context_tag: str = None, extra_data: str = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM clients WHERE email = ?", (email,))
            row = cursor.fetchone()
            if row:
                cursor.execute("""
                    UPDATE clients SET name = COALESCE(?, name),
                                       company = COALESCE(?, company),
                                       context_tag = COALESCE(?, context_tag),
                                       extra_data = COALESCE(?, extra_data)
                    WHERE id = ?
                """, (name, company, context_tag, extra_data, row["id"]))
                return row["id"]
            cursor.execute("""
                INSERT INTO clients (email, name, company, context_tag, extra_data)
                VALUES (?, ?, ?, ?, ?)
            """, (email, name, company, context_tag, extra_data))
            return cursor.lastrowid

    def get_client_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_all_clients(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM clients ORDER BY id DESC")
            return [dict(r) for r in cursor.fetchall()]

    # ---------- Email operations ----------

    def record_email(self, client_id: int, email_address: str, subject: str,
                     body: str, status: str, error_message: str = None,
                     message_id: str = None, attempt_number: int = 1,
                     is_retarget: int = 0, sent_at: datetime = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO emails_sent
                (client_id, email_address, subject, body, status, error_message,
                 message_id, attempt_number, is_retarget, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (client_id, email_address, subject, body, status, error_message,
                  message_id, attempt_number, is_retarget,
                  sent_at.isoformat() if sent_at else datetime.now().isoformat()))
            return cursor.lastrowid

    def update_email_status(self, email_id: int, status: str, error_message: str = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE emails_sent SET status = ?, error_message = COALESCE(?, error_message)
                WHERE id = ?
            """, (status, error_message, email_id))

    def get_failed_emails(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT es.*, c.name, c.company, c.context_tag
                FROM emails_sent es
                LEFT JOIN clients c ON c.id = es.client_id
                WHERE es.status = ?
                ORDER BY es.created_at DESC
            """, (self.EMAIL_STATUS_FAILED,))
            return [dict(r) for r in cursor.fetchall()]

    def get_emails_by_status(self, status: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT es.*, c.name, c.company, c.context_tag
                FROM emails_sent es
                LEFT JOIN clients c ON c.id = es.client_id
                WHERE es.status = ?
                ORDER BY es.created_at DESC
            """, (status,))
            return [dict(r) for r in cursor.fetchall()]

    def get_email_by_message_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            clean_id = message_id.strip().strip("<>")
            cursor.execute("""
                SELECT * FROM emails_sent WHERE message_id = ? OR message_id = ?
            """, (message_id, f"<{clean_id}>"))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_non_responders_for_retarget(self, after_days: int, max_attempts: int) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT es.*, c.name, c.company, c.context_tag
                FROM emails_sent es
                LEFT JOIN clients c ON c.id = es.client_id
                WHERE es.status IN (?, ?)
                  AND es.is_retarget = 0
                  AND es.attempt_number < ?
                  AND es.sent_at <= datetime('now', ?)
                  AND NOT EXISTS (
                      SELECT 1 FROM email_replies r
                      WHERE r.original_email_id = es.id
                  )
                GROUP BY es.email_address
                ORDER BY es.sent_at ASC
            """, (self.EMAIL_STATUS_SENT, self.EMAIL_STATUS_NO_REPLY,
                  max_attempts, f"-{after_days} days"))
            return [dict(r) for r in cursor.fetchall()]

    # ---------- Reply operations ----------

    def record_reply(self, from_address: str, subject: str, body: str,
                     reply_message_id: str, in_reply_to: str,
                     replied_at: datetime,
                     is_acknowledgment: int = 0) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM emails_sent WHERE message_id = ?", (in_reply_to,))
            original = cursor.fetchone()
            original_id = original["id"] if original else None

            cursor.execute("""
                INSERT INTO email_replies
                (original_email_id, from_address, subject, body, reply_message_id,
                 in_reply_to, replied_at, is_acknowledgment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (original_id, from_address, subject, body, reply_message_id,
                  in_reply_to, replied_at.isoformat(), is_acknowledgment))
            reply_id = cursor.lastrowid

            if original_id:
                new_status = (self.EMAIL_STATUS_REPLIED
                              if not is_acknowledgment else self.EMAIL_STATUS_ACKNOWLEDGED)
                cursor.execute("""
                    UPDATE emails_sent SET status = ? WHERE id = ?
                """, (new_status, original_id))
            return reply_id

    def reply_exists(self, reply_message_id: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM email_replies WHERE reply_message_id = ?",
                           (reply_message_id,))
            return cursor.fetchone() is not None

    def get_all_replies(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, c.name as client_name, c.company,
                       es.subject as original_subject, es.email_address
                FROM email_replies r
                LEFT JOIN emails_sent es ON es.id = r.original_email_id
                LEFT JOIN clients c ON c.id = es.client_id
                ORDER BY r.replied_at DESC
            """)
            return [dict(r) for r in cursor.fetchall()]

    # ---------- Reporting ----------

    def get_report_summary(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            summary = {}

            cursor.execute("SELECT COUNT(*) as cnt FROM emails_sent WHERE status = ?",
                           (self.EMAIL_STATUS_SENT,))
            summary["sent"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM emails_sent WHERE status = ?",
                           (self.EMAIL_STATUS_FAILED,))
            summary["failed"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM emails_sent WHERE status = ?",
                           (self.EMAIL_STATUS_REPLIED,))
            summary["replied"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM emails_sent WHERE status = ?",
                           (self.EMAIL_STATUS_ACKNOWLEDGED,))
            summary["acknowledged"] = cursor.fetchone()["cnt"]

            cursor.execute("""
                SELECT COUNT(*) as cnt FROM emails_sent
                WHERE status IN (?, ?)
                  AND NOT EXISTS (
                      SELECT 1 FROM email_replies r
                      WHERE r.original_email_id = emails_sent.id
                  )
            """, (self.EMAIL_STATUS_SENT, self.EMAIL_STATUS_NO_REPLY))
            summary["no_reply"] = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM emails_sent WHERE is_retarget = 1")
            summary["retargeted"] = cursor.fetchone()["cnt"]

            summary["total"] = summary["sent"] + summary["failed"] + summary["replied"] + \
                               summary["acknowledged"] + summary["no_reply"]
            return summary

    def get_non_responder_details(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT es.id, es.email_address, es.subject, es.sent_at,
                       c.name, c.company, c.context_tag, es.attempt_number
                FROM emails_sent es
                LEFT JOIN clients c ON c.id = es.client_id
                WHERE es.status IN (?, ?)
                  AND NOT EXISTS (
                      SELECT 1 FROM email_replies r
                      WHERE r.original_email_id = es.id
                  )
                ORDER BY es.sent_at ASC
            """, (self.EMAIL_STATUS_SENT, self.EMAIL_STATUS_NO_REPLY))
            return [dict(r) for r in cursor.fetchall()]
