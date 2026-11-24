from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any

import attrs
import hikari
from hikari.impl import ContextMenuCommandBuilder
from hikari.undefined import UNDEFINED

from discordia import di


@attrs.define()
class MessageMenu:
    callback: Callable[..., Awaitable[Any]] = attrs.field()
    name: str = attrs.field()
    default_member_permissions: hikari.UndefinedType | hikari.Permissions = attrs.field(default=UNDEFINED)
    is_nsfw: hikari.UndefinedOr[bool] = attrs.field(default=UNDEFINED)
    name_localizations: Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    integration_types: hikari.UndefinedOr[Sequence[hikari.ApplicationIntegrationType]] = attrs.field(default=UNDEFINED)
    context_types: hikari.UndefinedOr[Sequence[hikari.ApplicationContextType]] = attrs.field(default=UNDEFINED)

    def extract_message(self, interaction: hikari.CommandInteraction) -> hikari.Message:
        if interaction.resolved and interaction.target_id:
            return interaction.resolved.messages[interaction.target_id]

        msg = f"Message with target_id {interaction.target_id} was not found in resolved interaction data."
        raise ValueError(msg)

    def validate(self, validator: di.DependencyManager) -> None:
        lazy_types = {hikari.CommandInteraction, hikari.Message}
        validator.validate(self.callback, lazy_types)

    def build(self) -> ContextMenuCommandBuilder:
        return ContextMenuCommandBuilder(
            name=self.name,
            type=hikari.CommandType.MESSAGE,
            default_member_permissions=self.default_member_permissions,
            is_nsfw=self.is_nsfw,
            name_localizations=self.name_localizations,
            integration_types=self.integration_types,
            context_types=self.context_types,
        )
