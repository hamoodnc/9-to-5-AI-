from io import BytesIO
from pathlib import Path
import re

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from pypdf import PdfReader

from email_services.gmail import GmailService
from job_services.jobs import JobService
from application_services.applications import ApplicationService, ReviewConflict
from profile_services.profile import ProfileService
from ai_services.gemini import generate_application as generate_ai_application


app = FastAPI(
    title="9-to-5 AI",
    description="Your personal AI career and productivity assistant",
    version="0.1.0",
)


@app.exception_handler(ReviewConflict)
async def review_conflict_handler(request, error):
    return JSONResponse(status_code=409, content={"detail": str(error)})


gmail_service = GmailService()
job_service = JobService()
application_service = ApplicationService()
profile_service = ProfileService()


# --------------------------------------------------
# REQUEST MODELS
# --------------------------------------------------

class DraftRequest(BaseModel):
    to: str
    subject: str
    body: str


class ApplicationRequest(BaseModel):
    job_id: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    match_score: int = 0


class ProfileUpdateRequest(BaseModel):
    name: str = ""
    email: str = ""
    location: str = "Ottawa, Ontario, Canada"
    education: str = ""
    program: str = "Computer Programming and Data Analysis"
    skills: list[str] = []
    experience: list[str] = []
    target_roles: list[str] = []
    job_preferences: dict = {}
    resume_text: str = ""


class ResumeRequest(BaseModel):
    resume_text: str


class ContentVersionRequest(BaseModel):
    expected_version: int = Field(ge=0)


class ContentEditRequest(ContentVersionRequest):
    application_message: str = Field(min_length=1)
    cover_letter: str = Field(min_length=1)


class StatusCorrectionRequest(BaseModel):
    new_status: str
    note: str = "Status corrected manually"


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def clean_text(text):
    return re.sub(
        r"\s+",
        " ",
        text or "",
    ).strip()


def get_resume_facts(resume_text):
    lower_resume = resume_text.lower()

    facts = {
        "college": "",
        "program": "",
        "gpa": "",
        "honours": "",
        "skills": [],
        "experience_points": [],
    }

    if "algonquin college" in lower_resume:
        facts["college"] = "Algonquin College"

    if "computer engineering" in lower_resume:
        facts["program"] = "Computer Engineering"

    if "4.0" in resume_text:
        facts["gpa"] = "4.0 GPA"

    if "dean's honours list" in lower_resume:
        facts["honours"] = "Dean's Honours List"

    known_skills = [
        "Java",
        "C++",
        "SQL",
        "Oracle",
        "object-oriented programming",
        "debugging",
        "computer hardware",
        "PC building",
        "Windows",
        "hardware diagnostics",
        "technical troubleshooting",
        "basic networking",
        "Microsoft Office 365",
        "documentation",
        "end-user support",
        "customer service",
        "leadership",
    ]

    for skill in known_skills:
        if skill.lower() in lower_resume:
            facts["skills"].append(skill)

    lines = [
        clean_text(line)
        for line in resume_text.splitlines()
        if clean_text(line)
    ]

    experience_terms = [
        "best buy",
        "technical",
        "troubleshooting",
        "customers",
        "customer",
        "computers",
        "electronics",
        "diagnostics",
        "supervised",
        "led",
        "coached",
        "support",
    ]

    for line in lines:
        lowered = line.lower()

        if (
            len(line) >= 45
            and any(
                term in lowered
                for term in experience_terms
            )
        ):
            facts["experience_points"].append(line)

    return facts


def get_job_keywords(
    title,
    description,
):
    text = (
        f"{title} {description}"
        .lower()
    )

    keywords = [
        "help desk",
        "technical support",
        "it support",
        "customer service",
        "troubleshooting",
        "windows",
        "microsoft 365",
        "office 365",
        "networking",
        "hardware",
        "software",
        "documentation",
        "end-user",
        "endpoint",
        "onboarding",
        "asset management",
        "java",
        "c++",
        "sql",
        "database",
        "programming",
    ]

    return [
        keyword
        for keyword in keywords
        if keyword in text
    ]


