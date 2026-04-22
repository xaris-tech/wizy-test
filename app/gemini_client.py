import os
import base64
import httpx
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"


@dataclass
class AgentStep:
    type: str
    content: str
    image_data: Optional[str] = None


@dataclass
class AgenticResult:
    answer: str
    steps: List[Dict[str, Any]]


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

    def analyze_agentic(self, image_data: bytes, question: str) -> AgenticResult:
        """Analyze with code execution - returns steps + final answer."""
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
            ],
            "tools": [{"code_execution": {}}]
        }

        with httpx.Client(timeout=120.0) as client:
            response = client.post(self.url, json=payload)
            response.raise_for_status()

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise Exception("No response from Gemini")

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])

            steps = []
            final_answer = ""

            for part in parts:
                if "executableCode" in part:
                    steps.append({
                        "type": "code",
                        "content": part["executableCode"].get("code", ""),
                        "language": part["executableCode"].get("language", "python")
                    })
                elif "codeExecutionResult" in part:
                    steps.append({
                        "type": "output",
                        "content": part["codeExecutionResult"].get("output", ""),
                        "outcome": part["codeExecutionResult"].get("outcome", "")
                    })
                elif "inlineData" in part and "imageData" not in part.get("inlineData", {}):
                    pass
                elif "text" in part:
                    steps.append({
                        "type": "think",
                        "content": part.get("text", "")
                    })
                    final_answer = part.get("text", "")

            return AgenticResult(answer=final_answer, steps=steps)