"""The ``octools list`` CLI, driven through ``main`` and ``python -m octools``."""

import argparse
import io
import json
import os
import runpy
import sys

import pytest

from octools import __version__, example, render_listing
from octools.__main__ import _parser, main
from octools.example import ECHO_RECORDS, ExampleProvider

HERE = "tests.unit_tests.test_main"
EXAMPLE = "octools.example"
PROVIDER = ExampleProvider()
NOT_CALLABLE = 7
FORMATS = ["table", "md", "txt", "json"]


class Holder:
    provider = ExampleProvider()


class RaisingProvider:
    def all_tools(self):
        raise RuntimeError("backend down")


class JunkProvider:
    def all_tools(self):
        return (ECHO_RECORDS, 42)


RAISING = RaisingProvider()
JUNK = JunkProvider()


def make_provider():
    return ExampleProvider()


def broken_factory():
    raise RuntimeError("boom")


def not_a_provider():
    return 42


def interrupted():
    raise KeyboardInterrupt


class TTY(io.StringIO):
    def isatty(self):
        return True


def rendering(style="table", **kwargs):
    return render_listing(example, style=style, **kwargs)


@pytest.mark.parametrize(
    "spec",
    [
        EXAMPLE,
        f"{EXAMPLE}:ExampleProvider",
        f"{HERE}:PROVIDER",
        f"{HERE}:make_provider",
        f"{HERE}:Holder.provider",
    ],
)
@pytest.mark.parametrize("output_format", FORMATS)
def test_list_prints_the_rendering(capsys, spec, output_format):
    assert main(["list", spec, "--output-format", output_format]) == 0
    out, err = capsys.readouterr()
    assert out == rendering(output_format, pretty=False)
    assert err == ""


def test_list_defaults_to_table_and_filters_access(capsys):
    assert main(["list", EXAMPLE]) == 0
    assert capsys.readouterr().out.startswith("echo_records  local  read  Return")
    assert main(["list", EXAMPLE, "--access", "remote"]) == 0
    assert capsys.readouterr().out == ""
    assert main(["list", EXAMPLE, "--access", "local", "--output-format", "json"]) == 0
    assert capsys.readouterr().out == rendering("json", access="local", pretty=False)


def test_markdown_is_an_alias_for_md(capsys):
    assert main(["list", EXAMPLE, "--output-format", "markdown"]) == 0
    assert capsys.readouterr().out == rendering("md")


@pytest.mark.parametrize(
    ("argv", "isatty", "pretty"),
    [
        ([], False, False),
        ([], True, True),
        (["--pretty"], False, True),
        (["--no-pretty"], True, False),
    ],
)
def test_pretty_follows_the_terminal_unless_given(monkeypatch, argv, isatty, pretty):
    stdout = TTY() if isatty else io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    assert main(["list", EXAMPLE, "--output-format", "json", *argv]) == 0
    assert stdout.getvalue() == rendering("json", pretty=pretty)


@pytest.mark.parametrize(
    ("name", "argv", "style", "pretty"),
    [
        ("tools.md", [], "md", False),
        ("tools.markdown", [], "md", False),
        ("tools.JSON", [], "json", False),
        ("tools.json", ["--pretty"], "json", True),
        ("tools.txt", [], "txt", False),
        ("tools.out", [], "table", False),
        ("tools", [], "table", False),
        ("tools.md", ["--output-format", "json"], "json", False),
        ("tools.json", ["--output-format", "table"], "table", False),
    ],
)
def test_output_file_infers_the_format(
    tmp_path, monkeypatch, capsys, name, argv, style, pretty
):
    monkeypatch.setattr(sys, "stdout", TTY())
    path = tmp_path / name
    assert main(["list", EXAMPLE, "-o", str(path), *argv]) == 0
    assert sys.stdout.getvalue() == ""
    assert capsys.readouterr().err == ""
    assert path.read_text(encoding="utf-8") == rendering(style, pretty=pretty)
    assert [p.name for p in tmp_path.iterdir()] == [name]


