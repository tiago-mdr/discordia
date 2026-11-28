"""Dependency injection container, lifetimes, validation, and resolution engine."""

from __future__ import annotations

import enum
import inspect
import typing
from collections import abc

import attrs

from discordia import errors, signatures


class _Scope(enum.IntEnum):
    SINGLETON = 1
    SCOPED = 2
    TRANSIENT = 3


type _ScopeAlias = typing.Literal["singleton", "scoped", "transient"]
type _GenericGenerator = abc.Generator[typing.Any, typing.Any, typing.Any] | abc.AsyncGenerator[typing.Any, typing.Any]


def _extract_provided_type(call: abc.Callable[..., object], annotation: object) -> type:
    """Extract the underlying provided type from a return annotation, unpacking generators."""
    origin = typing.get_origin(annotation)
    is_gen_type = origin in (
        abc.Generator,
        abc.AsyncGenerator,
        abc.Iterator,
        abc.AsyncIterator,
    )
    is_gen_fn = inspect.isgeneratorfunction(call) or inspect.isasyncgenfunction(call)

    if is_gen_type or is_gen_fn:
        args = typing.get_args(annotation)
        target = args[0] if args else object
    else:
        target = annotation

    if target is None:
        return type(None)

    return target  # type: ignore[return-value]


class Dependency:
    """Represents a dependency provider."""

    def __init__(self, dependency: object, scope: _Scope) -> None:
        """Initialize and inspect a dependencyprovider.

        Args:
            dependency: A class constructor, callable factory, or instance.
            scope: Lifecycle scope for this dependency.

        Raises:
            ValueError: If dependency is an abstract class or if a factory callable lacks
                a return type annotation.
        """
        if inspect.isabstract(dependency):
            msg = f"Abstract classes cannot be used as dependencies: {dependency}"
            raise ValueError(msg)

        self.call: abc.Callable[..., object]
        self.return_type: type
        self.scope = scope

        if inspect.isclass(dependency):
            self.call = dependency
            self.return_type = dependency
        elif callable(dependency):
            self.call = dependency
        else:
            self.call = lambda: dependency
            self.call.__annotations__["return"] = type(dependency)

        self.signature = signatures.SignatureManager.get_signature(self.call)
        if not inspect.isclass(dependency):
            if self.signature.return_annotation is inspect.Parameter.empty:
                msg = "Dependency callables must define a return type annotation"
                raise ValueError(msg)
            self.return_type = _extract_provided_type(self.call, self.signature.return_annotation)

    def __repr__(self) -> str:
        name = getattr(self.call, "__name__", repr(self.call))
        return f'Dependency({name}, "{self.scope.name}")'


def inject(dependency: object, scope: _ScopeAlias = "scoped") -> Dependency:
    """Mark and configure an explicit dependency with a designated lifetime scope.

    Args:
        dependency: The class constructor, factory callable, or instance to inject.
        scope: Lifecycle scope for the dependency.

    Returns:
        A Dependency instance configuring the provider and lifetime.
    """
    match scope:
        case "singleton":
            scope_enum = _Scope.SINGLETON
        case "scoped":
            scope_enum = _Scope.SCOPED
        case "transient":
            scope_enum = _Scope.TRANSIENT
        case _:
            msg = f"scope must be a singleton, scoped or transient, not {scope}"
            raise ValueError(msg)

    return Dependency(dependency, scope_enum)


