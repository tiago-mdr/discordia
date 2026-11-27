from __future__ import annotations

import pytest
from hikari import (
    ComponentType,
    DMMessageCreateEvent,
    DMTypingEvent,
    Event,
    Locale,
    Permissions,
    Role,
)
from hikari.undefined import UNDEFINED

from discordia.handlers import ErrorResponder
from discordia.interactions import (
    Button,
    EventResponder,
    MessageMenu,
    Modal,
    SelectMenu,
    SlashCommand,
    UserMenu,
)
from discordia.modules import Module


class TestEventDecorator:
    def test_listen_infers_event_type_from_signature(self) -> None:
        mod = Module()

        @mod.events.listen()
        async def on_typing(event: DMTypingEvent) -> None:
            pass

        assert isinstance(on_typing, EventResponder)
        assert on_typing.event is DMTypingEvent
        assert DMTypingEvent in mod.registers.events
        assert mod.registers.events[DMTypingEvent] is on_typing
        assert any(r.data is on_typing for r in mod.metadata.get_registers())

    def test_listen_with_explicit_event_type_overrides_annotation(self) -> None:
        mod = Module()

        @mod.events.listen(DMMessageCreateEvent)
        async def on_generic_event(event: Event) -> None:
            pass

        assert on_generic_event.event is DMMessageCreateEvent
        assert DMMessageCreateEvent in mod.registers.events

    def test_listen_raises_type_error_when_event_cannot_be_inferred(self) -> None:
        mod = Module()

        with pytest.raises(TypeError, match="Could not infer event type"):

            @mod.events.listen()
            async def invalid_listener(not_an_event: int) -> None:
                pass

    def test_multiple_listeners_for_same_event_on_same_module(self) -> None:
        mod = Module()

        async def first_cb(event: DMTypingEvent) -> None:
            pass

        async def second_cb(event: DMTypingEvent) -> None:
            pass

        mod.events.listen()(first_cb)
        mod.events.listen()(second_cb)

        responder = mod.registers.events.get(DMTypingEvent)
        assert responder is not None
        assert responder.callbacks == {first_cb, second_cb}


class TestCatchErrorDecorator:
    def test_catch_error_infers_exception_type_from_signature(self) -> None:
        mod = Module()

        @mod.catch_error()
        async def handle_value_error(err: ValueError) -> None:
            pass

        assert isinstance(handle_value_error, ErrorResponder)
        assert handle_value_error.error is ValueError
        assert ValueError in mod.registers.errors
        assert mod.registers.errors[ValueError] is handle_value_error
        assert any(r.data is handle_value_error for r in mod.metadata.get_registers())

    def test_catch_error_with_explicit_exception_type(self) -> None:
        mod = Module()

        @mod.catch_error(KeyError)
        async def handle_generic(err: Exception) -> None:
            pass

        assert handle_generic.error is KeyError
        assert KeyError in mod.registers.errors

    def test_catch_error_raises_value_error_when_type_cannot_be_inferred(self) -> None:
        mod = Module()

        with pytest.raises(ValueError, match="Cannot infer the error type"):

            @mod.catch_error()
            async def bad_error_handler(x: str) -> None:
                pass

    def test_duplicate_catch_error_for_same_exception_raises_value_error(self) -> None:
        mod = Module()

        @mod.catch_error()
        async def first_handler(err: RuntimeError) -> None:
            pass

        with pytest.raises(ValueError):

            @mod.catch_error()
            async def second_handler(err: RuntimeError) -> None:
                pass


