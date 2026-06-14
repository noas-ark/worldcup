"""Gemini REST API wrapper — works with X-goog-api-key format."""
import os
import requests

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"

def generate(prompt: str) -> str:
    """Call Gemini and return the text response."""
    key = os.getenv("GEMINI_API_KEY", "")
    resp = requests.post(
        GEMINI_URL,
        headers={"Content-Type": "application/json", "X-goog-api-key": key},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
