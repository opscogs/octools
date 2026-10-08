"""Test scripts/sync_claude_config.py."""

from pathlib import Path

import pytest

from scripts.tests.support import load_script, unload_script


@pytest.fixture(scope="module")
def sync_claude_config():
    """Load the config-sync script under a private module name."""
    name, module = load_script("sync_claude_config.py")
    yield module
    unload_script(name)


ALWAYS_RULE = """---
description: Always on
alwaysApply: true
---

# Always

See `.cursor/rules/scoped.mdc` and ask the `Task` tool.
"""
SCOPED_RULE = """---
description: Scoped
# no key here
globs: ["docs/**/*.md", 'src/*.{py,pyi}']
alwaysApply: false
---
# Scoped
"""


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    write(tmp_path, ".cursor/rules/always.mdc", ALWAYS_RULE)
    write(tmp_path, ".cursor/rules/scoped.mdc", SCOPED_RULE)
    write(tmp_path, ".cursor/rules/bare.mdc", "# Bare\n")
    return tmp_path


def test_repository_config_is_in_sync(sync_claude_config):
    assert sync_claude_config.main(["--check"]) == 0


def test_sync_writes_translated_files(sync_claude_config, repo: Path, capsys):
    main = sync_claude_config.main
    assert main(["--root", str(repo), "--check"]) == 1
    assert "out of date" in capsys.readouterr().err
    assert main(["--root", str(repo)]) == 0
    assert main(["--root", str(repo), "--check"]) == 0
    always = (repo / ".claude/rules/always.md").read_text()
    assert always == (
        "<!-- Generated from .cursor/rules/always.mdc by "
        "scripts/sync_claude_config.py; edit the source. -->\n\n# Always\n\n"
        "See `.claude/rules/scoped.md` and ask the `Agent` tool.\n"
    )
    scoped = (repo / ".claude/rules/scoped.md").read_text()
    assert scoped.startswith(
        '---\npaths:\n  - "docs/**/*.md"\n  - "src/*.{py,pyi}"\n---\n<!-- '
    )
    assert (repo / ".claude/rules/bare.md").read_text().startswith("<!-- ")


def test_sync_removes_only_stale_generated_files(sync_claude_config, repo: Path):
    main = sync_claude_config.main
    assert main(["--root", str(repo)]) == 0
    (repo / ".cursor/rules/bare.mdc").unlink()
    own = write(repo, ".claude/rules/own.md", "# Hand-written\n")
    assert main(["--root", str(repo), "--check"]) == 1
    assert main(["--root", str(repo)]) == 0
    assert not (repo / ".claude/rules/bare.md").exists()
    assert own.exists()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", []),
        ("CHANGELOG.md", ["CHANGELOG.md"]),
        ("docs/a/**/*.md, docs/b/**/*.md", ["docs/a/**/*.md", "docs/b/**/*.md"]),
        ('["x/*.py", "y/*.{json,csv}"]', ["x/*.py", "y/*.{json,csv}"]),
    ],
)
def test_parse_globs(sync_claude_config, value, expected):
    assert sync_claude_config.parse_globs(value) == expected


@pytest.mark.parametrize(
    ("relative", "text", "error"),
    [
        (".cursor/rules/open.mdc", "---\nglobs: x\n", "never closed"),
        (".cursor/rules/e1.mdc", "---\nglobs:\n---\n", "e1.mdc: globs is present"),
        (".cursor/rules/e2.mdc", "---\nglobs: []\n---\n", "globs is present"),
        (".cursor/rules/e3.mdc", "---\nglobs:\n  [\n  ]\n---\n", "globs is present"),
        (".cursor/rules/e4.mdc", "---\nglobs: a\njunk\n---\n", "e4.mdc: unassignable"),
        (".cursor/rules/e5.mdc", "---\n  - a\n---\n", "unassignable"),
        (".cursor/rules/e6.mdc", "---\n: a\n---\n", "unassignable"),
    ],
)
def test_invalid_source_fails(
    sync_claude_config, tmp_path: Path, capsys, relative, text, error
):
    write(tmp_path, relative, text)
    assert sync_claude_config.main(["--root", str(tmp_path)]) == 1
    assert error in capsys.readouterr().err


WRAPPED_GLOBS = [
    'globs: ["a/**/*.py", "b/*.{md,mdx}"]',
    'globs:\n  [\n    "a/**/*.py",\n    "b/*.{md,mdx}",\n  ]',
    'globs: [\n  "a/**/*.py",\n  "b/*.{md,mdx}"\n]',
    "globs:\n  - \"a/**/*.py\"\n  - 'b/*.{md,mdx}'",
    "# note\nglobs: a/**/*.py, b/*.{md,mdx}",
]


@pytest.mark.parametrize("globs", WRAPPED_GLOBS)
def test_wrapped_globs_render_same_paths(sync_claude_config, tmp_path: Path, globs):
    write(
        tmp_path, ".cursor/rules/r.mdc", f"---\n{globs}\nalwaysApply: false\n---\n# R\n"
    )
    assert sync_claude_config.main(["--root", str(tmp_path)]) == 0
    assert (
        (tmp_path / ".claude/rules/r.md")
        .read_text()
        .startswith('---\npaths:\n  - "a/**/*.py"\n  - "b/*.{md,mdx}"\n---\n<!-- ')
    )
