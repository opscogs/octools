"""The generated spec files match what the installed octools generates."""

from scripts.tests.support import load_script, unload_script


def test_generated_spec_is_in_sync():
    name, module = load_script("sync_spec.py")
    try:
        assert module.main(["--check"]) == 0
    finally:
        unload_script(name)