def find_matching_resume_strengths(
    resume_facts,
    job_keywords,
    max_results=5,
):
    matches = []

    for skill in resume_facts["skills"]:
        skill_lower = skill.lower()

        for keyword in job_keywords:
            if (
                keyword in skill_lower
                or skill_lower in keyword
            ):
                matches.append(skill)
                break

    fallback_skills = [
        "technical troubleshooting",
        "end-user support",
        "computer hardware",
        "Windows",
        "customer service",
        "documentation",
        "basic networking",
    ]

    for skill in fallback_skills:
        if (
            skill in resume_facts["skills"]
            and skill not in matches
        ):
            matches.append(skill)

        if len(matches) >= max_results:
            break

    return matches[:max_results]


# --------------------------------------------------
# HOME / DASHBOARD
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "name": "9-to-5 AI",
        "status": "online",
        "message": "Welcome to 9-to-5 AI",
    }


@app.get("/dashboard")
def dashboard():
    return FileResponse(
        Path(__file__).parent
        / "frontend"
        / "index.html"
    )


# --------------------------------------------------
# EMAIL
# --------------------------------------------------

@app.get("/emails")
def get_emails(
    max_results: int = 5
):
    return gmail_service.read_emails(
        max_results
    )


@app.post("/emails/draft")
def create_email_draft(
    request: DraftRequest
):
    return gmail_service.create_draft(
        request.to,
        request.subject,
        request.body,
    )


# --------------------------------------------------
# JOBS
# --------------------------------------------------

@app.get("/jobs")
def get_jobs(
    keywords: str = "IT support",
    location: str = "Ottawa",
    max_results: int = 10,
):
    return job_service.search_jobs(
        keywords=keywords,
        location=location,
        max_results=max_results,
    )


# --------------------------------------------------
# PROFILE
# --------------------------------------------------

@app.get("/profile")
def get_profile():
    return (
        profile_service.get_profile()
    )


@app.post("/profile")
def update_profile(
    request: ProfileUpdateRequest
):
    return (
        profile_service.update_profile(
            request.model_dump()
        )
    )


@app.post("/profile/resume")
def update_resume(
    request: ResumeRequest
):
    return (
        profile_service.set_resume_text(
            request.resume_text
        )
    )


@app.post("/profile/resume/upload")
async def upload_resume(
    file: UploadFile = File(...)
):
    filename = (
        file.filename or ""
    )

    if not filename.lower().endswith(
        ".pdf"
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Please upload a PDF resume."
            ),
        )

    try:
        contents = await file.read()

        reader = PdfReader(
            BytesIO(contents)
        )

        extracted_pages = []

        for page in reader.pages:
            text = (
                page.extract_text()
            )

            if text:
                extracted_pages.append(
                    text
                )

        resume_text = "\n\n".join(
            extracted_pages
        ).strip()

        if not resume_text:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No readable text was found "
                    "in the PDF."
                ),
            )

        profile_service.set_resume_text(
            resume_text
        )

        return {
            "status": "resume_uploaded",
            "filename": filename,
            "pages": len(
                reader.pages
            ),
            "characters_extracted": len(
                resume_text
            ),
            "resume_text": resume_text,
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not read PDF: "
                f"{str(error)}"
            ),
        )


# --------------------------------------------------
# APPLICATIONS
# --------------------------------------------------

@app.get("/applications")
def get_applications():
    return (
        application_service
        .get_applications()
    )


@app.post("/applications")
def create_application(
    request: ApplicationRequest
):
    return (
        application_service
        .create_application(
            job_id=request.job_id,
            title=request.title,
            company=request.company,
            location=request.location,
            url=request.url,
            description=(
                request.description
            ),
            match_score=(
                request.match_score
            ),
        )
    )


# --------------------------------------------------
# APPLICATION GENERATION
# --------------------------------------------------

