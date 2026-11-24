from __future__ import annotations

import typing
from collections import abc

import attrs
import hikari

from discordia import handlers
from discordia.interactions import commands, components

if typing.TYPE_CHECKING:
    from discordia.modules.module import Module


@attrs.frozen()
class RegistrationData[T]:
    owner: Module = attrs.field()
    data: T = attrs.field(hash=False)


@attrs.define()
class Registry[K: abc.Hashable, D]:
    _name: str = attrs.field()
    _get_key: abc.Callable[[D], K] = attrs.field(repr=False)
    _data: dict[K, RegistrationData[D]] = attrs.field(factory=dict[K, RegistrationData[D]])

    def add(self, item: D, owner: Module) -> None:
        key = self._get_key(item)
        if key in self._data:
            msg = f'The {self._name} "{key}" already exists in the registry.'
            raise ValueError(msg)

        registered = RegistrationData(owner, item)
        self._data[key] = registered
        owner.metadata.add_register(registered)

    def add_register(self, register: RegistrationData[D]) -> None:
        key = self._get_key(register.data)
        if key in self._data:
            msg = f'The {self._name} "{key}" already exists in the registry.'
            raise ValueError(msg)
        self._data[key] = register

    def remove(self, key: K) -> D:
        registered = self._data.get(key)
        if registered is None:
            msg = f'The {self._name} "{key}" was not found in the registry.'
            raise KeyError(msg)

        del self._data[key]
        registered.owner.metadata.remove_register(registered)
        return registered.data

    def get(self, key: K) -> D | None:
        registered = self._data.get(key)
        return registered.data if registered else None

    def get_registers(self) -> tuple[RegistrationData[D], ...]:
        return tuple(self._data.values())

    def merge(self, registers: abc.Sequence[RegistrationData[D]]) -> None:
        for register in registers:
            self.add_register(register)

    def unmerge(self, item: RegistrationData[D], destination: typing.Self) -> None:
        key = self._get_key(item.data)
        if key in self._data:
            del self._data[key]
        destination.add_register(item)

    def __getitem__(self, key: K) -> D:
        return self._data[key].data

    def __contains__(self, key: K) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def __iter__(self) -> typing.Generator[D, None, None]:
        for register in self._data.values():
            yield register.data


class EventRegistry(Registry[type[hikari.Event], commands.EventResponder]):
    def __init__(self) -> None:
        super().__init__("event", lambda i: i.event)

    def add(self, item: commands.EventResponder, owner: Module) -> None:
        key = self._get_key(item)
        if key in self._data:
            self._data[key].data.callbacks.update(item.callbacks)
        else:
            self._data[key] = RegistrationData(owner, item)

        registered = RegistrationData(owner, item)
        owner.metadata.add_register(registered)

    def merge(self, registers: typing.Sequence[RegistrationData[commands.EventResponder]]) -> None:
        for register in registers:
            data = register.data
            if data.event in self._data:
                self._data[data.event].data.callbacks.update(data.callbacks)
            else:
                new_responder = commands.EventResponder(data.event)
                new_responder.callbacks = set(data.callbacks)
                self._data[data.event] = RegistrationData(register.owner, new_responder)

    def unmerge(
        self,
        item: RegistrationData[commands.EventResponder],
        destination: Registry[type[hikari.Event], commands.EventResponder],
    ) -> None:
        data = item.data
        if data.event in self._data:
            self._data[data.event].data.callbacks.difference_update(data.callbacks)
            if not self._data[data.event].data.callbacks:
                del self._data[data.event]

        if data.event in destination:
            destination[data.event].callbacks.update(data.callbacks)
        else:
            destination.add_register(item)


class SlashCommandRegistry(Registry[str, commands.SlashCommand]):
    def __init__(self) -> None:
        super().__init__("slash command", lambda i: i.name)


class UserMenuRegistry(Registry[str, commands.UserMenu]):
    def __init__(self) -> None:
        super().__init__("user menu", lambda i: i.name)


class MessageMenuRegistry(Registry[str, commands.MessageMenu]):
    def __init__(self) -> None:
        super().__init__("message menu", lambda i: i.name)


class ButtonRegistry(Registry[str, components.Button]):
    def __init__(self) -> None:
        super().__init__("button", lambda i: i.custom_id)


class SelectMenuRegistry(Registry[str, components.SelectMenu]):
    def __init__(self) -> None:
        super().__init__("select menu", lambda i: i.custom_id)


class ModalRegistry(Registry[str, components.Modal]):
    def __init__(self) -> None:
        super().__init__("modal", lambda i: i.custom_id)


class ErrorRegistry(Registry[type[Exception], handlers.ErrorResponder]):
    def __init__(self) -> None:
        super().__init__("error", lambda i: i.error)
