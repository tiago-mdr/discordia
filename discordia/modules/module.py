"""Modular architecture supporting composable module trees, registries, and decorators."""

from __future__ import annotations

import typing

from discordia import errors, handlers, signatures
from discordia.modules import decorators, registry_store

if typing.TYPE_CHECKING:
    from collections.abc import Awaitable

    from .registries import RegistrationData


class ModuleMetaData:
    """Stores family data and registries in a module."""

    def __init__(self, module: Module) -> None:
        """Initialize metadata for a module.

        Args:
            module: The module being configured.
        """
        self.module = module
        self.children: set[Module] = set()
        self.owner: Module | None = None
        self._family: set[Module] = {self.module}
        self._root: Module = self.module
        self._my_registers: set[RegistrationData[typing.Any]] = set()

    @property
    def root(self) -> Module:
        """The top-most ancestor module in the hierarchy."""
        while self._root.metadata.owner is not None:
            self._root = self._root.metadata.owner
        return self._root

    @root.setter
    def root(self, other: Module) -> None:
        self._root = other

    @property
    def family(self) -> set[Module]:
        """All modules that belong to the current tree hierarchy."""
        if self.root is self.module:
            return self._family

        return self.root.metadata.family

    @family.setter
    def family(self, other: set[Module]) -> None:
        self._family = other

    def get_registers(self) -> set[RegistrationData[typing.Any]]:
        """Return all registrations declared directly by this module.

        Returns:
            A set of RegistrationData instances owned by this module.
        """
        return self._my_registers

    def add_register(self, new: RegistrationData[typing.Any]) -> None:
        """Track a new registration owned by this module.

        Args:
            new: The registration data wrapper to add.
        """
        self._my_registers.add(new)

    def remove_register(self, register: RegistrationData[typing.Any]) -> None:
        """Untrack a registration owned by this module.

        Args:
            register: The registration data wrapper to remove.
        """
        self._my_registers.discard(register)


class Module:
    """Composable container for handlers."""

    def __init__(self) -> None:
        """Initialize an empty module instance."""
        self._registers = registry_store.RegistryStore()
        self.metadata = ModuleMetaData(self)
        self.events = decorators.EventDecorator(self)
        self.interactions = decorators.InteractionDecorator(self)

    def _is_descendant(self, other: Module) -> bool:
        """Check whether another module is a direct or indirect descendant of this module."""
        curr = other.metadata.owner
        while curr is not None:
            if curr is self:
                return True
            curr = curr.metadata.owner
        return False

    def catch_error[Error: Exception](
        self, error: type[Error] | None = None
    ) -> typing.Callable[[typing.Callable[typing.Concatenate[Error, ...], Awaitable[object]]], handlers.ErrorResponder]:
        """Register a callback to handle specific exception types.

        Args:
            error: The Exception type to catch. If omitted, the type is inferred from
                the first parameter annotation of the decorated callback.

        Returns:
            A decorator function returning the registered ErrorResponder.

        Raises:
            ValueError: If error is not provided and cannot be inferred from the callback signature.
        """

        def wrapper(
            func: typing.Callable[typing.Concatenate[Error, ...], Awaitable[object]],
        ) -> handlers.ErrorResponder:
            inferred_error = error or signatures.find_for_type(func, Exception)
            if inferred_error is None:
                msg = f"Cannot infer the error type for {func.__name__}. Please specify it explicitly."
                raise ValueError(msg)

            new_error_responder = handlers.ErrorResponder(inferred_error, func)
            self.registers.errors.add(new_error_responder, self)
            return new_error_responder

        return wrapper

    @property
    def registers(self) -> registry_store.RegistryStore:
        """The RegistryStore of the hierarchy."""
        root = self.metadata.root

        if root is self:
            return self._registers
        return self.metadata.root.registers

    @registers.setter
    def registers(self, other: registry_store.RegistryStore) -> None:
        self._registers = other

    def merge(self, other: Module) -> None:
        """Merge another module into this module.

        Args:
            other: The child module to attach.

        Raises:
            ModuleMergeError: If attempting to merge a module into itself, if the module
                already has an owner, or if it is already in the tree.
        """
        if other is self:
            msg = "Cannot merge a module into itself."
            raise errors.ModuleMergeError(msg)

        if other.metadata.owner is not None:
            msg = "Cannot merge a module that already has an owner."
            raise errors.ModuleMergeError(msg)

        if other in self.metadata.family:
            msg = "Cannot merge a module that is already part of this hierarchy."
            raise errors.ModuleMergeError(msg)

        root = self.metadata.root
        other_registers = other.registers
        other_family = other.metadata.family

        try:
            root.registers.merge(other_registers)
        except Exception:
            temp_dest = registry_store.RegistryStore()
            for mod in other_family:
                root.registers.unmerge(mod.metadata.get_registers(), temp_dest)
            raise

        other.metadata.owner = self
        self.metadata.children.add(other)
        root.metadata.family.update(other_family)
        other.registers = root.registers
        other.metadata.family = root.metadata.family

    def unmerge(self, other: Module) -> None:
        """Detach a descendant module from this module hierarchy.

        Args:
            other: The descendant module to detach.

        Raises:
            ModuleUnmergeError: If attempting to unmerge self or a module that is
                not a descendant of this module.
        """
        if other is self:
            msg = "Cannot unmerge a module from itself."
            raise errors.ModuleUnmergeError(msg)

        if not self._is_descendant(other):
            msg = "Cannot unmerge a module that is not a descendant of this module."
            raise errors.ModuleUnmergeError(msg)

        old_root = self.metadata.root
        new_registers = registry_store.RegistryStore()
        new_family: set[Module] = set()

        def _recursive_unmerge(node: Module) -> None:
            node.metadata.root = other

            old_root.metadata.family.discard(node)
            new_family.add(node)

            old_root.registers.unmerge(node.metadata.get_registers(), new_registers)

            for child in node.metadata.children:
                _recursive_unmerge(child)

        _recursive_unmerge(other)

        parent = other.metadata.owner
        if parent is not None:
            parent.metadata.children.discard(other)
        other.metadata.owner = None

        other.registers = new_registers
        other.metadata.family = new_family
