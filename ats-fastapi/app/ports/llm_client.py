"""Port for the LLM backend. The scoring stage sends the built prompt through it to Ollama."""

from typing import Protocol

from app.pipeline.prompt import ChatMessage


class ILlmClient(Protocol):
    """Runs the chat messages through the model and returns its raw reply (Req 7).

    Raises LlmTimeoutError past the configured timeout and LlmUnavailableError when the backend is
    unreachable, errors, or does not have the configured model.
    """

    model: str

    async def complete(self, messages: list[ChatMessage], *, json_mode: bool = True) -> str:
        """Send the chat messages to the model and return its raw text reply."""
        ...

    async def check_ready(self) -> bool:
        """True when the backend is reachable and the configured model is available (Req 18.2)."""
        ...
