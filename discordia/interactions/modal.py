"""Modal dialog interaction responder."""

from __future__ import annotations

import typing

import attrs
import hikari

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from discordia import di


@attrs.define()
class Modal:
    """Represents a modal submit interaction responder."""

    callback: Callable[..., Awaitable[object]] = attrs.field()
    """Callable executed when the modal form is submitted."""

    custom_id: str = attrs.field()
    """Unique string identifying the modal component."""

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate parameter dependencies for the modal callback.

        Args:
            validator: The DependencyManager used to validate dependencies.
        """
        validator.validate(self.callback, {hikari.ComponentInteraction})
