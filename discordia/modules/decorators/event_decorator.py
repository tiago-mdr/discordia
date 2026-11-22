import typing
from collections import abc

from hikari import events

from discordia import signatures
from discordia.interactions import commands
from discordia.modules.module import Module


class EventDecorator:
    # possible event namespace here
    def __init__(self, owner: Module) -> None:
        self._owner = owner

    def listen[E: events.Event](
        self, event_type: type[E] | None = None
    ) -> abc.Callable[[abc.Callable[typing.Concatenate[E, ...], abc.Awaitable[typing.Any]]], commands.EventResponder]:
        def wrapper(
            callback: abc.Callable[typing.Concatenate[E, ...], abc.Awaitable[typing.Any]],
        ) -> commands.EventResponder:
            infered_event = event_type or signatures.find_for_type(callback, events.Event)
            if infered_event is None:
                msg = (
                    f"Could not infer event type from callback {callback.__name__}. "
                    "Please specify the event type explicitly."
                )
                raise TypeError(msg)

            event_responder = commands.EventResponder(infered_event, callback)
            self._owner.registers.events.add(event_responder, self._owner)
            return event_responder

        return wrapper
