"""Tom core exceptions."""


class TomException(Exception):
    """Base exception for Tom operations."""
    pass


class TomAuthException(TomException):
    """Authentication/authorization errors."""
    pass


class TomNotFoundException(TomException):
    """Resource not found errors."""
    pass


class TomValidationException(TomException):
    """Validation/bad request errors."""
    pass