class DependencyContainer:
    """Stores dependencies and dependency overrides."""

    def __init__(self) -> None:
        self.standard_dependencies: dict[type[object], Dependency] = {}
        self.overrides: dict[abc.Callable[..., object], Dependency] = {}

    def add_dependency(self, dependency: object, scope: _ScopeAlias = "scoped") -> None:
        """Register a default dependency mapped to its provided return type.

        Args:
            dependency: The class constructor, factory callable, or instance to register.
            scope: Lifecycle scope for the dependency.

        Raises:
            ValueError: If a dependency is already registered for this type.
        """
        dep = inject(dependency, scope)
        if dep.return_type in self.standard_dependencies:
            msg = f"Dependency already registered for type: {dep.return_type}"
            raise ValueError(msg)
        self.standard_dependencies[dep.return_type] = dep

    def remove_dependency(self, dependency_type: type[object]) -> Dependency:
        """Remove and return the registered dependency for a given type.

        Args:
            dependency_type: The type key whose dependency should be removed.

        Returns:
            The unregistered Dependency instance.

        Raises:
            KeyError: If no dependency is registered for the specified type.
        """
        return self.standard_dependencies.pop(dependency_type)

    def add_override(
        self,
        overridden: abc.Callable[..., typing.Any],
        override: abc.Callable[..., typing.Any],
        scope: _ScopeAlias = "scoped",
    ) -> None:
        """Register an override dependency that substitutes a specific callable.

        Args:
            overridden: The target callable to replace during resolution.
            override: The replacement callable providing the dependency value.
            scope: Lifetime scope for the override provider.

        Raises:
            ValueError: If an override is already registered for this callable.
        """
        if overridden in self.overrides:
            msg = f"Override already registered for callable: {overridden}"
            raise ValueError(msg)
        self.overrides[overridden] = inject(override, scope)

    def remove_override(self, overridden: abc.Callable[..., typing.Any]) -> Dependency:
        """Remove and return the registered override for a callable.

        Args:
            overridden: The target callable whose override should be removed.

        Returns:
            The unregistered Dependency override instance.

        Raises:
            KeyError: If no override is registered for the specified callable.
        """
        return self.overrides.pop(overridden)


class ParameterContext:
    """Tracks state and characteristics of a single parameter during dependency inspection."""

    def __init__(self, parameter: inspect.Parameter) -> None:
        """Initialize parameter tracking context.

        Args:
            parameter: The inspect.Parameter instance to wrap.
        """
        self.parameter = parameter
        self.parameter_type = parameter.annotation
        self.is_resolved = False

    @property
    def has_annotation(self) -> bool:
        """Whether the parameter defines an explicit type annotation."""
        return self.parameter.annotation is not inspect.Parameter.empty

    @property
    def is_optional(self) -> bool:
        """Whether the parameter permits None or defines a default value."""
        annotation = self.parameter.annotation

        if signatures.is_annotated(annotation):
            annotation = typing.get_args(annotation)[0]

        if signatures.is_union(annotation) and (
            type(None) in typing.get_args(annotation) or None in typing.get_args(annotation)
        ):
            return True

        if annotation in (None, type(None)):
            return True

        return self.has_default

    @property
    def has_default(self) -> bool:
        """Whether the parameter defines a default value."""
        return self.parameter.default is not inspect.Parameter.empty


