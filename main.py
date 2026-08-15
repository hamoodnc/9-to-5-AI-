from fastapi import FastAPI

app = FastAPI(
    title="9-to-5 AI",
    description="Your personal AI career and productivity assistant",
    version="0.1.0"
)


@app.get("/")
def home():
    return {
        "name": "9-to-5 AI",
        "status": "online",
        "message": "Welcome to 9-to-5 AI"
    }