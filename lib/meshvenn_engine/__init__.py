"""Public provider-independent engine facade. No Blender or agent SDK imports."""
from pathlib import Path

# Setuptools maps meshvenn_engine.core directly to the add-on's authoritative
# core directory. Support the same mapping when developing from lib/ directly;
# installed wheels already contain core/ and never search a checkout.
_directory = Path(__file__).resolve().parent
if not (_directory / "core").is_dir() and _directory.parent.name == "lib":
    _checkout = _directory.parent.parent
    if (_checkout / "core" / "__init__.py").is_file() and (_checkout / "pyproject.toml").is_file():
        __path__.append(str(_checkout))

from .errors import EngineError
from .engine import MeshvennEngine

__version__ = "0.1.0"
__all__ = ["MeshvennEngine", "EngineError", "__version__"]
