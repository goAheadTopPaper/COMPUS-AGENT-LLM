"""Minimal .env reader shared by CLI and frontend; values are never executed."""
from pathlib import Path


def unquote(value):
    value = value.strip()
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return value[1:-1]
    return value


def read_env(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name(".env")
    values = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            name, sep, value = line.partition("=")
            if sep and not name.lstrip().startswith("#"):
                values[name.strip()] = unquote(value)
    return values
