import importlib.util
import sys


_REAL_FIND_SPEC = importlib.util.find_spec


def _safe_find_spec(name, package=None):
    """Keep legacy test dependency stubs from breaking later collection.

    Some older tests install lightweight ModuleType stubs at module import time.
    Those stubs may not carry __spec__, which makes importlib.util.find_spec
    raise ValueError for later tests. Returning None preserves the intended
    "dependency missing" semantics for those stubs.
    """
    try:
        return _REAL_FIND_SPEC(name, package)
    except ValueError:
        module = sys.modules.get(name)
        if module is not None and getattr(module, "__spec__", None) is None:
            return None
        raise


importlib.util.find_spec = _safe_find_spec

