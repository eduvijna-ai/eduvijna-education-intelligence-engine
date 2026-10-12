from __future__ import annotations


class RegistryVersionNotFound(LookupError):
    """Raised when an exact versioned registry payload does not exist."""

    def __init__(self, registry: str, version: str) -> None:
        self.registry = registry
        self.version = version
        super().__init__(f"{registry} version not found: {version}")
