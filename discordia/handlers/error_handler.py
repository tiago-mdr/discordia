import typing
from collections import abc

import attrs

from discordia import di


@attrs.define()
class ErrorResponder:
    error: type[Exception] = attrs.field()
    callback: typing.Callable[..., abc.Awaitable[typing.Any]] = attrs.field()

    def validate(self, validator: di.DependencyManager) -> None:
        validator.validate(self.callback, {Exception})
