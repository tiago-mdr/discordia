"""Select menu message component interaction responder and value parser."""

from __future__ import annotations

import typing
from typing import Any, get_origin

import attrs
import hikari

from discordia import signatures

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from discordia import di


@attrs.define()
class SelectMenu:
    """Represents an interactive select menu message component responder."""

    callback: Callable[..., Awaitable[Any]] = attrs.field()
    """Callable executed when selections are submitted."""

    custom_id: str = attrs.field()
    """Unique string identifying the select menu component."""

    type: hikari.ComponentType = attrs.field()
    """The specific ComponentType"""

    field: str = attrs.field(default="", init=False)
    """Parameter name on callback that will receive the parsed values list."""

    def __attrs_post_init__(self) -> None:
        """Validate the component type and infer the injected values parameter."""
        if self.type not in (
            hikari.ComponentType.TEXT_SELECT_MENU,
            hikari.ComponentType.USER_SELECT_MENU,
            hikari.ComponentType.CHANNEL_SELECT_MENU,
            hikari.ComponentType.ROLE_SELECT_MENU,
            hikari.ComponentType.MENTIONABLE_SELECT_MENU,
        ):
            msg = f"Component type {self.type} is not recognized as a valid select menu."
            raise ValueError(msg)

        parameter_inject = self._extract_field()
        if parameter_inject:
            self.field = parameter_inject

    def _is_compatible(self, types: typing.Sequence[typing.Any]) -> bool:
        match self.type:
            case hikari.ComponentType.TEXT_SELECT_MENU:
                return str in types
            case hikari.ComponentType.CHANNEL_SELECT_MENU:
                return hikari.InteractionChannel in types
            case hikari.ComponentType.MENTIONABLE_SELECT_MENU:
                return hikari.User in types and hikari.Role in types
            case hikari.ComponentType.USER_SELECT_MENU:
                return hikari.User in types
            case hikari.ComponentType.ROLE_SELECT_MENU:
                return hikari.Role in types
            case _:
                return False

    def _extract_field(self) -> str | None:
        signature = signatures.SignatureManager.get_signature(self.callback)
        for parameter in signature.parameters.values():
            if parameter.annotation is parameter.empty or get_origin(parameter.annotation) is not list:
                continue

            types = typing.get_args(parameter.annotation)
            if self._is_compatible(types):
                return parameter.name

        return None

    def _parse_values(
        self, values: typing.Sequence[str], resolved_maps: typing.Sequence[typing.Mapping[hikari.Snowflake, typing.Any]]
    ) -> list[typing.Any]:
        response: list[typing.Any] = []
        for value in values:
            snowflake_value = hikari.Snowflake(value)
            for resolved_map in resolved_maps:
                resolved = resolved_map.get(snowflake_value)

                if resolved is not None:
                    response.append(resolved)
                    break
        return response

    def parse_select_menu(self, interaction: hikari.ComponentInteraction) -> dict[str, list[typing.Any]]:
        """Extract and resolve selected values from the interaction component payload.

        Args:
            interaction: The incoming component interaction.

        Returns:
            Dictionary mapping the callback parameter field to the resolved list of values.

        Raises:
            ValueError: If the select menu type requires resolved data but none is present.
        """
        response: dict[str, list[typing.Any]] = {}
        if not self.field:
            return response

        values: list[typing.Any] = []
        response[self.field] = values

        if self.type == hikari.ComponentType.TEXT_SELECT_MENU:
            values.extend(interaction.values)
            return response

        if interaction.resolved is None:
            msg = (
                f"Select menu interaction is of type {self.type}, but contains no resolved data to extract values from."
            )
            raise ValueError(msg)

        match self.type:
            case hikari.ComponentType.CHANNEL_SELECT_MENU:
                values.extend(self._parse_values(interaction.values, (interaction.resolved.channels,)))

            case hikari.ComponentType.MENTIONABLE_SELECT_MENU:
                values.extend(
                    self._parse_values(interaction.values, (interaction.resolved.users, interaction.resolved.roles))
                )

            case hikari.ComponentType.USER_SELECT_MENU:
                values.extend(
                    self._parse_values(interaction.values, (interaction.resolved.members, interaction.resolved.users))
                )

            case hikari.ComponentType.ROLE_SELECT_MENU:
                values.extend(self._parse_values(interaction.values, (interaction.resolved.roles,)))

            case _:
                pass

        return response

    def validate(self, validator: di.DependencyManager) -> None:
        """Validate parameter injection requirements for the select menu callback.

        Args:
            validator: The DependencyManager used to validate dependencies.
        """
        lazy_types = {hikari.ComponentInteraction, list}
        validator.validate(self.callback, lazy_types)
