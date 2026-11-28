"""Button message component interaction responder."""

from __future__ import annotations

import typing

import attrs
import hikari

if typing.TYPE_CHECKING:
    from collections import abc

    from discordia import di


@attrs.define()
class Button:
    """Represents an interactive button message component responder."""

    callback: abc.Callable[..., abc.Awaitable[object]] = attrs.field()
    """Callable executed when the button is pressed."""

    custom_id: str = attrs.field()
    """Unique string identifying the button component."""

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate parameter dependencies for the button callback.

        Args:
            validator: The DependencyManager used to validate dependencies.
        """
        validator.validate(self.callback, {hikari.ComponentInteraction})
