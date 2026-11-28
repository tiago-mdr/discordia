"""Message context menu interaction command definition."""

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
class MessageMenu:
    """Represents a Discord message context menu command."""

    callback: Callable[..., Awaitable[Any]] = attrs.field()
    """Callable executed when the command is triggered."""

    name: str = attrs.field()
    """The display name of the message menu command."""

    default_member_permissions: hikari.UndefinedType | hikari.Permissions = attrs.field(default=UNDEFINED)
    """Permissions required for a member to execute this command."""

    is_nsfw: hikari.UndefinedOr[bool] = attrs.field(default=UNDEFINED)
    """Whether the command is restricted to age-restricted channels."""

    name_localizations: Mapping[hikari.Locale | str, str] = attrs.field(factory=dict[hikari.Locale | str, str])
    """Localized names for the command across Discord client locales."""

    integration_types: hikari.UndefinedOr[Sequence[hikari.ApplicationIntegrationType]] = attrs.field(default=UNDEFINED)
    """Supported installation contexts for the command."""

    context_types: hikari.UndefinedOr[Sequence[hikari.ApplicationContextType]] = attrs.field(default=UNDEFINED)
    """Contexts where the command can be used"""

    def extract_message(self, interaction: hikari.CommandInteraction) -> hikari.Message:
        """Extract the target Message instance from resolved interaction payload.

        Args:
            interaction: The incoming command interaction event payload.

        Returns:
            The resolved target Message object.

        Raises:
            ValueError: If the target message cannot be found in resolved interaction data.
        """
        if interaction.resolved and interaction.target_id:
            return interaction.resolved.messages[interaction.target_id]

        msg = f"Message with target_id {interaction.target_id} was not found in resolved interaction data."
        raise ValueError(msg)

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate parameter injection requirements for the menu callback.

        Args:
            validator: The DependencyManager used to inspect and validate dependencies.
        """
        lazy_types = {hikari.CommandInteraction, hikari.Message}
        validator.validate(self.callback, lazy_types)

    def build(self) -> ContextMenuCommandBuilder:
        """Construct the Hikari ContextMenuCommandBuilder for registration with Discord.

        Returns:
            A configured ContextMenuCommandBuilder instance.
        """
        return ContextMenuCommandBuilder(
            name=self.name,
            type=hikari.CommandType.MESSAGE,
            default_member_permissions=self.default_member_permissions,
            is_nsfw=self.is_nsfw,
            name_localizations=self.name_localizations,
            integration_types=self.integration_types,
            context_types=self.context_types,
        )
