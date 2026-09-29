import json
import sqlite3
from datetime import datetime
from pathlib import Path


class DatabaseService:
    def __init__(self):
        self.database_path = (
            Path(__file__).parent.parent / "9to5_ai.db"
        )

        self.create_tables()

    def connect(self):
        connection = sqlite3.connect(
            self.database_path
        )

        connection.row_factory = sqlite3.Row

        return connection

    def create_tables(self):
        with self.connect() as connection:
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

    def save_application(self, application):
        with self.connect() as connection:
            cursor = connection.cursor()

            cursor.execute(
                """
                INSERT INTO applications (
                    job_id,
                    title,
                    company,
                    location,
                    url,
                    description,
                    match_score,
                    status,
                    generation_status,
                    approval_status,
                    application_message,
                    cover_letter,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

                ON CONFLICT(job_id)
                DO UPDATE SET
                    title = excluded.title,
                    company = excluded.company,
                    location = excluded.location,
                    url = excluded.url,
                    description = excluded.description,
                    match_score = excluded.match_score,
                    status = excluded.status,
                    generation_status = excluded.generation_status,
                    approval_status = excluded.approval_status,
                    application_message = excluded.application_message,
                    cover_letter = excluded.cover_letter,
                    updated_at = excluded.updated_at
                """,
                (
                    application.get("job_id"),
                    application.get("title", ""),
                    application.get("company", ""),
                    application.get("location", ""),
                    application.get("url", ""),
                    application.get(
                        "description",
                        "",
                    ),
                    application.get(
                        "match_score",
                        0,
                    ),
                    application.get(
                        "status",
                        "draft",
                    ),
                    application.get(
                        "generation_status",
                        "not_generated",
                    ),
                    application.get(
                        "approval_status",
                        "pending",
                    ),
                    application.get(
                        "application_message",
                        "",
                    ),
                    application.get(
                        "cover_letter",
                        "",
                    ),
                    application.get(
                        "created_at",
                        "",
                    ),
                    application.get(
                        "updated_at",
                        "",
                    ),
                ),
            )

            connection.commit()

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