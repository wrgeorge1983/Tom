"""Tom core exceptions."""


class TomException(Exception):
    """Base exception for Tom operations."""

    pass


class GatingException(TomException):
    pass


class TransientException(TomException):
    pass


class PermanentException(TomException):
    pass

class TomAuthException(TomException):
    pass
