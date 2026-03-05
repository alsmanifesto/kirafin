from abc import ABC, abstractmethod
from api.vendors.vendor_a import VendorA
from api.vendors.vendor_b import VendorB

# ─── Vendor registry ──────────────────────────────────────────────────────────
# To add vendorC: create api/vendors/vendor_c.py, subclass BaseVendor,
# then register it here with one line. Zero other changes required.
VENDOR_REGISTRY: dict = {
    "vendorA": VendorA(),
    "vendorB": VendorB(),
    # "vendorC": VendorC(),  ← adding a new vendor is this simple
}


def get_vendor(name: str):
    if name not in VENDOR_REGISTRY:
        raise KeyError(f"Vendor '{name}' not registered")
    return VENDOR_REGISTRY[name]
