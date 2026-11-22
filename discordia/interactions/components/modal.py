from collections.abc import Awaitable, Callable
from typing import Any

import attrs


@attrs.define()
class Modal:
    # This is a temporary implementation for the modal, it will be changed once the v2 modal system is implemented
    callback: Callable[..., Awaitable[Any]] = attrs.field()
    custom_id: str = attrs.field()