def test_output_file_replaces_an_existing_file(tmp_path, capsys):
    path = tmp_path / "tools.md"
    path.write_text("old\n", encoding="utf-8")
    assert main(["list", EXAMPLE, "--output-file", str(path)]) == 0
    assert path.read_bytes() == rendering("md").encode("utf-8")
    assert capsys.readouterr().out == ""


def test_dash_is_stdout(capsys):
    assert main(["list", EXAMPLE, "-o", "-", "--output-format", "md"]) == 0
    assert capsys.readouterr().out == rendering("md")


def test_output_file_in_the_working_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["list", EXAMPLE, "-o", "tools.txt"]) == 0
    assert (tmp_path / "tools.txt").read_text(encoding="utf-8") == rendering("txt")
    assert capsys.readouterr().out == ""


def test_failed_write_exits_1_and_leaves_no_temp_file(tmp_path, monkeypatch, capsys):
    def refuse(_src, _dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", refuse)
    path = tmp_path / "tools.json"
    assert main(["list", EXAMPLE, "-o", str(path)]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    error = json.loads(err)["error"]
    assert error["type"] == "api_failure"
    assert error["message"] == f"cannot write {str(path)!r}: disk full"
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ("missing/tools.md", "does not exist"),
        (".", "is a directory, not a file"),
        ("locked/tools.md", "is not writable"),
    ],
)
def test_unusable_output_file_is_a_usage_error(
    tmp_path, monkeypatch, capsys, target, message
):
    locked = tmp_path / "locked"
    locked.mkdir()
    locked.chmod(0o500)
    monkeypatch.chdir(tmp_path)
    try:
        with pytest.raises(SystemExit) as excinfo:
            main(["list", EXAMPLE, "-o", target])
    finally:
        locked.chmod(0o700)
    assert excinfo.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("usage: octools list")
    assert "argument -o/--output-file" in err
    assert message in err


USAGE_ERRORS = [
    (
        "tests.unit_tests.no_such_module",
        "cannot import 'tests.unit_tests.no_such_module': No module named",
    ),
    (":PROVIDER", "cannot import '': Empty module name"),
    (f"{HERE}:MISSING", f"'{HERE}:MISSING': no attribute 'MISSING'"),
    (f"{HERE}:Holder.missing", f"'{HERE}:Holder.missing': no attribute 'missing'"),
    (HERE, f"'{HERE}' is not a tool provider or a factory"),
    (f"{HERE}:NOT_CALLABLE", f"'{HERE}:NOT_CALLABLE' is not a tool provider"),
]
FAILURES = [
    (
        f"{HERE}:broken_factory",
        f"'{HERE}:broken_factory': factory raised RuntimeError: boom",
        None,
    ),
    (
        f"{HERE}:not_a_provider",
        f"'{HERE}:not_a_provider': factory returned int, not a tool provider",
        None,
    ),
    (
        f"{EXAMPLE}:all_tools",
        f"'{EXAMPLE}:all_tools': factory returned tuple, not a tool provider",
        f"name the module '{EXAMPLE}' to use its all_tools",
    ),
    (
        f"{HERE}:RAISING",
        f"'{HERE}:RAISING': all_tools raised RuntimeError: backend down",
        None,
    ),
    (f"{HERE}:JUNK", f"'{HERE}:JUNK': all_tools returned int, not an OCTool", None),
]


@pytest.mark.parametrize(("spec", "message"), USAGE_ERRORS)
def test_unresolvable_spec_is_a_usage_error(capsys, spec, message):
    assert main(["list", spec]) == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert err.startswith("usage: octools list [-h]")
    assert err.splitlines()[-1].startswith(f"octools list: error: {message}")
    assert err.count("error:") == 1
    assert err.endswith("\n")


@pytest.mark.parametrize(("spec", "message", "hint"), FAILURES)
def test_unreadable_listing_exits_1(capsys, spec, message, hint):
    assert main(["list", spec]) == 1
    out, err = capsys.readouterr()
    assert out == ""
    expected = f"{message}; {hint}" if hint else message
    assert err == f"error: {expected}\n"


