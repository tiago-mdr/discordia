from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import attrs
import hikari
from hikari.impl import ContextMenuCommandBuilder
from hikari.undefined import UNDEFINED

from discordia import di


@attrs.define()
class UserMenu:
    callback: Callable[..., Awaitable[Any]] = attrs.field()
    name: str = attrs.field()
    default_member_permissions: hikari.UndefinedType | hikari.Permissions = attrs.field(default=UNDEFINED)
    is_nsfw: hikari.UndefinedOr[bool] = attrs.field(default=UNDEFINED)
    name_localizations: Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    integration_types: hikari.UndefinedOr[Sequence[hikari.ApplicationIntegrationType]] = attrs.field(default=UNDEFINED)
    context_types: hikari.UndefinedOr[Sequence[hikari.ApplicationContextType]] = attrs.field(default=UNDEFINED)

    def parse_user_menu(self, interaction: hikari.CommandInteraction) -> hikari.User:
        if interaction.target_id is None or interaction.resolved is None:
            msg = "No target_id or resolved interaction data found in user menu interaction."
            raise ValueError(msg)

        response = interaction.resolved.members.get(interaction.target_id) or interaction.resolved.users.get(
            interaction.target_id
        )

        if response is None:
            msg = f"No user or member was found for id {interaction.target_id} in resolved interaction data."
            raise ValueError(msg)

        return response

    def validate(self, validator: di.DependencyManager) -> None:
        lazy_types = {hikari.CommandInteraction, hikari.Member}
        validator.validate(self.callback, lazy_types)

    def build(self) -> ContextMenuCommandBuilder:
        return ContextMenuCommandBuilder(
            name=self.name,
            type=hikari.CommandType.USER,
            default_member_permissions=self.default_member_permissions,
            is_nsfw=self.is_nsfw,
            name_localizations=self.name_localizations,
            integration_types=self.integration_types,
            context_types=self.context_types,
        )
