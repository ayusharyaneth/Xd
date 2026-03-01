# ============================================================
# STRUCTURED LOGGING CONFIGURATION
# ============================================================

import sys
import os
from pathlib import Path
from loguru import logger
from typing import Optional
import json


class InterceptHandler:
    """Intercept standard logging and redirect to loguru"""
    
    def write(self, message: str):
        if message.strip():
            logger.opt(depth=0, exception=None).info(message.strip())
    
    def flush(self):
        pass


def setup_logger(
    log_level: str = "INFO",
    log_file: Optional[str] = "logs/dex_intel.log",
    json_format: bool = False,
    rotation: str = "10 MB",
    retention: str = "7 days"
) -> logger:
    """
    Configure structured logging with loguru
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Path to log file (None for console only)
        json_format: Whether to use JSON formatting
        rotation: Log file rotation size
        retention: Log file retention period
    
    Returns:
        Configured logger instance
    """
    
    # Remove default handler
    logger.remove()
    
    # Create logs directory if needed
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Console handler with color
    if json_format:
        console_format = (
            "{\"timestamp\":\"{time:YYYY-MM-DD HH:mm:ss.SSS}\","
            "\"level\":\"{level}\",\"message\":\"{message}\","
            "\"source\":\"{name}\",\"function\":\"{function}\","
            "\"line\":{line}}"
        )
    else:
        console_format = (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        )
    
    # Add console handler
    logger.add(
        sys.stdout,
        level=log_level,
        format=console_format,
        colorize=True,
        enqueue=True,
        backtrace=True,
        diagnose=True
    )
    
    # Add file handler if specified
    if log_file:
        if json_format:
            file_format = (
                "{\"timestamp\":\"{time:YYYY-MM-DD HH:mm:ss.SSS}\","
                "\"level\":\"{level}\",\"message\":\"{message}\","
                "\"source\":\"{name}\",\"function\":\"{function}\","
                "\"line\":{line}}"
            )
        else:
            file_format = (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
                "{name}:{function}:{line} | {message}"
            )
        
        logger.add(
            log_file,
            level=log_level,
            format=file_format,
            rotation=rotation,
            retention=retention,
            compression="zip",
            enqueue=True,
            backtrace=True,
            diagnose=True
        )
    
    # Intercept standard library logging
    import logging
    logging.basicConfig(handlers=[InterceptHandler()], level=logging.INFO)
    
    return logger


def get_logger(name: Optional[str] = None):
    """Get logger instance with optional name binding"""
    if name:
        return logger.bind(name=name)
    return logger


class StructuredLogFormatter:
    """Custom formatter for structured logging"""
    
    @staticmethod
    def format_event(
        event_type: str,
        data: dict,
        metadata: Optional[dict] = None
    ) -> str:
        """Format event as structured log entry"""
        log_entry = {
            "event_type": event_type,
            "data": data
        }
        if metadata:
            log_entry["metadata"] = metadata
        return json.dumps(log_entry)
    
    @staticmethod
    def format_alert(
        alert_type: str,
        token_address: str,
        severity: str,
        message: str,
        metrics: Optional[dict] = None
    ) -> str:
        """Format alert as structured log entry"""
        alert_entry = {
            "event_type": "ALERT",
            "alert_type": alert_type,
            "token_address": token_address,
            "severity": severity,
            "message": message
        }
        if metrics:
            alert_entry["metrics"] = metrics
        return json.dumps(alert_entry)
    
    @staticmethod
    def format_metric(
        metric_name: str,
        value: float,
        labels: Optional[dict] = None,
        timestamp: Optional[str] = None
    ) -> str:
        """Format metric as structured log entry"""
        metric_entry = {
            "event_type": "METRIC",
            "metric_name": metric_name,
            "value": value
        }
        if labels:
            metric_entry["labels"] = labels
        if timestamp:
            metric_entry["timestamp"] = timestamp
        return json.dumps(metric_entry)


# Performance logging decorator
import functools
import time


def log_execution_time(level: str = "DEBUG"):
    """Decorator to log function execution time"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.opt(depth=1).log(
                    level,
                    f"{func.__name__} completed in {execution_time:.3f}s"
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.opt(depth=1).error(
                    f"{func.__name__} failed after {execution_time:.3f}s: {e}"
                )
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.opt(depth=1).log(
                    level,
                    f"{func.__name__} completed in {execution_time:.3f}s"
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.opt(depth=1).error(
                    f"{func.__name__} failed after {execution_time:.3f}s: {e}"
                )
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


import asyncio


class ContextualLogger:
    """Logger with context binding for tracing"""
    
    def __init__(self, context: dict):
        self.context = context
        self._logger = logger.bind(**context)
    
    def debug(self, message: str, **extra):
        self._logger.bind(**extra).debug(message)
    
    def info(self, message: str, **extra):
        self._logger.bind(**extra).info(message)
    
    def warning(self, message: str, **extra):
        self._logger.bind(**extra).warning(message)
    
    def error(self, message: str, **extra):
        self._logger.bind(**extra).error(message)
    
    def critical(self, message: str, **extra):
        self._logger.bind(**extra).critical(message)
    
    def exception(self, message: str, **extra):
        self._logger.bind(**extra).exception(message)


def create_contextual_logger(**context) -> ContextualLogger:
    """Create a contextual logger with bound context"""
    return ContextualLogger(context)
