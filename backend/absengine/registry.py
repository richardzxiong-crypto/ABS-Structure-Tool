"""Generic type registry binding config models (Pydantic) to handler classes.

Everything config is data; everything behavior is a registered handler.
Adding a feature = one module that calls @REGISTRY.register("key", config_model=...).
"""

from __future__ import annotations

from typing import Any, Type


class RegistryError(Exception):
    pass


class Registry:
    def __init__(self, name: str):
        self.name = name
        self._config_models: dict[str, type] = {}
        self._handlers: dict[str, type] = {}

    def register(self, type_key: str, config_model: type):
        """Decorator: bind a handler class to a type key + config model."""

        def deco(handler_cls: type) -> type:
            if type_key in self._handlers:
                raise RegistryError(f"{self.name}: duplicate registration for {type_key!r}")
            self._config_models[type_key] = config_model
            self._handlers[type_key] = handler_cls
            return handler_cls

        return deco

    def handler_for(self, cfg: Any):
        """Instantiate the handler for a config object (uses its `type` field)."""
        type_key = getattr(cfg, "type", None)
        if type_key is None or type_key not in self._handlers:
            raise RegistryError(f"{self.name}: no handler registered for type {type_key!r}")
        return self._handlers[type_key]()

    def config_model_for(self, type_key: str) -> type:
        if type_key not in self._config_models:
            raise RegistryError(f"{self.name}: unknown type {type_key!r}")
        return self._config_models[type_key]

    @property
    def type_keys(self) -> list[str]:
        return sorted(self._config_models)

    def json_schemas(self) -> dict[str, dict]:
        """JSON schema per registered config model (drives /api/meta and dynamic UI forms)."""
        return {k: m.model_json_schema() for k, m in self._config_models.items()}
