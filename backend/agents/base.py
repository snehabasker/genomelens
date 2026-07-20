from typing import AsyncGenerator


class BaseAgent:
    name: str = "base"

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
