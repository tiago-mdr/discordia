from typing import Annotated, Protocol, runtime_checkable

import pytest

from discordia.di import DependencyManager, Resolution, inject
from discordia.errors import DependencyNotFoundError, MissingAnnotationError


@pytest.fixture
def manager() -> DependencyManager:
    return DependencyManager()


class TestExecutionAndResolution:
    async def test_sync_function_execution(self, manager: DependencyManager):
        def get_int() -> int:
            return 5

        manager.add_dependency(get_int)

        def add_five(val: int) -> int:
            return val + 5

        result = await manager.execute(add_five)
        assert result == 10

    async def test_async_function_execution(self, manager: DependencyManager):
        async def get_greeting() -> str:
            return "hello"

        manager.add_dependency(get_greeting)

        async def async_handler(greeting: str) -> str:
            return f"{greeting} world"

        result = await manager.execute(async_handler)
        assert result == "hello world"

    async def test_direct_resolve_returns_resolution(self, manager: DependencyManager):
        def get_value() -> int:
            return 42

        def target(x: Annotated[int, inject(get_value)], *, label: str = "ans") -> str:
            return f"{label}: {x}"

        resolution = await manager.resolve(target)

        assert isinstance(resolution, Resolution)
        assert resolution.args == (42,)
        assert resolution.kwargs == {"label": "ans"}
        await resolution.finish()

    async def test_class_instantiation_as_target(self, manager: DependencyManager):
        class Database:
            def __init__(self) -> None:
                self.connected = True

        class Service:
            def __init__(self, db: Database) -> None:
                self.db = db

        manager.add_dependency(Database)

        service = await manager.execute(Service)
        assert isinstance(service, Service)
        assert isinstance(service.db, Database)
        assert service.db.connected is True

    async def test_multi_level_dependency_hierarchy(self, manager: DependencyManager):
        class Config:
            def __init__(self) -> None:
                self.db_url = "db/discordia"

        class Database:
            def __init__(self, config: Config) -> None:
                self.url = config.db_url

        class UserRepository:
            def __init__(self, db: Database) -> None:
                self.db = db

        class UserService:
            def __init__(self, repo: UserRepository) -> None:
                self.repo = repo

        manager.add_dependency(Config)
        manager.add_dependency(Database)
        manager.add_dependency(UserRepository)

        service = await manager.execute(UserService)
        assert isinstance(service, UserService)
        assert service.repo.db.url == "db/discordia"

    async def test_non_callable_instance_as_dependency(self, manager: DependencyManager):
        class AppSettings:
            def __init__(self, env: str) -> None:
                self.env = env

        production_settings = AppSettings("production")
        manager.add_dependency(production_settings)

        def get_env(settings: AppSettings) -> str:
            return settings.env

        result = await manager.execute(get_env)
        assert result == "production"

    async def test_subclass_runtime_injection(self, manager: DependencyManager):
        class Animal:
            pass

        class Cat(Animal):
            def meow(self) -> str:
                return "meow"

        def get_cat() -> Cat:
            return Cat()

        def pet(animal: Annotated[Animal, inject(get_cat)]) -> str:
            return animal.meow()

        result = await manager.execute(pet)
        assert result == "meow"

    async def test_runtime_checkable_protocol_injection(self, manager: DependencyManager):
        @runtime_checkable
        class Notifier(Protocol):
            def notify(self, msg: str) -> str: ...

        class DiscordNotifier:
            def notify(self, msg: str) -> str:
                return f"discord: {msg}"

        def get_notifier() -> DiscordNotifier:
            return DiscordNotifier()

        def send_alert(n: Annotated[Notifier, inject(get_notifier)]) -> str:
            return n.notify("alert")

        result = await manager.execute(send_alert)
        assert result == "discord: alert"

    async def test_dependency_returning_none_is_not_cached_even_in_singleton_scope(self, manager: DependencyManager):
        calls = 0

        def nullable_dep() -> int | None:
            nonlocal calls
            calls += 1
            return None if calls == 1 else 99

        def consumer(val: Annotated[int | None, inject(nullable_dep, "singleton")]) -> int | None:
            return val

        first = await manager.execute(consumer)
        second = await manager.execute(consumer)
        third = await manager.execute(consumer)

        assert first is None
        assert second == 99
        assert third == 99
        assert calls == 2