class DependencyGraphValidator:
    """Statically validates the dependency tree of a callable for missing types, cycles, and scope errors."""

    def __init__(
        self,
        call: abc.Callable[..., object],
        signature: inspect.Signature,
        container: DependencyContainer,
        lazy_types: set[type],
        call_stack: list[abc.Callable[..., object]] | None = None,
        *,
        in_singleton: bool = False,
    ) -> None:
        """Initialize the dependency graph validator.

        Args:
            call: The root callable to validate.
            signature: The resolved signature of the callable.
            container: The container providing registered dependency definitions.
            lazy_types: Set of types deferred to runtime.
            call_stack: Recursion stack tracking callbacks in the current branch.
            in_singleton: Whether the validation branch originated from a singleton scope.
        """
        self._call = call
        self._signature = signature
        self._container = container
        self._lazy_types = lazy_types
        self._call_stack = [] if call_stack is None else call_stack
        self._in_singleton = in_singleton
        self._current_parameter: ParameterContext

    def _validate_dependency(self, dependency: Dependency) -> None:
        in_singleton = self._in_singleton or dependency.scope is _Scope.SINGLETON

        if in_singleton and dependency.scope is not _Scope.SINGLETON:
            raise errors.ScopeError(self._call, self._current_parameter.parameter)

        try:
            DependencyGraphValidator(
                dependency.call,
                dependency.signature,
                self._container,
                self._lazy_types,
                self._call_stack,
                in_singleton=in_singleton,
            ).validate()

            if signatures.is_equals(dependency.return_type, self._current_parameter.parameter_type):
                self._current_parameter.is_resolved = True
        except errors.DependencyError as error:
            error.add_path(self._call, self._current_parameter.parameter)
            raise

    def _validate_parameter_type(self) -> None:
        type_ = self._current_parameter.parameter_type
        if (
            type_ in self._container.standard_dependencies
            or type_ in self._container.overrides
            or type_ in (None, type(None))
        ):
            return

        if hasattr(type_, "__mro__"):
            for cls in type_.__mro__:
                if cls in self._lazy_types:
                    return

        raise errors.DependencyNotFoundError(self._call, self._current_parameter.parameter)

    def _validate_union(self) -> None:
        types_in_union = typing.get_args(self._current_parameter.parameter_type)
        for type_ in types_in_union:
            try:
                self._current_parameter.parameter_type = type_
                self._validate_parameter_type()
            except errors.DependencyNotFoundError:
                continue
            return
        raise errors.DependencyNotFoundError(self._call, self._current_parameter.parameter)

    def _validate_annotated(self) -> None:
        param_type, *metadata = typing.get_args(self._current_parameter.parameter_type)
        self._current_parameter.parameter_type = param_type
        for meta in metadata:
            if isinstance(meta, Dependency):
                self._validate_dependency(meta)

        if self._current_parameter.is_resolved:
            return

        self._validate_annotation()

    def _validate_annotation(self) -> None:
        if signatures.is_annotated(self._current_parameter.parameter_type):
            self._validate_annotated()
            return

        if signatures.is_union(self._current_parameter.parameter_type):
            self._validate_union()
            return

        self._validate_parameter_type()

    def _validate_parameter(self) -> None:
        try:
            self._validate_annotation()
        except errors.DependencyError:
            if not self._current_parameter.has_default:
                raise

    def validate(self) -> None:
        """Validate the full dependency graph of the callable.

        Raises:
            CircularDependencyError: If a cyclic reference is detected.
            MissingAnnotationError: If a parameter lacks an annotation.
            DependencyNotFoundError: If a parameter dependency cannot be resolved.
            ScopeError: If a singleton provider depends on a scoped or transient dependency.
        """
        if self._call in self._call_stack:
            raise errors.CircularDependencyError(self._call)

        self._call_stack.append(self._call)
        try:
            for parameter in self._signature.parameters.values():
                self._current_parameter = ParameterContext(parameter)
                if not self._current_parameter.has_annotation:
                    raise errors.MissingAnnotationError(self._call, self._current_parameter.parameter)

                if parameter.kind is parameter.VAR_POSITIONAL or parameter.kind is parameter.VAR_KEYWORD:
                    continue
                self._validate_parameter()
        finally:
            self._call_stack.pop()


async def _close_generators(generators: list[_GenericGenerator]) -> None:
    """Close and finalize synchronous and asynchronous generator dependencies in reverse order."""
    for generator in reversed(generators):
        if isinstance(generator, abc.Generator):
            generator.close()
        else:
            await generator.aclose()

    generators.clear()


@attrs.define(frozen=True, slots=True)
class Resolution:
    """Stores data and resolved generators from a callable."""

    args: tuple[object, ...]
    """Positional arguments ready to unpack into the callable."""

    kwargs: dict[str, object]
    """Keyword arguments ready to unpack into the callable."""

    scoped_generators: list[_GenericGenerator] = attrs.field(factory=list[_GenericGenerator])
    """Active generator dependencies bound to scoped lifecycle."""

    transient_generators: list[_GenericGenerator] = attrs.field(factory=list[_GenericGenerator])
    """Active generator dependencies bound to transient lifecycle."""

    async def finish_scoped(self) -> None:
        """Close and finalize all scoped generator dependencies."""
        await _close_generators(self.scoped_generators)

    async def finish_transients(self) -> None:
        """Close and finalize all transient generator dependencies."""
        await _close_generators(self.transient_generators)

    async def finish(self) -> None:
        """Close and finalize both transient and scoped generator dependencies."""
        await self.finish_transients()
        await self.finish_scoped()


