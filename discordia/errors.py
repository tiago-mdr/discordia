import inspect
import typing
from collections import abc

import attrs
import hikari


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class DiscordiaError(Exception):
    pass


@attrs.define(auto_exc=True, repr=False, slots=False)
class SignatureErrorPath:
    callback: abc.Callable[..., object]
    parameter: inspect.Parameter


def format_error_path(
    path: list[SignatureErrorPath],
    callback: abc.Callable[..., object],
    parameter: inspect.Parameter | None = None,
) -> str:
    path_str = [f"-> {context.callback.__name__} ({context.parameter})" for context in reversed(path)]

    final = f"* {callback.__name__}"
    if parameter:
        final += f" ({parameter})"
    path_str.append(final)

    return "\n".join(path_str)


@attrs.define(auto_exc=True, repr=False, slots=False)
class SignatureError(DiscordiaError):
    path: list[SignatureErrorPath] = attrs.field(factory=list[SignatureErrorPath], init=False)

    def add_path(self, callback: abc.Callable[..., object], parameter: inspect.Parameter) -> typing.Self:
        self.path.append(SignatureErrorPath(callback, parameter))
        return self


@attrs.define(auto_exc=True, repr=False, slots=False)
class CircularSignatureError(SignatureError):
    callback: abc.Callable[..., object] = attrs.field()

    def __str__(self) -> str:
        path_str = format_error_path(self.path, self.callback)
        return (
            f'Callback "{self.callback.__name__}" appears twice in the same '
            "dependency chain, causing a circular dependency.\n\n"
            f"Path:\n{path_str}"
        )


@attrs.define(auto_exc=True, repr=False, slots=False)
class DependencyError(DiscordiaError):
    path: list[SignatureErrorPath] = attrs.field(factory=list[SignatureErrorPath], init=False)

    def add_path(self, callback: abc.Callable[..., object], parameter: inspect.Parameter) -> typing.Self:
        self.path.append(SignatureErrorPath(callback, parameter))
        return self


@attrs.define(auto_exc=True, repr=False, slots=False)
class DependencyNotFoundError(DependencyError):
    callback: abc.Callable[..., object] = attrs.field()
    parameter: inspect.Parameter = attrs.field()

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
    callback: abc.Callable[..., object] = attrs.field()
    parameter: inspect.Parameter = attrs.field()

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
    callback: abc.Callable[..., object] = attrs.field()

    def __str__(self) -> str:
        path_str = format_error_path(self.path, self.callback)
        return (
            f'Callback "{self.callback.__name__}" appears twice in the same '
            "dependency chain, causing a circular dependency.\n\n"
            f"Path:\n{path_str}"
        )


@attrs.define(auto_exc=True, repr=False, slots=False)
class ScopeError(DependencyError):
    callback: abc.Callable[..., object] = attrs.field()
    parameter: inspect.Parameter = attrs.field()

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
    pass


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class ModuleMergeError(ModularizationError):
    pass


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class ModuleUnmergeError(ModularizationError):
    pass


@attrs.define(auto_exc=True, repr=False, init=False, slots=False)
class InteractionNotFoundError(DiscordiaError):
    pass


@attrs.define(auto_exc=True, repr=False, slots=False)
class CommandInteractionRoutingError(DiscordiaError):
    interaction_event: hikari.CommandInteractionCreateEvent = attrs.field()


@attrs.define(auto_exc=True, repr=False, slots=False)
class AutoCompleteRoutinError(DiscordiaError):
    autocomplete_event: hikari.AutocompleteInteractionCreateEvent = attrs.field()


@attrs.define(auto_exc=True, repr=False, slots=False)
class ComponentInteractionRoutingError(DiscordiaError):
    interaction_event: hikari.ComponentInteractionCreateEvent = attrs.field()


@attrs.define(auto_exc=True, repr=False, slots=False)
class ModalRoutingError(DiscordiaError):
    interaction_event: hikari.ModalInteractionCreateEvent = attrs.field()


@attrs.define(auto_exc=True, repr=False, slots=False)
class SlashCommandDefinitionError(DiscordiaError):
    reason: str = attrs.field()
    func: abc.Callable[..., object] = attrs.field()
    parameter: inspect.Parameter = attrs.field()

    def __attrs_post_init__(self) -> None:
        context = f"function: {self.func.__name__}\nparameter: {self.parameter}\nlocation: {inspect.getfile(self.func)}"

        self.reason += "\n\n" + context
