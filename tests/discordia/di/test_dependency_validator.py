from typing import Annotated, Protocol, runtime_checkable

import pytest

from discordia.di import DependencyManager, inject
from discordia.errors import DependencyNotFoundError, MissingAnnotationError, ScopeError


@pytest.fixture
def manager() -> DependencyManager:
    return DependencyManager()


class TestValidatorBasicFunctions:
    def test_function_without_parameters(self, manager: DependencyManager):
        def sync_fn():
            pass

        async def async_fn():
            pass

        manager.validate(sync_fn)
        manager.validate(async_fn)

    def test_function_with_optional_union_parameters(self, manager: DependencyManager):
        def fn(
            p1: int | None,
            p2: str | None,
            p3: None | float,
        ):
            pass

        manager.validate(fn)

    def test_function_with_literal_none_annotation(self, manager: DependencyManager):
        def fn(p: None):
            pass

        manager.validate(fn)

    def test_function_with_default_values(self, manager: DependencyManager):
        def fn(p1: int = 10, p2: float | None = 12.5, p3: str = "default"):
            pass

        manager.validate(fn)

    def test_annotated_varargs_and_kwargs_pass_validation(self, manager: DependencyManager):
        def fn(*args: int, **kwargs: str):
            pass

        manager.validate(fn)

    def test_unannotated_varargs_raises_missing_annotation_error(self, manager: DependencyManager):
        def fn_args(*args):
            pass

        def fn_kwargs(**kwargs):
            pass

        with pytest.raises(MissingAnnotationError) as exc_args:
            manager.validate(fn_args)
        assert exc_args.value.parameter.name == "args"

        with pytest.raises(MissingAnnotationError) as exc_kwargs:
            manager.validate(fn_kwargs)
        assert exc_kwargs.value.parameter.name == "kwargs"

    def test_unknown_parameter_type_raises_error(self, manager: DependencyManager):
        def fn(p1: int):
            pass

        with pytest.raises(DependencyNotFoundError) as exc_info:
            manager.validate(fn)

        assert exc_info.value.parameter.name == "p1"
        assert exc_info.value.callback is fn

    def test_missing_annotation_raises_error(self, manager: DependencyManager):
        def unannotated(x):
            pass

        with pytest.raises(MissingAnnotationError) as exc_info:
            manager.validate(unannotated)

        assert exc_info.value.parameter.name == "x"
        assert exc_info.value.callback is unannotated

    def test_missing_annotation_with_default_value_still_raises_error(self, manager: DependencyManager):
        def unannotated_with_default(x=42):
            pass

        with pytest.raises(MissingAnnotationError) as exc_info:
            manager.validate(unannotated_with_default)

        assert exc_info.value.parameter.name == "x"

    def test_union_passes_when_at_least_one_branch_is_registered(self, manager: DependencyManager):
        def get_str() -> str:
            return "available"

        manager.add_dependency(get_str)

        def fn(value: int | str):
            pass

        manager.validate(fn)

    def test_union_raises_when_no_branch_is_registered(self, manager: DependencyManager):
        def fn(value: int | str):
            pass

        with pytest.raises(DependencyNotFoundError) as exc_info:
            manager.validate(fn)
        assert exc_info.value.parameter.name == "value"

    def test_remove_dependency_causes_subsequent_validation_to_fail(self, manager: DependencyManager):
        def get_int() -> int:
            return 1

        def fn(value: int):
            pass

        manager.add_dependency(get_int)
        manager.validate(fn)

        manager.remove_dependency(int)
        with pytest.raises(DependencyNotFoundError):
            manager.validate(fn)


