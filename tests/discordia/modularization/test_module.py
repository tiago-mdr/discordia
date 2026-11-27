from __future__ import annotations

import pytest
from hikari import DMMessageCreateEvent, DMTypingEvent, GuildChannelCreateEvent

from discordia.errors import DiscordiaError, ModularizationError, ModuleMergeError, ModuleUnmergeError
from discordia.modules import Module


class TestModuleInitialization:
    def test_empty_module_initial_state(self) -> None:
        m = Module()
        assert m.metadata.module is m
        assert m.metadata.owner is None
        assert m.metadata.children == set()
        assert m.metadata.root is m
        assert m.metadata.family == {m}
        assert m.metadata.get_registers() == set()
        assert len(m.registers.events) == 0
        assert len(m.registers.slash_commands) == 0
        assert len(m.registers.errors) == 0

    def test_modularization_error_hierarchy(self) -> None:
        assert issubclass(ModularizationError, DiscordiaError)
        assert issubclass(ModuleMergeError, ModularizationError)
        assert issubclass(ModuleUnmergeError, ModularizationError)


class TestModuleHierarchyMergeAndUnmerge:
    def test_simple_merge_and_unmerge(self) -> None:
        a = Module()
        b = Module()

        @a.events.listen()
        async def f1(e: DMTypingEvent) -> None:
            pass

        @b.events.listen()
        async def f2(e: DMMessageCreateEvent) -> None:
            pass

        @b.interactions.slash_command("ping", "Ping command")
        async def ping() -> None:
            pass

        a.merge(b)

        assert b.metadata.owner is a
        assert b in a.metadata.children
        assert b.metadata.root is a
        assert a.metadata.family == {a, b}
        assert b.metadata.family is a.metadata.family

        assert DMTypingEvent in a.registers.events
        assert DMMessageCreateEvent in a.registers.events
        assert "ping" in a.registers.slash_commands
        assert a.registers is b.registers

        a.unmerge(b)

        assert b.metadata.owner is None
        assert b not in a.metadata.children
        assert b.metadata.root is b
        assert a.metadata.family == {a}
        assert b.metadata.family == {b}

        assert DMTypingEvent in a.registers.events
        assert DMMessageCreateEvent not in a.registers.events
        assert "ping" not in a.registers.slash_commands

        assert DMMessageCreateEvent in b.registers.events
        assert "ping" in b.registers.slash_commands
        assert DMTypingEvent not in b.registers.events
        assert a.registers is not b.registers

    def test_merge_and_unmerge_preserves_error_handlers(self) -> None:
        a = Module()
        b = Module()

        @b.catch_error()
        async def on_value_err(err: ValueError) -> None:
            pass

        a.merge(b)
        assert ValueError in a.registers.errors

        a.unmerge(b)
        assert ValueError not in a.registers.errors
        assert ValueError in b.registers.errors

    def test_multi_level_merge_bottom_up(self) -> None:
        a, b, c = Module(), Module(), Module()

        @c.events.listen()
        async def fc(e: GuildChannelCreateEvent) -> None:
            pass

        b.merge(c)
        a.merge(b)

        assert c.metadata.owner is b
        assert b.metadata.owner is a
        assert c.metadata.root is a
        assert b.metadata.root is a
        assert a.metadata.root is a

        assert a.metadata.family == {a, b, c}
        assert b.metadata.family is a.metadata.family
        assert c.metadata.family is a.metadata.family
        assert GuildChannelCreateEvent in a.registers.events
        assert a.registers is b.registers is c.registers

        a.unmerge(b)

        assert a.metadata.family == {a}
        assert b.metadata.family == {b, c}
        assert c.metadata.family is b.metadata.family
        assert b.metadata.owner is None
        assert c.metadata.owner is b
        assert c.metadata.root is b

        assert GuildChannelCreateEvent not in a.registers.events
        assert GuildChannelCreateEvent in b.registers.events
        assert b.registers is c.registers
        assert a.registers is not b.registers

    def test_multi_level_merge_top_down(self) -> None:
        a, b, c = Module(), Module(), Module()

        @c.events.listen()
        async def fc(e: GuildChannelCreateEvent) -> None:
            pass

        a.merge(b)
        b.merge(c)

        assert c.metadata.owner is b
        assert b.metadata.owner is a
        assert c.metadata.root is a
        assert b.metadata.root is a
        assert a.metadata.family == {a, b, c}
        assert GuildChannelCreateEvent in a.registers.events
        assert a.registers is b.registers is c.registers

        b.unmerge(c)

        assert a.metadata.family == {a, b}
        assert b.metadata.family is a.metadata.family
        assert c.metadata.family == {c}
        assert GuildChannelCreateEvent not in a.registers.events
        assert GuildChannelCreateEvent in c.registers.events

    def test_unmerge_indirect_descendant_from_root(self) -> None:
        a, b, c = Module(), Module(), Module()

        @c.events.listen()
        async def fc(e: GuildChannelCreateEvent) -> None:
            pass

        a.merge(b)
        b.merge(c)

        a.unmerge(c)

        assert c.metadata.owner is None
        assert c not in b.metadata.children
        assert a.metadata.family == {a, b}
        assert b.metadata.family is a.metadata.family
        assert c.metadata.family == {c}

        assert GuildChannelCreateEvent not in a.registers.events
        assert GuildChannelCreateEvent in c.registers.events

    def test_registrations_added_to_child_after_merge_migrate_on_unmerge(self) -> None:
        a = Module()
        b = Module()
        a.merge(b)

        @b.events.listen()
        async def on_typing(e: DMTypingEvent) -> None:
            pass

        @b.interactions.slash_command("hello", "Says hello")
        async def hello() -> None:
            pass

        assert DMTypingEvent in a.registers.events
        assert "hello" in a.registers.slash_commands

        a.unmerge(b)

        assert DMTypingEvent not in a.registers.events
        assert "hello" not in a.registers.slash_commands
        assert DMTypingEvent in b.registers.events
        assert "hello" in b.registers.slash_commands

    def test_remerge_into_same_or_different_parent_after_unmerge(self) -> None:
        a, b, new_parent = Module(), Module(), Module()

        @b.events.listen()
        async def on_typing(e: DMTypingEvent) -> None:
            pass

        a.merge(b)
        a.unmerge(b)

        # Re-merge into original parent
        a.merge(b)
        assert b.metadata.owner is a
        assert a.metadata.family == {a, b}
        assert DMTypingEvent in a.registers.events

        # Detach again and attach to a brand-new parent
        a.unmerge(b)
        new_parent.merge(b)
        assert b.metadata.owner is new_parent
        assert new_parent.metadata.family == {new_parent, b}
        assert DMTypingEvent in new_parent.registers.events
        assert DMTypingEvent not in a.registers.events

    def test_root_cache_path_compression(self) -> None:
        a, b, c, d, e = Module(), Module(), Module(), Module(), Module()
        d.merge(e)
        c.merge(d)
        b.merge(c)
        a.merge(b)

        assert e.metadata.root is a

        super_root = Module()
        super_root.merge(a)

        assert e.metadata.root is super_root

    def test_deep_hierarchy_subtree_unmerge(self) -> None:
        a, b, c, d, e = Module(), Module(), Module(), Module(), Module()

        @a.events.listen()
        async def fa(ev: DMTypingEvent) -> None:
            pass

        @e.events.listen()
        async def fe(ev: DMMessageCreateEvent) -> None:
            pass

        d.merge(e)
        c.merge(d)
        b.merge(c)
        a.merge(b)

        assert a.metadata.family == {a, b, c, d, e}
        assert DMMessageCreateEvent in a.registers.events

        a.unmerge(c)

        assert a.metadata.family == {a, b}
        assert b.metadata.family is a.metadata.family
        assert DMMessageCreateEvent not in a.registers.events
        assert DMTypingEvent in a.registers.events

        assert c.metadata.family == {c, d, e}
        assert d.metadata.family is c.metadata.family
        assert e.metadata.family is c.metadata.family
        assert c.metadata.owner is None
        assert d.metadata.root is c
        assert e.metadata.root is c
        assert DMMessageCreateEvent in c.registers.events
        assert DMTypingEvent not in c.registers.events


