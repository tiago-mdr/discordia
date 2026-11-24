from collections.abc import Awaitable, Callable
from typing import Any

import attrs
import hikari

from discordia import di


@attrs.define()
class Modal:
    # This is a temporary implementation for the modal, it will be changed once the v2 modal system is implemented
    callback: Callable[..., Awaitable[Any]] = attrs.field()
    custom_id: str = attrs.field()

    def validate(self, validator: di.DependencyManager) -> None:
        validator.validate(self.callback, {hikari.ComponentInteraction})
