"""Utilities for inspecting and resolving function and callable signatures."""

from __future__ import annotations

import inspect
import sys
import types
import typing

from discordia import errors

if typing.TYPE_CHECKING:
    from collections import abc


def is_annotated(annotation: object) -> bool:
    """Check whether an annotation is an Annotated type.

    Args:
        annotation: The annotation to inspect.

    Returns:
        True if the annotation is an Annotated type, False otherwise.
    """
    return typing.get_origin(annotation) is typing.Annotated


def is_union(annotation: object) -> bool:
    """Check whether an annotation is a Union type.

    Args:
        annotation: The annotation to inspect.

    Returns:
        True if the annotation is a Union or UnionType, False otherwise.
    """
    origin = typing.get_origin(annotation)
    return origin is typing.Union or origin is types.UnionType


def is_equals(source: object, target: object) -> bool:
    """Check whether the source type matches or is compatible with the target type.

    Args:
        source: The source type or annotation to check.
        target: The target type or annotation to match against.

    Returns:
        True if source equals target, is a subclass, or satisfies its type union.
    """
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


def find_for_type[T](func: abc.Callable[..., object], target: type[T]) -> type[T] | None:
    """Look for a parameter whose type satisfies the target in a function signature.

    Args:
        func: The callable whose signature will be inspected.
        target: The target type to search for.

    Returns:
        The matching parameter annotation if found, or None otherwise.
    """
    signature = SignatureManager.get_signature(func)
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
    """An object that safely resolves function signatures without falling into recursion cycles."""

    _func_stack: list[abc.Callable[..., typing.Any]] = []  # noqa: RUF012

    def __init__(self, func: abc.Callable[..., typing.Any]) -> None:
        """Initialize the resolver.

        Args:
            func: The callable whose signature will be resolved.
        """
        self._func = func
        self._current_parameter: inspect.Parameter | None = None

    def resolve(self) -> inspect.Signature:
        """Resolve and build the signature of the wrapped callable.

        Returns:
            The resolved function signature.

        Raises:
            CircularSignatureError: If a cycle was found in the function signature.
        """
        if self._func in self._func_stack:
            raise errors.CircularSignatureError(self._func)

        self._func_stack.append(self._func)
        try:
            return self._build_signature()
        finally:
            self._func_stack.pop()

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
                error.add_path(self._func, self._current_parameter)
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
        raw_sig = inspect.signature(self._func)

        globalns = _get_callable_globals(self._func)
        localns: dict[str, typing.Any] = {}
        if isinstance(self._func, type):
            localns[self._func.__name__] = self._func

        new_params: list[inspect.Parameter] = []
        for param in raw_sig.parameters.values():
            self._current_parameter = param
            annotation = self._resolve_annotation(param.annotation, globalns, localns)
            new_params.append(param.replace(annotation=annotation))

        self._current_parameter = None
        return_annotation = self._resolve_annotation(raw_sig.return_annotation, globalns, localns)

        return raw_sig.replace(parameters=new_params, return_annotation=return_annotation)


class SignatureManager:
    """Safely resolves function signatures and manages their cache."""

    _cache: dict[abc.Callable[..., object], inspect.Signature] = {}  # noqa: RUF012

    @classmethod
    def get_signature(cls, func: abc.Callable[..., object], *, cache: bool = True) -> inspect.Signature:
        """Get the function signature.

        Args:
            func: The callable to inspect.
            cache: Whether to cache the function signature. Defaults to True.

        Returns:
            The resolved function signature.

        Raises:
            CircularSignatureError: If a cycle was found in the function signature.
        """
        cached_signature = cls._cache.get(func)
        if cached_signature is not None:
            return cached_signature

        signature = SecureResolver(func).resolve()

        if cache:
            cls._cache[func] = signature
        return signature

    @classmethod
    def discard_cache(cls, func: abc.Callable[..., object]) -> None:
        """Discard the cached signature for a specific callable.

        Args:
            func: The callable whose cached signature should be discarded.
        """
        if cls._cache.get(func):
            del cls._cache[func]

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached signatures."""
        cls._cache.clear()
