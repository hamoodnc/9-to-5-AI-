from datetime import datetime

from database_services.database import DatabaseService


class ApplicationService:
    def __init__(self):
        self.database = DatabaseService()

        self.applications = (
            self.database.load_applications()
        )

    def _now(self):
        return datetime.now().isoformat()

    def _refresh(self):
        self.applications = (
            self.database.load_applications()
        )

    def get_applications(self):
        self._refresh()
        return self.applications

    def get_application(self, application_id):
        self._refresh()

        for application in self.applications:
            if application["id"] == application_id:
                return application

        return None

    def create_application(
        self,
        job_id,
        title,
        company,
        location,
        url,
        description="",
        match_score=0,
    ):
        self._refresh()

        for application in self.applications:
            if str(application["job_id"]) == str(job_id):
                return application

        now = self._now()

        application = {
            "job_id": str(job_id),
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "description": description,
            "match_score": match_score,
            "status": "draft",
            "generation_status": "not_generated",
            "approval_status": "pending",
            "application_message": "",
            "cover_letter": "",
            "created_at": now,
            "updated_at": now,
        }

        self.database.save_application(
            application
        )

        self._refresh()

        saved_application = None

        for item in self.applications:
            if str(item["job_id"]) == str(job_id):
                saved_application = item
                break

        if saved_application:
            self.database.add_application_history(
                application_id=saved_application["id"],
                status="draft",
                note="Application created",
            )

            return saved_application

        return application

    def save_generated_content(
        self,
        application_id,
        application_message,
        cover_letter,
    ):
        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["application_message"] = (
            application_message
        )

        application["cover_letter"] = (
            cover_letter
        )

        application["generation_status"] = (
            "generated"
        )

        application["status"] = (
            "ready_for_review"
        )

        application["approval_status"] = (
            "pending"
        )

        application["updated_at"] = (
            self._now()
        )

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status="ready_for_review",
            note="Application content generated",
        )

        return self.get_application(
            application_id
        )

    def approve_application(
        self,
        application_id,
    ):
        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["approval_status"] = (
            "approved"
        )

        application["status"] = (
            "approved"
        )

        application["updated_at"] = (
            self._now()
        )

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status="approved",
            note="Application approved for submission",
        )

        return self.get_application(
            application_id
        )

    def reject_application(
        self,
        application_id,
    ):
        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["approval_status"] = (
            "needs_changes"
        )

        application["status"] = (
            "needs_changes"
        )

        application["updated_at"] = (
            self._now()
        )

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status="needs_changes",
            note="Application marked for changes",
        )

        return self.get_application(
            application_id
        )

    def mark_applied(
        self,
        application_id,
    ):
        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["status"] = "applied"
        application["updated_at"] = self._now()

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status="applied",
            note="Application marked as submitted",
        )

        return self.get_application(
            application_id
        )

    def mark_interview(
        self,
        application_id,
    ):
        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["status"] = "interview"
        application["updated_at"] = self._now()

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status="interview",
            note="Interview stage reached",
        )

        return self.get_application(
            application_id
        )

    def mark_rejected(
        self,
        application_id,
    ):
        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["status"] = "rejected"
        application["updated_at"] = self._now()

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status="rejected",
            note="Application marked as rejected",
        )

        return self.get_application(
            application_id
        )

    def mark_offer(
        self,
        application_id,
    ):
        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["status"] = "offer"
        application["updated_at"] = self._now()

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status="offer",
            note="Offer received",
        )

        return self.get_application(
            application_id
        )

    def correct_status(
        self,
        application_id,
        new_status,
        note="Status corrected manually",
    ):
        allowed_statuses = [
            "draft",
            "ready_for_review",
            "approved",
            "needs_changes",
            "applied",
            "interview",
            "rejected",
            "offer",
        ]

        if new_status not in allowed_statuses:
            return None

        application = self.get_application(
            application_id
        )

        if application is None:
            return None

        application["status"] = new_status
        application["updated_at"] = self._now()

        self.database.save_application(
            application
        )

        self.database.add_application_history(
            application_id=application_id,
            status=new_status,
            note=note,
        )

        return self.get_application(
            application_id
        )

    def get_history(
        self,
        application_id,
    ):
        return self.database.get_application_history(
            application_id
        )