class Resolver:
    """Class responsible for resolving the dependencies of the callable."""

    def __init__(
        self,
        call: abc.Callable[..., object],
        signature: inspect.Signature,
        container: DependencyContainer,
        *extra_args: object,
        call_stack: list[abc.Callable[..., typing.Any]] | None = None,
        singleton_instances: dict[abc.Callable[..., typing.Any], object] | None = None,
        singleton_generators: list[_GenericGenerator] | None = None,
        scoped_instances: dict[abc.Callable[..., typing.Any], object] | None = None,
        scoped_generators: list[_GenericGenerator] | None = None,
        **extra_kwargs: object,
    ) -> None:
        """Initialize the invocation resolver.

        Args:
            call: The callable to resolve dependencies for.
            signature: The resolved signature of the callable.
            container: The dependency container holding providers and overrides.
            *extra_args: Runtime positional values to match by type.
            call_stack: Stack tracking callables to detect cycles during execution.
            singleton_instances: Cache of singleton instances shared across executions.
            singleton_generators: Singleton generators tracked for application shutdown.
            scoped_instances: Cache of scoped instances for the current execution.
            scoped_generators: Scoped generators to close after the current execution.
            **extra_kwargs: Runtime keyword values to match by parameter name.
        """
        self._call = call
        self._signature = signature
        self._container = container
        self._call_stack = [] if call_stack is None else call_stack
        self._singleton_instances = {} if singleton_instances is None else singleton_instances
        self._singleton_generators = [] if singleton_generators is None else singleton_generators
        self._scoped_instances = {} if scoped_instances is None else scoped_instances
        self._scoped_generators = [] if scoped_generators is None else scoped_generators
        self._transient_generators: list[_GenericGenerator] = []
        self._extra_args = extra_args
        self._extra_kwargs = extra_kwargs

        self._current_parameter: ParameterContext
        self._resolved_args: list[object] = []
        self._resolved_kwargs: dict[str, object] = {}

    def _add_resolved(self, value: object) -> None:
        if self._current_parameter.parameter.kind in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            self._resolved_args.append(value)
        else:
            self._resolved_kwargs[self._current_parameter.parameter.name] = value

        self._current_parameter.is_resolved = True

    def _store_resolved_dependency(
        self, call: abc.Callable[..., typing.Any], resolved_dependency: object, scope: _Scope
    ) -> None:
        if resolved_dependency is None:
            return

        match scope:
            case _Scope.SINGLETON:
                self._singleton_instances[call] = resolved_dependency
            case _Scope.SCOPED:
                self._scoped_instances[call] = resolved_dependency
            case _Scope.TRANSIENT:
                pass

    async def _resolve_dependency(self, dependency: Dependency) -> object:
        if dependency.scope is _Scope.SINGLETON and dependency.call in self._singleton_instances:
            return self._singleton_instances[dependency.call]

        if dependency.scope is _Scope.SCOPED and dependency.call in self._scoped_instances:
            return self._scoped_instances[dependency.call]

        if dependency.call in self._container.overrides:
            dependency = self._container.overrides[dependency.call]

        try:
            dependency_resolution = await Resolver(
                dependency.call,
                dependency.signature,
                self._container,
                *self._extra_args,
                call_stack=self._call_stack,
                singleton_instances=self._singleton_instances,
                singleton_generators=self._singleton_generators,
                scoped_instances=self._scoped_instances,
                scoped_generators=self._scoped_generators,
                **self._extra_kwargs,
            ).resolve()

            self._transient_generators.extend(dependency_resolution.transient_generators)
            result = await self._execute_dependency(dependency, dependency_resolution)
        except errors.DependencyError as error:
            error.add_path(self._call, self._current_parameter.parameter)
            raise
        return result

    async def _execute_dependency(self, dependency: Dependency, resolution: Resolution) -> object:
        callback = dependency.call
        generator: abc.AsyncGenerator[typing.Any, typing.Any] | abc.Generator[typing.Any, typing.Any] | None = None

        if inspect.iscoroutinefunction(callback):
            result = await callback(*resolution.args, **resolution.kwargs)
        elif inspect.isasyncgenfunction(callback):
            generator = callback(*resolution.args, **resolution.kwargs)
            result = await anext(generator)
        elif inspect.isgeneratorfunction(callback):
            generator = callback(*resolution.args, **resolution.kwargs)
            result = next(generator)
        else:
            result = callback(*resolution.args, **resolution.kwargs)

        if generator:
            match dependency.scope:
                case _Scope.SINGLETON:
                    self._singleton_generators.append(generator)
                case _Scope.SCOPED:
                    self._scoped_generators.append(generator)
                case _Scope.TRANSIENT:
                    self._transient_generators.append(generator)

        self._store_resolved_dependency(dependency.call, result, dependency.scope)
        return result

    async def _resolve_annotated(self) -> None:
        parameter_type, *metadata = typing.get_args(self._current_parameter.parameter_type)
        for meta in metadata:
            if isinstance(meta, Dependency):
                resolved_dependency = await self._resolve_dependency(meta)

                if signatures.is_equals(type(resolved_dependency), parameter_type):
                    self._add_resolved(resolved_dependency)

        if not self._current_parameter.is_resolved:
            self._current_parameter.parameter_type = parameter_type
            await self._resolve_annotation()

    async def _resolve_union(self) -> None:
        types_in_union = typing.get_args(self._current_parameter.parameter_type)
        for type_ in types_in_union:
            self._current_parameter.parameter_type = type_
            try:
                await self._resolve_type()
                break
            except errors.DependencyError:
                continue

        if not self._current_parameter.is_resolved:
            raise errors.DependencyNotFoundError(self._call, self._current_parameter.parameter)

    async def _resolve_type(self) -> None:
        if self._current_parameter.parameter.name in self._extra_kwargs:
            self._add_resolved(self._extra_kwargs[self._current_parameter.parameter.name])
            return

        for extra in self._extra_args:
            if signatures.is_equals(type(extra), self._current_parameter.parameter_type):
                self._add_resolved(extra)
                return

        stantard_dependency = self._container.standard_dependencies.get(self._current_parameter.parameter_type)
        if stantard_dependency:
            resolved_dependency = await self._resolve_dependency(stantard_dependency)
            self._add_resolved(resolved_dependency)
            self._store_resolved_dependency(
                stantard_dependency.call,
                resolved_dependency,
                stantard_dependency.scope,
            )
            return

        if self._current_parameter.parameter.kind in (
            inspect.Parameter.VAR_KEYWORD,
            inspect.Parameter.VAR_POSITIONAL,
        ):
            return

        raise errors.DependencyNotFoundError(self._call, self._current_parameter.parameter)

    async def _resolve_annotation(self) -> None:
        try:
            if signatures.is_annotated(self._current_parameter.parameter_type):
                await self._resolve_annotated()
                return

            if signatures.is_union(self._current_parameter.parameter_type):
                await self._resolve_union()
                return

            await self._resolve_type()
        except errors.DependencyError:
            if self._current_parameter.has_default:
                self._add_resolved(self._current_parameter.parameter.default)
                return

            if self._current_parameter.is_optional:
                self._add_resolved(None)
                return

            raise

    async def resolve(self) -> Resolution:
        """Resolve the callable's dependencies.

        Returns:
            A Resolution object containing args, kwargs, and active generators.

        Raises:
            CircularDependencyError: If a cyclic reference is detected.
            MissingAnnotationError: If a parameter lacks an annotation.
            DependencyNotFoundError: If a required dependency cannot be satisfied.
        """
        if self._call in self._call_stack:
            raise errors.CircularDependencyError(self._call)

        self._call_stack.append(self._call)
        try:
            for parameter in self._signature.parameters.values():
                self._current_parameter = ParameterContext(parameter)

                if not self._current_parameter.has_annotation:
                    raise errors.MissingAnnotationError(self._call, parameter)

                await self._resolve_annotation()
        except errors.DependencyError:
            await _close_generators(self._transient_generators)
            raise
        finally:
            self._call_stack.pop()

        return Resolution(
            tuple(self._resolved_args),
            self._resolved_kwargs,
            self._scoped_generators,
            self._transient_generators,
        )


