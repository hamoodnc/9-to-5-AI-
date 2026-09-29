import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors


load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY was not found in the .env file."
    )

client = genai.Client(api_key=api_key)

MODEL_NAME = "gemini-3-flash-preview"


def generate_with_retry(
    contents,
    max_attempts=4,
    initial_delay=2,
):
    """
    Send a request to Gemini.

    Automatically retries temporary server errors such as
    503 UNAVAILABLE using exponential backoff.
    """

    delay = initial_delay

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=contents,
            )

            return response.text

        except errors.ServerError as error:
            # Retry temporary Gemini server errors.
            if attempt == max_attempts:
                raise

            print(
                f"Gemini temporarily unavailable "
                f"(attempt {attempt}/{max_attempts}). "
                f"Retrying in {delay} seconds..."
            )

            time.sleep(delay)

            # Exponential backoff:
            # 2 -> 4 -> 8 seconds
            delay *= 2


def test_gemini():
    return generate_with_retry(
        "Reply with exactly: 9-to-5 AI is connected"
    )


def generate_application(profile, job):
    prompt = f"""
You are the AI application assistant inside 9-to-5 AI.

Your job is to help Ahmed create accurate, tailored job applications.

STRICT RULES:

1. Use ONLY facts contained in the candidate profile and resume below.

2. Never invent skills, experience, education, certifications,
   employers, dates, achievements, or qualifications.

3. Tailor the writing specifically to the job description.

4. Highlight the candidate's most relevant real experience
   and skills.

5. Write naturally and professionally.
   Do not sound robotic.

6. Do not claim the candidate meets a requirement unless
   the profile or resume supports it.

7. If the candidate lacks a requirement, do not fabricate it.

8. Everything generated must be returned for human review
   before submission.

9. Never claim that an application has been submitted.

10. Keep the cover letter concise and specific to the position.


CANDIDATE PROFILE AND RESUME:

{profile}


JOB INFORMATION AND DESCRIPTION:

{job}


Create the following:


APPLICATION MESSAGE:

Write a short, tailored message to the employer.
Aim for approximately 80 to 150 words.


COVER LETTER:

Write a tailored cover letter.
Aim for approximately 250 to 400 words.


Return exactly in this format:

APPLICATION MESSAGE:
[message]

COVER LETTER:
[cover letter]
"""

    return generate_with_retry(prompt)