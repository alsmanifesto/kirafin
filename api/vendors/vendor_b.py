from api.vendors.base import BaseVendor


class VendorB(BaseVendor):
    """
    VendorB mock: transfer is queued for async processing.
    In production, this would call VendorB's real API.
    """

    async def process(self, amount: float, txhash: str) -> dict:
        return {
            "status": "pending",
            "vendor": "vendorB",
            "queue_id": f"VB-QUEUE-{txhash[-6:].upper()}",
            "estimated_minutes": 15,
        }
