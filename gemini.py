"""Gemini REST API wrapper — works with X-goog-api-key format."""
import logging
import os
import time

import requests

log = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent"


def generate(
    prompt: str,
    retries: int = 2,
    temperature: float = 0.7,
    json_mode: bool = False,
) -> str:
    """Call Gemini and return the text response, retrying on empty replies."""
    key = os.getenv("GEMINI_API_KEY", "")
    last_err = None
    generation_config: dict = {"temperature": temperature}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    for attempt in range(retries + 1):
        try:
            resp = requests.post(
                GEMINI_URL,
                headers={"Content-Type": "application/json", "X-goog-api-key": key},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": generation_config,
                },
                timeout=90,
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                last_err = RuntimeError("Gemini returned no candidates")
                time.sleep(2 * (attempt + 1))
                continue
            parts = candidates[0].get("content", {}).get("parts") or []
            text = parts[0].get("text", "") if parts else ""
            if text.strip():
                return text
            last_err = RuntimeError("Gemini returned empty text")
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Gemini failed after {retries + 1} attempts: {last_err}")
