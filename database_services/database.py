import json
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager


class DatabaseService:
    def __init__(self, database_path=None):
        self.database_path = (
            Path(database_path) if database_path else
            Path(__file__).parent.parent / "9to5_ai.db"
        )

        self.create_tables()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(
            self.database_path
        )

        connection.row_factory = sqlite3.Row

        connection.execute("PRAGMA foreign_keys = ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_tables(self):
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.cursor()

            # -------------------------
            # PROFILE
            # -------------------------

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS profile (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    location TEXT,
                    education TEXT,
                    program TEXT,
                    skills TEXT,
                    experience TEXT,
                    target_roles TEXT,
                    job_preferences TEXT,
                    resume_text TEXT
                )
                """
            )

            # -------------------------
            # APPLICATIONS
            # -------------------------

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT UNIQUE,
                    title TEXT,
                    company TEXT,
                    location TEXT,
                    url TEXT,
                    description TEXT,
                    match_score INTEGER,
                    status TEXT,
                    generation_status TEXT,
                    approval_status TEXT,
                    application_message TEXT,
                    cover_letter TEXT,
                    created_at TEXT,
                    updated_at TEXT
                )
                """
            )

            # -------------------------
            # APPLICATION HISTORY
            # -------------------------

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS application_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(application_id)
                        REFERENCES applications(id)
                )
                """
            )

            self._migrate_review_versions(connection)
            connection.commit()

    # ==================================================
    # PROFILE
    # ==================================================

    def save_profile(self, profile):
        with self.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO profile (
                    id,
                    name,
                    email,
                    location,
                    education,
                    program,
                    skills,
                    experience,
                    target_roles,
                    job_preferences,
                    resume_text
                )
                VALUES (
                    1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(id)
                DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email,
                    location = excluded.location,
                    education = excluded.education,
                    program = excluded.program,
                    skills = excluded.skills,
                    experience = excluded.experience,
                    target_roles = excluded.target_roles,
                    job_preferences = excluded.job_preferences,
                    resume_text = excluded.resume_text
                """,
                (
                    profile.get("name", ""),
                    profile.get("email", ""),
                    profile.get("location", ""),
                    profile.get("education", ""),
                    profile.get("program", ""),
                    json.dumps(
                        profile.get("skills", [])
                    ),
                    json.dumps(
                        profile.get("experience", [])
                    ),
                    json.dumps(
                        profile.get("target_roles", [])
                    ),
                    json.dumps(
                        profile.get(
                            "job_preferences",
                            {},
                        )
                    ),
                    profile.get("resume_text", ""),
                ),
            )

            connection.commit()

    def load_profile(self):
        with self.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT *
                FROM profile
                WHERE id = 1
                """
            )

            row = cursor.fetchone()

            if row is None:
                return None

            return {
                "name": row["name"] or "",
                "email": row["email"] or "",
                "location": row["location"] or "",
                "education": row["education"] or "",
                "program": row["program"] or "",
                "skills": json.loads(
                    row["skills"] or "[]"
                ),
                "experience": json.loads(
                    row["experience"] or "[]"
                ),
                "target_roles": json.loads(
                    row["target_roles"] or "[]"
                ),
                "job_preferences": json.loads(
                    row["job_preferences"] or "{}"
                ),
                "resume_text": row["resume_text"] or "",
            }

    # ==================================================
    # APPLICATIONS
    # ==================================================

    def create_application(self, application):
        # Creation is insert-only: duplicate requests must never overwrite approval.
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM applications WHERE job_id = ?",
                (application["job_id"],),
            ).fetchone()
            if existing:
                return dict(existing)
            columns = tuple(application)
            cursor = connection.execute(
                f"INSERT INTO applications ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(application.values()),
            )
            application = dict(application, id=cursor.lastrowid)
            self._history(connection, application, "created", "Application created")
            return dict(connection.execute(
                "SELECT * FROM applications WHERE id = ?", (cursor.lastrowid,)
            ).fetchone())

    def get_application(self, application_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_application(self, application_id, change):
        """Validate and update under one write lock, including versions and history."""
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM applications WHERE id = ?", (application_id,)
            ).fetchone()
            if row is None:
                return None
            application = dict(row)
            events = change(application)
            if not events:
                return application
            application["updated_at"] = datetime.now().isoformat()
            fields = (
                "status", "generation_status", "approval_status", "application_message",
                "cover_letter", "content_version", "approved_version", "approved_at",
                "updated_at",
            )
            connection.execute(
                "UPDATE applications SET " + ", ".join(f"{f} = ?" for f in fields)
                + " WHERE id = ?",
                tuple(application[f] for f in fields) + (application_id,),
            )
            if application["content_version"] != row["content_version"]:
                self._snapshot(connection, application)
            for event_type, note in events:
                self._history(connection, application, event_type, note)
            return application

    def _snapshot(self, connection, application):
        connection.execute(
            """INSERT INTO application_versions
               (application_id, content_version, application_message, cover_letter, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (application["id"], application["content_version"],
             application["application_message"] or "", application["cover_letter"] or "",
             datetime.now().isoformat()),
        )

    def _history(self, connection, application, event_type, note):
        connection.execute(
            """INSERT INTO application_history
               (application_id, status, note, created_at, event_type, content_version)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (application["id"], application["status"], note, datetime.now().isoformat(),
             event_type, application.get("content_version", 0)),
        )

    def _migrate_review_versions(self, connection):
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(applications)")}
        first_migration = "content_version" not in columns
        for name, definition in (
            ("content_version", "INTEGER NOT NULL DEFAULT 0"),
            ("approved_version", "INTEGER"),
            ("approved_at", "TEXT"),
        ):
            if name not in columns:
                connection.execute(f"ALTER TABLE applications ADD COLUMN {name} {definition}")
        history_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(application_history)")
        }
        for name, definition in (("event_type", "TEXT"), ("content_version", "INTEGER")):
            if name not in history_columns:
                connection.execute(f"ALTER TABLE application_history ADD COLUMN {name} {definition}")
        connection.execute("""CREATE TABLE IF NOT EXISTS application_versions (
            application_id INTEGER NOT NULL REFERENCES applications(id),
            content_version INTEGER NOT NULL,
            application_message TEXT NOT NULL,
            cover_letter TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (application_id, content_version)
        )""")
        if not first_migration:
            return
        for row in connection.execute("SELECT * FROM applications").fetchall():
            application = dict(row)
            has_content = bool(application["application_message"] or application["cover_letter"])
            application["content_version"] = 1 if has_content else 0
            was_approved = application["approval_status"] == "approved" or application["status"] == "approved"
            application["approval_status"] = "pending"
            # Preserve historical tracking outcomes, but never trust unversioned approval.
            if application["status"] in ("draft", "ready_for_review", "needs_changes", "approved"):
                application["status"] = "ready_for_review" if has_content else "draft"
            connection.execute(
                """UPDATE applications SET content_version = ?, approved_version = NULL,
                   approved_at = NULL, approval_status = ?, status = ? WHERE id = ?""",
                (application["content_version"], application["approval_status"],
                 application["status"], application["id"]),
            )
            if has_content:
                self._snapshot(connection, application)
            self._history(connection, application, "migrated",
                          "Existing content migrated; version-specific human review required")
            if was_approved:
                self._history(connection, application, "approval_invalidated",
                              "Legacy approval invalidated: no approved content version was recorded")

    def load_applications(self):
        with self.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT *
                FROM applications
                ORDER BY id DESC
                """
            )

            rows = cursor.fetchall()

            return [
                dict(row)
                for row in rows
            ]

    # ==================================================
    # APPLICATION HISTORY
    # ==================================================

    def add_application_history(
        self,
        application_id,
        status,
        note="",
    ):
        with self.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO application_history (
                    application_id,
                    status,
                    note,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    application_id,
                    status,
                    note,
                    datetime.now().isoformat(),
                ),
            )

            connection.commit()

    def get_application_history(
        self,
        application_id,
    ):
        with self.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                SELECT *
                FROM application_history
                WHERE application_id = ?
                ORDER BY id ASC
                """,
                (
                    application_id,
                ),
            )

            rows = cursor.fetchall()

            return [
                dict(row)
                for row in rows
            ]