@app.post(
    "/applications/{application_id}/generate"
)
def generate_application(
    application_id: int
):
    application = application_service.get_application(application_id)

    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    profile = profile_service.get_profile()
    resume_text = profile.get("resume_text") or ""

    if not resume_text:
        raise HTTPException(
            status_code=400,
            detail="Upload your resume before generating an application.",
        )

    candidate_data = {
        "name": profile.get("name", ""),
        "email": profile.get("email", ""),
        "location": profile.get("location", ""),
        "education": profile.get("education", ""),
        "program": profile.get("program", ""),
        "skills": profile.get("skills", []),
        "experience": profile.get("experience", []),
        "target_roles": profile.get("target_roles", []),
        "resume": resume_text,
    }

    job_data = {
        "title": application.get("title", ""),
        "company": application.get("company", ""),
        "location": application.get("location", ""),
        "description": application.get("description", ""),
        "url": application.get("url", ""),
    }

    try:
        ai_result = generate_ai_application(candidate_data, job_data)
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"Gemini could not generate the application: {str(error)}",
        )

    marker = "COVER LETTER:"

    if not isinstance(ai_result, str) or marker not in ai_result:
        raise HTTPException(
            status_code=500,
            detail="Gemini returned an unexpected response format.",
        )

    message_part, cover_part = ai_result.split(marker, 1)

    application_message = (
        message_part.replace("APPLICATION MESSAGE:", "", 1).strip()
    )
    cover_letter = cover_part.strip()

    if not application_message or not cover_letter:
        raise HTTPException(
            status_code=500,
            detail="Gemini returned incomplete application content.",
        )

    return application_service.save_generated_content(
        application_id=application_id,
        application_message=application_message,
        cover_letter=cover_letter,
        expected_version=application["content_version"],
    )


@app.put("/applications/{application_id}/content")
def edit_application_content(application_id: int, request: ContentEditRequest):
    application = application_service.edit_content(
        application_id, request.application_message, request.cover_letter,
        request.expected_version,
    )
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


# --------------------------------------------------
# APPLICATION APPROVAL
# --------------------------------------------------

@app.post(
    "/applications/{application_id}/approve"
)
def approve_application(
    application_id: int,
    request: ContentVersionRequest,
):
    application = (
        application_service
        .approve_application(
            application_id, request.expected_version
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    return application


@app.post(
    "/applications/{application_id}/reject"
)
def reject_application(
    application_id: int,
    request: ContentVersionRequest,
):
    application = (
        application_service
        .reject_application(
            application_id, request.expected_version
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    return application


# --------------------------------------------------
# APPLICATION STATUS TRACKER
# --------------------------------------------------

@app.post(
    "/applications/{application_id}/applied"
)
def mark_application_applied(
    application_id: int,
    request: ContentVersionRequest,
):
    application = (
        application_service
        .mark_applied(
            application_id, request.expected_version
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    return application


@app.post(
    "/applications/{application_id}/interview"
)
def mark_application_interview(
    application_id: int
):
    application = (
        application_service
        .mark_interview(
            application_id
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    return application


@app.post(
    "/applications/{application_id}/rejected"
)
def mark_application_rejected(
    application_id: int
):
    application = (
        application_service
        .mark_rejected(
            application_id
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    return application


@app.post(
    "/applications/{application_id}/offer"
)
def mark_application_offer(
    application_id: int
):
    application = (
        application_service
        .mark_offer(
            application_id
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    return application


# --------------------------------------------------
# CORRECT APPLICATION STATUS
# --------------------------------------------------

@app.post(
    "/applications/{application_id}/correct-status"
)
def correct_application_status(
    application_id: int,
    request: StatusCorrectionRequest,
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

    if (
        request.new_status
        not in allowed_statuses
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid status. Allowed statuses: "
                + ", ".join(
                    allowed_statuses
                )
            ),
        )

    existing_application = (
        application_service
        .get_application(
            application_id
        )
    )

    if existing_application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    application = (
        application_service
        .correct_status(
            application_id=(
                application_id
            ),
            new_status=(
                request.new_status
            ),
            note=(
                request.note
            ),
        )
    )

    return application


# --------------------------------------------------
# APPLICATION HISTORY
# --------------------------------------------------

@app.get(
    "/applications/{application_id}/history"
)
def get_application_history(
    application_id: int
):
    application = (
        application_service
        .get_application(
            application_id
        )
    )

    if application is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Application not found"
            ),
        )

    return (
        application_service
        .get_history(
            application_id
        )
    )