class TestParameterKinds:
    async def test_positional_only_parameters(self, manager: DependencyManager):
        def get_a() -> int:
            return 1

        def get_b() -> str:
            return "b"

        def func(
            a: Annotated[int, inject(get_a)],
            /,
            b: Annotated[str, inject(get_b)],
        ) -> tuple[int, str]:
            return (a, b)

        result = await manager.execute(func)
        assert result == (1, "b")

    async def test_keyword_only_parameters(self, manager: DependencyManager):
        def get_a() -> int:
            return 10

        def get_b() -> str:
            return "kw"

        def func(
            *,
            a: Annotated[int, inject(get_a)],
            b: Annotated[str, inject(get_b)],
        ) -> dict[str, object]:
            return {"a": a, "b": b}

        result = await manager.execute(func)
        assert result == {"a": 10, "b": "kw"}

    async def test_varargs_and_varkwargs_ignored_cleanly_at_runtime(self, manager: DependencyManager):
        def get_int() -> int:
            return 7

        manager.add_dependency(get_int)

        def func(val: int, *args: str, **kwargs: bool) -> tuple[int, tuple[str, ...], dict[str, bool]]:
            return (val, args, kwargs)

        result = await manager.execute(func)
        assert result == (7, (), {})

    async def test_mixed_parameter_kinds(self, manager: DependencyManager):
        def get_int() -> int:
            return 1

        def get_str() -> str:
            return "mid"

        def get_bool() -> bool:
            return True

        def func(
            p1: Annotated[int, inject(get_int)],
            /,
            p2: Annotated[str, inject(get_str)],
            *args: object,
            p3: Annotated[bool, inject(get_bool)],
            **kwargs: object,
        ) -> tuple[int, str, bool]:
            return (p1, p2, p3)

        result = await manager.execute(func)
        assert result == (1, "mid", True)


class TestExtras:
    async def test_passing_named_extra_parameters(self, manager: DependencyManager):
        def handler(event_name: str, channel_id: int) -> str:
            return f"{event_name}:{channel_id}"

        result = await manager.execute(handler, event_name="MESSAGE_CREATE", channel_id=12345)
        assert result == "MESSAGE_CREATE:12345"

    async def test_extras_override_container_dependency_of_same_name(self, manager: DependencyManager):
        def get_name() -> str:
            return "from_container"

        manager.add_dependency(get_name)

        def handler(name: str) -> str:
            return name

        assert await manager.execute(handler) == "from_container"
        assert await manager.execute(handler, name="from_extras") == "from_extras"

    async def test_extras_do_not_override_explicit_annotated_inject(self, manager: DependencyManager):
        def fixed_dep() -> str:
            return "fixed"

        def handler(val: Annotated[str, inject(fixed_dep)]) -> str:
            return val

        result = await manager.execute(handler, val="ignored_extra")
        assert result == "fixed"


class TestPositionalExtras:
    async def test_positional_extra_injected_by_type(self, manager: DependencyManager):
        class Event:
            def __init__(self, name: str) -> None:
                self.name = name

        def handler(ev: Event) -> str:
            return ev.name

        result = await manager.execute(handler, Event("message_create"))
        assert result == "message_create"

    async def test_positional_extra_subclass_matching(self, manager: DependencyManager):
        def error_handler(err: Exception) -> str:
            return f"handled: {err}"

        result = await manager.execute(error_handler, ValueError("invalid value"))
        assert result == "handled: invalid value"

    async def test_named_extra_priority_over_positional(self, manager: DependencyManager):
        def handler(err: Exception) -> str:
            return str(err)

        pos_err = ValueError("positional")
        named_err = TypeError("named")

        result = await manager.execute(handler, pos_err, err=named_err)
        assert result == "named"

    async def test_unrequested_positional_extras_are_ignored(self, manager: DependencyManager):
        def handler(count: int = 10) -> int:
            return count

        result = await manager.execute(handler, ValueError("ignored"), "another_ignored")
        assert result == 10

    async def test_positional_extra_propagated_to_sub_dependencies(self, manager: DependencyManager):
        class Context:
            def __init__(self, user_id: int) -> None:
                self.user_id = user_id

        def get_user_id(ctx: Context) -> int:
            return ctx.user_id

        manager.add_dependency(get_user_id)

        def handler(user_id: int) -> str:
            return f"user:{user_id}"

        result = await manager.execute(handler, Context(42))
        assert result == "user:42"


