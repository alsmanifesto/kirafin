from api.vendors.base import BaseVendor


class VendorA(BaseVendor):
    """
    VendorA mock: immediately confirms the transfer.
    In production, this would call VendorA's real API.
    """

    async def process(self, amount: float, txhash: str) -> dict:
        return {
            "status": "success",
            "vendor": "vendorA",
            "reference_id": f"VA-{txhash[-8:].upper()}",
            "amount_cop": round(amount * 4150, 2),  # mock USDC → COP rate
        }
