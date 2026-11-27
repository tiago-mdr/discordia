from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from typing import Annotated

import pytest

from discordia.di import DependencyManager, inject
from discordia.errors import DependencyNotFoundError


@pytest.fixture
def manager() -> DependencyManager:
    return DependencyManager()


class TestSyncGeneratorDependencies:
    async def test_sync_generator_yields_value_and_cleans_up(self, manager: DependencyManager):
        events: list[str] = []

        def db_session() -> Generator[str]:
            events.append("open_session")
            try:
                yield "session_active"
            finally:
                events.append("close_session")

        def consumer(
            session: Annotated[str, inject(db_session)],
        ) -> str:
            events.append(f"consume_{session}")
            return session

        result = await manager.execute(consumer)

        assert result == "session_active"
        assert events == ["open_session", "consume_session_active", "close_session"]

    async def test_sync_generator_cleans_up_on_consumer_exception(self, manager: DependencyManager):
        events: list[str] = []

        def resource() -> Generator[str]:
            events.append("acquire")
            try:
                yield "res"
            finally:
                events.append("release")

        def failing_consumer(
            r: Annotated[str, inject(resource)],
        ) -> None:
            events.append("fail")
            raise RuntimeError("something went wrong")

        with pytest.raises(RuntimeError, match="something went wrong"):
            await manager.execute(failing_consumer)

        assert events == ["acquire", "fail", "release"]

    async def test_multiple_generators_cleaned_up_in_lifo_order(self, manager: DependencyManager):
        cleanup_order: list[str] = []

        def gen_first() -> Generator[int]:
            try:
                yield 1
            finally:
                cleanup_order.append("first_closed")

        def gen_second(
            f: Annotated[int, inject(gen_first)],
        ) -> Generator[int]:
            try:
                yield f + 1
            finally:
                cleanup_order.append("second_closed")

        def consumer(
            s: Annotated[int, inject(gen_second)],
        ) -> int:
            return s

        res = await manager.execute(consumer)
        assert res == 2
        assert cleanup_order == ["second_closed", "first_closed"]

    async def test_iterator_typed_generator_yields_and_closes(self, manager: DependencyManager):
        closed = False

        def iter_dep() -> Iterator[int]:
            nonlocal closed
            try:
                yield 123
            finally:
                closed = True

        def consumer(val: Annotated[int, inject(iter_dep)]) -> int:
            return val

        manager.validate(consumer)
        assert await manager.execute(consumer) == 123
        assert closed is True


class TestAsyncGeneratorDependencies:
    async def test_async_generator_yields_value_and_cleans_up(self, manager: DependencyManager):
        events: list[str] = []

        async def async_resource() -> AsyncGenerator[str]:
            events.append("async_acquire")
            try:
                yield "async_conn"
            finally:
                events.append("async_release")

        async def consumer(
            conn: Annotated[str, inject(async_resource)],
        ) -> str:
            events.append(f"use_{conn}")
            return conn

        result = await manager.execute(consumer)

        assert result == "async_conn"
        assert events == ["async_acquire", "use_async_conn", "async_release"]

    async def test_async_generator_cleans_up_on_consumer_exception(self, manager: DependencyManager):
        events: list[str] = []

        async def async_resource() -> AsyncGenerator[str]:
            events.append("acquire")
            try:
                yield "conn"
            finally:
                events.append("release")

        async def failing_consumer(
            conn: Annotated[str, inject(async_resource)],
        ) -> None:
            events.append("failing")
            raise ValueError("async consumer error")

        with pytest.raises(ValueError, match="async consumer error"):
            await manager.execute(failing_consumer)

        assert events == ["acquire", "failing", "release"]

    async def test_combined_sync_and_async_generators_lifo_cleanup(self, manager: DependencyManager):
        cleanup_order: list[str] = []

        def sync_gen() -> Generator[str]:
            try:
                yield "sync"
            finally:
                cleanup_order.append("sync_closed")

        async def async_gen() -> AsyncGenerator[str]:
            try:
                yield "async"
            finally:
                cleanup_order.append("async_closed")

        def consumer(
            s: Annotated[str, inject(sync_gen)],
            a: Annotated[str, inject(async_gen)],
        ) -> tuple[str, str]:
            return (s, a)

        result = await manager.execute(consumer)
        assert result == ("sync", "async")
        assert cleanup_order == ["async_closed", "sync_closed"]

    async def test_async_iterator_typed_generator_yields_and_closes(self, manager: DependencyManager):
        closed = False

        async def async_iter_dep() -> AsyncIterator[str]:
            nonlocal closed
            try:
                yield "stream"
            finally:
                closed = True

        async def consumer(val: Annotated[str, inject(async_iter_dep)]) -> str:
            return val

        manager.validate(consumer)
        assert await manager.execute(consumer) == "stream"
        assert closed is True


