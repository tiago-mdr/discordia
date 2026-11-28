"""Error responder definitions."""

from __future__ import annotations

import typing

import attrs

if typing.TYPE_CHECKING:
    from collections import abc

    from discordia import di


@attrs.define()
class ErrorResponder:
    """Encapsulates an exception type and its handling callback."""

    error: type[Exception] = attrs.field()
    """The specific Exception class to catch and handle."""

    callback: typing.Callable[..., abc.Awaitable[object]] = attrs.field()
    """Callable invoked when the mapped exception is caught."""

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate the parameter dependencies of the error handler callback.

        Args:
            validator: The DependencyManager used to validate injectable types.
        """
        validator.validate(self.callback, {Exception})
