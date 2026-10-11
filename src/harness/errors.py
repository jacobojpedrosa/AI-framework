"""Errors safe to display without input values or exception reprs."""


class HarnessError(Exception):
    """Expected, user-facing failure."""


class ConfigurationError(HarnessError):
    """Invalid declarative configuration."""


class RegistryError(HarnessError):
    """Inconsistent registry metadata."""