class TestGeneratorLifetimesAndCleanup:
    async def test_transient_generator_runs_and_closes_each_time(self, manager: DependencyManager):
        open_count = 0
        close_count = 0

        def transient_gen() -> Generator[int]:
            nonlocal open_count, close_count
            open_count += 1
            try:
                yield open_count
            finally:
                close_count += 1

        def consumer(
            a: Annotated[int, inject(transient_gen, "transient")],
            b: Annotated[int, inject(transient_gen, "transient")],
        ) -> tuple[int, int]:
            return (a, b)

        res = await manager.execute(consumer)
        assert res == (1, 2)
        assert open_count == 2
        assert close_count == 2

    async def test_scoped_generator_shared_within_execution_closed_once(self, manager: DependencyManager):
        open_count = 0
        close_count = 0

        def scoped_gen() -> Generator[str]:
            nonlocal open_count, close_count
            open_count += 1
            try:
                yield f"session_{open_count}"
            finally:
                close_count += 1

        def consumer(
            s1: Annotated[str, inject(scoped_gen, "scoped")],
            s2: Annotated[str, inject(scoped_gen, "scoped")],
        ) -> tuple[str, str]:
            return (s1, s2)

        res1 = await manager.execute(consumer)
        assert res1 == ("session_1", "session_1")
        assert open_count == 1
        assert close_count == 1

        res2 = await manager.execute(consumer)
        assert res2 == ("session_2", "session_2")
        assert open_count == 2
        assert close_count == 2

    async def test_singleton_sync_and_async_generators_stay_open_until_manager_close(self, manager: DependencyManager):
        events: list[str] = []

        def singleton_sync_gen() -> Generator[str]:
            events.append("open_sync")
            try:
                yield "pool_sync"
            finally:
                events.append("close_sync")

        async def singleton_async_gen() -> AsyncGenerator[str]:
            events.append("open_async")
            try:
                yield "pool_async"
            finally:
                events.append("close_async")

        def handler(
            s: Annotated[str, inject(singleton_sync_gen, "singleton")],
            a: Annotated[str, inject(singleton_async_gen, "singleton")],
        ) -> tuple[str, str]:
            return (s, a)

        assert await manager.execute(handler) == ("pool_sync", "pool_async")
        assert await manager.execute(handler) == ("pool_sync", "pool_async")
        # Neither singleton generator should have closed after individual executions
        assert events == ["open_sync", "open_async"]

        await manager.close()
        assert events == ["open_sync", "open_async", "close_async", "close_sync"]

        # Calling close() again is idempotent
        await manager.close()
        assert events == ["open_sync", "open_async", "close_async", "close_sync"]

    async def test_resolution_granular_finish_transients_and_finish_scoped(self, manager: DependencyManager):
        events: list[str] = []

        def scoped_gen() -> Generator[str]:
            events.append("open_scoped")
            try:
                yield "sc"
            finally:
                events.append("close_scoped")

        def transient_gen() -> Generator[str]:
            events.append("open_transient")
            try:
                yield "tr"
            finally:
                events.append("close_transient")

        def target(
            s: Annotated[str, inject(scoped_gen, "scoped")],
            t: Annotated[str, inject(transient_gen, "transient")],
        ) -> tuple[str, str]:
            return (s, t)

        resolution = await manager.resolve(target)
        assert events == ["open_scoped", "open_transient"]

        await resolution.finish_transients()
        assert events == ["open_scoped", "open_transient", "close_transient"]

        await resolution.finish_scoped()
        assert events == ["open_scoped", "open_transient", "close_transient", "close_scoped"]

    async def test_transient_generator_closed_when_later_parameter_fails_resolution(self, manager: DependencyManager):
        closed = False

        def transient_gen() -> Generator[int]:
            nonlocal closed
            try:
                yield 10
            finally:
                closed = True

        def broken_target(
            ok_val: Annotated[int, inject(transient_gen, "transient")],
            missing_dep: str,
        ) -> None:
            pass

        with pytest.raises(DependencyNotFoundError):
            await manager.execute(broken_target)

        assert closed is True


class TestGeneratorValidationAndContainerRegistration:
    def test_generator_and_async_generator_dependency_validation(self, manager: DependencyManager):
        def get_number() -> Generator[int]:
            yield 42

        async def get_text() -> AsyncGenerator[str]:
            yield "hello"

        def consumer(
            n: Annotated[int, inject(get_number)],
            t: Annotated[str, inject(get_text)],
        ):
            pass

        manager.validate(consumer)

    async def test_container_registered_generator_resolution_by_yielded_type(self, manager: DependencyManager):
        class Session:
            def __init__(self, token: str) -> None:
                self.token = token

        closed = False

        def get_session() -> Generator[Session]:
            nonlocal closed
            try:
                yield Session("active_token")
            finally:
                closed = True

        manager.add_dependency(get_session)

        def handle_request(session: Session) -> str:
            return session.token

        manager.validate(handle_request)
        result = await manager.execute(handle_request)

        assert result == "active_token"
        assert closed is True