class TestDefaultsAndOptionals:
    async def test_parameter_with_default_uses_default_when_unregistered(self, manager: DependencyManager):
        def handler(count: int = 100) -> int:
            return count

        assert await manager.execute(handler) == 100

    async def test_parameter_with_default_uses_container_when_registered(self, manager: DependencyManager):
        def get_count() -> int:
            return 999

        manager.add_dependency(get_count)

        def handler(count: int = 100) -> int:
            return count

        assert await manager.execute(handler) == 999

    async def test_optional_union_resolves_to_none_when_unregistered(self, manager: DependencyManager):
        def handler(
            p1: int | None,
            p2: Annotated[str | None, "meta"],
            p3: None | float,
        ) -> tuple[object, object, object]:
            return (p1, p2, p3)

        assert await manager.execute(handler) == (None, None, None)

    async def test_optional_union_resolves_to_value_when_registered(self, manager: DependencyManager):
        def get_int() -> int:
            return 77

        manager.add_dependency(get_int)

        def handler(val: int | None, annotated_val: Annotated[int | None, "meta"]) -> tuple[int | None, int | None]:
            return (val, annotated_val)

        assert await manager.execute(handler) == (77, 77)

    async def test_union_resolves_to_available_type(self, manager: DependencyManager):
        def get_str() -> str:
            return "hello"

        manager.add_dependency(get_str)

        def handler(val: int | str) -> int | str:
            return val

        assert await manager.execute(handler) == "hello"


class TestOverridesAndRemoval:
    async def test_add_and_remove_override_for_injected_dependency(self, manager: DependencyManager):
        def real_service() -> str:
            return "production"

        def mock_service() -> str:
            return "testing_mock"

        def handler(svc: Annotated[str, inject(real_service)]) -> str:
            return svc

        manager.add_override(real_service, mock_service)
        assert await manager.execute(handler) == "testing_mock"

        manager.remove_override(real_service)
        assert await manager.execute(handler) == "production"

    async def test_add_override_for_container_dependency(self, manager: DependencyManager):
        def real_dep() -> str:
            return "real_val"

        def mock_dep() -> str:
            return "mock_val"

        manager.add_dependency(real_dep)
        manager.add_override(real_dep, mock_dep)

        def handler(val: str) -> str:
            return val

        assert await manager.execute(handler) == "mock_val"

    async def test_remove_dependency_prevents_future_resolution(self, manager: DependencyManager):
        def get_token() -> str:
            return "secret"

        def handler(token: str) -> str:
            return token

        manager.add_dependency(get_token)
        assert await manager.execute(handler) == "secret"

        manager.remove_dependency(str)
        with pytest.raises(DependencyNotFoundError):
            await manager.execute(handler)


class TestResolverErrors:
    async def test_unresolvable_dependency_raises_error(self, manager: DependencyManager):
        def handler(missing: int) -> None:
            pass

        with pytest.raises(DependencyNotFoundError) as exc_info:
            await manager.execute(handler)

        assert exc_info.value.parameter.name == "missing"

    async def test_nested_unresolvable_dependency_builds_error_path(self, manager: DependencyManager):
        def broken_leaf(missing_port: int) -> str:
            return str(missing_port)

        def mid_service(conn: Annotated[str, inject(broken_leaf)]) -> str:
            return conn

        def endpoint(svc: Annotated[str, inject(mid_service)]) -> str:
            return svc

        with pytest.raises(DependencyNotFoundError) as exc_info:
            await manager.execute(endpoint)

        err = exc_info.value
        assert err.callback is broken_leaf
        assert err.parameter.name == "missing_port"
        assert [step.callback for step in err.path] == [mid_service, endpoint]

    async def test_unannotated_parameter_raises_error(self, manager: DependencyManager):
        def handler(unannotated) -> None:
            pass

        with pytest.raises(MissingAnnotationError) as exc_info:
            await manager.execute(handler)

        assert exc_info.value.parameter.name == "unannotated"