class TestModuleSharedEventsAcrossTree:
    def test_two_modules_with_same_event_combine_and_split_cleanly(self) -> None:
        a, b = Module(), Module()

        async def cb_a(e: DMTypingEvent) -> None:
            pass

        async def cb_b(e: DMTypingEvent) -> None:
            pass

        a.events.listen()(cb_a)
        b.events.listen()(cb_b)

        a.merge(b)
        assert a.registers.events[DMTypingEvent].callbacks == {cb_a, cb_b}

        a.unmerge(b)
        assert a.registers.events[DMTypingEvent].callbacks == {cb_a}
        assert b.registers.events[DMTypingEvent].callbacks == {cb_b}

    def test_child_listening_to_event_already_registered_in_parent_after_merge(self) -> None:
        a, b = Module(), Module()

        async def cb_a(e: DMTypingEvent) -> None:
            pass

        async def cb_b(e: DMTypingEvent) -> None:
            pass

        a.events.listen()(cb_a)
        a.merge(b)
        b.events.listen()(cb_b)

        assert a.registers.events[DMTypingEvent].callbacks == {cb_a, cb_b}

        a.unmerge(b)
        assert a.registers.events[DMTypingEvent].callbacks == {cb_a}
        assert b.registers.events[DMTypingEvent].callbacks == {cb_b}

    def test_three_modules_where_two_children_share_event_and_first_child_unmerges(self) -> None:
        root, child_b, child_c = Module(), Module(), Module()

        async def cb_b(e: DMTypingEvent) -> None:
            pass

        async def cb_c(e: DMTypingEvent) -> None:
            pass

        child_b.events.listen()(cb_b)
        child_c.events.listen()(cb_c)

        root.merge(child_b)
        root.merge(child_c)
        assert root.registers.events[DMTypingEvent].callbacks == {cb_b, cb_c}

        root.unmerge(child_b)

        assert DMTypingEvent in root.registers.events
        assert root.registers.events[DMTypingEvent].callbacks == {cb_c}
        assert child_b.registers.events[DMTypingEvent].callbacks == {cb_b}


