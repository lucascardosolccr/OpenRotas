"""Custom exceptions for provider module."""


class ProviderException(Exception):
    """Base exception for provider errors."""
    pass


class ProviderTimeoutException(ProviderException):
    """Provider request timed out."""
    pass


class ProviderValidationException(ProviderException):
    """Data validation failed."""
    pass
