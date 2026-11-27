from __future__ import annotations

import attrs
import pytest
from hikari import ComponentType, DMMessageCreateEvent, DMTypingEvent, GuildChannelCreateEvent, Role

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
from discordia.modules import Module, Registry, RegistryStore
from discordia.modules.registries import RegistrationData


async def dummy_typing_cb_1(event: DMTypingEvent) -> None:
    pass


async def dummy_typing_cb_2(event: DMTypingEvent) -> None:
    pass


async def dummy_message_cb(event: DMMessageCreateEvent) -> None:
    pass


async def dummy_interaction_cb(ctx: object) -> None:
    pass


async def dummy_role_select_cb(roles: list[Role]) -> None:
    pass


async def dummy_error_cb(err: ValueError) -> None:
    pass


class TestRegistrationData:
    def test_stores_owner_and_data(self) -> None:
        module = Module()
        responder = EventResponder(DMTypingEvent, dummy_typing_cb_1)
        registered = RegistrationData(owner=module, data=responder)

        assert registered.owner is module
        assert registered.data is responder

    def test_is_immutable(self) -> None:
        module = Module()
        registered = RegistrationData(owner=module, data="payload")

        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            registered.owner = Module()

    def test_distinct_data_with_same_owner_coexist_in_set(self) -> None:
        module = Module()
        reg1 = RegistrationData(owner=module, data=SlashCommand("ping", "Ping"))
        reg2 = RegistrationData(owner=module, data=SlashCommand("pong", "Pong"))

        bucket = {reg1, reg2}
        assert len(bucket) == 2


class TestGenericRegistry:
    def test_crud_and_container_protocol(self) -> None:
        module = Module()
        registry: Registry[str, tuple[str, int]] = Registry("custom", lambda item: item[0])

        item_a = ("alpha", 1)
        item_b = ("beta", 2)

        registry.add(item_a, module)
        registry.add(item_b, module)

        assert len(registry) == 2
        assert "alpha" in registry
        assert "missing" not in registry
        assert registry["alpha"] == item_a
        assert registry.get("beta") == item_b
        assert registry.get("missing") is None
        assert list(registry) == [item_a, item_b]
        assert len(registry.get_registers()) == 2
        assert {r.data for r in module.metadata.get_registers()} == {item_a, item_b}

    def test_getitem_missing_key_raises_key_error(self) -> None:
        registry: Registry[str, str] = Registry("custom", lambda s: s)
        with pytest.raises(KeyError):
            _ = registry["nonexistent"]

    def test_duplicate_key_raises_value_error_in_add_and_add_register(self) -> None:
        module = Module()
        registry: Registry[str, tuple[str, int]] = Registry("custom", lambda item: item[0])

        registry.add(("dup", 1), module)
        with pytest.raises(ValueError, match="custom"):
            registry.add(("dup", 2), module)

        with pytest.raises(ValueError, match="custom"):
            registry.add_register(RegistrationData(module, ("dup", 3)))

    def test_remove_deletes_entry_and_syncs_owner_metadata(self) -> None:
        module = Module()
        registry: Registry[str, str] = Registry("tag", lambda s: s)
        registry.add("hello", module)

        removed = registry.remove("hello")
        assert removed == "hello"
        assert "hello" not in registry
        assert len(module.metadata.get_registers()) == 0

        with pytest.raises(KeyError):
            registry.remove("hello")


