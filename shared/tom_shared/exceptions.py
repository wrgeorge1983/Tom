"""Shared exceptions for Tom."""


class TomException(Exception):
    """Base exception for Tom operations."""
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
