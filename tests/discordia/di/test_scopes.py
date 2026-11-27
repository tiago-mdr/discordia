from typing import Annotated

import pytest

from discordia.di import DependencyManager, inject


@pytest.fixture
def manager() -> DependencyManager:
    return DependencyManager()


class TestDefaultScopeBehavior:
    async def test_default_inject_scope_is_scoped_at_runtime(self, manager: DependencyManager):
        class Context:
            pass

        def consumer(
            c1: Annotated[Context, inject(Context)],
            c2: Annotated[Context, inject(Context)],
        ) -> tuple[Context, Context]:
            return (c1, c2)

        first_c1, first_c2 = await manager.execute(consumer)
        second_c1, _ = await manager.execute(consumer)

        assert first_c1 is first_c2
        assert first_c1 is not second_c1

    async def test_default_add_dependency_scope_is_scoped_at_runtime(self, manager: DependencyManager):
        class RequestState:
            pass

        manager.add_dependency(RequestState)

        def consumer(s1: RequestState, s2: RequestState) -> tuple[RequestState, RequestState]:
            return (s1, s2)

        r1_a, r1_b = await manager.execute(consumer)
        r2_a, _ = await manager.execute(consumer)

        assert r1_a is r1_b
        assert r1_a is not r2_a


class TestTransientLifetime:
    async def test_transient_creates_new_instance_per_injection(self, manager: DependencyManager):
        class Service:
            pass

        def consumer(
            s1: Annotated[Service, inject(Service, "transient")],
            s2: Annotated[Service, inject(Service, "transient")],
        ) -> tuple[Service, Service]:
            return (s1, s2)

        s1, s2 = await manager.execute(consumer)
        assert s1 is not s2
        assert isinstance(s1, Service)
        assert isinstance(s2, Service)

    async def test_transient_creates_new_instance_across_executions(self, manager: DependencyManager):
        class Service:
            pass

        manager.add_dependency(Service, "transient")

        def consumer(s: Service) -> Service:
            return s

        res1 = await manager.execute(consumer)
        res2 = await manager.execute(consumer)
        assert res1 is not res2

    async def test_transient_in_diamond_graph(self, manager: DependencyManager):
        class Leaf:
            pass

        class BranchA:
            def __init__(self, leaf: Annotated[Leaf, inject(Leaf, "transient")]) -> None:
                self.leaf = leaf

        class BranchB:
            def __init__(self, leaf: Annotated[Leaf, inject(Leaf, "transient")]) -> None:
                self.leaf = leaf

        class Root:
            def __init__(
                self,
                a: Annotated[BranchA, inject(BranchA)],
                b: Annotated[BranchB, inject(BranchB)],
            ) -> None:
                self.a = a
                self.b = b

        root = await manager.execute(Root)
        assert root.a.leaf is not root.b.leaf


class TestScopedLifetime:
    async def test_scoped_shares_instance_within_same_execution(self, manager: DependencyManager):
        class Session:
            pass

        def consumer(
            s1: Annotated[Session, inject(Session, "scoped")],
            s2: Annotated[Session, inject(Session, "scoped")],
        ) -> tuple[Session, Session]:
            return (s1, s2)

        s1, s2 = await manager.execute(consumer)
        assert s1 is s2

    async def test_scoped_creates_new_instance_across_executions(self, manager: DependencyManager):
        class Session:
            pass

        manager.add_dependency(Session, "scoped")

        def consumer(s: Session) -> Session:
            return s

        res1 = await manager.execute(consumer)
        res2 = await manager.execute(consumer)
        assert res1 is not res2

    async def test_scoped_in_diamond_dependency_graph(self, manager: DependencyManager):
        class RequestContext:
            pass

        class ServiceA:
            def __init__(self, ctx: Annotated[RequestContext, inject(RequestContext, "scoped")]) -> None:
                self.ctx = ctx

        class ServiceB:
            def __init__(self, ctx: Annotated[RequestContext, inject(RequestContext, "scoped")]) -> None:
                self.ctx = ctx

        class Endpoint:
            def __init__(
                self,
                a: Annotated[ServiceA, inject(ServiceA)],
                b: Annotated[ServiceB, inject(ServiceB)],
            ) -> None:
                self.a = a
                self.b = b

        endpoint1 = await manager.execute(Endpoint)
        assert endpoint1.a.ctx is endpoint1.b.ctx

        endpoint2 = await manager.execute(Endpoint)
        assert endpoint2.a.ctx is endpoint2.b.ctx
        assert endpoint1.a.ctx is not endpoint2.a.ctx


class TestSingletonLifetime:
    async def test_singleton_shares_instance_within_same_execution(self, manager: DependencyManager):
        class DatabasePool:
            pass

        def consumer(
            p1: Annotated[DatabasePool, inject(DatabasePool, "singleton")],
            p2: Annotated[DatabasePool, inject(DatabasePool, "singleton")],
        ) -> tuple[DatabasePool, DatabasePool]:
            return (p1, p2)

        p1, p2 = await manager.execute(consumer)
        assert p1 is p2

    async def test_singleton_shares_instance_across_executions(self, manager: DependencyManager):
        class DatabasePool:
            pass

        manager.add_dependency(DatabasePool, "singleton")

        def consumer(pool: DatabasePool) -> DatabasePool:
            return pool

        res1 = await manager.execute(consumer)
        res2 = await manager.execute(consumer)
        assert res1 is res2

    async def test_singleton_function_executed_only_once(self, manager: DependencyManager):
        call_count = 0

        def create_connection() -> str:
            nonlocal call_count
            call_count += 1
            return f"conn_{call_count}"

        manager.add_dependency(create_connection, "singleton")

        def consumer(c: str) -> str:
            return c

        assert await manager.execute(consumer) == "conn_1"
        assert await manager.execute(consumer) == "conn_1"
        assert await manager.execute(consumer) == "conn_1"
        assert call_count == 1


class TestMixedLifetimeGraphs:
    async def test_transient_depending_on_scoped(self, manager: DependencyManager):
        class RequestId:
            pass

        class TransientLogger:
            def __init__(self, req: Annotated[RequestId, inject(RequestId, "scoped")]) -> None:
                self.req = req

        def handler(
            log1: Annotated[TransientLogger, inject(TransientLogger, "transient")],
            log2: Annotated[TransientLogger, inject(TransientLogger, "transient")],
        ) -> tuple[TransientLogger, TransientLogger]:
            return (log1, log2)

        l1, l2 = await manager.execute(handler)
        assert l1 is not l2
        assert l1.req is l2.req

    async def test_scoped_depending_on_singleton(self, manager: DependencyManager):
        class GlobalCache:
            pass

        class ScopedSession:
            def __init__(self, cache: Annotated[GlobalCache, inject(GlobalCache, "singleton")]) -> None:
                self.cache = cache

        def handler(
            sess: Annotated[ScopedSession, inject(ScopedSession, "scoped")],
        ) -> ScopedSession:
            return sess

        s1 = await manager.execute(handler)
        s2 = await manager.execute(handler)

        assert s1 is not s2
        assert s1.cache is s2.cache
