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

# Minimum-build floors: a per-hardware constraint the bundle's own version
# range does not express.
from catalog import check_minimum_build, minimum_build_for  # noqa: E402

assert minimum_build_for("0750-8302") == 30, "PFC300 needs build 30"
assert minimum_build_for("0751-9401") == 28
assert minimum_build_for("0750-8212/0025-0000") == 28, "variant suffix must not defeat the lookup"
assert check_minimum_build("0750-8302", "31") == 31
assert check_minimum_build("0751-9401", 28) == 28, "exactly at the floor is allowed"

expect_error_msg = None
try:
    check_minimum_build("0750-8302", "28")
except ValueError as e:
    expect_error_msg = str(e)
assert expect_error_msg and "below the minimum 30" in expect_error_msg, expect_error_msg

try:
    check_minimum_build("0751-9401", "27")
except ValueError as e:
    assert "below the minimum 28" in str(e)
else:
    raise AssertionError("build 27 must be refused")

try:
    check_minimum_build("0751-9401", None)
except ValueError as e:
    assert "cannot read the device's firmware build" in str(e)
else:
    raise AssertionError("an unreadable build must be refused, not assumed good")

# The modem variant gets a useful hint instead of a bare "set TARGET_VERSION".
MODEM_STD = {**STD, "article_numbers": ["0750-8212", "0750-8217"]}
MODEM_CAT = {"bundles": [MODEM_STD, {**MODEM_STD, "wup_file": "PFC-G2-red-autoupdate.wup",
                                     "revision": "4.9.50"}]}
try:
    resolve_bundle(MODEM_CAT, "0750-8217", "04.08.09")
except ValueError as e:
    assert "modem variant" in str(e) and "4.9.50" in str(e), str(e)
else:
    raise AssertionError("0750-8217 matches two bundles and must refuse")

print("minimum-build and modem-variant checks: all passed")
