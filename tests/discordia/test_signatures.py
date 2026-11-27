from __future__ import annotations

import functools
import inspect
from typing import Annotated, Any, Protocol, Union, get_args, runtime_checkable

import pytest

from discordia.errors import CircularSignatureError, SignatureErrorPath
from discordia.signatures import (
    SecureResolver,
    SignatureManager,
    find_for_type,
    is_annotated,
    is_equals,
    is_union,
)


@pytest.fixture(autouse=True)
def clean_signature_state():
    # Ensure global cache and resolver call stack do not leak across tests
    yield
    SignatureManager.clear_cache()


# Shared helpers #


def simple_fn(x: int, y: str) -> bool:
    return bool(x and y)


class BaseEvent:
    pass


class MessageEvent(BaseEvent):
    pass


class SubMessageEvent(MessageEvent):
    pass


class UnrelatedModel:
    pass


@runtime_checkable
class CheckableGreeter(Protocol):
    def greet(self) -> str: ...


class NonCheckableGreeter(Protocol):
    def greet(self) -> str: ...


class Greeter:
    def greet(self) -> str:
        return "hi"


class SelfReferencingNode:
    def __init__(self, child: SelfReferencingNode | None = None) -> None:
        self.child = child


def _trigger_resolve(target: Any) -> Any:
    SecureResolver(target).resolve()
    return target


def mutual_cycle_a(b: Annotated[int, _trigger_resolve(mutual_cycle_b)]) -> None:
    pass


def mutual_cycle_b(a: Annotated[int, _trigger_resolve(mutual_cycle_a)]) -> None:
    pass


# Tests #


class TestIsAnnotated:
    @pytest.mark.parametrize(
        "annotation",
        [
            Annotated[int, "meta"],
            Annotated[str, 1, 2, 3],
            Annotated[int | None, "nullable"],
            Annotated[Annotated[int, "inner"], "outer"],
        ],
    )
    def test_returns_true_for_annotated_types(self, annotation: object):
        assert is_annotated(annotation) is True

    @pytest.mark.parametrize(
        "annotation",
        [
            int,
            str,
            None,
            type(None),
            int | str,
            list[int],
            "int",
            Any,
            inspect.Parameter.empty,
        ],
    )
    def test_returns_false_for_non_annotated_types(self, annotation: object):
        assert is_annotated(annotation) is False


class TestIsUnion:
    @pytest.mark.parametrize(
        "annotation",
        [
            int | str,
            int | None,
            int | str | float,
            Union[int, str],
            Union[int, None],
        ],
    )
    def test_returns_true_for_union_types(self, annotation: object):
        assert is_union(annotation) is True

    @pytest.mark.parametrize(
        "annotation",
        [
            int,
            None,
            type(None),
            Annotated[int | str, "meta"],
            list[int | str],
            Any,
            "int | str",
            inspect.Parameter.empty,
        ],
    )
    def test_returns_false_for_non_union_types(self, annotation: object):
        assert is_union(annotation) is False


class TestIsEquals:
    def test_identical_types_match(self):
        assert is_equals(int, int) is True
        assert is_equals(str, str) is True

    def test_unrelated_types_do_not_match(self):
        assert is_equals(int, str) is False
        assert is_equals(MessageEvent, UnrelatedModel) is False

    @pytest.mark.parametrize("source", [int, str, None, list[int], MessageEvent])
    def test_any_or_object_as_target_matches_everything(self, source: object):
        assert is_equals(source, Any) is True
        assert is_equals(source, object) is True

    def test_any_or_object_as_source_does_not_match_specific_target(self):
        assert is_equals(Any, int) is False
        assert is_equals(object, int) is False

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            (None, None),
            (type(None), type(None)),
            (None, type(None)),
            (type(None), None),
        ],
    )
    def test_none_and_nonetype_are_interchangeable(self, source: object, target: object):
        assert is_equals(source, target) is True

    def test_none_does_not_match_concrete_type(self):
        assert is_equals(None, int) is False
        assert is_equals(int, None) is False

    def test_single_type_matches_union_target_containing_compatible_branch(self):
        assert is_equals(int, int | str) is True
        assert is_equals(bool, int | str) is True
        assert is_equals(None, int | None) is True
        assert is_equals(SubMessageEvent, UnrelatedModel | BaseEvent) is True

    def test_single_type_does_not_match_disjoint_union_target(self):
        assert is_equals(float, int | str) is False

    def test_union_source_matches_superset_union_target(self):
        assert is_equals(int | str, int | str | float) is True
        assert is_equals(MessageEvent | SubMessageEvent, BaseEvent | str) is True

    def test_union_source_does_not_match_partial_union_target(self):
        assert is_equals(int | float, int | str) is False

    def test_union_source_does_not_match_single_target(self):
        assert is_equals(int | str, int) is False

    def test_subclass_matches_superclass_but_not_vice_versa(self):
        assert is_equals(MessageEvent, BaseEvent) is True
        assert is_equals(SubMessageEvent, BaseEvent) is True
        assert is_equals(BaseEvent, MessageEvent) is False
        assert is_equals(bool, int) is True

    def test_parameterized_generics_comparison(self):
        assert is_equals(list[int], list[int]) is True
        assert is_equals(list[int], list[str]) is False
        assert is_equals(list, list[int]) is True

    def test_runtime_checkable_protocol_matches_structural_implementation(self):
        assert is_equals(Greeter, CheckableGreeter) is True

    def test_non_runtime_checkable_protocol_returns_false_safely(self):
        assert is_equals(Greeter, NonCheckableGreeter) is False

    def test_empty_annotation_returns_false(self):
        assert is_equals(inspect.Parameter.empty, int) is False


