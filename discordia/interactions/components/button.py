import typing
from collections import abc

import attrs


@attrs.define()
class Button:
    callback: abc.Callable[..., abc.Awaitable[typing.Any]] = attrs.field()
    custom_id: str = attrs.field()
