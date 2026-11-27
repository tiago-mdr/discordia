import inspect

import pytest

from discordia.errors import (
    CircularDependencyError,
    CircularSignatureError,
    DependencyError,
    DependencyNotFoundError,
    DiscordiaError,
    MissingAnnotationError,
    ScopeError,
    SignatureError,
    SignatureErrorPath,
    format_error_path,
)


def sample_callback(sample_param: int) -> None:
    pass


def caller_callback(caller_param: str) -> None:
    pass


def root_callback(root_param: bool) -> None:
    pass


class TestErrorHierarchy:
    @pytest.mark.parametrize(
        ("exc_cls", "parent_cls"),
        [
            (SignatureError, DiscordiaError),
            (CircularSignatureError, SignatureError),
            (DependencyError, DiscordiaError),
            (DependencyNotFoundError, DependencyError),
            (MissingAnnotationError, DependencyError),
            (CircularDependencyError, DependencyError),
            (ScopeError, DependencyError),
        ],
    )
    def test_exception_inheritance(self, exc_cls: type[Exception], parent_cls: type[Exception]):
        assert issubclass(exc_cls, parent_cls)
        assert issubclass(exc_cls, Exception)


class TestErrorPathFormatting:
    def test_signature_error_path_stores_callback_and_parameter(self):
        param = inspect.signature(sample_callback).parameters["sample_param"]
        entry = SignatureErrorPath(callback=sample_callback, parameter=param)

        assert entry.callback is sample_callback
        assert entry.parameter is param

    def test_format_error_path_without_chain(self):
        assert format_error_path([], sample_callback) == "* sample_callback"

        param = inspect.signature(sample_callback).parameters["sample_param"]
        assert format_error_path([], sample_callback, param) == "* sample_callback (sample_param: int)"

    def test_format_error_path_reverses_call_stack_entries(self):
        p_sample = inspect.signature(sample_callback).parameters["sample_param"]
        p_caller = inspect.signature(caller_callback).parameters["caller_param"]
        p_root = inspect.signature(root_callback).parameters["root_param"]

        # Added from innermost caller outward during stack unwinding
        path = [
            SignatureErrorPath(caller_callback, p_caller),
            SignatureErrorPath(root_callback, p_root),
        ]

        formatted = format_error_path(path, sample_callback, p_sample)
        assert formatted.splitlines() == [
            "-> root_callback (root_param: bool)",
            "-> caller_callback (caller_param: str)",
            "* sample_callback (sample_param: int)",
        ]

    def test_dependency_and_signature_error_add_path_chaining(self):
        p_sample = inspect.signature(sample_callback).parameters["sample_param"]
        p_caller = inspect.signature(caller_callback).parameters["caller_param"]

        dep_err = DependencyError()
        assert dep_err.path == []
        returned_dep = dep_err.add_path(caller_callback, p_caller).add_path(sample_callback, p_sample)
        assert returned_dep is dep_err
        assert [entry.callback for entry in dep_err.path] == [caller_callback, sample_callback]

        sig_err = SignatureError()
        assert sig_err.path == []
        returned_sig = sig_err.add_path(caller_callback, p_caller)
        assert returned_sig is sig_err
        assert len(sig_err.path) == 1


class TestErrorMessages:
    def test_dependency_not_found_error_message_and_chain(self):
        p_sample = inspect.signature(sample_callback).parameters["sample_param"]
        p_caller = inspect.signature(caller_callback).parameters["caller_param"]

        error = DependencyNotFoundError(sample_callback, p_sample)
        error.add_path(caller_callback, p_caller)
        msg = str(error)

        assert "Could not resolve annotation \"<class 'int'>\"" in msg
        assert 'for parameter "sample_param"' in msg
        assert 'in callback "sample_callback"' in msg
        assert "Register a default dependency" in msg
        assert "-> caller_callback (caller_param: str)" in msg
        assert "* sample_callback (sample_param: int)" in msg

    def test_missing_annotation_error_message(self):
        def unannotated(x):
            pass

        param = inspect.signature(unannotated).parameters["x"]
        error = MissingAnnotationError(unannotated, param)
        msg = str(error)

        assert '"x" in callback "unannotated" does not have a type annotation.' in msg
        assert "Add a type annotation or provide a default value." in msg
        assert "Path:\n* unannotated (x)" in msg

    def test_circular_dependency_error_message(self):
        def cycle_fn():
            pass

        p_caller = inspect.signature(caller_callback).parameters["caller_param"]
        error = CircularDependencyError(cycle_fn)
        error.add_path(caller_callback, p_caller)
        msg = str(error)

        assert error.callback is cycle_fn
        assert 'Callback "cycle_fn" appears twice in the same dependency chain' in msg
        assert "-> caller_callback (caller_param: str)" in msg
        assert "* cycle_fn" in msg

    def test_circular_signature_error_message(self):
        def cycle_sig_fn():
            pass

        p_caller = inspect.signature(caller_callback).parameters["caller_param"]
        error = CircularSignatureError(cycle_sig_fn)
        error.add_path(caller_callback, p_caller)
        msg = str(error)

        assert error.callback is cycle_sig_fn
        assert 'Callback "cycle_sig_fn" appears twice in the same dependency chain' in msg
        assert "-> caller_callback (caller_param: str)" in msg
        assert "* cycle_sig_fn" in msg

    def test_scope_error_message(self):
        param = inspect.signature(sample_callback).parameters["sample_param"]
        error = ScopeError(sample_callback, param)
        msg = str(error)

        assert '"sample_param" in callback "sample_callback"' in msg
        assert "depends on a scoped or transient dependency from a singleton context" in msg
        assert "Path:\n* sample_callback (sample_param: int)" in msg
