import os
import re
import requests

from dotenv import load_dotenv


load_dotenv()


class JobService:
    def __init__(self):
        self.app_id = os.getenv("ADZUNA_APP_ID")
        self.app_key = os.getenv("ADZUNA_APP_KEY")

        if not self.app_id or not self.app_key:
            raise ValueError(
                "Adzuna API credentials are missing from the .env file."
            )

        self.target_keywords = [
            "it support",
            "help desk",
            "helpdesk",
            "technical support",
            "desktop support",
            "service desk",
            "l1 support",
            "level 1 support",
            "junior developer",
            "software developer",
            "programmer",
            "data analyst",
            "computer technician",
            "systems support",
        ]

        self.entry_level_title_keywords = [
            "entry level",
            "entry-level",
            "junior",
            "l1",
            "level 1",
            "new grad",
            "graduate",
            "associate",
        ]

        self.senior_title_keywords = [
            "senior",
            "manager",
            "lead",
            "director",
            "principal",
            "architect",
        ]

    def search_jobs(
        self,
        keywords="IT support",
        location="Ottawa",
        max_results=10,
    ):
        url = "https://api.adzuna.com/v1/api/jobs/ca/search/1"

        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": keywords,
            "where": location,
            "results_per_page": max_results,
            "content-type": "application/json",
        }

        response = requests.get(
            url,
            params=params,
            timeout=20,
        )

        response.raise_for_status()

        data = response.json()

        jobs = []
        seen_jobs = set()

        for result in data.get("results", []):
            job = {
                "id": result.get("id"),
                "title": result.get("title", ""),
                "company": (
                    result.get("company", {})
                    .get("display_name", "")
                ),
                "location": (
                    result.get("location", {})
                    .get("display_name", "")
                ),
                "description": result.get(
                    "description",
                    "",
                ),
                "url": result.get("redirect_url", ""),
                "created": result.get("created", ""),
                "salary_min": result.get("salary_min"),
                "salary_max": result.get("salary_max"),
                "status": "new",
            }

            duplicate_key = self.make_duplicate_key(job)

            if duplicate_key in seen_jobs:
                continue

            seen_jobs.add(duplicate_key)

            score_data = self.calculate_match_score(job)

            job["match_score"] = score_data["score"]
            job["match_reasons"] = score_data["reasons"]

            jobs.append(job)

        jobs.sort(
            key=lambda job: job["match_score"],
            reverse=True,
        )

        return jobs

    def calculate_match_score(self, job):
        score = 50
        reasons = []

        title = job.get("title", "").lower()
        description = job.get("description", "").lower()
        location = job.get("location", "").lower()

        combined_text = f"{title} {description}"

        # Target role match
        for keyword in self.target_keywords:
            if keyword in combined_text:
                score += 8
                reasons.append(
                    f"Matches target role keyword: {keyword}"
                )
                break

        # Entry-level bonus only checks the TITLE now
        for keyword in self.entry_level_title_keywords:
            if keyword in title:
                score += 12
                reasons.append(
                    "Title appears entry-level or junior"
                )
                break

        # Ottawa bonus
        if "ottawa" in location:
            score += 10
            reasons.append("Located in Ottawa")

        # Remote bonus
        if "remote" in combined_text:
            score += 8
            reasons.append("Remote work mentioned")

        # Relocation bonus
        relocation_terms = [
            "relocation",
            "relocation assistance",
            "relocation package",
            "relocation support",
        ]

        if any(term in combined_text for term in relocation_terms):
            score += 8
            reasons.append(
                "Relocation assistance may be available"
            )

        # Senior role penalty
        for keyword in self.senior_title_keywords:
            if keyword in title:
                score -= 20
                reasons.append(
                    f"Role appears more senior: {keyword}"
                )
                break

        years = self.extract_years_experience(combined_text)

        if years is not None:
            if years >= 8:
                score -= 30
                reasons.append(
                    f"High experience requirement: {years}+ years"
                )

            elif years >= 5:
                score -= 20
                reasons.append(
                    f"Requires about {years}+ years of experience"
                )

            elif years >= 3:
                score -= 10
                reasons.append(
                    f"Requires about {years}+ years of experience"
                )

            elif years <= 2:
                score += 8
                reasons.append(
                    "Experience requirement appears achievable"
                )

        # Salary bonus
        if (
            job.get("salary_min") is not None
            or job.get("salary_max") is not None
        ):
            score += 3
            reasons.append("Salary information is available")

        score = max(0, min(score, 100))

        return {
            "score": score,
            "reasons": reasons,
        }

    def extract_years_experience(self, text):
        patterns = [
            r"(\d+)\+?\s+years?\s+of\s+experience",
            r"(\d+)\+?\s+years?\s+experience",
            r"(\d+)\+?\s+years?\s+exp\b",
            r"(\d+)\+?\s*yrs?\b",
            r"minimum\s+of\s+(\d+)\s+years",
            r"at\s+least\s+(\d+)\s+years",
        ]

        found_years = []

        for pattern in patterns:
            matches = re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            for match in matches:
                try:
                    found_years.append(int(match))
                except ValueError:
                    pass

        # Also catch written-out values that appear commonly
        written_numbers = {
            "one year": 1,
            "two years": 2,
            "three years": 3,
            "four years": 4,
            "five years": 5,
            "six years": 6,
            "seven years": 7,
            "eight years": 8,
            "nine years": 9,
            "ten years": 10,
        }

        for phrase, value in written_numbers.items():
            if phrase in text:
                found_years.append(value)

        if not found_years:
            return None

        return max(found_years)

    def make_duplicate_key(self, job):
        title = self.normalize_text(
            job.get("title", "")
        )

        company = self.normalize_text(
            job.get("company", "")
        )

        return f"{title}|{company}"

    def normalize_text(self, value):
        value = value.lower().strip()

        value = re.sub(
            r"[^a-z0-9\s]",
            "",
            value,
        )

        value = re.sub(
            r"\s+",
            " ",
            value,
        )

        return value