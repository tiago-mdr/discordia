from __future__ import annotations

import functools
from typing import Annotated

import pytest

from discordia.di import DependencyManager, inject
from discordia.errors import CircularSignatureError, SignatureErrorPath
from discordia.signatures import SecureResolver, SignatureManager


@pytest.fixture(autouse=True)
def reset_signature_cache():
    SignatureManager.clear_cache()
    SecureResolver._call_stack.clear()
    yield
    SignatureManager.clear_cache()
    SecureResolver._call_stack.clear()


class ForwardService:
    def __init__(self, name: str = "svc") -> None:
        self.name = name


def consumer_with_forward_inject(
    svc: Annotated[ForwardService, inject(ForwardService)],
) -> str:
    return svc.name


def cycle_fn_a(b: Annotated[int, inject(cycle_fn_b)]) -> int:
    return b


def cycle_fn_b(a: Annotated[int, inject(cycle_fn_a)]) -> int:
    return a


class TestDISecureResolverIntegration:
    async def test_resolves_and_executes_forward_referenced_inject(self):
        manager = DependencyManager()
        manager.validate(consumer_with_forward_inject)
        result = await manager.execute(consumer_with_forward_inject)
        assert result == "svc"

    async def test_resolves_decorated_target_with_injected_dependencies(self):
        def trace_decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                return f"traced:{fn(*args, **kwargs)}"

            return wrapper

        @trace_decorator
        def endpoint(svc: Annotated[ForwardService, inject(ForwardService)]) -> str:
            return svc.name

        manager = DependencyManager()
        manager.validate(endpoint)
        assert await manager.execute(endpoint) == "traced:svc"

    def test_circular_inject_tracks_signature_error_path(self):
        with pytest.raises(CircularSignatureError) as exc_info:
            SignatureManager.get_signature(cycle_fn_a)

        error = exc_info.value
        assert error.callback is cycle_fn_a
        assert len(error.path) == 2

        assert isinstance(error.path[0], SignatureErrorPath)
        assert error.path[0].callback is cycle_fn_b
        assert error.path[0].parameter.name == "a"

        assert isinstance(error.path[1], SignatureErrorPath)
        assert error.path[1].callback is cycle_fn_a
        assert error.path[1].parameter.name == "b"

        error_msg = str(error)
        assert "cycle_fn_a" in error_msg
        assert "cycle_fn_b" in error_msg
        assert "Path:" in error_msg
