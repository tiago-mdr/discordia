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
    origin = typing.get_origin(annotation)
    is_gen_type = origin in (
        abc.Generator,
        abc.AsyncGenerator,
        abc.Iterator,
        abc.AsyncIterator,
    )
    is_gen_fn = inspect.isgeneratorfunction(call) or inspect.isasyncgenfunction(call)

    if is_gen_type or is_gen_fn:
        args = signatures.extract_args(annotation)
        target = args[0] if args else object
    else:
        target = annotation

    if target is None:
        return type(None)

    return target  # type: ignore[return-value]


class Dependency:
    def __init__(self, dependency: object, scope: _Scope) -> None:
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
    def __init__(self) -> None:
        self.standard_dependencies: dict[type[object], Dependency] = {}
        self.overrides: dict[abc.Callable[..., object], Dependency] = {}

    def add_dependency(self, dependency: object, scope: _ScopeAlias = "scoped") -> None:
        dependency = inject(dependency, scope)
        if dependency.return_type in self.standard_dependencies:
            msg = f"Dependency already registered for type: {dependency.return_type}"
            raise ValueError(msg)
        self.standard_dependencies[dependency.return_type] = dependency

    def remove_dependency(self, dependency_type: type[object]) -> Dependency:
        return self.standard_dependencies.pop(dependency_type)

    def add_override(
        self,
        overridden: abc.Callable[..., typing.Any],
        override: abc.Callable[..., typing.Any],
        scope: _ScopeAlias = "scoped",
    ) -> None:
        if overridden in self.overrides:
            msg = f"Override already registered for callable: {overridden}"
            raise ValueError(msg)
        self.overrides[overridden] = inject(override, scope)

    def remove_override(self, overridden: abc.Callable[..., typing.Any]) -> Dependency:
        return self.overrides.pop(overridden)


class ParameterContext:
    def __init__(self, parameter: inspect.Parameter) -> None:
        self.parameter = parameter
        self.parameter_type = parameter.annotation
        self.is_resolved = False

    @property
    def has_annotation(self) -> bool:
        return self.parameter.annotation is not inspect.Parameter.empty

    @property
    def is_optional(self) -> bool:
        annotation = self.parameter.annotation

        if signatures.is_annotated(annotation):
            annotation = signatures.extract_args(annotation)[0]

        if signatures.is_union(annotation) and (
            type(None) in signatures.extract_args(annotation) or None in signatures.extract_args(annotation)
        ):
            return True

        if annotation in (None, type(None)):
            return True

        return self.has_default

    @property
    def has_default(self) -> bool:
        return self.parameter.default is not inspect.Parameter.empty


