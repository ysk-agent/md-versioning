"""Markdown + frontmatter versioning engine."""

from .engine import Document, Engine
from .errors import (
    ConflictError,
    InvalidNameError,
    InvalidTagError,
    NameCollisionError,
    UnknownDocumentError,
    VersioningError,
)
from .surface import AGENT_PROMPT, AgentSurface

__all__ = [
    "AGENT_PROMPT",
    "AgentSurface",
    "ConflictError",
    "Document",
    "Engine",
    "InvalidNameError",
    "InvalidTagError",
    "NameCollisionError",
    "UnknownDocumentError",
    "VersioningError",
]
