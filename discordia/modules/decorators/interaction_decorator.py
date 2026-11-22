import typing
from collections import abc

import hikari
from hikari.undefined import UNDEFINED

from discordia.interactions import commands, components
from discordia.modules.module import Module


class InteractionDecorator:
    def __init__(self, owner: Module) -> None:
        self._owner = owner

    def slash_command(
        self,
        name: str = "",
        description: str = "...",
        *,
        default_member_permissions: hikari.UndefinedType | hikari.Permissions = UNDEFINED,
        is_nsfw: hikari.UndefinedOr[bool] = UNDEFINED,
        name_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
        integration_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationIntegrationType]] = UNDEFINED,
        context_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationContextType]] = UNDEFINED,
        description_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
    ) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], commands.SlashCommand]:
        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> commands.SlashCommand:
            registers = self._owner.registers
            command_name = name or func.__name__
            new_slash_command = commands.SlashCommand(
                name=command_name,
                description=description,
                default_member_permissions=default_member_permissions,
                is_nsfw=is_nsfw,
                name_localizations=name_localizations if name_localizations is not None else {},
                integration_types=integration_types,
                context_types=context_types,
                description_localizations=description_localizations if description_localizations is not None else {},
            )
            new_slash_command.responder(func)
            registers.slash_commands.add(new_slash_command, owner=self._owner)
            return new_slash_command

        return wrapper

    def user_menu(
        self,
        name: str,
        *,
        default_member_permissions: hikari.UndefinedType | hikari.Permissions = UNDEFINED,
        is_nsfw: hikari.UndefinedOr[bool] = UNDEFINED,
        name_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
        integration_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationIntegrationType]] = UNDEFINED,
        context_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationContextType]] = UNDEFINED,
    ) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], commands.UserMenu]:
        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> commands.UserMenu:
            registers = self._owner.registers
            new_user_menu = commands.UserMenu(
                callback=func,
                name=name,
                default_member_permissions=default_member_permissions,
                is_nsfw=is_nsfw,
                name_localizations=name_localizations if name_localizations is not None else {},
                integration_types=integration_types,
                context_types=context_types,
            )
            registers.user_menus.add(new_user_menu, owner=self._owner)
            return new_user_menu

        return wrapper

    def message_menu(
        self,
        name: str,
        *,
        default_member_permissions: hikari.UndefinedType | hikari.Permissions = UNDEFINED,
        is_nsfw: hikari.UndefinedOr[bool] = UNDEFINED,
        name_localizations: abc.Mapping[hikari.Locale | str, str] | None = None,
        integration_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationIntegrationType]] = UNDEFINED,
        context_types: hikari.UndefinedOr[abc.Sequence[hikari.ApplicationContextType]] = UNDEFINED,
    ) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], commands.MessageMenu]:
        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> commands.MessageMenu:
            registers = self._owner.registers
            new_message_menu = commands.MessageMenu(
                callback=func,
                name=name,
                default_member_permissions=default_member_permissions,
                is_nsfw=is_nsfw,
                name_localizations=name_localizations if name_localizations is not None else {},
                integration_types=integration_types,
                context_types=context_types,
            )
            registers.message_menus.add(new_message_menu, owner=self._owner)
            return new_message_menu

        return wrapper

    def button(self, custom_id: str) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], components.Button]:
        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> components.Button:
            registers = self._owner.registers
            new_button = components.Button(func, custom_id)
            registers.buttons.add(new_button, self._owner)
            return new_button

        return wrapper

    def select_menu(
        self,
        custom_id: str,
        type: hikari.ComponentType = hikari.ComponentType.TEXT_SELECT_MENU,  # noqa: A002
    ) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], components.SelectMenu]:
        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> components.SelectMenu:
            registers = self._owner.registers
            new_select_menu = components.SelectMenu(func, custom_id, type)
            registers.select_menus.add(new_select_menu, self._owner)
            return new_select_menu

        return wrapper

    def modal(self, custom_id: str) -> abc.Callable[[abc.Callable[..., abc.Awaitable[typing.Any]]], components.Modal]:
        def wrapper(func: abc.Callable[..., abc.Awaitable[typing.Any]]) -> components.Modal:
            registers = self._owner.registers
            new_modal = components.Modal(func, custom_id)
            registers.modals.add(new_modal, self._owner)
            return new_modal

        return wrapper