class TestSecureResolver:
    def test_resolves_sync_function_annotations(self):
        sig = SecureResolver(simple_fn).resolve()
        assert sig.parameters["x"].annotation is int
        assert sig.parameters["y"].annotation is str
        assert sig.return_annotation is bool

    def test_resolves_async_and_generator_functions(self):
        async def async_fn(count: int) -> str:
            return str(count)

        sig = SecureResolver(async_fn).resolve()
        assert sig.parameters["count"].annotation is int
        assert sig.return_annotation is str

    def test_resolves_zero_parameter_function(self):
        def empty_fn() -> None:
            pass

        sig = SecureResolver(empty_fn).resolve()
        assert len(sig.parameters) == 0
        assert sig.return_annotation is None

    def test_resolves_class_init_signature(self):
        class Service:
            def __init__(self, host: str, port: int = 8080) -> None:
                self.host = host
                self.port = port

        sig = SecureResolver(Service).resolve()
        assert list(sig.parameters) == ["host", "port"]
        assert sig.parameters["host"].annotation is str
        assert sig.parameters["port"].annotation is int
        assert sig.parameters["port"].default == 8080

    def test_resolves_class_with_custom_new_and_no_init(self):
        class CustomNewOnly:
            def __new__(cls, token: str) -> CustomNewOnly:
                return super().__new__(cls)

        sig = SecureResolver(CustomNewOnly).resolve()
        assert sig.parameters["token"].annotation is str

    def test_resolves_class_without_custom_init_or_new(self):
        class PlainEmptyClass:
            pass

        sig = SecureResolver(PlainEmptyClass).resolve()
        assert len(sig.parameters) == 0

    def test_resolves_self_referential_class_annotation(self):
        sig = SecureResolver(SelfReferencingNode).resolve()
        annotation = sig.parameters["child"].annotation
        assert is_union(annotation)
        assert SelfReferencingNode in get_args(annotation)

    def test_resolves_wrapped_decorated_function(self):
        def decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                return fn(*args, **kwargs)

            return wrapper

        @decorator
        def target(event: MessageEvent) -> int:
            return 1

        sig = SecureResolver(target).resolve()
        assert sig.parameters["event"].annotation is MessageEvent
        assert sig.return_annotation is int

    def test_preserves_parameter_kinds_and_defaults(self):
        def complex_fn(
            pos_only: int,
            /,
            standard: str = "abc",
            *args: float,
            kw_only: bool = True,
            **kwargs: bytes,
        ) -> None:
            pass

        sig = SecureResolver(complex_fn).resolve()
        params = sig.parameters

        assert params["pos_only"].kind is inspect.Parameter.POSITIONAL_ONLY
        assert params["pos_only"].annotation is int
        assert params["standard"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
        assert params["standard"].default == "abc"
        assert params["args"].kind is inspect.Parameter.VAR_POSITIONAL
        assert params["args"].annotation is float
        assert params["kw_only"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["kw_only"].default is True
        assert params["kwargs"].kind is inspect.Parameter.VAR_KEYWORD
        assert params["kwargs"].annotation is bytes

    def test_preserves_empty_annotations_when_unannotated(self):
        def unannotated(a, b=10):
            return a, b

        sig = SecureResolver(unannotated).resolve()
        assert sig.parameters["a"].annotation is inspect.Parameter.empty
        assert sig.parameters["b"].annotation is inspect.Parameter.empty
        assert sig.return_annotation is inspect.Signature.empty

    def test_keeps_string_annotation_when_name_cannot_be_resolved(self):
        def forward_ref_fn(missing: UnknownForwardType) -> AnotherUnknownType:
            pass

        sig = SecureResolver(forward_ref_fn).resolve()
        assert sig.parameters["missing"].annotation == "UnknownForwardType"
        assert sig.return_annotation == "AnotherUnknownType"

    def test_detects_real_circular_signature_and_tracks_path(self):
        with pytest.raises(CircularSignatureError) as exc_info:
            SecureResolver(mutual_cycle_a).resolve()

        err = exc_info.value
        assert err.callback is mutual_cycle_a
        assert len(err.path) == 2
        assert isinstance(err.path[0], SignatureErrorPath)
        assert err.path[0].callback is mutual_cycle_b
        assert err.path[0].parameter.name == "a"
        assert err.path[1].callback is mutual_cycle_a
        assert err.path[1].parameter.name == "b"
        assert SecureResolver._call_stack == []


class TestSignatureManager:
    def test_get_signature_caches(self):
        sig1 = SignatureManager.get_signature(simple_fn)
        sig2 = SignatureManager.get_signature(simple_fn)

        assert sig1 is sig2
        assert simple_fn in SignatureManager._cache

    def test_get_signature_with_cache_false_does_not_store(self):
        sig = SignatureManager.get_signature(simple_fn, cache=False)

        assert sig.parameters["x"].annotation is int
        assert simple_fn not in SignatureManager._cache

    def test_get_signature_returns_already_cached_entry_even_when_cache_false(self):
        cached = SignatureManager.get_signature(simple_fn, cache=True)
        fetched = SignatureManager.get_signature(simple_fn, cache=False)

        assert fetched is cached

    def test_discard_cache_removes_only_target_callable(self):
        def other_fn(a: int) -> int:
            return a

        SignatureManager.get_signature(simple_fn, cache=True)
        SignatureManager.get_signature(other_fn, cache=True)

        SignatureManager.discard_cache(simple_fn)

        assert simple_fn not in SignatureManager._cache
        assert other_fn in SignatureManager._cache

    def test_discard_cache_is_safe_when_callable_not_cached(self):
        SignatureManager.discard_cache(simple_fn)
        assert simple_fn not in SignatureManager._cache

    def test_clear_cache_removes_all_entries(self):
        def other_fn(a: int) -> int:
            return a

        SignatureManager.get_signature(simple_fn, cache=True)
        SignatureManager.get_signature(other_fn, cache=True)
        assert len(SignatureManager._cache) == 2

        SignatureManager.clear_cache()
        assert len(SignatureManager._cache) == 0


class TestFindForType:
    def test_finds_exact_type_match(self):
        def handler(count: int, label: str) -> None:
            pass

        assert find_for_type(handler, str) is str
        assert find_for_type(handler, int) is int

    def test_finds_subclass_matching_base_target(self):
        def on_message(ctx: str, event: SubMessageEvent) -> None:
            pass

        result = find_for_type(on_message, BaseEvent)
        assert result is SubMessageEvent

    def test_returns_first_matching_annotation_when_multiple_match(self):
        def multi_event_handler(first: MessageEvent, second: SubMessageEvent) -> None:
            pass

        assert find_for_type(multi_event_handler, BaseEvent) is MessageEvent

    def test_returns_none_when_no_parameter_matches(self):
        def handler(a: int, b: str) -> None:
            pass

        assert find_for_type(handler, BaseEvent) is None

        def empty() -> None:
            pass

        assert find_for_type(empty, int) is None

    def test_ignores_unannotated_parameters_and_finds_later_match(self):
        def mixed_handler(untyped, err: ValueError) -> None:
            pass

        assert find_for_type(mixed_handler, Exception) is ValueError

    def test_works_with_class_constructors(self):
        class Consumer:
            def __init__(self, event: MessageEvent) -> None:
                self.event = event

        assert find_for_type(Consumer, BaseEvent) is MessageEvent
