"""Helpers shared by the script tests."""

import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]


def load_script(filename: str):
    """Load ``scripts/filename`` under a private ``sys.modules`` name."""
    path = _SCRIPTS / filename
    name = f"_octools_script_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    loaded = False
    try:
        spec.loader.exec_module(module)
        loaded = True
    finally:
        if not loaded:
            sys.modules.pop(name, None)
    return name, module


def unload_script(name: str) -> None:
    """Drop a script module loaded by :func:`load_script`."""
    sys.modules.pop(name, None)
