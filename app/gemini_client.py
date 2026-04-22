import os
import base64
import httpx
from typing import Optional


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"


class GeminiClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.url = f"{GEMINI_API_URL}?key={api_key}"

    def analyze(self, image_data: bytes, question: str) -> str:
        """Analyze an image with a question using Gemini API."""
        image_b64 = base64.b64encode(image_data).decode("utf-8")

        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": question},
                        {
                            "inlineData": {
                                "mimeType": "image/jpeg",
                                "data": image_b64
                            }
                        }
                    ]
                }
            ]
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(self.url, json=payload)
            response.raise_for_status()

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise Exception("No response from Gemini")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                raise Exception("No text in Gemini response")

            return parts[0].get("text", "") or "[No text response]"