@pytest.mark.parametrize(
    ("spec", "message", "hint", "error_type", "code"),
    [
        *((spec, message, None, "usage", 2) for spec, message in USAGE_ERRORS),
        *((*failure, "api_failure", 1) for failure in FAILURES),
    ],
)
@pytest.mark.parametrize(
    "argv",
    [["--output-format", "json"], ["-o", "{tmp}/tools.json"]],
)
def test_json_failure_is_one_error_object(
    tmp_path, capsys, argv, spec, message, hint, error_type, code
):
    argv = [arg.replace("{tmp}", str(tmp_path)) for arg in argv]
    assert main(["list", spec, *argv]) == code
    out, err = capsys.readouterr()
    assert out == ""
    assert err.count("\n") == 1
    error = json.loads(err)["error"]
    assert list(error) == [
        "type",
        "exit_code",
        "message",
        "reason",
        "status_code",
        "details",
        "hint",
    ]
    assert error["type"] == error_type
    assert error["exit_code"] == code
    assert error["message"].startswith(message)
    assert (error["reason"], error["status_code"], error["details"]) == (
        None,
        None,
        None,
    )
    assert error["hint"] == hint
    assert list(tmp_path.iterdir()) == []


def test_keyboard_interrupt_exits_130(capsys):
    assert main(["list", f"{HERE}:interrupted"]) == 130
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("flag", ["-v", "-V", "--version"])
def test_version(capsys, flag):
    with pytest.raises(SystemExit) as excinfo:
        main([flag])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == f"octools {__version__}\n"


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["list"],
        ["list", EXAMPLE, "--output-format", "fancy"],
        ["list", EXAMPLE, "--output-format", "compact"],
        ["list", EXAMPLE, "--output-format", "detail"],
        ["list", EXAMPLE, "--style", "md"],
        ["list", EXAMPLE, "--output"],
        ["list", EXAMPLE, "--output-form", "md"],
        ["list", EXAMPLE, "--acc", "local"],
        ["list", EXAMPLE, "--access", "everywhere"],
        ["--vers"],
        ["frob", EXAMPLE],
    ],
)
def test_usage_errors_exit_2(capsys, argv):
    with pytest.raises(SystemExit) as excinfo:
        main(argv)
    assert excinfo.value.code == 2
    out, err = capsys.readouterr()
    assert out == ""
    assert "usage: octools" in err


def test_parser_conventions():
    root, listing = _parser()
    for parser in (root, listing):
        assert parser.allow_abbrev is False
        for action in parser._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            assert action.help, action.dest
            assert action.help[0].isupper(), action.help
            assert action.help.endswith("."), action.help
            assert action.help.count(". ") == 0, action.help
            if action.nargs != 0:
                assert action.metavar, action.dest
    options = {
        option: action
        for action in listing._actions
        for option in action.option_strings
    }
    access = options["--access"]
    assert (access.metavar, access.choices, access.default, access.help) == (
        "ACCESS",
        ("local", "remote"),
        None,
        "Only list tools with this access.",
    )
    assert options["-o"] is options["--output-file"]
    assert options["-o"].metavar == "PATH|-"
    assert options["--output-format"].metavar == "FORMAT"
    assert list(options["--output-format"].choices) == [*FORMATS, "markdown"]
    assert options["--no-pretty"] is options["--pretty"]
    assert "PATH|-" in listing.format_help()


def test_python_dash_m(monkeypatch, capsys):
    monkeypatch.delitem(sys.modules, "octools.__main__", raising=False)
    monkeypatch.setattr(
        sys, "argv", ["octools", "list", EXAMPLE, "--output-format", "md"]
    )
    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("octools", run_name="__main__", alter_sys=True)
    assert excinfo.value.code == 0
    assert capsys.readouterr().out == rendering("md")


def test_working_directory_is_importable(tmp_path, monkeypatch, capsys):
    (tmp_path / "local_tools.py").write_text("from octools.example import all_tools\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "path", [p for p in sys.path if p not in ("", str(tmp_path))]
    )
    monkeypatch.delitem(sys.modules, "local_tools", raising=False)
    assert main(["list", "local_tools"]) == 0
    assert sys.path[0] == str(tmp_path)
    assert capsys.readouterr().out == rendering()
