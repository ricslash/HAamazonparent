"""Custom exceptions for the Amazon Parent Dashboard integration."""
from __future__ import annotations


class AmazonParentException(Exception):
    """Base exception for Amazon Parent Dashboard integration."""


class AuthenticationError(AmazonParentException):
    """Exception raised when authentication fails."""


class SessionExpiredError(AmazonParentException):
    """Exception raised when session has expired (401/403)."""


class NetworkError(AmazonParentException):
    """Exception raised when network operations fail."""


class ConfigurationError(AmazonParentException):
    """Exception raised when configuration is invalid."""


class CookieError(AmazonParentException):
    """Exception raised when cookie operations fail."""
