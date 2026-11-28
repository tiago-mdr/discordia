"""Registries for storing Discordia interactions and events."""

from __future__ import annotations

import typing
from collections import abc

import attrs
import hikari

from discordia import handlers, interactions

if typing.TYPE_CHECKING:
    from discordia.modules.module import Module


@attrs.frozen()
class RegistrationData[T]:
    """Representation of a registered item."""

    owner: Module = attrs.field()
    """The module that registered and owns this item."""

    data: T = attrs.field(hash=False)
    """The registered data"""


@attrs.define()
class Registry[K: abc.Hashable, D]:
    """Generic registry that stores items."""

    _name: str = attrs.field()
    _get_key: abc.Callable[[D], K] = attrs.field(repr=False)
    _data: dict[K, RegistrationData[D]] = attrs.field(factory=dict[K, RegistrationData[D]])

    def add(self, item: D, owner: Module) -> None:
        """Add a new item to the registry with its owner module.

        Args:
            item: The item to be stored in the registry.
            owner: The module claiming ownership of the item.

        Raises:
            ValueError: If an item with the same key already exists.
        """
        key = self._get_key(item)
        if key in self._data:
            msg = f'The {self._name} "{key}" already exists in the registry.'
            raise ValueError(msg)

        registered = RegistrationData(owner, item)
        self._data[key] = registered
        owner.metadata.add_register(registered)

    def add_register(self, register: RegistrationData[D]) -> None:
        """Add an existing RegistrationData entry directly to the registry.

        Args:
            register: The pre-constructed RegistrationData wrapper.

        Raises:
            ValueError: If an item with the same key already exists.
        """
        key = self._get_key(register.data)
        if key in self._data:
            msg = f'The {self._name} "{key}" already exists in the registry.'
            raise ValueError(msg)
        self._data[key] = register

    def remove(self, key: K) -> D:
        """Remove and return an item from the registry by its key.

        Args:
            key: The key of the item to remove.

        Returns:
            The unregistered item instance.

        Raises:
            KeyError: If no item matches the provided key.
        """
        registered = self._data.get(key)
        if registered is None:
            msg = f'The {self._name} "{key}" was not found in the registry.'
            raise KeyError(msg)

        del self._data[key]
        registered.owner.metadata.remove_register(registered)
        return registered.data

    def get(self, key: K) -> D | None:
        """Retrieve an item by its key, or None if not found.

        Args:
            key: The unique key to look up.

        Returns:
            The item instance if registered, otherwise None.
        """
        registered = self._data.get(key)
        return registered.data if registered else None

    def get_registers(self) -> tuple[RegistrationData[D], ...]:
        """Return all registered items as a tuple.

        Returns:
            A tuple containing all RegistrationData wrappers.
        """
        return tuple(self._data.values())

    def merge(self, registers: abc.Iterable[RegistrationData[D]]) -> None:
        """Merge a sequence of registration items into this registry.

        Args:
            registers: Itarable of RegistrationData entries to merge.
        """
        for register in registers:
            self.add_register(register)

    def unmerge(self, item: RegistrationData[D], destination: typing.Self) -> None:
        """Transfer a registration item from this registry to a destination registry.

        Args:
            item: The registration item to transfer.
            destination: The target registry where the item will be added.
        """
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


class EventRegistry(Registry[type[hikari.Event], interactions.EventResponder]):
    """Registry for Discord event responders."""

    def __init__(self) -> None:
        super().__init__("event", lambda i: i.event)

    def add(self, item: interactions.EventResponder, owner: Module) -> None:
        """Add an event responder.

        Args:
            item: The EventResponder containing the target event and callback(s).
            owner: The module registering the responder.
        """
        key = self._get_key(item)
        if key in self._data:
            self._data[key].data.callbacks.update(item.callbacks)
        else:
            self._data[key] = RegistrationData(owner, item)

        registered = RegistrationData(owner, item)
        owner.metadata.add_register(registered)

    def merge(self, registers: abc.Iterable[RegistrationData[interactions.EventResponder]]) -> None:
        """Merge a sequence of event responders.

        Args:
            registers: Iterable of event responder registrations to merge.
        """
        for register in registers:
            data = register.data
            if data.event in self._data:
                self._data[data.event].data.callbacks.update(data.callbacks)
            else:
                new_responder = interactions.EventResponder(data.event)
                new_responder.callbacks = set(data.callbacks)
                self._data[data.event] = RegistrationData(register.owner, new_responder)

    def unmerge(
        self,
        item: RegistrationData[interactions.EventResponder],
        destination: Registry[type[hikari.Event], interactions.EventResponder],
    ) -> None:
        """Unmerge an event responder.

        Args:
            item: The registration item to unmerge.
            destination: The target registry where the unmerged responder will reside.
        """
        data = item.data
        if data.event in destination:
            destination[data.event].callbacks.update(data.callbacks)
        else:
            destination.add_register(item)

        if data.event in self._data:
            self._data[data.event].data.callbacks.difference_update(data.callbacks)
            if not self._data[data.event].data.callbacks:
                del self._data[data.event]


class SlashCommandRegistry(Registry[str, interactions.SlashCommand]):
    """Registry for Discord application slash interactions."""

    def __init__(self) -> None:
        super().__init__("slash command", lambda i: i.name)


class UserMenuRegistry(Registry[str, interactions.UserMenu]):
    """Registry for user context menu interactions."""

    def __init__(self) -> None:
        super().__init__("user menu", lambda i: i.name)


class MessageMenuRegistry(Registry[str, interactions.MessageMenu]):
    """Registry for message context menu interactions."""

    def __init__(self) -> None:
        super().__init__("message menu", lambda i: i.name)


class ButtonRegistry(Registry[str, interactions.Button]):
    """Registry for interactive button interactions."""

    def __init__(self) -> None:
        super().__init__("button", lambda i: i.custom_id)


class SelectMenuRegistry(Registry[str, interactions.SelectMenu]):
    """Registry for interactive select menu interactions."""

    def __init__(self) -> None:
        super().__init__("select menu", lambda i: i.custom_id)


class ModalRegistry(Registry[str, interactions.Modal]):
    """Registry for modal form submit interactions."""

    def __init__(self) -> None:
        super().__init__("modal", lambda i: i.custom_id)


class ErrorRegistry(Registry[type[Exception], handlers.ErrorResponder]):
    """Registry for exception handlers keyed by exception class."""

    def __init__(self) -> None:
        super().__init__("error", lambda i: i.error)
