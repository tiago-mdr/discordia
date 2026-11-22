import typing
from collections.abc import Awaitable, Callable
from typing import Any, get_origin

import attrs
import hikari

from discordia import signatures


@attrs.define()
class SelectMenu:
    callback: Callable[..., Awaitable[Any]] = attrs.field()
    custom_id: str = attrs.field()
    type: hikari.ComponentType = attrs.field()
    field: str = attrs.field(default="", init=False)

    def __attrs_post_init__(self) -> None:
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
        signature = signatures.SignatureManager.get_signature(self.callback, cache=True)

        for parameter in signature.parameters.values():
            if parameter.annotation is parameter.empty or get_origin(parameter.annotation) is not list:
                continue

            types = signatures.extract_args(parameter.annotation)
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
                f"Select menu interaction is of type {self.type}, "
                "but contains no resolved data to extract values from."
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
