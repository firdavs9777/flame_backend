from fastapi import HTTPException, status
from typing import Any, Optional, Dict


class AppException(HTTPException):
    """Base exception for the application."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.code = code
        self.details = details
        super().__init__(
            status_code=status_code,
            detail={"code": code, "message": message, "details": details},
        )


class ValidationError(AppException):
    """Validation error exception."""

    def __init__(self, message: str = "Validation failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="VALIDATION_ERROR",
            message=message,
            details=details,
        )


class InvalidCredentialsError(AppException):
    """Invalid credentials exception."""

    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="INVALID_CREDENTIALS",
            message=message,
        )


class UnauthorizedError(AppException):
    """Unauthorized exception."""

    def __init__(self, message: str = "Missing or invalid token"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHORIZED",
            message=message,
        )


class TokenExpiredError(AppException):
    """Token expired exception."""

    def __init__(self, message: str = "Access token has expired"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="TOKEN_EXPIRED",
            message=message,
        )


class ForbiddenError(AppException):
    """Forbidden exception."""

    def __init__(self, message: str = "Action not allowed"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="FORBIDDEN",
            message=message,
        )


class NotFoundError(AppException):
    """Not found exception."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="NOT_FOUND",
            message=message,
        )


class EmailExistsError(AppException):
    """Email already exists exception."""

    def __init__(self, message: str = "Email already registered"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="EMAIL_EXISTS",
            message=message,
        )


class AlreadyMatchedError(AppException):
    """Already matched exception."""

    def __init__(self, message: str = "Already matched with user"):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="ALREADY_MATCHED",
            message=message,
        )


class RateLimitedError(AppException):
    """Rate limited exception."""

    def __init__(self, message: str = "Too many requests"):
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="RATE_LIMITED",
            message=message,
        )


class ServerError(AppException):
    """Server error exception."""

    def __init__(self, message: str = "Internal server error"):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="SERVER_ERROR",
            message=message,
        )
