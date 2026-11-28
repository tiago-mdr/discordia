"""User context menu interaction command definition."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import attrs
import hikari
from hikari.impl import ContextMenuCommandBuilder
from hikari.undefined import UNDEFINED

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from discordia import di


@attrs.define()
class UserMenu:
    """Represents a Discord user context menu command.

    Attributes:
        callback: Asynchronous callable executed when the command is triggered.
        name: The display name of the user menu command.
        default_member_permissions: Permissions required for a member to execute this command.
        is_nsfw: Whether the command is restricted to age-restricted channels.
        name_localizations: Localized names for the command across Discord client locales.
        integration_types: Supported installation contexts for the command.
        context_types: Contexts where the command can be used (guild, DM, group DM).
    """

    callback: Callable[..., Awaitable[Any]] = attrs.field()
    name: str = attrs.field()
    default_member_permissions: hikari.UndefinedType | hikari.Permissions = attrs.field(default=UNDEFINED)
    is_nsfw: hikari.UndefinedOr[bool] = attrs.field(default=UNDEFINED)
    name_localizations: Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    integration_types: hikari.UndefinedOr[Sequence[hikari.ApplicationIntegrationType]] = attrs.field(default=UNDEFINED)
    context_types: hikari.UndefinedOr[Sequence[hikari.ApplicationContextType]] = attrs.field(default=UNDEFINED)

    def parse_user_menu(self, interaction: hikari.CommandInteraction) -> hikari.User:
        """Extract the target Member or User from resolved interaction data.

        Args:
            interaction: The incoming command interaction event payload.

        Returns:
            The resolved target User or Member object.

        Raises:
            ValueError: If target_id or resolved data is missing, or the user/member is not found.
        """
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
        """Validate parameter injection requirements for the user menu callback.

        Args:
            validator: The DependencyManager used to inspect and validate dependencies.
        """
        lazy_types = {hikari.CommandInteraction, hikari.Member}
        validator.validate(self.callback, lazy_types)

    def build(self) -> ContextMenuCommandBuilder:
        """Construct the Hikari ContextMenuCommandBuilder for registration with Discord.

        Returns:
            A configured ContextMenuCommandBuilder instance.
        """
        return ContextMenuCommandBuilder(
            name=self.name,
            type=hikari.CommandType.USER,
            default_member_permissions=self.default_member_permissions,
            is_nsfw=self.is_nsfw,
            name_localizations=self.name_localizations,
            integration_types=self.integration_types,
            context_types=self.context_types,
        )
