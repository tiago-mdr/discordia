import typing
from collections import abc

import attrs
import hikari

from discordia import di


@attrs.define()
class Button:
    callback: abc.Callable[..., abc.Awaitable[typing.Any]] = attrs.field()
    custom_id: str = attrs.field()

    def validate(self, validator: di.DependencyManager) -> None:
        validator.validate(self.callback, {hikari.ComponentInteraction})