class TestEventRegistry:
    def test_add_lookup_and_remove_event(self) -> None:
        store = RegistryStore()
        module = Module()

        ev_typing = EventResponder(DMTypingEvent, dummy_typing_cb_1)
        ev_msg = EventResponder(DMMessageCreateEvent, dummy_message_cb)

        store.events.add(ev_typing, module)
        store.events.add(ev_msg, module)

        assert len(store.events) == 2
        assert DMTypingEvent in store.events
        assert store.events[DMTypingEvent] is ev_typing
        registered_before = [r.data for r in module.metadata.get_registers()]
        assert ev_typing in registered_before
        assert ev_msg in registered_before

        removed = store.events.remove(DMTypingEvent)
        assert removed is ev_typing
        assert DMTypingEvent not in store.events
        assert [r.data for r in module.metadata.get_registers()] == [ev_msg]

        with pytest.raises(KeyError):
            store.events.remove(GuildChannelCreateEvent)

    def test_merge_and_unmerge_combines_and_separates_callbacks(self) -> None:
        s1, s2, s_dest = RegistryStore(), RegistryStore(), RegistryStore()
        m1, m2 = Module(), Module()

        ev1 = EventResponder(DMTypingEvent, dummy_typing_cb_1)
        ev2 = EventResponder(DMTypingEvent, dummy_typing_cb_2)

        s1.events.add(ev1, m1)
        s2.events.add(ev2, m2)

        s1.events.merge(s2.events.get_registers())
        assert s1.events[DMTypingEvent].callbacks == {dummy_typing_cb_1, dummy_typing_cb_2}

        for reg in m2.metadata.get_registers():
            s1.events.unmerge(reg, s_dest.events)

        assert s1.events[DMTypingEvent].callbacks == {dummy_typing_cb_1}
        assert s_dest.events[DMTypingEvent].callbacks == {dummy_typing_cb_2}

    def test_merge_two_children_into_empty_event_registry_then_unmerge_first(self) -> None:
        root_store, store_b, store_c, dest_b = RegistryStore(), RegistryStore(), RegistryStore(), RegistryStore()
        mod_b, mod_c = Module(), Module()

        ev_b = EventResponder(DMTypingEvent, dummy_typing_cb_1)
        ev_c = EventResponder(DMTypingEvent, dummy_typing_cb_2)

        store_b.events.add(ev_b, mod_b)
        store_c.events.add(ev_c, mod_c)

        root_store.events.merge(store_b.events.get_registers())
        root_store.events.merge(store_c.events.get_registers())
        assert root_store.events[DMTypingEvent].callbacks == {dummy_typing_cb_1, dummy_typing_cb_2}

        for reg in mod_b.metadata.get_registers():
            root_store.events.unmerge(reg, dest_b.events)

        # Root must still retain mod_c's listener, and dest_b must only contain mod_b's listener
        assert DMTypingEvent in root_store.events
        assert root_store.events[DMTypingEvent].callbacks == {dummy_typing_cb_2}
        assert dest_b.events[DMTypingEvent].callbacks == {dummy_typing_cb_1}


class TestSpecializedRegistries:
    def test_slash_commands_registry(self) -> None:
        store = RegistryStore()
        module = Module()

        cmd = SlashCommand("ban", "Ban a member").responder(dummy_interaction_cb)
        store.slash_commands.add(cmd, module)
        assert store.slash_commands["ban"] is cmd

        with pytest.raises(ValueError):
            store.slash_commands.add(SlashCommand("ban", "Duplicate"), module)

        assert store.slash_commands.remove("ban") is cmd
        with pytest.raises(KeyError):
            store.slash_commands.remove("ban")

    def test_user_and_message_menu_registries(self) -> None:
        store = RegistryStore()
        module = Module()

        u_menu = UserMenu(dummy_interaction_cb, "User Info")
        m_menu = MessageMenu(dummy_interaction_cb, "Pin Message")

        store.user_menus.add(u_menu, module)
        store.message_menus.add(m_menu, module)

        assert store.user_menus["User Info"] is u_menu
        assert store.message_menus["Pin Message"] is m_menu

        with pytest.raises(ValueError):
            store.user_menus.add(UserMenu(dummy_interaction_cb, "User Info"), module)
        with pytest.raises(ValueError):
            store.message_menus.add(MessageMenu(dummy_interaction_cb, "Pin Message"), module)

        assert store.user_menus.remove("User Info") is u_menu
        assert store.message_menus.remove("Pin Message") is m_menu

    def test_component_registries_buttons_select_menus_and_modals(self) -> None:
        store = RegistryStore()
        module = Module()

        btn = Button(dummy_interaction_cb, "btn:confirm")
        sel = SelectMenu(dummy_role_select_cb, "sel:roles", ComponentType.ROLE_SELECT_MENU)
        mdl = Modal(dummy_interaction_cb, "mdl:feedback")

        store.buttons.add(btn, module)
        store.select_menus.add(sel, module)
        store.modals.add(mdl, module)

        assert store.buttons["btn:confirm"] is btn
        assert store.select_menus["sel:roles"] is sel
        assert store.modals["mdl:feedback"] is mdl

        with pytest.raises(ValueError):
            store.buttons.add(Button(dummy_interaction_cb, "btn:confirm"), module)
        with pytest.raises(ValueError):
            store.select_menus.add(
                SelectMenu(dummy_role_select_cb, "sel:roles", ComponentType.ROLE_SELECT_MENU), module
            )
        with pytest.raises(ValueError):
            store.modals.add(Modal(dummy_interaction_cb, "mdl:feedback"), module)

        assert store.buttons.remove("btn:confirm") is btn
        assert store.select_menus.remove("sel:roles") is sel
        assert store.modals.remove("mdl:feedback") is mdl

    def test_error_registry(self) -> None:
        store = RegistryStore()
        module = Module()

        err_resp = ErrorResponder(ValueError, dummy_error_cb)
        store.errors.add(err_resp, module)
        assert store.errors[ValueError] is err_resp

        with pytest.raises(ValueError):
            store.errors.add(ErrorResponder(ValueError, dummy_error_cb), module)

        assert store.errors.remove(ValueError) is err_resp
        with pytest.raises(KeyError):
            store.errors.remove(ValueError)


