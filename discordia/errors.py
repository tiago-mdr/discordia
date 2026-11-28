"""Exception classes and error-path formatting utilities for Discordia."""

from __future__ import annotations

import inspect
import typing

import attrs

if typing.TYPE_CHECKING:
    from collections import abc

    import hikari


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class DiscordiaError(Exception):
    """Base exception class for all Discordia errors."""


@attrs.define(auto_exc=True, repr=False, slots=False)
class SignatureErrorPath:
    """Represents a node in a signature resolution error."""

    callback: abc.Callable[..., object]
    """The callable associated with this step in the path."""

    parameter: inspect.Parameter
    """The parameter where the error occurred."""


def format_error_path(
    path: list[SignatureErrorPath],
    callback: abc.Callable[..., object],
    parameter: inspect.Parameter | None = None,
) -> str:
    """Format a human-readable trace of nested dependency resolution paths.

    Args:
        path: A list of traversed signature paths in ascending resolution order.
        callback: The root or leaf callback where the failure occurred.
        parameter: Optional parameter causing the failure in the callback.

    Returns:
        A multiline formatted string visualizing the dependency call chain.
    """
    path_str = [f"-> {context.callback.__name__} ({context.parameter})" for context in reversed(path)]

    final = f"* {callback.__name__}"
    if parameter:
        final += f" ({parameter})"
    path_str.append(final)

    return "\n".join(path_str)


@attrs.define(auto_exc=True, repr=False, slots=False)
class SignatureError(DiscordiaError):
    """Base exception for errors encountered while inspecting or resolving function signatures."""

    path: list[SignatureErrorPath] = attrs.field(factory=list[SignatureErrorPath], init=False)
    """Trace of callbacks and parameters traversed prior to the error."""

    def add_path(self, callback: abc.Callable[..., object], parameter: inspect.Parameter) -> typing.Self:
        """Add a callback and parameter step to the error traceback path.

        Args:
            callback: The callable being resolved when the error propagated.
            parameter: The parameter currently being inspected.

        Returns:
            The current exception instance for method chaining.
        """
        self.path.append(SignatureErrorPath(callback, parameter))
        return self


@attrs.define(auto_exc=True, repr=False, slots=False)
class CircularSignatureError(SignatureError):
    """Raised when a circular reference is encountered while resolving type signatures."""

    callback: abc.Callable[..., object] = attrs.field()
    """The callable that triggered the circular dependency."""

    def __str__(self) -> str:
        path_str = format_error_path(self.path, self.callback)
        return (
            f'Callback "{self.callback.__name__}" appears twice in the same '
            "dependency chain, causing a circular dependency.\n\n"
            f"Path:\n{path_str}"
        )


@attrs.define(auto_exc=True, repr=False, slots=False)
class DependencyError(DiscordiaError):
    """Base exception for errors occurring during dependency injection resolution."""

    path: list[SignatureErrorPath] = attrs.field(factory=list[SignatureErrorPath], init=False)
    """Trace of callbacks and parameters traversed prior to the error."""

    def add_path(self, callback: abc.Callable[..., object], parameter: inspect.Parameter) -> typing.Self:
        """Add a callback and parameter step to the error traceback path.

        Args:
            callback: The callable being resolved when the error propagated.
            parameter: The parameter currently being inspected.

        Returns:
            The current exception instance for method chaining.
        """
        self.path.append(SignatureErrorPath(callback, parameter))
        return self


@attrs.define(auto_exc=True, repr=False, slots=False)
class DependencyNotFoundError(DependencyError):
    """Raised when a required dependency cannot be resolved for a callable parameter."""

    callback: abc.Callable[..., object] = attrs.field()
    """The callable requiring the dependency."""

    parameter: inspect.Parameter = attrs.field()
    """The parameter that could not be satisfied."""

    def __str__(self) -> str:
        path_str = format_error_path(self.path, self.callback, self.parameter)

        return (
            f'Could not resolve annotation "{self.parameter.annotation}" '
            f'for parameter "{self.parameter.name}" '
            f'in callback "{self.callback.__name__}".\n\n'
            "Register a default dependency for this type, pass this type as a "
            '"lazy type" during validation or use inject() to provide an explicit dependency.\n\n'
            f"Path:\n{path_str}"
        )


