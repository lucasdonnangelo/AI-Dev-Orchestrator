from __future__ import annotations


def hello(name: str) -> str:
    """Return a greeting string for the given name.

    Args:
        name: The name to greet. Can be any string, including empty.

    Returns:
        A greeting in the format 'Hello, {name}!'
    """
    return f"Hello, {name}!"
