from __future__ import annotations

import inspect
import sys
import types
import typing

from discordia import errors

if typing.TYPE_CHECKING:
    from collections import abc


def is_annotated(annotation: object) -> bool:
    return typing.get_origin(annotation) is typing.Annotated


def is_union(annotation: object) -> bool:
    origin = typing.get_origin(annotation)
    return origin is typing.Union or origin is types.UnionType


def is_equals(source: object, target: object) -> bool:
    if source == target or target is typing.Any or target is object:
        return True

    if source in (None, type(None)) and target in (None, type(None)):
        return True

    if is_union(target):
        if is_union(source):
            args_source = typing.get_args(source)
            args_target = typing.get_args(target)

            return all(any(is_equals(arg1, arg2) for arg2 in args_target) for arg1 in args_source)

        if any(is_equals(source, branch) for branch in typing.get_args(target)):
            return True

    if inspect.isclass(source):
        origin = typing.get_origin(target) or target
        if inspect.isclass(origin):
            try:
                return issubclass(source, origin)
            except TypeError:
                return False

    return False


def find_for_type[T](callback: abc.Callable[..., object], target: type[T]) -> type[T] | None:
    signature = SignatureManager.get_signature(callback)
    for param in signature.parameters.values():
        if is_equals(param.annotation, target):
            return param.annotation

    return None


def _get_callable_globals(fn: abc.Callable[..., object]) -> dict[str, typing.Any]:
    unwrapped = inspect.unwrap(fn)

    if isinstance(unwrapped, type):
        init = getattr(unwrapped, "__init__", None)
        if init is not None and hasattr(init, "__globals__"):
            return init.__globals__

        new = getattr(unwrapped, "__new__", None)
        if new is not None and new is not object.__new__ and hasattr(new, "__globals__"):
            return new.__globals__

        mod = sys.modules.get(unwrapped.__module__, None)
        return vars(mod) if mod is not None else {}

    if hasattr(unwrapped, "__globals__"):
        return unwrapped.__globals__

    return {}


class SecureResolver:
    _call_stack: list[abc.Callable[..., typing.Any]] = []  # noqa: RUF012

    def __init__(self, call: abc.Callable[..., typing.Any]) -> None:
        self._call = call
        self._current_parameter: inspect.Parameter | None = None

    def resolve(self) -> inspect.Signature:
        if self._call in self._call_stack:
            raise errors.CircularSignatureError(self._call)

        self._call_stack.append(self._call)
        try:
            return self._build_signature()
        finally:
            self._call_stack.pop()

    def _resolve_annotation_string(
        self,
        annotation_str: str,
        globalns: dict[str, typing.Any],
        localns: dict[str, typing.Any] | None = None,
    ) -> object:
        try:
            return eval(annotation_str, globalns, localns)  # noqa: S307
        except errors.CircularSignatureError as error:
            if self._current_parameter is not None:
                error.add_path(self._call, self._current_parameter)
            raise
        except NameError:
            return annotation_str

    def _resolve_annotation(
        self,
        annotation: object,
        globalns: dict[str, typing.Any],
        localns: dict[str, typing.Any],
    ) -> object:
        if annotation is inspect.Parameter.empty:
            return annotation

        if isinstance(annotation, str):
            return self._resolve_annotation_string(annotation, globalns, localns)

        return annotation

    def _build_signature(self) -> inspect.Signature:
        raw_sig = inspect.signature(self._call)

        globalns = _get_callable_globals(self._call)
        localns: dict[str, typing.Any] = {}
        if isinstance(self._call, type):
            localns[self._call.__name__] = self._call

        new_params: list[inspect.Parameter] = []
        for param in raw_sig.parameters.values():
            self._current_parameter = param
            annotation = self._resolve_annotation(param.annotation, globalns, localns)
            new_params.append(param.replace(annotation=annotation))

        self._current_parameter = None
        return_annotation = self._resolve_annotation(raw_sig.return_annotation, globalns, localns)

        return raw_sig.replace(parameters=new_params, return_annotation=return_annotation)


class SignatureManager:
    _cache: dict[abc.Callable[..., object], inspect.Signature] = {}  # noqa: RUF012

    @classmethod
    def get_signature(cls, callback: abc.Callable[..., object], *, cache: bool = True) -> inspect.Signature:
        cached_signature = cls._cache.get(callback)
        if cached_signature is not None:
            return cached_signature

        signature = SecureResolver(callback).resolve()

        if cache:
            cls._cache[callback] = signature
        return signature

    @classmethod
    def discard_cache(cls, callback: abc.Callable[..., object]) -> None:
        if cls._cache.get(callback):
            del cls._cache[callback]

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache.clear()
