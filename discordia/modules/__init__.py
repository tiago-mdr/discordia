"""Modularization system and registry storage for Discordia."""

from .decorators import EventDecorator, InteractionDecorator
from .module import Module, ModuleMetaData
from .registries import Registry
from .registry_store import RegistryStore

__all__ = [
    "EventDecorator",
    "InteractionDecorator",
    "Module",
    "ModuleMetaData",
    "Registry",
    "RegistryStore",
]
