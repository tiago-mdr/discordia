"""Event responder encapsulating event types and associated listener callbacks."""

from __future__ import annotations

import typing

import attrs

if typing.TYPE_CHECKING:
    from collections import abc

    from hikari.events import Event

    from discordia import di


@attrs.define(init=False)
class EventResponder:
    """Manages an event type and groups all callbacks listening for that event."""

    event: type[Event] = attrs.field()
    """The event class being listened for."""

    callbacks: set[abc.Callable[..., typing.Awaitable[object]]] = attrs.field()
    """Set of callables invoked when the event fires."""

    def __init__(
        self,
        event: type[Event],
        callback: abc.Callable[..., typing.Awaitable[object]] | None = None,
    ) -> None:
        """Initialize the event responder.

        Args:
            event: The Hikari Event class to listen for.
            callback: Optional initial callback to register for this event.
        """
        self.callbacks = set()
        self.event = event

        if callback is not None:
            self.callbacks.add(callback)

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate dependencies for all registered event callbacks.

        Args:
            validator: The DependencyManager used to validate injectable parameters.
        """
        for callback in self.callbacks:
            validator.validate(callback, {self.event})
