"""Unofficial Python clients for Colruyt Xtra, Monizze and Pluxee.

None of these providers publishes an API. Every endpoint here was derived from
the traffic of their own web and mobile clients, and can change without notice.
"""

from .credentials import TokenStore, from_env
from .errors import (
    AuthExpired,
    BeapiError,
    ContractError,
    CredentialMissing,
    UpstreamError,
)
from .monizze import Monizze
from .pluxee import Pluxee
from .xtra import Xtra

__all__ = [
    "AuthExpired",
    "BeapiError",
    "ContractError",
    "CredentialMissing",
    "Monizze",
    "Pluxee",
    "TokenStore",
    "UpstreamError",
    "Xtra",
    "from_env",
]

__version__ = "0.1.0"
