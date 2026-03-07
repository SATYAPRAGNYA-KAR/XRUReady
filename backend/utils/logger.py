"""
backend/utils/logger.py
Structured logging setup.
"""
import sys
from loguru import logger
import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logger.remove()
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> — <level>{message}</level>",
    colorize=True,
)
logger.add(
    "logs/server.log",
    level="DEBUG",
    rotation="10 MB",
    retention="7 days",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{line} — {message}",
)
