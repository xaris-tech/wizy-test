import logging
import json
import uuid
from contextvars import ContextVar
from datetime import datetime
from typing import Optional, Any
from functools import wraps
import asyncio

request_id_context: ContextVar[Optional[str]] = ContextVar('request_id', default=None)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        request_id = request_id_context.get()
        if request_id:
            log_data["request_id"] = request_id
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        for key, value in record.__dict__.items():
            if key not in ('msg', 'args', 'exc_info', 'exc_text', 'levelname', 
                          'levelno', 'pathname', 'filename', 'module', 'funcName',
                          'lineno', 'created', 'msecs', 'relativeCreated', 'thread',
                          'threadName', 'processName', 'process', 'message', 'name',
                          'stack_info'):
                if value is not None:
                    log_data[key] = str(value) if not isinstance(value, (str, int, float, bool)) else value
        
        return json.dumps(log_data)


class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(StructuredFormatter())
            self.logger.addHandler(handler)
    
    def _log(self, level: int, message: str, **kwargs):
        extra = kwargs.pop('extra', {})
        if kwargs:
            extra.update(kwargs)
        self.logger.log(level, message, extra=extra)
    
    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)


def get_logger(name: str) -> StructuredLogger:
    return StructuredLogger(name)


def set_request_id(request_id: str):
    request_id_context.set(request_id)


def get_request_id() -> Optional[str]:
    return request_id_context.get()


class RequestIdLogger:
    """Context manager for request-scoped logging"""
    def __init__(self, request_id: str):
        self.request_id = request_id
        self.old_value = None
    
    def __enter__(self):
        self.old_value = request_id_context.get()
        request_id_context.set(self.request_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        request_id_context.set(self.old_value)


def log_with_request_id(logger: StructuredLogger, level: int, message: str):
    request_id = get_request_id()
    if request_id:
        logger.log(level, message, request_id=request_id)
    else:
        logger.log(level, message)