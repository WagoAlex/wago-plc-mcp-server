"""ponytail: one runnable check for the resolution rules. python3 test_catalog.py"""
from catalog import resolve_bundle

STD = {"wup_file": "PFC-G2.wup", "revision": "4.9.1", "release_index": "31",
       "article_numbers": ["0750-8212"], "upgrade_range": "3.0.0-4.9.99",
       "downgrade_range": "3.0.0-99.99.99"}
RED = {**STD, "wup_file": "PFC-G2-red-autoupdate.wup", "revision": "4.9.50"}
CAT = {"bundles": [STD, RED]}


def expect_error(fragment, **kw):
    try:
        resolve_bundle(**kw)
    except ValueError as e:
        assert fragment in str(e), f"expected {fragment!r} in {e}"
        return
    raise AssertionError(f"expected ValueError containing {fragment!r}")


# Fix 1: two bundles claim the same order number -> refuse, don't pick 4.9.50.
expect_error("Set TARGET_VERSION", catalog=CAT, device_order_number="0750-8212",
             current_version="04.08.09")
# ...and TARGET_VERSION resolves it.
b, d = resolve_bundle(CAT, "0750-8212", "04.08.09", "4.9.1")
assert b["wup_file"] == "PFC-G2.wup" and d == "upgrade"
# Single candidate still auto-picks, no TARGET_VERSION needed.
b, d = resolve_bundle({"bundles": [STD]}, "0750-8212", "04.08.09")
assert b["wup_file"] == "PFC-G2.wup" and d == "upgrade"
# Variant suffix on the device's order number still matches the base article.
b, _ = resolve_bundle({"bundles": [STD]}, "0750-8212/0025-0000", "04.08.09")
assert b["wup_file"] == "PFC-G2.wup"
# Guard rails that already existed.
expect_error("already at", catalog={"bundles": [STD]}, device_order_number="0750-8212",
             current_version="4.9.1")
expect_error("No bundle in catalog", catalog=CAT, device_order_number="0000-0000",
             current_version="4.9.1")
expect_error("outside this bundle's upgrade range", catalog={"bundles": [STD]},
             device_order_number="0750-8212", current_version="2.9.0")

# Same-version re-flash: refused by default, allowed explicitly, and still
# range-checked so allow_reflash cannot become a way around the guard rails.
b, d = resolve_bundle({"bundles": [STD]}, "0750-8212", "4.9.1", allow_reflash=True)
assert d == "reflash" and b["wup_file"] == "PFC-G2.wup"
expect_error("outside this bundle's upgrade range", catalog={"bundles": [STD]},
             device_order_number="0750-8212", current_version="2.9.0", allow_reflash=True)

print("catalog resolution: all checks passed")
