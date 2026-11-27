from __future__ import annotations

from typing import Annotated

import pytest

from discordia.di import DependencyManager, inject
from discordia.errors import CircularDependencyError, CircularSignatureError
from discordia.signatures import SignatureManager


@pytest.fixture
def manager() -> DependencyManager:
    SignatureManager.clear_cache()
    return DependencyManager()


# Cycles #


class SelfReferencingNode:
    def __init__(
        self,
        dep: Annotated[SelfReferencingNode, inject(SelfReferencingNode)],
    ) -> None:
        self.dep = dep


class CycleA:
    def __init__(self, b: Annotated[CycleB, inject(CycleB)]) -> None:
        self.b = b


class CycleB:
    def __init__(self, a: Annotated[CycleA, inject(CycleA)]) -> None:
        self.a = a


class TriCycleA:
    def __init__(self, b: Annotated[TriCycleB, inject(TriCycleB)]) -> None:
        self.b = b


class TriCycleB:
    def __init__(self, c: Annotated[TriCycleC, inject(TriCycleC)]) -> None:
        self.c = c


class TriCycleC:
    def __init__(self, a: Annotated[TriCycleA, inject(TriCycleA)]) -> None:
        self.a = a


# Container-registered runtime cycles (caught by Resolver as CircularDependencyError) #


class ContainerSelfCycle:
    def __init__(self, me: ContainerSelfCycle) -> None:
        self.me = me


class ContainerCycleA:
    def __init__(self, b: ContainerCycleB) -> None:
        self.b = b


class ContainerCycleB:
    def __init__(self, a: ContainerCycleA) -> None:
        self.a = a


class ContainerTriA:
    def __init__(self, b: ContainerTriB) -> None:
        self.b = b


class ContainerTriB:
    def __init__(self, c: ContainerTriC) -> None:
        self.c = c


class ContainerTriC:
    def __init__(self, a: ContainerTriA) -> None:
        self.a = a


def overridable_dep() -> int:
    return 1


def cyclic_override_dep(val: Annotated[int, inject(overridable_dep, "transient")]) -> int:
    return val + 1


def override_cycle_consumer(x: Annotated[int, inject(overridable_dep, "transient")]) -> int:
    return x


# Diamond DAG #


class CommonBottom:
    def __init__(self) -> None:
        self.value = "bottom"


class LeftBranch:
    def __init__(self, bottom: Annotated[CommonBottom, inject(CommonBottom)]) -> None:
        self.bottom = bottom


class RightBranch:
    def __init__(self, bottom: Annotated[CommonBottom, inject(CommonBottom)]) -> None:
        self.bottom = bottom


class DiamondTop:
    def __init__(
        self,
        left: Annotated[LeftBranch, inject(LeftBranch)],
        right: Annotated[RightBranch, inject(RightBranch)],
    ) -> None:
        self.left = left
        self.right = right


class ContainerDiamondLeaf:
    pass


class ContainerDiamondLeft:
    def __init__(self, leaf: ContainerDiamondLeaf) -> None:
        self.leaf = leaf


class ContainerDiamondRight:
    def __init__(self, leaf: ContainerDiamondLeaf) -> None:
        self.leaf = leaf


class ContainerDiamondRoot:
    def __init__(self, left: ContainerDiamondLeft, right: ContainerDiamondRight) -> None:
        self.left = left
        self.right = right


# Tests #


class TestSignatureCircularDependency:
    def test_direct_self_cycle_in_validation(self, manager: DependencyManager):
        with pytest.raises(CircularSignatureError) as exc_info:
            manager.validate(SelfReferencingNode)

        assert exc_info.value.callback is SelfReferencingNode
        assert "SelfReferencingNode" in str(exc_info.value)

    def test_two_node_cycle_in_validation(self, manager: DependencyManager):
        with pytest.raises(CircularSignatureError) as exc_info:
            manager.validate(CycleA)

        assert exc_info.value.callback is CycleA
        msg = str(exc_info.value)
        assert "CycleA" in msg
        assert "CycleB" in msg

    def test_three_node_cycle_in_validation(self, manager: DependencyManager):
        with pytest.raises(CircularSignatureError) as exc_info:
            manager.validate(TriCycleA)

        assert exc_info.value.callback is TriCycleA
        msg = str(exc_info.value)
        assert "TriCycleA" in msg
        assert "TriCycleB" in msg
        assert "TriCycleC" in msg

    @pytest.mark.parametrize("target", [SelfReferencingNode, CycleA, TriCycleA])
    async def test_signature_cycle_in_execution(self, manager: DependencyManager, target: type):
        with pytest.raises(CircularSignatureError) as exc_info:
            await manager.execute(target)
        assert exc_info.value.callback is target


class TestRuntimeContainerCircularDependency:
    async def test_direct_container_self_cycle_raises_circular_dependency_error(self, manager: DependencyManager):
        manager.add_dependency(ContainerSelfCycle, "transient")

        with pytest.raises(CircularDependencyError) as exc_info:
            await manager.execute(ContainerSelfCycle)

        err = exc_info.value
        assert err.callback is ContainerSelfCycle
        assert len(err.path) == 1
        assert err.path[0].callback is ContainerSelfCycle
        assert err.path[0].parameter.name == "me"

    async def test_two_node_container_cycle_raises_circular_dependency_error(self, manager: DependencyManager):
        manager.add_dependency(ContainerCycleA, "transient")
        manager.add_dependency(ContainerCycleB, "transient")

        with pytest.raises(CircularDependencyError) as exc_info:
            await manager.execute(ContainerCycleA)

        err = exc_info.value
        assert err.callback is ContainerCycleA
        assert [step.callback for step in err.path] == [ContainerCycleB, ContainerCycleA]
        assert "ContainerCycleA" in str(err)
        assert "ContainerCycleB" in str(err)

    async def test_three_node_container_cycle_raises_circular_dependency_error(self, manager: DependencyManager):
        manager.add_dependency(ContainerTriA, "transient")
        manager.add_dependency(ContainerTriB, "transient")
        manager.add_dependency(ContainerTriC, "transient")

        with pytest.raises(CircularDependencyError) as exc_info:
            await manager.execute(ContainerTriA)

        err = exc_info.value
        assert err.callback is ContainerTriA
        assert [step.callback for step in err.path] == [ContainerTriC, ContainerTriB, ContainerTriA]

    async def test_cycle_introduced_via_override_raises_circular_dependency_error(self, manager: DependencyManager):
        manager.add_override(overridable_dep, cyclic_override_dep, "transient")

        with pytest.raises(CircularDependencyError) as exc_info:
            await manager.execute(override_cycle_consumer)

        assert exc_info.value.callback is cyclic_override_dep


class TestDiamondDependencyIsNotCircular:
    def test_diamond_dependency_validation_succeeds(self, manager: DependencyManager):
        manager.validate(DiamondTop)

    async def test_diamond_dependency_execution_succeeds(self, manager: DependencyManager):
        top = await manager.execute(DiamondTop)
        assert isinstance(top, DiamondTop)
        assert top.left.bottom.value == "bottom"
        assert top.right.bottom.value == "bottom"
        # Default scope is scoped, so both branches share CommonBottom within one execution
        assert top.left.bottom is top.right.bottom

    async def test_container_diamond_dependency_execution_succeeds(self, manager: DependencyManager):
        manager.add_dependency(ContainerDiamondLeaf)
        manager.add_dependency(ContainerDiamondLeft)
        manager.add_dependency(ContainerDiamondRight)

        root = await manager.execute(ContainerDiamondRoot)
        assert root.left.leaf is root.right.leaf
