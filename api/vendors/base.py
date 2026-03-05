from abc import ABC, abstractmethod


class BaseVendor(ABC):
    """
    All vendors must implement this interface.
    Adding a new vendor = subclass this + register in __init__.py.
    """

    @abstractmethod
    async def process(self, amount: float, txhash: str) -> dict:
        """
        Process a transfer request.
        Returns a dict with at minimum {"status": "..."}
        """
        ...
