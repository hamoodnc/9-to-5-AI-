from datetime import datetime

from database_services.database import DatabaseService


class ReviewConflict(ValueError):
    """The requested action is not valid for the current saved review state."""


class ApplicationService:
    TRACKING_STATUSES = {"applied", "interview", "rejected", "offer"}
    ALLOWED_STATUSES = {"draft", "ready_for_review", "approved", "needs_changes"} | TRACKING_STATUSES

    def __init__(self, database=None):
        self.database = database or DatabaseService()

    @staticmethod
    def has_valid_approval(application):
        return bool(
            application["content_version"] > 0
            and application["approved_version"] == application["content_version"]
            and application["approval_status"] == "approved"
            and application["approved_at"]
            and (application["application_message"] or "").strip()
            and (application["cover_letter"] or "").strip()
        )

    def _present(self, application):
        if application is not None:
            application["current_version_approved"] = self.has_valid_approval(application)
        return application

    def get_applications(self):
        return [self._present(a) for a in self.database.load_applications()]

    def get_application(self, application_id):
        return self._present(self.database.get_application(application_id))

    def _change(self, application_id, change):
        return self._present(self.database.update_application(application_id, change))

    @staticmethod
    def _expect_version(application, expected_version):
        if expected_version != application["content_version"]:
            raise ReviewConflict("Content changed since you loaded it. Reload and review the latest version.")

    @staticmethod
    def _require_content(application):
        if (application["content_version"] < 1
                or not (application["application_message"] or "").strip()
                or not (application["cover_letter"] or "").strip()):
            raise ReviewConflict("Save a nonempty application message and cover letter before approval.")

    def _invalidate(self, application, reason):
        events = []
        if application["approved_version"] is not None:
            events.append(("approval_invalidated",
                           f"Approval for version {application['approved_version']} invalidated: {reason}"))
        application["approved_version"] = None
        application["approved_at"] = None
        application["approval_status"] = "pending"
        return events

    def create_application(self, job_id, title, company, location, url,
                           description="", match_score=0):
        now = datetime.now().isoformat()
        return self._present(self.database.create_application({
            "job_id": str(job_id), "title": title, "company": company,
            "location": location, "url": url, "description": description,
            "match_score": match_score, "status": "draft",
            "generation_status": "not_generated", "approval_status": "pending",
            "application_message": "", "cover_letter": "",
            "created_at": now, "updated_at": now,
        }))

    def _save_content(self, application_id, application_message, cover_letter,
                      expected_version, event_type):
        if not application_message.strip() or not cover_letter.strip():
            raise ReviewConflict("Both the application message and cover letter must contain text.")

        def change(application):
            self._expect_version(application, expected_version)
            if event_type == "edited" and application["content_version"] == 0:
                raise ReviewConflict("Generate application content before editing it.")
            if (event_type == "edited"
                    and application["application_message"] == application_message
                    and application["cover_letter"] == cover_letter):
                # Saving unchanged text must not invalidate a valid approval.
                return []
            events = self._invalidate(application, "application content changed")
            application["application_message"] = application_message
            application["cover_letter"] = cover_letter
            application["content_version"] += 1
            application["generation_status"] = "generated"
            application["status"] = "ready_for_review"
            events.append((event_type,
                           f"Content {event_type}; version {application['content_version']} requires review"))
            return events

        return self._change(application_id, change)

    def save_generated_content(self, application_id, application_message, cover_letter,
                               expected_version):
        return self._save_content(application_id, application_message, cover_letter,
                                  expected_version, "generated")

    def edit_content(self, application_id, application_message, cover_letter, expected_version):
        return self._save_content(application_id, application_message, cover_letter,
                                  expected_version, "edited")

    def approve_application(self, application_id, expected_version):
        def change(application):
            self._expect_version(application, expected_version)
            self._require_content(application)
            if self.has_valid_approval(application):
                return []
            application["approved_version"] = application["content_version"]
            application["approved_at"] = datetime.now().isoformat()
            application["approval_status"] = "approved"
            application["status"] = "approved"
            return [("approved", f"Human approved content version {application['content_version']}")]
        return self._change(application_id, change)

    def reject_application(self, application_id, expected_version):
        def change(application):
            self._expect_version(application, expected_version)
            self._require_content(application)
            events = self._invalidate(application, "human requested changes")
            application["approval_status"] = "needs_changes"
            application["status"] = "ready_for_review"
            return events + [("changes_requested", "Human requested changes; content still requires review")]
        return self._change(application_id, change)

    def _set_status(self, application_id, new_status, note, expected_version=None):
        if new_status not in self.ALLOWED_STATUSES:
            raise ReviewConflict("Invalid application status.")
        if new_status == "approved":
            raise ReviewConflict("Use Approve current version after reviewing the saved content.")

        def change(application):
            if expected_version is not None:
                self._expect_version(application, expected_version)
            events = []
            if new_status in self.TRACKING_STATUSES:
                if not self.has_valid_approval(application):
                    raise ReviewConflict("The current content version requires human approval first.")
            else:
                if new_status == "draft" and application["content_version"] > 0:
                    raise ReviewConflict("Generated content must remain ready for review until approved.")
                if new_status != "draft":
                    self._require_content(application)
                events = self._invalidate(application, "returned to review")
                if new_status == "needs_changes":
                    application["approval_status"] = "needs_changes"
            application["status"] = "ready_for_review" if new_status == "needs_changes" else new_status
            return events + [("status_changed", note)]
        return self._change(application_id, change)

    def mark_applied(self, application_id, expected_version):
        return self._set_status(application_id, "applied",
                                "Application manually marked as submitted; no automatic submission performed",
                                expected_version)

    def mark_interview(self, application_id):
        return self._set_status(application_id, "interview", "Interview stage reached")

    def mark_rejected(self, application_id):
        return self._set_status(application_id, "rejected", "Application marked as rejected")

    def mark_offer(self, application_id):
        return self._set_status(application_id, "offer", "Offer received")

    def correct_status(self, application_id, new_status, note="Status corrected manually"):
        return self._set_status(application_id, new_status, note)

    def get_history(self, application_id):
        return self.database.get_application_history(application_id)
