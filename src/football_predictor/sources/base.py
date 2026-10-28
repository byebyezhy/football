"""Capability-driven registry for independently deployable data adapters."""

from __future__ import annotations

from typing import Protocol

from football_predictor.domain import FetchContext, ResultBatch


RESULTS = "results"
FIXTURES = "fixtures"
TEAM_STATS = "team_stats"
XG = "xg"
ODDS = "odds"


class SourceAdapter(Protocol):
    name: str
    capabilities: frozenset[str]

    def fetch(self, capability: str, context: FetchContext) -> ResultBatch:
        """Return data with explicit provenance; future types will have own batches."""
        ...


class SourceRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        if not adapter.name or adapter.name in self._adapters:
            raise ValueError(f"Duplicate or invalid source: {adapter.name!r}")
        self._adapters[adapter.name] = adapter

    def sources_for(self, capability: str) -> tuple[str, ...]:
        return tuple(name for name, adapter in self._adapters.items()
                     if capability in adapter.capabilities)

    def fetch(self, name: str, capability: str, context: FetchContext) -> ResultBatch:
        adapter = self._adapters[name]
        if capability not in adapter.capabilities:
            raise ValueError(f"Source {name} does not provide {capability}")
        return adapter.fetch(capability, context)
