"""Decorator interface for registering Discord gateway event listeners."""

from __future__ import annotations

import typing

from hikari import events

from discordia import interactions, signatures

if typing.TYPE_CHECKING:
    from collections import abc

    from discordia.modules.module import Module


class EventDecorator:
    """Provides decorators to bind callbacks to Hikari gateway events."""

    def __init__(self, owner: Module) -> None:
        """Initialize the event decorator for an owner module.

        Args:
            owner: The module instance that owns this decorator namespace.
        """
        self._owner = owner

    def listen[E: events.Event](
        self, event_type: type[E] | None = None
    ) -> abc.Callable[[abc.Callable[typing.Concatenate[E, ...], abc.Awaitable[object]]], interactions.EventResponder]:
        """Register an asynchronous callback to listen for a Discord gateway event.

        Args:
            event_type: The specific Hikari event class to listen for. If None, the
                event type is inferred from the first parameter annotation of type
                Event in the callback.

        Returns:
            A decorator function returning the registered EventResponder.

        Raises:
            TypeError: If event_type is not provided and cannot be inferred from the callback signature.
        """

        def wrapper(
            callback: abc.Callable[typing.Concatenate[E, ...], abc.Awaitable[object]],
        ) -> interactions.EventResponder:
            infered_event = event_type or signatures.find_for_type(callback, events.Event)
            if infered_event is None:
                msg = (
                    f"Could not infer event type from callback {callback.__name__}. "
                    "Please specify the event type explicitly."
                )
                raise TypeError(msg)

            event_responder = interactions.EventResponder(infered_event, callback)
            self._owner.registers.events.add(event_responder, self._owner)
            return event_responder

        return wrapper