class DependencyResolver:
    """Manages invocation resolution and execution lifecycles for dependencies."""

    def __init__(self, container: DependencyContainer) -> None:
        """Initialize the dependency resolver.

        Args:
            container: The dependency container holding providers and overrides.
        """
        self._container = container
        self._singleton_instances: dict[abc.Callable[..., typing.Any], object] = {}
        self._singleton_generators: list[_GenericGenerator] = []

    async def resolve(
        self, call: abc.Callable[..., typing.Any], *extra_args: object, **extra_kwargs: object
    ) -> Resolution:
        """Resolve all dependencies for a callable.

        Args:
            call: The callable to resolve dependencies for.
            *extra_args: Positional runtime values passed to the invocation.
            **extra_kwargs: Keyword runtime values passed to the invocation.

        Returns:
            A Resolution object containing resolved arguments and generator hooks.
        """
        signature = signatures.SignatureManager.get_signature(call)
        return await Resolver(
            call,
            signature,
            self._container,
            *extra_args,
            call_stack=None,
            singleton_instances=self._singleton_instances,
            singleton_generators=self._singleton_generators,
            scoped_instances=None,
            scoped_generators=None,
            **extra_kwargs,
        ).resolve()

    async def execute[T](self, call: abc.Callable[..., T], *extra_args: object, **extra_kwargs: object) -> T:
        """Execute a callable and return its result.

        This function will resolve dependencies, execute the callable and close the generators.

        Args:
            call: The synchronous or asynchronous callable to execute.
            *extra_args: Positional runtime values to inject into the call.
            **extra_kwargs: Keyword runtime values to inject into the call.

        Returns:
            The return value of the executed callable.
        """
        resolution = await self.resolve(call, *extra_args, **extra_kwargs)
        try:
            if inspect.iscoroutinefunction(call):
                return await call(*resolution.args, **resolution.kwargs)

            return call(*resolution.args, **resolution.kwargs)
        finally:
            await resolution.finish()

    async def close(self) -> None:
        """Close and finalize all cached singleton generator dependencies."""
        await _close_generators(self._singleton_generators)


class DependencyManager(DependencyContainer, DependencyResolver):
    """Manages the resolution and validation of callable elements and their dependencies."""

    def __init__(self) -> None:
        DependencyContainer.__init__(self)
        DependencyResolver.__init__(self, self)

    def validate(self, call: abc.Callable[..., typing.Any], lazy_types: set[type] | None = None) -> None:
        """Statically validate that all dependencies for a callable can be resolved.

        Args:
            call: The callable to validate.
            lazy_types: Optional set of types deferred to runtime.

        Raises:
            CircularDependencyError: If a cycle exists in the dependency graph.
            MissingAnnotationError: If a parameter lacks a type annotation.
            DependencyNotFoundError: If a required dependency cannot be satisfied.
            ScopeError: If a singleton provider depends on a scoped/transient dependency.
        """
        signature = signatures.SignatureManager.get_signature(call)
        DependencyGraphValidator(
            call,
            signature,
            self._container,
            lazy_types or set(),
        ).validate()
