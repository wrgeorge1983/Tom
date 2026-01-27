"""Tom core exceptions."""


class TomException(Exception):
    """Base exception for Tom operations."""

    pass


class TomAuthException(TomException):
    """Authentication errors (401)."""

    pass


class TomAuthorizationException(TomException):
    """Authorization errors (403) - authenticated but not permitted."""

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


class TomCacheException(TomException):
    """Cache errors."""

    pass


class TomCacheSerializationError(TomCacheException):
    """Raised when serializing data to cache fails."""

    pass


class TomCacheBackendError(TomCacheException):
    """Raised when cache backend fails."""

    pass


class TomCacheInvalidKeyError(TomCacheException):
    """Raised when cache key is invalid."""

    pass


class TomCacheDecodingError(TomCacheException):
    """Raised when decoding data from cache fails."""

    pass


class TomParsingException(TomException):
    """Raised when output parsing fails."""

    pass


class TomTemplateNotFoundException(TomParsingException):
    """Raised when a parsing template is not found."""

    pass
