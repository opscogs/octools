"""Test version."""

import importlib
from pathlib import Path

import pytest

import octools

DUMMY_VERSION = "999.999.999"
_PACKAGE_DIR = Path(octools.__file__).resolve().parent


@pytest.fixture
def version_file(tmp_path, monkeypatch):
    """Redirect the VERSION read to ``tmp_path`` and restore the real version."""
    target = tmp_path / "VERSION"
    original = Path.__truediv__

    def truediv(self, other):
        if other == "VERSION" and Path(self).resolve() == _PACKAGE_DIR:
            return target
        return original(self, other)

    monkeypatch.setattr(Path, "__truediv__", truediv)
    yield target
    monkeypatch.undo()
    importlib.reload(octools)


def test_version_no_file(version_file) -> None:
    """A missing VERSION file reads as 0.0.0."""
    assert not version_file.exists()
    importlib.reload(octools)
    assert octools.__version__ == "0.0.0"


def test_version_file(version_file) -> None:
    """``__version__`` is the stripped contents of the VERSION file."""
    version_file.write_text(DUMMY_VERSION)
    importlib.reload(octools)
    assert octools.__version__ == DUMMY_VERSION


def test_only_the_version_string_is_public() -> None:
    """The version-file helpers stay private; __version__ is the public name."""
    assert {"filepath", "version_file", "version"}.isdisjoint(vars(octools))
    assert "__version__" in octools.__all__


def test_every_public_name_is_defined() -> None:
    """Every ``octools.__all__`` entry exists on the package."""
    assert len(set(octools.__all__)) == len(octools.__all__)
    missing = [name for name in octools.__all__ if not hasattr(octools, name)]
    assert missing == []
