"""Exception hierarchy shared by all three providers."""

from __future__ import annotations


class BeapiError(RuntimeError):
    """Base for every error this package raises."""


class CredentialMissing(BeapiError):
    """A required credential resolved to empty."""


class AuthExpired(BeapiError):
    """The credential was rejected and a human must supply a new one.

    Separate from UpstreamError because the remedy differs: this one always
    means a browser login or a fresh copy-paste, never a retry.
    """


class UpstreamError(BeapiError):
    """The provider answered with an error, or could not be reached."""

    def __init__(self, message: str, *, status: int | None = None, body: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.body = body


class ContractError(BeapiError):
    """The response parsed, but its shape is not the one this client knows.

    Raised instead of returning an empty result, so an upstream rename is
    reported rather than mistaken for "you have nothing".
    """