class TestValidatorLazyDependencies:
    def test_lazy_parameter_type_primitives(self, manager: DependencyManager):
        def fn(p1: str, p2: int, p3: float):
            pass

        manager.validate(fn, lazy_types={str, int, float})

    def test_lazy_parameter_type_with_class_hierarchy(self, manager: DependencyManager):
        class BaseEvent:
            pass

        class MessageCreateEvent(BaseEvent):
            pass

        class UnrelatedEvent:
            pass

        def handle_event(e: MessageCreateEvent):
            pass

        def handle_unrelated(e: UnrelatedEvent):
            pass

        manager.validate(handle_event, lazy_types={BaseEvent})

        with pytest.raises(DependencyNotFoundError):
            manager.validate(handle_unrelated, lazy_types={BaseEvent})

    def test_event_and_error_handlers_isolated_lazy_types(self, manager: DependencyManager):
        class Event:
            pass

        class CustomEvent(Event):
            pass

        class CustomError(Exception):
            pass

        def on_event(event: CustomEvent):
            pass

        def on_error(error: CustomError):
            pass

        manager.validate(on_event, lazy_types={Event})
        with pytest.raises(DependencyNotFoundError):
            manager.validate(on_error, lazy_types={Event})

        manager.validate(on_error, lazy_types={Exception})
        with pytest.raises(DependencyNotFoundError):
            manager.validate(on_event, lazy_types={Exception})

    def test_union_with_lazy_type_branch_passes(self, manager: DependencyManager):
        class Event:
            pass

        def fn(target: int | Event):
            pass

        manager.validate(fn, lazy_types={Event})


class TestValidatorAnnotatedDependencies:
    def test_annotated_only_metadata(self, manager: DependencyManager):
        def fn(
            p1: Annotated[Annotated[str | None, "nested_meta"], "outer_meta"],
            p2: Annotated[int, "description"] = 10,
        ):
            pass

        manager.validate(fn)

    def test_valid_injected_dependency(self, manager: DependencyManager):
        def dependency(p1: int | None, p2: str = "") -> int:
            return 10

        def function_with_dependency(
            p1: Annotated[int, "metadata", inject(dependency), "other_metadata"],
        ):
            pass

        manager.validate(function_with_dependency)

    def test_injected_dependency_with_unknown_sub_dependency_tracks_error_path(self, manager: DependencyManager):
        def failing_sub_dependency(unregistered: int) -> str:
            return "data"

        def target_fn(p1: Annotated[str, inject(failing_sub_dependency)]):
            pass

        with pytest.raises(DependencyNotFoundError) as exc_info:
            manager.validate(target_fn)

        err = exc_info.value
        assert err.callback is failing_sub_dependency
        assert err.parameter.name == "unregistered"
        assert len(err.path) == 1
        assert err.path[0].callback is target_fn
        assert err.path[0].parameter.name == "p1"

    def test_injected_dependency_with_wrong_return_type(self, manager: DependencyManager):
        def dependency() -> int:
            return 1

        def function_expecting_str(p1: Annotated[str, inject(dependency)]):
            pass

        with pytest.raises(DependencyNotFoundError):
            manager.validate(function_expecting_str)

    def test_injected_dependency_with_union_return_type(self, manager: DependencyManager):
        def dependency() -> int:
            return 1

        def function_with_union(
            p1: Annotated[str | int, inject(dependency)],
        ):
            pass

        manager.validate(function_with_union)

    def test_injected_subclass_satisfies_base_class_annotation(self, manager: DependencyManager):
        class Animal:
            pass

        class Dog(Animal):
            pass

        def get_dog() -> Dog:
            return Dog()

        def feed(a: Annotated[Animal, inject(get_dog)]):
            pass

        manager.validate(feed)

    def test_injected_runtime_checkable_protocol_satisfies_protocol_annotation(self, manager: DependencyManager):
        @runtime_checkable
        class Greeter(Protocol):
            def greet(self) -> str: ...

        class DiscordUser:
            def greet(self) -> str:
                return "hello"

        def get_user() -> DiscordUser:
            return DiscordUser()

        def handle(g: Annotated[Greeter, inject(get_user)]):
            pass

        manager.validate(handle)

    def test_injected_non_runtime_checkable_protocol_is_rejected(self, manager: DependencyManager):
        class StaticOnlyGreeter(Protocol):
            def greet(self) -> str: ...

        class DiscordUser:
            def greet(self) -> str:
                return "hello"

        def get_user() -> DiscordUser:
            return DiscordUser()

        def handle(g: Annotated[StaticOnlyGreeter, inject(get_user)]):
            pass

        with pytest.raises(DependencyNotFoundError):
            manager.validate(handle)