@attrs.define(auto_exc=True, repr=False, slots=False)
class MissingAnnotationError(DependencyError):
    """Raised when a parameter in a callable lacks a type annotation."""

    callback: abc.Callable[..., object] = attrs.field()
    """The callable containing the unannotated parameter."""

    parameter: inspect.Parameter = attrs.field()
    """The parameter missing an annotation."""

    def __str__(self) -> str:
        path_str = format_error_path(self.path, self.callback, self.parameter)

        return (
            f'Parameter "{self.parameter.name}" in callback '
            f'"{self.callback.__name__}" does not have a type annotation.\n\n'
            "Add a type annotation or provide a default value.\n\n"
            f"Path:\n{path_str}"
        )


@attrs.define(auto_exc=True, repr=False, slots=False)
class CircularDependencyError(DependencyError):
    """Raised when a circular dependency chain is detected between providers."""

    callback: abc.Callable[..., object] = attrs.field()
    """The callable that appears multiple times in the chain."""

    def __str__(self) -> str:
        path_str = format_error_path(self.path, self.callback)
        return (
            f'Callback "{self.callback.__name__}" appears twice in the same '
            "dependency chain, causing a circular dependency.\n\n"
            f"Path:\n{path_str}"
        )


@attrs.define(auto_exc=True, repr=False, slots=False)
class ScopeError(DependencyError):
    """Raised when a singleton provider depends on a scoped or transient dependency."""

    callback: abc.Callable[..., object] = attrs.field()
    """The singleton provider callback."""

    parameter: inspect.Parameter = attrs.field()
    """The parameter referencing an incompatible shorter-lived dependency."""

    def __str__(self) -> str:
        path_str = format_error_path(self.path, self.callback, self.parameter)

        return (
            f'Parameter "{self.parameter.name}" in callback '
            f'"{self.callback.__name__}" depends on a scoped or transient '
            "dependency from a singleton context. This can leak dependencies "
            "or cause runtime bugs.\n\n"
            "Consider reorganizing the lifetimes in this dependency chain.\n\n"
            f"Path:\n{path_str}"
        )


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class ModularizationError(DiscordiaError):
    """Base exception for errors related to module composition."""


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class ModuleMergeError(ModularizationError):
    """Raised when merging a submodule into a target module fails."""


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class ModuleUnmergeError(ModularizationError):
    """Raised when detaching or unmerging a submodule fails."""


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class InteractionNotFoundError(DiscordiaError):
    """Raised when an incoming Discord interaction does not match any registered handlers."""


@attrs.define(auto_exc=True, repr=False, slots=False)
class CommandInteractionRoutingError(DiscordiaError):
    """Raised when an error occurs during the routing or execution of a command interaction."""

    interaction_event: hikari.CommandInteractionCreateEvent = attrs.field()
    """The Hikari event for the command interaction."""


@attrs.define(auto_exc=True, repr=False, slots=False)
class AutoCompleteRoutinError(DiscordiaError):
    """Raised when an error occurs while routing an autocomplete interaction."""

    autocomplete_event: hikari.AutocompleteInteractionCreateEvent = attrs.field()
    """The Hikari event for the autocomplete interaction."""


@attrs.define(auto_exc=True, repr=False, slots=False)
class ComponentInteractionRoutingError(DiscordiaError):
    """Raised when an error occurs while routing a message component interaction."""

    interaction_event: hikari.ComponentInteractionCreateEvent = attrs.field()
    """The Hikari event for the component interaction."""


@attrs.define(auto_exc=True, repr=False, slots=False)
class ModalRoutingError(DiscordiaError):
    """Raised when an error occurs while routing a modal submission interaction."""

    interaction_event: hikari.ModalInteractionCreateEvent = attrs.field()
    """The Hikari event for the modal interaction."""


@attrs.define(auto_exc=True, repr=False, slots=False)
class SlashCommandDefinitionError(DiscordiaError):
    """Raised when a slash command handler signature or parameter definition is invalid."""

    reason: str = attrs.field()
    """Description of the validation error."""

    func: abc.Callable[..., object] = attrs.field()
    """The slash command callback function."""

    parameter: inspect.Parameter = attrs.field()
    """The parameter that failed validation."""

    def __attrs_post_init__(self) -> None:
        context = f"function: {self.func.__name__}\nparameter: {self.parameter}\nlocation: {inspect.getfile(self.func)}"
        self.reason += "\n\n" + context
