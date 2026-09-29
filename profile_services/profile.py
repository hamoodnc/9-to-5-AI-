from database_services.database import DatabaseService


class ProfileService:
    def __init__(self):
        self.database = DatabaseService()

        saved_profile = self.database.load_profile()

        if saved_profile:
            self.profile = saved_profile
        else:
            self.profile = {
                "name": "",
                "email": "",
                "location": "Ottawa, Ontario, Canada",
                "education": "",
                "program": "Computer Programming and Data Analysis",
                "skills": [],
                "experience": [],
                "target_roles": [
                    "IT Support",
                    "Help Desk",
                    "Technical Support",
                    "Junior Developer",
                    "Programmer",
                    "Data Analyst",
                ],
                "job_preferences": {
                    "preferred_location": "Ottawa",
                    "remote_anywhere_canada": True,
                    "relocation_if_assistance": True,
                },
                "resume_text": "",
            }

            self.database.save_profile(
                self.profile
            )

    def get_profile(self):
        return self.profile

    def update_profile(self, updates):
        for key, value in updates.items():
            if key in self.profile:
                self.profile[key] = value

        self.database.save_profile(
            self.profile
        )

        return self.profile

    def set_resume_text(self, resume_text):
        self.profile["resume_text"] = resume_text

        self.database.save_profile(
            self.profile
        )

        return self.profile