import typing
from collections import abc

import attrs


@attrs.define()
class ErrorResponder:
    error: type[Exception] = attrs.field()
    callback: typing.Callable[..., abc.Awaitable[typing.Any]] = attrs.field()
