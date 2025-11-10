"""Tom core exceptions."""


class TomException(Exception):
    """Base exception for Tom operations."""

    pass


class GatingException(TomException):
    pass


class TransientException(TomException):
    pass


class PermanentException(TomException):
    """Permanent failures that should not be retried."""
    pass


class TomAuthException(TomException):
    """Legacy auth exception - use AuthenticationException for worker jobs."""
    pass


class AuthenticationException(PermanentException):
    """Authentication failures that should never be retried.
    
    This includes:
    - Invalid credentials (username/password)
    - Expired credentials
    - Account lockouts
    - Permission denied
    
    These failures indicate a configuration problem that won't be
    resolved by retrying the same operation.
    """
    pass
