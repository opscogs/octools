<!-- Generated from .cursor/rules/no-extra-blank-lines.mdc by scripts/sync_claude_config.py; edit the source. -->

# Blank lines in generated code

When writing or editing code, use **only the required blank lines**. Do not add extra blank lines for visual separation or "breathing room." This keeps more code visible on screen.

## Required blank lines (Python / PEP 8)

- **Top-level**: At most **two** blank lines between top-level definitions (classes, functions).
- **Inside a class**: At most **one** blank line between methods.
- **Inside a function**: Use a single blank line only when it meaningfully separates logical blocks (e.g. a distinct step). Omit blank lines between a few related statements.

## Do not add

- Multiple blank lines in a row (e.g. 3+ between sections).
- Blank lines before every comment or block "for readability."
- Extra blank lines at the start or end of functions/classes beyond what’s above.

## Example

```python
# Prefer: minimal required blank lines
def foo():
    x = 1
    y = 2
    return x + y

def bar():
    return 3
```

```python
# Avoid: unnecessary extra blank lines
def foo():

    x = 1

    y = 2

    return x + y


def bar():

    return 3
```

Run `ruff format` and `ruff check --fix` to normalize existing files; when generating new code, follow these rules from the start.

