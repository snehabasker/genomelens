import asyncio
from typing import AsyncGenerator, Optional

from runtime import Run, current_run


class BaseAgent:
    name: str = "base"

    @property
    def rt(self) -> Optional[Run]:
        return current_run.get()

    async def evidence(self, source: str, title: str, text: str, url: str = "") -> Optional[dict]:
        """Register a citable fact for the synthesis step (no-op outside an analysis)."""
        rt = self.rt
        return await rt.register(source, title, text, url) if rt else None

    def failed(self, *sources: str) -> dict:
        """Which of `sources` failed during this run -> {source: reason}."""
        rt = self.rt
        if not (rt and rt.features.honest_errors):
            return {}      # v0 behaviour: an outage looks exactly like "nothing found"
        return {s: rt.failed_sources[s] for s in sources if s in rt.failed_sources}

    async def safe(self, coro, default, timeout: Optional[float] = None, source: str = ""):
        """Await a data-source call. With honest_errors on, a failing source degrades only itself
        (it is already recorded in run.failed_sources); in v0 the exception aborted the whole agent."""
        try:
            return await (asyncio.wait_for(coro, timeout) if timeout else coro)
        except asyncio.TimeoutError:
            if self.rt and source:
                self.rt.fail_source(source, f"no answer within {timeout:.0f}s")
            if not (self.rt and self.rt.features.honest_errors):
                raise
            return default
        except Exception:
            if not (self.rt and self.rt.features.honest_errors):
                raise
            return default

    def evt(self, event_type: str, **data) -> dict:
        return {"type": event_type, "agent": self.name, "data": data}

    def start(self, message: str = "") -> dict:
        return {"type": "agent_start", "agent": self.name, "data": {"message": message}}

    def progress(self, message: str) -> dict:
        return {"type": "agent_progress", "agent": self.name, "data": {"message": message}}

    def done(self) -> dict:
        return {"type": "agent_done", "agent": self.name, "data": {}}

    def error(self, msg: str) -> dict:
        return {"type": "agent_error", "agent": self.name, "data": {"error": msg}}

    async def run(self, **kwargs) -> AsyncGenerator[dict, None]:
        raise NotImplementedError
        yield  # make it an async generator
