from __future__ import annotations
from abc import ABC, abstractmethod


class BaseExecutor(ABC):
    @abstractmethod
    def execute(self, *, conversation, message, decision, organization) -> str | None:
        """
        Execute a router decision.
        Returns the bot reply text, or None if no reply should be sent.
        """
        ...
