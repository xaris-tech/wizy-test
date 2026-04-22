ERROR_CODES = {
    "EMPTY_FILE": "E001",
    "FILE_TOO_LARGE": "E002",
    "ANALYSIS_FAILED": "E003",
    "SESSION_NOT_FOUND": "E004",
    "INVALID_REQUEST": "E005",
}


def error_response(code: str, message: str) -> dict:
    """Create a structured error response."""
    return {
        "error": {
            "code": code,
            "message": message
        }
    }