class DependencyGraphValidator:
    def __init__(
        self,
        call: abc.Callable[..., object],
        signature: inspect.Signature,
        container: DependencyContainer,
        lazy_types: set[type],
        call_stack: list[abc.Callable[..., object]] | None = None,
        current_scope: _Scope | None = None,
    ) -> None:
        self._call = call
        self._signature = signature
        self._container = container
        self._lazy_types = lazy_types
        self._call_stack = [] if call_stack is None else call_stack
        self._current_scope = current_scope
        self._current_parameter: ParameterContext

    def _validate_dependency(self, dependency: Dependency) -> None:
        if self._current_scope is None:
            self._current_scope = dependency.scope

        if self._current_scope is _Scope.SINGLETON and dependency.scope is not _Scope.SINGLETON:
            raise errors.ScopeError(self._call, self._current_parameter.parameter)

        try:
            DependencyGraphValidator(
                dependency.call,
                dependency.signature,
                self._container,
                self._lazy_types,
                self._call_stack,
                self._current_scope,
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
        types_in_union = signatures.extract_args(self._current_parameter.parameter_type)
        for type_ in types_in_union:
            try:
                self._current_parameter.parameter_type = type_
                self._validate_parameter_type()
            except errors.DependencyNotFoundError:
                continue
            return
        raise errors.DependencyNotFoundError(self._call, self._current_parameter.parameter)

    def _validate_annotated(self) -> None:
        param_type, *metadata = signatures.extract_args(self._current_parameter.parameter_type)
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
    for generator in reversed(generators):
        if isinstance(generator, abc.Generator):
            generator.close()
        else:
            await generator.aclose()

    generators.clear()


@attrs.define(frozen=True, slots=True)
class Resolution:
    args: tuple[object, ...]
    kwargs: dict[str, object]
    scoped_generators: list[_GenericGenerator] = attrs.field(factory=list[_GenericGenerator])
    transient_generators: list[_GenericGenerator] = attrs.field(factory=list[_GenericGenerator])

    async def finish_scoped(self) -> None:
        await _close_generators(self.scoped_generators)

    async def finish_transients(self) -> None:
        await _close_generators(self.transient_generators)

    async def finish(self) -> None:
        await self.finish_transients()
        await self.finish_scoped()


class Resolver:
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
        parameter_type, *metadata = signatures.extract_args(self._current_parameter.parameter_type)
        for meta in metadata:
            if isinstance(meta, Dependency):
                resolved_dependency = await self._resolve_dependency(meta)

                if signatures.is_equals(type(resolved_dependency), parameter_type):
                    self._add_resolved(resolved_dependency)

        if not self._current_parameter.is_resolved:
            self._current_parameter.parameter_type = parameter_type
            await self._resolve_annotation()

    async def _resolve_union(self) -> None:
        types_in_union = signatures.extract_args(self._current_parameter.parameter_type)
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
    def __init__(self, container: DependencyContainer) -> None:
        self._container = container
        self._singleton_instances: dict[abc.Callable[..., typing.Any], object] = {}
        self._singleton_generators: list[_GenericGenerator] = []

    async def resolve(
        self, call: abc.Callable[..., typing.Any], *extra_args: object, **extra_kwargs: object
    ) -> Resolution:
        signature = signatures.SignatureManager.get_signature(call, cache=True)
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
        resolution = await self.resolve(call, *extra_args, **extra_kwargs)
        try:
            if inspect.iscoroutinefunction(call):
                return await call(*resolution.args, **resolution.kwargs)

            return call(*resolution.args, **resolution.kwargs)
        finally:
            await resolution.finish()

    async def close(self) -> None:
        await _close_generators(self._singleton_generators)


class DependencyManager:
    def __init__(self) -> None:
        self._container = DependencyContainer()
        self._resolver = DependencyResolver(self._container)

    def add_dependency(self, dependency: object, scope: _ScopeAlias = "scoped") -> None:
        self._container.add_dependency(dependency, scope)

    def remove_dependency(self, dependency_type: type[object]) -> Dependency:
        return self._container.remove_dependency(dependency_type)

    def add_override(
        self,
        overridden: abc.Callable[..., typing.Any],
        override: abc.Callable[..., typing.Any],
        scope: _ScopeAlias = "scoped",
    ) -> None:
        self._container.add_override(overridden, override, scope)

    def remove_override(self, overridden: abc.Callable[..., typing.Any]) -> Dependency:
        return self._container.remove_override(overridden)

    def validate(self, call: abc.Callable[..., typing.Any], lazy_types: set[type] | None = None) -> None:
        signature = signatures.SignatureManager.get_signature(call, cache=True)
        DependencyGraphValidator(
            call,
            signature,
            self._container,
            lazy_types or set(),
        ).validate()

    async def resolve(
        self, call: abc.Callable[..., typing.Any], *extra_args: object, **extra_kwargs: object
    ) -> Resolution:
        return await self._resolver.resolve(call, *extra_args, **extra_kwargs)

    async def execute[T](self, call: abc.Callable[..., T], *extra_args: object, **extra_kwargs: object) -> T:
        return await self._resolver.execute(call, *extra_args, **extra_kwargs)

    async def close(self) -> None:
        await self._resolver.close()