class TestValidatorScopeRules:
    def test_singleton_cannot_depend_on_scoped(self, manager: DependencyManager):
        def scoped_dep() -> str:
            return "scoped"

        def singleton_dep(
            s: Annotated[str, inject(scoped_dep, "scoped")],
        ) -> bool:
            return True

        def test_target(val: Annotated[bool, inject(singleton_dep, "singleton")]):
            pass

        with pytest.raises(ScopeError) as exc_info:
            manager.validate(test_target)

        assert exc_info.value.callback is singleton_dep
        assert exc_info.value.parameter.name == "s"
        assert exc_info.value.path[0].callback is test_target

    def test_singleton_cannot_depend_on_transient(self, manager: DependencyManager):
        def transient_dep() -> int:
            return 42

        def singleton_dep(
            t: Annotated[int, inject(transient_dep, "transient")],
        ) -> str:
            return "singleton"

        def test_target(val: Annotated[str, inject(singleton_dep, "singleton")]):
            pass

        with pytest.raises(ScopeError) as exc_info:
            manager.validate(test_target)

        assert exc_info.value.callback is singleton_dep
        assert exc_info.value.parameter.name == "t"

    def test_scoped_can_depend_on_transient_and_singleton(self, manager: DependencyManager):
        def transient_dep() -> int:
            return 1

        def singleton_dep() -> str:
            return "global"

        def scoped_dep(
            t: Annotated[int, inject(transient_dep, "transient")],
            s: Annotated[str, inject(singleton_dep, "singleton")],
        ) -> bool:
            return True

        def test_target(val: Annotated[bool, inject(scoped_dep, "scoped")]):
            pass

        manager.validate(test_target)

    def test_transient_can_depend_on_all_scopes(self, manager: DependencyManager):
        def singleton_dep() -> str:
            return "s"

        def scoped_dep() -> int:
            return 1

        def transient_dep(
            s: Annotated[str, inject(singleton_dep, "singleton")],
            sc: Annotated[int, inject(scoped_dep, "scoped")],
        ) -> float:
            return 1.0

        def test_target(val: Annotated[float, inject(transient_dep, "transient")]):
            pass

        manager.validate(test_target)

    def test_singleton_sibling_does_not_contaminate_scoped_sibling(self, manager: DependencyManager):
        """A function with a singleton param and a scoped param should NOT raise ScopeError
        when neither has sub-dependencies that violate scope rules.
        Previously, the first param's singleton scope contaminated the second param's check.
        """

        def singleton_dep() -> str:
            return "global"

        def scoped_dep() -> int:
            return 1

        def test_target(
            s: Annotated[str, inject(singleton_dep, "singleton")],
            sc: Annotated[int, inject(scoped_dep, "scoped")],
        ):
            pass

        manager.validate(test_target)

    def test_transitive_violation_through_non_singleton_intermediary(self, manager: DependencyManager):
        """scoped -> singleton -> transient must raise ScopeError.
        Previously, passing the parent's scope instead of the dependency's scope to the child
        validator prevented detection of violations through non-singleton intermediaries.
        """

        def transient_leaf() -> int:
            return 42

        def singleton_mid(
            t: Annotated[int, inject(transient_leaf, "transient")],
        ) -> str:
            return "mid"

        def scoped_root(
            m: Annotated[str, inject(singleton_mid, "singleton")],
        ) -> bool:
            return True

        def test_target(val: Annotated[bool, inject(scoped_root, "scoped")]):
            pass

        with pytest.raises(ScopeError) as exc_info:
            manager.validate(test_target)

        err = exc_info.value
        assert err.callback is singleton_mid
        assert err.parameter.name == "t"

    def test_transitive_scope_violation_tracks_full_path(self, manager: DependencyManager):
        def inner_transient() -> int:
            return 1

        def mid_singleton(
            i: Annotated[int, inject(inner_transient, "transient")],
        ) -> str:
            return "mid"

        def outer_singleton(
            m: Annotated[str, inject(mid_singleton, "singleton")],
        ) -> bool:
            return True

        def test_target(val: Annotated[bool, inject(outer_singleton, "singleton")]):
            pass

        with pytest.raises(ScopeError) as exc_info:
            manager.validate(test_target)

        err = exc_info.value
        assert err.callback is mid_singleton
        assert [step.callback for step in err.path] == [outer_singleton, test_target]


class TestValidatorCallStackDepth:
    def test_deep_dependency_chain_validation(self, manager: DependencyManager):
        def d1() -> int:
            return 1

        def d2(a: Annotated[int, inject(d1)]) -> float:
            return float(a)

        def d3(b: Annotated[float, inject(d2)]) -> str:
            return str(b)

        def d4(c: Annotated[str, inject(d3)]) -> bool:
            return bool(c)

        def d5(d: Annotated[bool, inject(d4)]) -> list[bool]:
            return [d]

        manager.validate(d5)