class TestCommandDecorator:
    def test_slash_command_with_explicit_metadata(self) -> None:
        mod = Module()

        @mod.interactions.slash_command(
            "kick",
            "Kick a member",
            default_member_permissions=Permissions.KICK_MEMBERS,
            is_nsfw=False,
            name_localizations={Locale.PT_BR: "expulsar"},
            description_localizations={Locale.PT_BR: "Expulsa um membro"},
        )
        async def kick_cmd(reason: str) -> None:
            pass

        assert isinstance(kick_cmd, SlashCommand)
        assert "kick" in mod.registers.slash_commands
        assert mod.registers.slash_commands["kick"] is kick_cmd
        assert kick_cmd.name == "kick"
        assert kick_cmd.description == "Kick a member"
        assert kick_cmd.default_member_permissions == Permissions.KICK_MEMBERS
        assert kick_cmd.is_nsfw is False
        assert kick_cmd.name_localizations == {Locale.PT_BR: "expulsar"}
        assert kick_cmd.description_localizations == {Locale.PT_BR: "Expulsa um membro"}
        assert kick_cmd.build() is not None

    def test_slash_command_defaults_name_to_function_name(self) -> None:
        mod = Module()

        @mod.interactions.slash_command()
        async def ping() -> None:
            pass

        assert "ping" in mod.registers.slash_commands
        assert ping.name == "ping"
        assert ping.description == "..."
        assert ping.default_member_permissions is UNDEFINED
        assert ping.name_localizations == {}

    def test_user_menu_decorator(self) -> None:
        mod = Module()

        @mod.interactions.user_menu("User Profile", is_nsfw=False)
        async def profile_cmd(ctx: object) -> None:
            pass

        assert isinstance(profile_cmd, UserMenu)
        assert "User Profile" in mod.registers.user_menus
        assert profile_cmd.name == "User Profile"
        assert profile_cmd.is_nsfw is False
        assert profile_cmd.name_localizations == {}
        assert profile_cmd.build() is not None

    def test_message_menu_decorator(self) -> None:
        mod = Module()

        @mod.interactions.message_menu("Bookmark Message")
        async def bookmark_cmd(ctx: object) -> None:
            pass

        assert isinstance(bookmark_cmd, MessageMenu)
        assert "Bookmark Message" in mod.registers.message_menus
        assert bookmark_cmd.name == "Bookmark Message"
        assert bookmark_cmd.name_localizations == {}
        assert bookmark_cmd.build() is not None


class TestComponentDecorator:
    def test_button_decorator(self) -> None:
        mod = Module()

        async def on_confirm(ctx: object) -> None:
            pass

        btn = mod.interactions.button("confirm_btn")(on_confirm)

        assert isinstance(btn, Button)
        assert btn.custom_id == "confirm_btn"
        assert btn.callback is on_confirm
        assert mod.registers.buttons["confirm_btn"] is btn
        assert any(r.data is btn for r in mod.metadata.get_registers())

    def test_select_menu_decorator_default_and_custom_type(self) -> None:
        mod = Module()

        async def on_text_select(choices: list[str]) -> None:
            pass

        async def on_role_select(roles: list[Role]) -> None:
            pass

        text_menu = mod.interactions.select_menu("pick_color")(on_text_select)
        role_menu = mod.interactions.select_menu("pick_role", type=ComponentType.ROLE_SELECT_MENU)(on_role_select)

        assert isinstance(text_menu, SelectMenu)
        assert text_menu.type == ComponentType.TEXT_SELECT_MENU
        assert text_menu.field == "choices"
        assert mod.registers.select_menus["pick_color"] is text_menu

        assert isinstance(role_menu, SelectMenu)
        assert role_menu.type == ComponentType.ROLE_SELECT_MENU
        assert role_menu.field == "roles"
        assert mod.registers.select_menus["pick_role"] is role_menu

    def test_modal_decorator(self) -> None:
        mod = Module()

        async def on_submit(ctx: object) -> None:
            pass

        modal = mod.interactions.modal("feedback_modal")(on_submit)

        assert isinstance(modal, Modal)
        assert modal.custom_id == "feedback_modal"
        assert modal.callback is on_submit
        assert mod.registers.modals["feedback_modal"] is modal
        assert any(r.data is modal for r in mod.metadata.get_registers())
