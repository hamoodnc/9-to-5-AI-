"""Offline regression tests. No .env loading, external requests, or live database access."""
import importlib
import sqlite3
import sys
import tempfile
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from application_services.applications import ApplicationService, ReviewConflict
from database_services.database import DatabaseService


class ReviewFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "test.db"
        self.db = DatabaseService(self.path)
        self.service = ApplicationService(self.db)
        self.application = self.service.create_application("job-1", "Support", "Example", "Ottawa", "https://example.com")
        self.id = self.application["id"]

    def generate(self):
        return self.service.save_generated_content(self.id, "Message", "Letter", 0)

    def approve(self):
        self.generate()
        return self.service.approve_application(self.id, 1)


class ReviewTests(ReviewFixture):
    def test_generation_requires_review(self):
        a = self.generate()
        self.assertEqual((a["status"], a["content_version"]), ("ready_for_review", 1))
        self.assertFalse(a["current_version_approved"])

    def test_empty_draft_cannot_be_approved_or_applied(self):
        for action in (self.service.approve_application, self.service.mark_applied):
            with self.assertRaises(ReviewConflict): action(self.id, 0)

    def test_approval_is_persisted_for_exact_version(self):
        self.approve()
        a = ApplicationService(DatabaseService(self.path)).get_application(self.id)
        self.assertEqual(a["approved_version"], 1)
        self.assertTrue(a["approved_at"])
        self.assertTrue(a["current_version_approved"])
        self.assertEqual(self.service.mark_applied(self.id, 1)["status"], "applied")

    def test_edit_either_field_invalidates_approval(self):
        self.approve()
        a = self.service.edit_content(self.id, "Changed message", "Letter", 1)
        self.assertEqual(a["content_version"], 2)
        self.assertEqual(a["status"], "ready_for_review")
        self.assertIsNone(a["approved_version"])
        self.assertIsNone(a["approved_at"])
        self.service.approve_application(self.id, 2)
        a = self.service.edit_content(self.id, "Changed message", "Changed letter", 2)
        self.assertFalse(a["current_version_approved"])
        with self.assertRaises(ReviewConflict): self.service.mark_applied(self.id, 3)

    def test_noop_edit_preserves_approval_and_history(self):
        self.approve()
        history = self.service.get_history(self.id)
        a = self.service.edit_content(self.id, "Message", "Letter", 1)
        self.assertTrue(a["current_version_approved"])
        self.assertEqual(a["content_version"], 1)
        self.assertEqual(history, self.service.get_history(self.id))

    def test_stale_edit_and_approval_and_applied_are_rejected(self):
        self.generate()
        self.service.edit_content(self.id, "New", "Letter", 1)
        for action in (
            lambda: self.service.edit_content(self.id, "Stale", "Letter", 1),
            lambda: self.service.approve_application(self.id, 1),
            lambda: self.service.mark_applied(self.id, 1),
            lambda: self.service.save_generated_content(self.id, "Stale AI", "Letter", 1),
        ):
            with self.assertRaises(ReviewConflict): action()
        self.assertEqual(self.service.get_application(self.id)["application_message"], "New")

    def test_corrections_cannot_bypass_approval(self):
        self.generate()
        for status in ("approved", "applied", "interview", "offer", "rejected", "draft"):
            with self.assertRaises(ReviewConflict): self.service.correct_status(self.id, status)
        self.assertEqual(self.service.get_application(self.id)["status"], "ready_for_review")

    def test_review_correction_revokes_approval(self):
        self.approve()
        a = self.service.correct_status(self.id, "ready_for_review")
        self.assertFalse(a["current_version_approved"])
        with self.assertRaises(ReviewConflict): self.service.correct_status(self.id, "applied")

    def test_needs_changes_remains_reviewable(self):
        self.approve()
        a = self.service.reject_application(self.id, 1)
        self.assertEqual(a["status"], "ready_for_review")
        self.assertFalse(a["current_version_approved"])
        self.service.edit_content(self.id, "Revision", "Letter", 1)
        self.assertTrue(self.service.approve_application(self.id, 2)["current_version_approved"])

    def test_regeneration_requires_fresh_review_even_if_identical(self):
        self.approve()
        a = self.service.save_generated_content(self.id, "Message", "Letter", 1)
        self.assertEqual(a["content_version"], 2)
        self.assertFalse(a["current_version_approved"])

    def test_edit_after_manual_application_requires_reapproval(self):
        self.approve()
        self.service.mark_applied(self.id, 1)
        a = self.service.edit_content(self.id, "Changed", "Letter", 1)
        self.assertEqual(a["status"], "ready_for_review")
        with self.assertRaises(ReviewConflict): self.service.mark_applied(self.id, 2)
        self.assertTrue(any(h["status"] == "applied" for h in self.service.get_history(self.id)))

    def test_blank_content_rejected_without_changes(self):
        self.generate()
        with self.assertRaises(ReviewConflict): self.service.edit_content(self.id, "  ", "Letter", 1)
        self.assertEqual(self.service.get_application(self.id)["content_version"], 1)

    def test_history_and_version_snapshots_preserved(self):
        self.approve()
        self.service.edit_content(self.id, "Revision", "Letter", 1)
        history = self.service.get_history(self.id)
        self.assertEqual([h["event_type"] for h in history],
                         ["created", "generated", "approved", "approval_invalidated", "edited"])
        with self.db.connect() as connection:
            rows = connection.execute("SELECT content_version, application_message FROM application_versions ORDER BY content_version").fetchall()
        self.assertEqual([tuple(r) for r in rows], [(1, "Message"), (2, "Revision")])

    def test_duplicate_creation_does_not_reset_approval(self):
        self.approve()
        a = self.service.create_application("job-1", "Other", "Other", "Other", "https://example.com")
        self.assertEqual(a["title"], "Support")
        self.assertTrue(a["current_version_approved"])

    def test_concurrent_edits_only_one_can_save(self):
        self.generate()
        def edit(text):
            try:
                return self.service.edit_content(self.id, text, "Letter", 1)["content_version"]
            except ReviewConflict:
                return "conflict"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(edit, ["Edit A", "Edit B"]))
        self.assertCountEqual(results, [2, "conflict"])

    def test_concurrent_approval_and_edit_never_approve_unreviewed_content(self):
        self.generate()
        def approve():
            try:
                self.service.approve_application(self.id, 1)
            except ReviewConflict:
                pass
        with ThreadPoolExecutor(max_workers=2) as pool:
            approval = pool.submit(approve)
            edit = pool.submit(self.service.edit_content, self.id, "New content", "Letter", 1)
            approval.result()
            edit.result()
        a = self.service.get_application(self.id)
        self.assertEqual(a["content_version"], 2)
        self.assertFalse(a["current_version_approved"])

    def test_history_failure_rolls_back_content_and_snapshot(self):
        self.generate()
        with patch.object(self.db, "_history", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaises(RuntimeError): self.service.edit_content(self.id, "New", "Letter", 1)
        self.assertEqual(self.service.get_application(self.id)["content_version"], 1)
        with self.db.connect() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM application_versions").fetchone()[0], 1)

    def test_legacy_migration_preserves_content_history_and_revokes_approval(self):
        legacy = Path(self.temp.name) / "legacy.db"
        with closing(sqlite3.connect(legacy)) as connection:
            connection.executescript("""
                CREATE TABLE applications (id INTEGER PRIMARY KEY, job_id TEXT UNIQUE,
                    title TEXT, company TEXT, location TEXT, url TEXT, description TEXT,
                    match_score INTEGER, status TEXT, generation_status TEXT, approval_status TEXT,
                    application_message TEXT, cover_letter TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE application_history (id INTEGER PRIMARY KEY, application_id INTEGER,
                    status TEXT, note TEXT, created_at TEXT);
                INSERT INTO applications VALUES (1, 'legacy', '', '', '', '', '', 0,
                    'approved', 'generated', 'approved', 'Old message', 'Old letter', '', '');
                INSERT INTO application_history VALUES (1, 1, 'approved', 'Old history', '');
            """)
        database = DatabaseService(legacy)
        service = ApplicationService(database)
        a = service.get_application(1)
        self.assertEqual((a["content_version"], a["application_message"]), (1, "Old message"))
        self.assertFalse(a["current_version_approved"])
        self.assertEqual(a["status"], "ready_for_review")
        self.assertEqual(service.get_history(1)[0]["note"], "Old history")
        count = len(service.get_history(1))
        DatabaseService(legacy)
        self.assertEqual(len(service.get_history(1)), count)


class ApiTests(ReviewFixture):
    def setUp(self):
        super().setUp()
        fakes = {}
        for name, attribute, value in (
            ("email_services.gmail", "GmailService", lambda: object()),
            ("job_services.jobs", "JobService", lambda: object()),
            ("ai_services.gemini", "generate_application", lambda *args: "APPLICATION MESSAGE: Message\nCOVER LETTER: Letter"),
        ):
            module = types.ModuleType(name)
            setattr(module, attribute, value)
            fakes[name] = module
        with patch.dict(sys.modules, fakes), \
             patch("application_services.applications.ApplicationService", return_value=self.service), \
             patch("profile_services.profile.ProfileService", return_value=types.SimpleNamespace(get_profile=lambda: {"resume_text": "Synthetic resume"})):
            sys.modules.pop("main", None)
            self.main = importlib.import_module("main")
        self.addCleanup(lambda: sys.modules.pop("main", None))
        self.client = TestClient(self.main.app)
        self.addCleanup(self.client.close)

    def test_api_review_lifecycle_and_missing_version(self):
        base = f"/applications/{self.id}"
        self.assertEqual(self.client.post(base + "/generate").status_code, 200)
        self.assertEqual(self.client.post(base + "/approve").status_code, 422)
        self.assertEqual(self.client.post(base + "/applied", json={"expected_version": 1}).status_code, 409)
        self.assertEqual(self.client.post(base + "/correct-status", json={"new_status": "approved"}).status_code, 409)
        self.assertEqual(self.client.post(base + "/approve", json={"expected_version": 1}).status_code, 200)
        edit = {"expected_version": 1, "application_message": "Edited", "cover_letter": "Edited letter"}
        response = self.client.put(base + "/content", json=edit)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["current_version_approved"])
        self.assertEqual(self.client.put(base + "/content", json=edit).status_code, 409)
        self.assertEqual(self.client.post(base + "/approve", json={"expected_version": 1}).status_code, 409)
        self.assertEqual(self.client.post(base + "/approve", json={"expected_version": 2}).status_code, 200)
        self.assertEqual(self.client.post(base + "/applied", json={"expected_version": 2}).status_code, 200)
        self.assertEqual(self.client.get(base + "/history").status_code, 200)
        self.assertEqual(self.client.get("/dashboard").status_code, 200)

    def test_api_unknown_application_and_blank_content(self):
        self.assertEqual(self.client.post("/applications/999/approve", json={"expected_version": 1}).status_code, 404)
        self.generate()
        response = self.client.put(f"/applications/{self.id}/content", json={
            "expected_version": 1, "application_message": " ", "cover_letter": "Letter"})
        self.assertEqual(response.status_code, 409)

    def test_generation_in_flight_cannot_overwrite_new_edit(self):
        self.generate()
        def generate(*args):
            self.service.edit_content(self.id, "Human edit", "Letter", 1)
            return "APPLICATION MESSAGE: Late AI result\nCOVER LETTER: Letter"
        with patch.object(self.main, "generate_ai_application", side_effect=generate):
            response = self.client.post(f"/applications/{self.id}/generate")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.service.get_application(self.id)["application_message"], "Human edit")

    def test_invalid_ai_output_leaves_existing_review_intact(self):
        self.approve()
        with patch.object(self.main, "generate_ai_application", return_value=None):
            response = self.client.post(f"/applications/{self.id}/generate")
        self.assertEqual(response.status_code, 500)
        self.assertTrue(self.service.get_application(self.id)["current_version_approved"])


if __name__ == "__main__":
    unittest.main()
