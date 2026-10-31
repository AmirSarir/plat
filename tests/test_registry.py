import pytest

from engops.modules.builtin import build_registry
from engops.modules.registry import ModuleInfo, ModuleRegistry, ModuleRegistryError


def _info(module_id, **kw):
    return ModuleInfo(id=module_id, name=module_id, version="1", description="", **kw)


def test_builtin_registry_is_valid():
    ids = [m.id for m in build_registry().enabled_modules()]
    assert ids == ["overview", "process_library", "reference_catalog", "run_history"]


def test_duplicate_id_rejected():
    reg = ModuleRegistry()
    reg.register(_info("a"))
    with pytest.raises(ModuleRegistryError):
        reg.register(_info("a"))


def test_invalid_id_rejected():
    with pytest.raises(ModuleRegistryError):
        ModuleRegistry().register(_info("Bad Id"))


def test_missing_dependency_rejected():
    reg = ModuleRegistry()
    reg.register(_info("a", dependencies=("ghost",)))
    with pytest.raises(ModuleRegistryError):
        reg.validate()


def test_disabled_dependency_rejected():
    reg = ModuleRegistry()
    reg.register(_info("base", enabled=False))
    reg.register(_info("child", dependencies=("base",)))
    with pytest.raises(ModuleRegistryError):
        reg.validate()