class TestModuleErrorsAndInvariants:
    def test_error_merge_self(self) -> None:
        a = Module()
        with pytest.raises(ModuleMergeError, match="Cannot merge a module into itself"):
            a.merge(a)

    def test_error_merge_already_owned(self) -> None:
        a, b, c = Module(), Module(), Module()
        a.merge(b)
        with pytest.raises(ModuleMergeError, match="already has an owner"):
            c.merge(b)

    def test_error_merge_direct_and_indirect_cycles(self) -> None:
        a, b, c = Module(), Module(), Module()
        a.merge(b)
        b.merge(c)

        with pytest.raises(ModuleMergeError):
            b.merge(a)

        with pytest.raises(ModuleMergeError):
            c.merge(a)

    def test_error_unmerge_self_or_unrelated_module(self) -> None:
        a, unrelated = Module(), Module()

        with pytest.raises(ModuleUnmergeError):
            a.unmerge(a)

        with pytest.raises(ModuleUnmergeError):
            a.unmerge(unrelated)

    def test_error_child_cannot_unmerge_its_own_parent(self) -> None:
        parent, child = Module(), Module()
        parent.merge(child)

        with pytest.raises(ModuleUnmergeError):
            child.unmerge(parent)

    def test_error_sibling_cannot_unmerge_another_sibling(self) -> None:
        root, sibling_a, sibling_b = Module(), Module(), Module()
        root.merge(sibling_a)
        root.merge(sibling_b)

        with pytest.raises(ModuleUnmergeError):
            sibling_a.unmerge(sibling_b)

    def test_failed_merge_due_to_duplicate_command_leaves_hierarchy_clean(self) -> None:
        a, b = Module(), Module()

        @a.interactions.slash_command("ping", "Ping A")
        async def ping_a() -> None:
            pass

        @b.interactions.slash_command("ping", "Ping B")
        async def ping_b() -> None:
            pass

        with pytest.raises(ValueError):
            a.merge(b)

        assert b.metadata.owner is None
        assert b not in a.metadata.children
        assert b not in a.metadata.family
