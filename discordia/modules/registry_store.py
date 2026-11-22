from __future__ import annotations

import typing

import attrs

from discordia import handlers
from discordia.interactions import commands, components, event
from discordia.modules import registries


@attrs.define()
class RegistryStore:
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
        self._map = {
            commands.SlashCommand: self.slash_commands,
            commands.UserMenu: self.user_menus,
            commands.MessageMenu: self.message_menus,
            components.Button: self.buttons,
            components.SelectMenu: self.select_menus,
            components.Modal: self.modals,
            event.EventResponder: self.events,
            handlers.ErrorResponder: self.errors,
        }

    def merge(self, other: RegistryStore) -> None:
        for data_type, my_registry in self._map.items():
            other_registry = other._map[data_type]
            my_registry.merge(other_registry.get_registers())

    def unmerge(self, registries: set[registries.RegistrationData[typing.Any]], destination: RegistryStore) -> None:
        for registry in registries:
            data = registry.data
            data_type: type[typing.Any] = type(data)  # type: ignore
            my_registry = self._map.get(data_type)
            other_registry = destination._map.get(data_type)

            if my_registry is None or other_registry is None:
                msg = f"Registration data type {data_type.__name__} is not recognized by RegistryStore."
                raise ValueError(msg)

            my_registry.unmerge(registry, other_registry)
