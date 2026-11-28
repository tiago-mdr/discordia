import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from typing import Annotated

import pytest

from discordia.di import (
    Dependency,
    DependencyContainer,
    DependencyManager,
    ParameterContext,
    _Scope,
    inject,
)


class TestInjectFunction:
    def test_valid_scopes(self):
        def sample() -> str:
            return "ok"

        assert inject(sample, "transient").scope is _Scope.TRANSIENT
        assert inject(sample, "scoped").scope is _Scope.SCOPED
        assert inject(sample, "singleton").scope is _Scope.SINGLETON

    def test_default_scope_is_scoped(self):
        def sample() -> str:
            return "ok"

        dep = inject(sample)
        assert dep.scope is _Scope.SCOPED

    def test_invalid_scope_raises_value_error(self):
        def sample() -> None:
            pass

        with pytest.raises(ValueError, match="scope must be a singleton, scoped or transient"):
            inject(sample, "invalid_scope")


class TestDependencyCreation:
    def test_rejects_abstract_class(self):
        class AbstractService(ABC):
            @abstractmethod
            def run(self) -> None:
                pass

        with pytest.raises(ValueError, match="Abstract classes cannot be used"):
            inject(AbstractService)

    def test_rejects_callables_without_return_annotation(self):
        def sync_no_ret():
            pass

        async def async_no_ret():
            pass

        def gen_no_ret():
            yield 1

        async def async_gen_no_ret():
            yield 1

        class CallableNoRet:
            def __call__(self):
                return 1

        for target in (sync_no_ret, async_no_ret, gen_no_ret, async_gen_no_ret, CallableNoRet()):
            with pytest.raises(ValueError, match="return type annotation"):
                inject(target)

    def test_dependency_from_sync_and_async_functions(self):
        def sample_func(a: int) -> str:
            return str(a)

        async def async_sample_func() -> int:
            return 42

        dep_sync = inject(sample_func)
        assert isinstance(dep_sync, Dependency)
        assert dep_sync.return_type is str
        assert dep_sync.callback is sample_func
        assert "a" in dep_sync.signature.parameters

        dep_async = inject(async_sample_func)
        assert dep_async.return_type is int
        assert dep_async.callback is async_sample_func

    def test_dependency_from_generator_and_iterator_annotations(self):
        def gen_func() -> Generator[int]:
            yield 1

        async def async_gen_func() -> AsyncGenerator[str]:
            yield "data"

        def iter_func() -> Iterator[float]:
            yield 1.5

        async def async_iter_func() -> AsyncIterator[bytes]:
            yield b"ok"

        def unparameterized_gen() -> Generator:
            yield "any"

        assert inject(gen_func).return_type is int
        assert inject(async_gen_func).return_type is str
        assert inject(iter_func).return_type is float
        assert inject(async_iter_func).return_type is bytes
        assert inject(unparameterized_gen).return_type is object

    def test_dependency_from_class(self):
        class Service:
            def __init__(self, port: int = 8080) -> None:
                self.port = port

        dep = inject(Service)
        assert dep.return_type is Service
        assert dep.callback is Service
        assert "port" in dep.signature.parameters

    def test_dependency_from_callable_instance(self):
        class Invoker:
            def __call__(self) -> bool:
                return True

        invoker = Invoker()
        dep = inject(invoker)
        assert dep.return_type is bool
        assert dep.callback is invoker

    def test_dependency_from_non_callable_instance(self):
        raw_config = {"db_host": "localhost"}
        dep = inject(raw_config)

        assert dep.return_type is dict
        assert callable(dep.callback)
        assert dep.callback() == raw_config

    def test_return_type_normalizes_none_to_nonetype(self):
        def returns_none() -> None:
            pass

        def yields_none() -> Generator[None]:
            yield None

        dep_fn = inject(returns_none)
        assert dep_fn.return_type is type(None)

        dep_gen = inject(yields_none)
        assert dep_gen.return_type is type(None)

    def test_dependency_repr(self):
        def my_service() -> str:
            return "service"

        assert repr(inject(my_service, "singleton")) == 'Dependency(my_service, "SINGLETON")'

        dep_obj = inject(123, "scoped")
        assert repr(dep_obj).startswith("Dependency(")
        assert repr(dep_obj).endswith(', "SCOPED")')


class TestDependencyContainerAndManagerRegistration:
    def test_add_and_remove_dependency_on_container(self):
        container = DependencyContainer()

        def get_port() -> int:
            return 8000

        container.add_dependency(get_port)
        assert int in container.standard_dependencies
        assert container.standard_dependencies[int].scope is _Scope.SCOPED

        removed = container.remove_dependency(int)
        assert removed.callback is get_port
        assert int not in container.standard_dependencies

    def test_duplicate_dependency_registration_raises_value_error(self):
        manager = DependencyManager()

        def first_str() -> str:
            return "a"

        def second_str() -> str:
            return "b"

        manager.add_dependency(first_str)
        with pytest.raises(ValueError, match="Dependency already registered for type"):
            manager.add_dependency(second_str)

    def test_remove_unregistered_dependency_raises_key_error(self):
        manager = DependencyManager()
        with pytest.raises(KeyError):
            manager.remove_dependency(int)

    def test_add_and_remove_override(self):
        manager = DependencyManager()

        def real_fn() -> str:
            return "real"

        def mock_fn() -> str:
            return "mock"

        manager.add_override(real_fn, mock_fn, "singleton")
        removed = manager.remove_override(real_fn)
        assert removed.callback is mock_fn
        assert removed.scope is _Scope.SINGLETON

    def test_duplicate_override_raises_value_error(self):
        manager = DependencyManager()

        def real_fn() -> str:
            return "real"

        def mock_fn() -> str:
            return "mock"

        manager.add_override(real_fn, mock_fn)
        with pytest.raises(ValueError, match="Override already registered for callable"):
            manager.add_override(real_fn, mock_fn)

    def test_remove_unregistered_override_raises_key_error(self):
        manager = DependencyManager()

        def real_fn() -> str:
            return "real"

        with pytest.raises(KeyError):
            manager.remove_override(real_fn)


class TestParameterContext:
    @staticmethod
    def _param_from(fn, name: str = "x") -> ParameterContext:
        return ParameterContext(inspect.signature(fn).parameters[name])

    def test_has_annotation_and_has_default(self):
        def fn(untyped, required: int, defaulted: int = 5):
            pass

        assert self._param_from(fn, "untyped").has_annotation is False
        assert self._param_from(fn, "untyped").has_default is False

        assert self._param_from(fn, "required").has_annotation is True
        assert self._param_from(fn, "required").has_default is False
        assert self._param_from(fn, "required").is_optional is False

        assert self._param_from(fn, "defaulted").has_annotation is True
        assert self._param_from(fn, "defaulted").has_default is True
        assert self._param_from(fn, "defaulted").is_optional is True

    def test_is_optional_variants(self):
        def fn(
            a: int | None,
            b: Annotated[str | None, "meta"],
            c: None,
            d: int | str,
        ):
            pass

        assert self._param_from(fn, "a").is_optional is True
        assert self._param_from(fn, "b").is_optional is True
        assert self._param_from(fn, "c").is_optional is True
        assert self._param_from(fn, "d").is_optional is False
