"""
Error handling framework for the video generation pipeline.

Strategies:
1. Retryable errors: Temporary failures that might succeed on retry
   - Network timeouts
   - Rate limits (429 Too Many Requests)
   - Temporary service unavailable (503)
   
2. Permanent errors: Failures that won't be fixed by retrying
   - Invalid input (400)
   - Authentication failed (401)
   - File not found (404)
   - Malformed data

Usage:
    try:
        metadata = fetch_imdb(url)
    except RetryableError as e:
        coordinator.handle_failure(job_id, str(e), should_retry=True)
    except PermanentError as e:
        coordinator.handle_failure(job_id, str(e), should_retry=False)
"""

import logging
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """Error categories for classification"""
    NETWORK = "network"
    API_RATE_LIMIT = "api_rate_limit"
    API_ERROR = "api_error"
    STORAGE = "storage"
    COMPUTATION = "computation"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


class RetryableError(Exception):
    """
    Base class for errors that should be retried.
    
    Examples:
    - Network timeout
    - Service temporarily unavailable
    - Rate limit hit
    """
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        retry_after_seconds: Optional[int] = None,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        self.retry_after_seconds = retry_after_seconds
        logger.warning(f"Retryable error ({category}): {message}")


class PermanentError(Exception):
    """
    Base class for errors that should NOT be retried.
    
    Examples:
    - Invalid input format
    - Missing required file
    - Authentication failure
    """
    
    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
    ):
        super().__init__(message)
        self.message = message
        self.category = category
        logger.error(f"Permanent error ({category}): {message}")


# ========== Network Errors ==========

class NetworkTimeoutError(RetryableError):
    """Request timed out before completion"""
    
    def __init__(self, message: str, timeout_seconds: int = 30):
        super().__init__(
            f"{message} (timeout after {timeout_seconds}s)",
            category=ErrorCategory.NETWORK,
        )


class ConnectionError(RetryableError):
    """Could not establish connection"""
    
    def __init__(self, message: str):
        super().__init__(message, category=ErrorCategory.NETWORK)


# ========== API Errors ==========

class RateLimitError(RetryableError):
    """API rate limit exceeded (HTTP 429)"""
    
    def __init__(self, service: str, retry_after_seconds: int = 60):
        super().__init__(
            f"{service} rate limit hit",
            category=ErrorCategory.API_RATE_LIMIT,
            retry_after_seconds=retry_after_seconds,
        )


class TemporaryServiceUnavailable(RetryableError):
    """Service temporarily unavailable (HTTP 503)"""
    
    def __init__(self, service: str, retry_after_seconds: int = 30):
        super().__init__(
            f"{service} temporarily unavailable",
            category=ErrorCategory.API_ERROR,
            retry_after_seconds=retry_after_seconds,
        )


class APIError(RetryableError):
    """Generic API error (might be temporary)"""
    
    def __init__(self, service: str, status_code: int, message: str):
        super().__init__(
            f"{service} API error {status_code}: {message}",
            category=ErrorCategory.API_ERROR,
        )


class AuthenticationError(PermanentError):
    """Authentication failed (invalid API key, etc.)"""
    
    def __init__(self, service: str):
        super().__init__(
            f"Authentication failed for {service}",
            category=ErrorCategory.VALIDATION,
        )


# ========== Storage Errors ==========

class FileNotFoundError(PermanentError):
    """Required file not found"""
    
    def __init__(self, file_path: str):
        super().__init__(
            f"File not found: {file_path}",
            category=ErrorCategory.STORAGE,
        )


class StorageError(RetryableError):
    """Storage operation failed (disk I/O, S3, etc.)"""
    
    def __init__(self, message: str, retryable: bool = True):
        error_class = RetryableError if retryable else PermanentError
        super().__init__(message, category=ErrorCategory.STORAGE)


# ========== Computation Errors ==========

class FFmpegError(PermanentError):
    """FFmpeg operation failed (usually not retryable)"""
    
    def __init__(self, message: str, is_retryable: bool = False):
        error_class = RetryableError if is_retryable else PermanentError
        super().__init__(
            f"FFmpeg error: {message}",
            category=ErrorCategory.COMPUTATION,
        )


class InvalidInputError(PermanentError):
    """Input validation failed"""
    
    def __init__(self, field: str, reason: str):
        super().__init__(
            f"Invalid {field}: {reason}",
            category=ErrorCategory.VALIDATION,
        )


# ========== Error Recovery Helpers ==========

class ErrorRecoveryStrategy:
    """
    Strategies for recovering from common errors.
    
    Usage:
        strategy = ErrorRecoveryStrategy()
        should_retry = strategy.should_retry_error(error)
        backoff = strategy.calculate_backoff(error, attempt)
    """
    
    @staticmethod
    def should_retry_error(error: Exception) -> bool:
        """Determine if error is retryable"""
        return isinstance(error, RetryableError)
    
    @staticmethod
    def classify_error(error: Exception) -> tuple[bool, ErrorCategory]:
        """
        Classify an error and return (is_retryable, category)
        
        Returns:
            (is_retryable, category)
        """
        if isinstance(error, RetryableError):
            return (True, error.category)
        elif isinstance(error, PermanentError):
            return (False, error.category)
        else:
            return (False, ErrorCategory.UNKNOWN)
    
    @staticmethod
    def get_retry_after_seconds(error: Exception) -> Optional[int]:
        """
        Extract retry-after hint from error (if available).
        
        Some APIs tell us how long to wait before retrying.
        """
        if isinstance(error, RetryableError):
            return error.retry_after_seconds
        return None
    
    @staticmethod
    def should_alert_monitoring(error: Exception) -> bool:
        """Determine if error should trigger monitoring alert"""
        # Alert on permanent errors and repeated retries
        return isinstance(error, PermanentError)


# ========== Validation Helpers ==========

class InputValidator:
    """Helpers for input validation"""
    
    @staticmethod
    def validate_imdb_url(url: str) -> bool:
        """
        Validate IMDb URL format.
        
        Valid formats:
        - https://www.imdb.com/title/tt0111161/
        - https://www.imdb.com/title/tt0111161
        
        Raises:
            InvalidInputError if invalid
        """
        import re
        
        pattern = r"https://www\.imdb\.com/title/(tt\d+)/?$"
        if not re.match(pattern, url):
            raise InvalidInputError(
                "imdb_url",
                "Must match format https://www.imdb.com/title/tt<digits>/",
            )
        return True
    
    @staticmethod
    def extract_imdb_id(url: str) -> str:
        """
        Extract IMDb ID from URL.
        
        Returns:
            IMDb ID (e.g., "tt0111161")
            
        Raises:
            InvalidInputError if URL invalid
        """
        InputValidator.validate_imdb_url(url)
        
        import re
        match = re.search(r"(tt\d+)", url)
        if not match:
            raise InvalidInputError("imdb_url", "Could not extract IMDb ID")
        
        return match.group(1)
