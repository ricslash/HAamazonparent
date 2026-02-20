"""Configuration management for the add-on."""
import os
from pydantic import BaseModel


class Config(BaseModel):
    """Application configuration."""

    log_level: str = "info"
    auth_timeout: int = 300
    session_duration: int = 86400
    host: str = "0.0.0.0"
    port: int = 8100

    # Scheduled re-authentication settings
    reauth_interval: int = 72000  # ~20 hours in seconds, randomized ±1h
    health_check_interval: int = 14400  # 4 hours in seconds
    reauth_max_retries: int = 3

    # Amazon credentials (for auto re-login)
    amazon_email: str = ""
    amazon_password: str = ""

    # Paths
    share_dir: str = "/share/amazonparent"
    cookie_file: str = "cookies.enc"
    key_file: str = ".key"

    # Browser settings
    browser_timeout: int = 300000  # 5 minutes in milliseconds
    browser_navigation_timeout: int = 30000  # 30 seconds


def get_config() -> Config:
    """Get configuration from environment variables."""
    return Config(
        log_level=os.getenv("LOG_LEVEL", "info"),
        auth_timeout=int(os.getenv("AUTH_TIMEOUT", "300")),
        session_duration=int(os.getenv("SESSION_DURATION", "86400")),
        reauth_interval=int(os.getenv("REAUTH_INTERVAL", "72000")),
        health_check_interval=int(os.getenv("HEALTH_CHECK_INTERVAL", "14400")),
        reauth_max_retries=int(os.getenv("REAUTH_MAX_RETRIES", "3")),
        amazon_email=os.getenv("AMAZON_EMAIL", ""),
        amazon_password=os.getenv("AMAZON_PASSWORD", ""),
    )
