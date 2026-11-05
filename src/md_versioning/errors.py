"""Engine errors. These are internal; the agent surface translates them."""


class VersioningError(Exception):
    """Base class for engine errors."""


class UnknownDocumentError(VersioningError):
    """An operation other than read was attempted on an unknown document."""


class InvalidTagError(VersioningError):
    """A tag was not a single plain word."""


class InvalidNameError(VersioningError):
    """A directory or filename was not acceptable."""


class NameCollisionError(VersioningError):
    """A different document already uses the requested filename."""


class ConflictError(VersioningError):
    """A save was based on an older state than the current document.

    Carries the current document so the caller can re-describe what it
    wants against the current state.
    """

    def __init__(self, current):
        super().__init__("file changed")
        self.current = current
