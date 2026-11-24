import typing
from collections import abc

import attrs
from hikari.events import Event

from discordia import di


@attrs.define(init=False)
class EventResponder:
    event: type[Event] = attrs.field()
    callbacks: set[abc.Callable[..., typing.Awaitable[object]]] = attrs.field()

    def __init__(
        self,
        event: type[Event],
        callback: abc.Callable[..., typing.Awaitable[object]] | None = None,
    ) -> None:
        self.callbacks = set()
        self.event = event

        if callback is not None:
            self.callbacks.add(callback)

    def validate(self, validator: di.DependencyManager) -> None:
        for callback in self.callbacks:
            validator.validate(callback, {self.event})
