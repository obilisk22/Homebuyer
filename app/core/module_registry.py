from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from nicegui import ui

RenderFn = Callable[[object, ui.element], None | Awaitable[None]]


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    title: str
    order: int
    render: RenderFn


_MODULES: list[ModuleSpec] | None = None


def discover_modules() -> list[ModuleSpec]:
    """Import every package under app.modules that exposes MODULE."""
    global _MODULES
    if _MODULES is not None:
        return _MODULES

    import importlib
    import pkgutil

    import app.modules as modules_pkg

    found: list[ModuleSpec] = []
    for mod_info in pkgutil.iter_modules(modules_pkg.__path__, modules_pkg.__name__ + "."):
        module = importlib.import_module(mod_info.name)
        spec = getattr(module, "MODULE", None)
        if isinstance(spec, ModuleSpec):
            found.append(spec)

    found.sort(key=lambda m: (m.order, m.title))
    _MODULES = found
    return found


def get_modules() -> list[ModuleSpec]:
    return discover_modules()
