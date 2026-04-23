import os
import base64
import httpx
import logging
import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"
GEMINI_API_STREAM_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:streamGenerateContent"

logger = logging.getLogger(__name__)


@dataclass
class AgentStep:
    type: str
    content: str
    image_data: Optional[str] = None


@dataclass
class AgenticResult:
    answer: str
    steps: List[Dict[str, Any]]


class GeminiAPI:
    def __init__(self, api_keys: List[str]):
        self.api_keys = api_keys
        self.current_key_index = 0
        self.retry_count = 0
        self.max_retries = 3

    @property
    def current_key(self) -> str:
        return self.api_keys[self.current_key_index]

    @property
    def current_url(self) -> str:
        return f"{GEMINI_API_URL}?key={self.current_key}"

    def rotate_key(self):
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        self.retry_count = 0
        logger.info(f"Rotated to API key #{self.current_key_index + 1}")

    def is_quota_error(self, response) -> bool:
        """Check if response is a quota/rate limit error."""
        if response.status_code in (429, 503):
            return True
        if response.status_code == 400:
            try:
                data = response.json()
                error = data.get("error", {})
                return error.get("code") in ("RESOURCE_EXHAUSTED", "rateLimitExceeded", " quota ")
            except:
                pass
        return False

    def _call_api(self, payload: Dict, timeout: float = 60.0) -> Dict:
        """Make API call with exponential backoff on quota errors."""
        last_error = None
        
        # Try each key up to max_retries times
        while self.current_key_index < len(self.api_keys):
            try:
                with httpx.Client(timeout=timeout) as client:
                    response = client.post(self.current_url, json=payload)

                    if self.is_quota_error(response):
                        # Calculate exponential backoff: 1s, 2s, 4s...
                        wait_time = 2 ** self.retry_count
                        logger.warning(f"Quota error on key #{self.current_key_index + 1}. Waiting {wait_time}s before retry...")
                        time.sleep(wait_time)
                        self.retry_count += 1
                        
                        if self.retry_count >= self.max_retries:
                            logger.warning(f"Max retries ({self.max_retries}) reached for key #{self.current_key_index + 1}, rotating...")
                            self.rotate_key()
                        continue

                    response.raise_for_status()
                    self.retry_count = 0
                    return response.json()

            except httpx.HTTPStatusError as e:
                if "429" in str(e) or "503" in str(e):
                    wait_time = 2 ** self.retry_count
                    logger.warning(f"Rate limit on key #{self.current_key_index + 1}. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    self.retry_count += 1
                    
                    if self.retry_count >= self.max_retries:
                        logger.warning(f"Max retries for key #{self.current_key_index + 1}, rotating...")
                        self.rotate_key()
                    continue
                raise
            except Exception as e:
                last_error = e
                break

        raise Exception(f"All {len(self.api_keys)} API keys exhausted after {self.max_retries} retries each.")

    def analyze(self, image_data: bytes, question: str) -> str:
        """Analyze an image with a question."""
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

        data = self._call_api(payload, timeout=60.0)
        candidates = data.get("candidates", [])
        if not candidates:
            raise Exception("No response from Gemini")

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise Exception("No text in Gemini response")

        return parts[0].get("text", "") or "[No text response]"

    def analyze_agentic(self, image_data: bytes, question: str) -> AgenticResult:
        """Analyze with code execution."""
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

        data = self._call_api(payload, timeout=120.0)
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
                result = part["codeExecutionResult"]
                step_data = {
                    "type": "output",
                    "content": result.get("output", ""),
                    "outcome": result.get("outcome", "")
                }
                # Check for intermediate images in code execution result
                if "inlineData" in result:
                    step_data["image_data"] = result["inlineData"].get("data", "")
                    step_data["image_mime_type"] = result["inlineData"].get("mimeType", "image/png")
                steps.append(step_data)
            elif "inlineData" in part:
                # Image from code execution (cropped/annotated)
                steps.append({
                    "type": "observe",
                    "content": "Intermediate image from code execution",
                    "image_data": part["inlineData"].get("data", ""),
                    "image_mime_type": part["inlineData"].get("mimeType", "image/png")
                })
            elif "text" in part and part.get("text"):
                steps.append({
                    "type": "think",
                    "content": part.get("text", "")
                })
                final_answer = part.get("text", "")

        return AgenticResult(answer=final_answer, steps=steps)


def get_gemini_client() -> GeminiAPI:
    """Factory function to create GeminiAPI with single or multiple keys."""
    # Check for multiple keys first
    keys_env = os.getenv("GEMINI_API_KEYS", "")
    if keys_env:
        api_keys = [k.strip() for k in keys_env.split(",") if k.strip()]
        if api_keys:
            logger.info(f"Using {len(api_keys)} API keys for rotation")
            return GeminiAPI(api_keys)

    # Fall back to single key
    single_key = os.getenv("GEMINI_API_KEY", "")
    if not single_key:
        raise ValueError("GEMINI_API_KEY or GEMINI_API_KEYS is required")

    return GeminiAPI([single_key])