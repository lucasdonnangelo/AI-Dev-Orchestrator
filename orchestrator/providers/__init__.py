"""Provider package — factory, plugin registry, and re-exports."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Callable

from orchestrator.providers.base import BaseAgent
from orchestrator.providers.anthropic import ClaudeProvider
from orchestrator.providers.google import GeminiProvider
from orchestrator.providers.openai import OpenAIProvider

if TYPE_CHECKING:
    from orchestrator.config import Config

__all__ = [
    "BaseAgent",
    "ClaudeProvider",
    "GeminiProvider",
    "OpenAIProvider",
    "make_provider",
    "register_provider",
]

# ---------------------------------------------------------------------------
# Global plugin registry
# ---------------------------------------------------------------------------
# Maps a short provider name to a factory callable: (config: Config) -> BaseAgent.
# Populated via register_provider() at any time; changes take effect immediately
# on the next make_provider() call (hot-swap without restart).

_plugin_registry: dict[str, Callable[["Config"], BaseAgent]] = {}


def register_provider(name: str, factory: "Callable[[Config], BaseAgent]") -> None:
    """Register a custom provider factory under *name*.

    The *factory* callable receives the full :class:`~orchestrator.config.Config`
    object and must return a :class:`BaseAgent` instance.  This registration
    takes effect immediately — any subsequent ``make_provider(name, ...)`` call
    will use the new factory (hot-swap without restart).

    Args:
        name: Short identifier for the provider (e.g. ``"mistral"``).
              Case-insensitive; leading/trailing whitespace is ignored.
        factory: A callable ``(config: Config) -> BaseAgent`` that instantiates
                 the provider.

    Example::

        from orchestrator.providers import register_provider, BaseAgent

        class MistralProvider(BaseAgent):
            def __init__(self, config):
                self._key = config.mistral_api_key  # custom config field

            async def call(self, prompt, system=""):
                ...

        register_provider("mistral", MistralProvider)
    """
    _plugin_registry[name.lower().strip()] = factory


def _load_plugin(dotted: str, config: "Config") -> BaseAgent:
    """Dynamically import and instantiate a provider from a dotted path.

    Args:
        dotted: Fully-qualified class reference, e.g. ``"my_pkg.MyProvider"``.
        config: Passed as the sole argument to the provider's constructor.

    Returns:
        An instantiated :class:`BaseAgent`.

    Raises:
        ValueError: If *dotted* is not in ``"module.ClassName"`` format.
        ImportError: If the module cannot be imported.
        AttributeError: If the class is not found in the module.
        TypeError: If the class is not a subclass of :class:`BaseAgent`.
    """
    module_path, sep, class_name = dotted.rpartition(".")
    if not sep or not module_path or not class_name:
        raise ValueError(
            f"Invalid provider path {dotted!r}. "
            "Expected 'module.ClassName' (e.g. 'my_pkg.providers.MistralProvider')."
        )

    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ImportError(
            f"Cannot import provider module '{module_path}': {exc}. "
            "Make sure the package is installed in the current environment."
        ) from exc

    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(
            f"Module '{module_path}' has no attribute '{class_name}'."
        )
    if not (isinstance(cls, type) and issubclass(cls, BaseAgent)):
        raise TypeError(
            f"'{dotted}' must be a subclass of BaseAgent, got {cls!r}."
        )
    return cls(config)


def make_provider(provider_name: str, config: "Config") -> BaseAgent:
    """Instantiate the correct provider for the given name.

    Resolution order
    ----------------
    1. **Built-ins** — ``"anthropic"``, ``"google"``, ``"openai"``
    2. **Global registry** — providers registered via :func:`register_provider`
    3. **Config-level plugins** — ``config.plugin_providers`` dict (loaded from
       the ``providers:`` block in ``.orchestrator.yaml``)
    4. **Dotted-path import** — if *provider_name* contains a ``"."`` it is
       treated as ``"module.ClassName"`` and imported dynamically.

    Plugin providers (cases 2–4) are instantiated with ``cls(config)`` and must
    therefore accept a single :class:`~orchestrator.config.Config` argument.

    Args:
        provider_name: Provider identifier or dotted import path.
        config: Resolved orchestrator configuration.

    Returns:
        A ready-to-use :class:`BaseAgent` instance.

    Raises:
        ValueError: If the provider name is unknown or the dotted path is malformed.
        ImportError: If the required SDK / module is not installed.
        TypeError: If the resolved class is not a :class:`BaseAgent` subclass.
    """
    name = provider_name.lower().strip()

    # 1. Built-ins
    if name == "anthropic":
        return ClaudeProvider(api_key=config.api_key, model=config.model)
    if name == "google":
        return GeminiProvider(api_key=config.google_api_key, model=config.google_model)
    if name == "openai":
        return OpenAIProvider(api_key=config.openai_api_key, model=config.openai_model)

    # 2. Global registry (register_provider API)
    if name in _plugin_registry:
        return _plugin_registry[name](config)

    # 3. Config-level plugin_providers (.orchestrator.yaml `providers:` block)
    if name in config.plugin_providers:
        return _load_plugin(config.plugin_providers[name], config)

    # 4. Dotted path passed directly as the provider name
    if "." in provider_name:
        return _load_plugin(provider_name, config)

    known = ["anthropic", "google", "openai"] + list(_plugin_registry)
    raise ValueError(
        f"Unknown provider: {provider_name!r}. "
        f"Built-ins: {', '.join(known)}. "
        "To add a custom provider, use register_provider() or set "
        "'providers:' in .orchestrator.yaml."
    )
