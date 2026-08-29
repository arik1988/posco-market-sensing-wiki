"""Market Sensing API package with an optional Deep Agent runtime."""

from typing import Any

__all__ = ["ResearchRequest", "run_research"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .service import ResearchRequest, run_research

        return {"ResearchRequest": ResearchRequest, "run_research": run_research}[name]
    raise AttributeError(name)
