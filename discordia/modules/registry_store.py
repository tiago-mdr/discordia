"""Registry store encapsulating all types of registries."""

from __future__ import annotations

import typing

import attrs

from discordia import handlers, interactions
from discordia.modules import registries


@attrs.define()
class RegistryStore:
    """Central storage holding all category-specific registries in a module."""

    events: registries.EventRegistry = attrs.field(factory=registries.EventRegistry, init=False)
    slash_commands: registries.SlashCommandRegistry = attrs.field(factory=registries.SlashCommandRegistry, init=False)
    user_menus: registries.UserMenuRegistry = attrs.field(factory=registries.UserMenuRegistry, init=False)
    message_menus: registries.MessageMenuRegistry = attrs.field(factory=registries.MessageMenuRegistry, init=False)
    buttons: registries.ButtonRegistry = attrs.field(factory=registries.ButtonRegistry, init=False)
    select_menus: registries.SelectMenuRegistry = attrs.field(factory=registries.SelectMenuRegistry, init=False)
    modals: registries.ModalRegistry = attrs.field(factory=registries.ModalRegistry, init=False)
    errors: registries.ErrorRegistry = attrs.field(factory=registries.ErrorRegistry, init=False)

    _map: dict[type, registries.Registry[typing.Any, typing.Any]] = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        """Map supported interaction and handler types to their dedicated registries."""
        self._map = {
            interactions.SlashCommand: self.slash_commands,
            interactions.UserMenu: self.user_menus,
            interactions.MessageMenu: self.message_menus,
            interactions.Button: self.buttons,
            interactions.SelectMenu: self.select_menus,
            interactions.Modal: self.modals,
            interactions.EventResponder: self.events,
            handlers.ErrorResponder: self.errors,
        }

    def merge(self, other: RegistryStore) -> None:
        """Merge all entries from another registry store into this store.

        Args:
            other: The source RegistryStore whose items will be merged.
        """
        for data_type, my_registry in self._map.items():
            other_registry = other._map[data_type]
            my_registry.merge(other_registry.get_registers())

    def unmerge(
        self, registries: typing.Iterable[registries.RegistrationData[typing.Any]], destination: RegistryStore
    ) -> None:
        """Unmerge specified registration items from this store into a destination store.

        Args:
            registries: Iterable of registration items to remove from this store.
            destination: Target RegistryStore to receive the unmerged registrations.

        Raises:
            ValueError: If an item's data type is not recognized by any registered category.
        """
        for registry in registries:
            data = registry.data
            data_type: type[typing.Any] = type(data)  # type: ignore[reportUnknownVariableType]
            my_registry = self._map.get(data_type)
            other_registry = destination._map.get(data_type)

            if my_registry is None or other_registry is None:
                msg = f"Registration data type {data_type.__name__} is not recognized by RegistryStore."
                raise ValueError(msg)

            my_registry.unmerge(registry, other_registry)
