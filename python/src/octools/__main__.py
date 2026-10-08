"""Command line entry point: ``octools list SPEC`` prints a tool listing.

``SPEC`` is ``package.module`` or ``package.module:attr`` (``attr`` may be
dotted). The target is used as the provider when it exposes ``all_tools``;
otherwise it is called with no arguments and the result must. The working
directory is importable, as it is under ``python -m``.

Exit codes: ``0`` success; ``1`` the listing could not be read (a factory or
``all_tools`` raised or returned the wrong type) or written; ``2`` a usage
error, including a SPEC that does not import, lacks an attribute or names
neither a provider nor a callable; ``130`` interrupted. A failure prints one
``error: <message>`` line on stderr, or one JSON error object when the
output format is ``json``, and nothing on stdout.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from octools import __version__
from octools.descriptor import Access, OCTool, ToolProvider
from octools.listing import LISTING_STYLES, ListingStyle, render_listing

STDOUT = "-"
_FORMAT_ALIASES: dict[str, ListingStyle] = {"markdown": "md"}
_FORMAT_CHOICES = (*LISTING_STYLES, *_FORMAT_ALIASES)
_EXTENSION_FORMATS: dict[str, ListingStyle] = {
    ".md": "md",
    ".markdown": "md",
    ".json": "json",
    ".txt": "txt",
}
_DEFAULT_FORMAT: ListingStyle = "table"
_EXIT_FAILURE = 1
_EXIT_USAGE = 2
_EXIT_INTERRUPTED = 130
ErrorType = Literal["usage", "api_failure"]


class _CliError(Exception):
    """A failure reported as ``error: <message>`` or a JSON error object."""

    error_type: ErrorType = "api_failure"
    exit_code = _EXIT_FAILURE

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        """Keep the one-line ``message`` and an optional ``hint``."""
        super().__init__(message)
        self.message = message
        self.hint = hint

    def text(self) -> str:
        """Return the message with the hint appended after a semicolon."""
        return f"{self.message}; {self.hint}" if self.hint else self.message


class _SpecUsageError(_CliError):
    """A SPEC that does not name an importable provider or factory."""

    error_type: ErrorType = "usage"
    exit_code = _EXIT_USAGE


@dataclass(frozen=True)
class _Listed:
    """A provider over tools already read from the provider SPEC names."""

    tools: tuple[OCTool, ...]

    def all_tools(self) -> tuple[OCTool, ...]:
        """Return the tools read once from the named provider."""
        return self.tools


def _output_file(value: str) -> str:
    """Accept ``-`` or a file path whose parent directory exists and is writable.

    Raises ``argparse.ArgumentTypeError`` otherwise, which argparse reports as
    a usage error with exit code 2.
    """
    if value == STDOUT:
        return value
    path = Path(value)
    if path.is_dir():
        raise argparse.ArgumentTypeError(f"{value!r} is a directory, not a file")
    parent = path.parent
    if not parent.is_dir():
        raise argparse.ArgumentTypeError(f"directory {str(parent)!r} does not exist")
    if not os.access(parent, os.W_OK):
        raise argparse.ArgumentTypeError(f"directory {str(parent)!r} is not writable")
    return value


def _parser() -> tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    """Build the ``octools`` parser; return it and its ``list`` subparser."""
    parser = argparse.ArgumentParser(
        prog="octools", description="Inspect OCTool providers.", allow_abbrev=False
    )
    parser.add_argument(
        "-v",
        "-V",
        "--version",
        action="version",
        version=f"octools {__version__}",
        help="Print the octools version and exit.",
    )
    commands = parser.add_subparsers(
        title="commands",
        metavar="COMMAND",
        dest="command",
        required=True,
        help="The command to run.",
    )
    listing = commands.add_parser(
        "list",
        help="Print a provider's tool listing.",
        description="Print a provider's tool listing.",
        allow_abbrev=False,
    )
    listing.add_argument(
        "spec",
        metavar="SPEC",
        help=(
            "A module, a module:attr object or a zero-argument factory that "
            "lists tools."
        ),
    )
    listing.add_argument(
        "--access",
        dest="access",
        metavar="ACCESS",
        choices=("local", "remote"),
        default=None,
        help="Only list tools with this access.",
    )
    listing.add_argument(
        "-o",
        "--output-file",
        metavar="PATH|-",
        type=_output_file,
        default=STDOUT,
        help="Write the listing to this file, or to stdout for - or when omitted.",
    )
    listing.add_argument(
        "--output-format",
        metavar="FORMAT",
        choices=_FORMAT_CHOICES,
        default=None,
        help=(
            "Render as table, md (alias markdown), txt or json, inferred from "
            "the output file extension when omitted and table otherwise."
        ),
    )
    listing.add_argument(
        "--pretty",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Indent json output, by default only when stdout is a terminal.",
    )
    return parser, listing


def _output_format(explicit: str | None, output_file: str) -> ListingStyle:
    """Return the explicit format, else the one ``output_file`` implies."""
    if explicit is not None:
        return _FORMAT_ALIASES.get(explicit, cast(ListingStyle, explicit))
    if output_file == STDOUT:
        return _DEFAULT_FORMAT
    return _EXTENSION_FORMATS.get(Path(output_file).suffix.lower(), _DEFAULT_FORMAT)


def _is_provider(target: object) -> bool:
    """Return whether ``target`` is a provider instance or module, not a class."""
    return not isinstance(target, type) and isinstance(target, ToolProvider)


def _resolve_provider(spec: str) -> ToolProvider:
    """Import ``spec`` and return the provider it names or builds.

    Raises ``_SpecUsageError`` when the module does not import, an attribute
    is missing, or the target is neither a provider nor callable, and
    ``_CliError`` when a factory raises or returns something else.
    """
    module_name, _, attr = spec.partition(":")
    try:
        target: object = importlib.import_module(module_name)
    except Exception as exc:
        raise _SpecUsageError(f"cannot import {module_name!r}: {exc}") from exc
    for part in attr.split(".") if attr else ():
        try:
            target = getattr(target, part)
        except AttributeError as exc:
            raise _SpecUsageError(f"{spec!r}: no attribute {part!r}") from exc
    if _is_provider(target):
        return cast(ToolProvider, target)
    if not callable(target):
        raise _SpecUsageError(f"{spec!r} is not a tool provider or a factory")
    try:
        built = target()
    except Exception as exc:
        raise _CliError(
            f"{spec!r}: factory raised {type(exc).__name__}: {exc}"
        ) from exc
    if not _is_provider(built):
        message = (
            f"{spec!r}: factory returned {type(built).__name__}, not a tool provider"
        )
        hint = None
        if isinstance(built, Sequence) and not isinstance(built, str):
            hint = f"name the module {module_name!r} to use its all_tools"
        raise _CliError(message, hint=hint)
    return cast(ToolProvider, built)


def _read_tools(spec: str, provider: ToolProvider) -> _Listed:
    """Call ``all_tools`` once and check every item is an ``OCTool``.

    Raises ``_CliError`` when ``all_tools`` raises or returns something else.
    """
    try:
        tools = tuple(provider.all_tools())
    except Exception as exc:
        raise _CliError(
            f"{spec!r}: all_tools raised {type(exc).__name__}: {exc}"
        ) from exc
    for tool in tools:
        if not isinstance(tool, OCTool):
            raise _CliError(
                f"{spec!r}: all_tools returned {type(tool).__name__}, not an OCTool"
            )
    return _Listed(tools)


def _write_atomically(path: str, text: str) -> None:
    """Write ``text`` as UTF-8 to ``path`` through a temp file and ``os.replace``.

    Raises ``_CliError`` when the file cannot be written; the temp file is
    removed and an existing ``path`` is left as it was.
    """
    target = Path(path)
    fd, temp = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(temp, target)
    except OSError as exc:
        Path(temp).unlink(missing_ok=True)
        raise _CliError(f"cannot write {path!r}: {exc}") from exc


def _report(
    error: _CliError, *, as_json: bool, listing: argparse.ArgumentParser
) -> int:
    """Print ``error`` on stderr in the format in effect; return its exit code."""
    if as_json:
        body = {
            "type": error.error_type,
            "exit_code": error.exit_code,
            "message": error.message,
            "reason": None,
            "status_code": None,
            "details": None,
            "hint": error.hint,
        }
        sys.stderr.write(json.dumps({"error": body}) + "\n")
    elif error.error_type == "usage":
        sys.stderr.write(listing.format_usage())
        sys.stderr.write(f"{listing.prog}: error: {error.text()}\n")
    else:
        sys.stderr.write(f"error: {error.text()}\n")
    return error.exit_code


def _run(args: argparse.Namespace, listing: argparse.ArgumentParser) -> int:
    """List the provider ``args.spec`` names; report failures on stderr."""
    output_file = cast(str, args.output_file)
    style = _output_format(cast(str | None, args.output_format), output_file)
    pretty = cast(bool | None, args.pretty)
    if pretty is None:
        pretty = output_file == STDOUT and sys.stdout.isatty()
    if os.getcwd() not in sys.path and "" not in sys.path:
        sys.path.insert(0, os.getcwd())
    try:
        provider = _read_tools(args.spec, _resolve_provider(args.spec))
        text = render_listing(
            provider,
            style=style,
            access=cast(Access | None, args.access),
            pretty=pretty,
        )
        if output_file == STDOUT:
            sys.stdout.write(text)
        else:
            _write_atomically(output_file, text)
    except _CliError as error:
        return _report(error, as_json=style == "json", listing=listing)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code: 0, 1, 2 or 130."""
    parser, listing = _parser()
    try:
        return _run(parser.parse_args(argv), listing)
    except KeyboardInterrupt:
        return _EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
