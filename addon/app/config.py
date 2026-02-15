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

    # Keep-alive settings
    keepalive_interval: int = 2700  # 45 minutes in seconds

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
        keepalive_interval=int(os.getenv("KEEPALIVE_INTERVAL", "2700")),
        amazon_email=os.getenv("AMAZON_EMAIL", ""),
        amazon_password=os.getenv("AMAZON_PASSWORD", ""),
    )
