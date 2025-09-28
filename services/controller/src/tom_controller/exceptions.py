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


class JWTValidationError(TomAuthException):
    """Raised when JWT validation fails."""

    pass


class JWTExpiredError(JWTValidationError):
    """Raised when JWT has expired."""

    pass


class JWTInvalidSignatureError(JWTValidationError):
    """Raised when JWT signature is invalid."""

    pass


class JWTInvalidClaimsError(JWTValidationError):
    """Raised when JWT claims are invalid."""

    pass


class JWKSFetchError(TomAuthException):
    """Raised when fetching JWKS fails."""

    pass