class TestRegistryStore:
    def test_initializes_all_eight_registries_empty(self) -> None:
        store = RegistryStore()
        assert len(store.events) == 0
        assert len(store.slash_commands) == 0
        assert len(store.user_menus) == 0
        assert len(store.message_menus) == 0
        assert len(store.buttons) == 0
        assert len(store.select_menus) == 0
        assert len(store.modals) == 0
        assert len(store.errors) == 0

    def test_store_merge_and_unmerge_events_commands_and_components(self) -> None:
        s1, s2, s_dest = RegistryStore(), RegistryStore(), RegistryStore()
        m1, m2 = Module(), Module()

        s1.events.add(EventResponder(DMTypingEvent, dummy_typing_cb_1), m1)
        s1.slash_commands.add(SlashCommand("ping", "Ping"), m1)

        s2.events.add(EventResponder(DMMessageCreateEvent, dummy_message_cb), m2)
        s2.slash_commands.add(SlashCommand("ban", "Ban"), m2)
        s2.user_menus.add(UserMenu(dummy_interaction_cb, "Inspect User"), m2)
        s2.message_menus.add(MessageMenu(dummy_interaction_cb, "Report Msg"), m2)
        s2.buttons.add(Button(dummy_interaction_cb, "btn:ok"), m2)
        s2.select_menus.add(SelectMenu(dummy_role_select_cb, "sel:role", ComponentType.ROLE_SELECT_MENU), m2)
        s2.modals.add(Modal(dummy_interaction_cb, "mdl:form"), m2)

        s1.merge(s2)

        assert DMMessageCreateEvent in s1.events
        assert "ban" in s1.slash_commands
        assert "Inspect User" in s1.user_menus
        assert "Report Msg" in s1.message_menus
        assert "btn:ok" in s1.buttons
        assert "sel:role" in s1.select_menus
        assert "mdl:form" in s1.modals

        s1.unmerge(m2.metadata.get_registers(), s_dest)

        assert DMTypingEvent in s1.events
        assert "ping" in s1.slash_commands
        assert DMMessageCreateEvent not in s1.events
        assert "ban" not in s1.slash_commands
        assert "Inspect User" not in s1.user_menus
        assert "Report Msg" not in s1.message_menus
        assert "btn:ok" not in s1.buttons
        assert "sel:role" not in s1.select_menus
        assert "mdl:form" not in s1.modals

        assert DMMessageCreateEvent in s_dest.events
        assert "ban" in s_dest.slash_commands
        assert "Inspect User" in s_dest.user_menus
        assert "Report Msg" in s_dest.message_menus
        assert "btn:ok" in s_dest.buttons
        assert "sel:role" in s_dest.select_menus
        assert "mdl:form" in s_dest.modals

    def test_store_merge_and_unmerge_errors(self) -> None:
        s1, s2, s_dest = RegistryStore(), RegistryStore(), RegistryStore()
        m2 = Module()

        s2.errors.add(ErrorResponder(ValueError, dummy_error_cb), m2)
        s1.merge(s2)
        assert ValueError in s1.errors

        s1.unmerge(m2.metadata.get_registers(), s_dest)
        assert ValueError not in s1.errors
        assert ValueError in s_dest.errors

    def test_store_merge_raises_on_duplicate_command(self) -> None:
        s1, s2 = RegistryStore(), RegistryStore()
        m1, m2 = Module(), Module()

        s1.slash_commands.add(SlashCommand("ban", "Ban 1"), m1)
        s2.slash_commands.add(SlashCommand("ban", "Ban 2"), m2)

        with pytest.raises(ValueError):
            s1.merge(s2)

    def test_store_unmerge_unknown_data_type_raises_value_error(self) -> None:
        s_source, s_dest = RegistryStore(), RegistryStore()
        mod = Module()
        bogus = RegistrationData(owner=mod, data="unrecognized_payload")

        with pytest.raises(ValueError):
            s_source.unmerge({bogus}, s_dest)
