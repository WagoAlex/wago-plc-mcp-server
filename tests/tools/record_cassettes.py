"""TT5 capture helper — dump live WDA responses into the cassette layout.

Usage during TT5 live runs
───────────────────────────
    from tests.tools.record_cassettes import record_class

    # Inside a pytest-asyncio test marked @pytest.mark.live:
    await record_class(
        ip="10.0.0.110",
        username="admin",
        password=os.environ["PLC_PASSWORD"],
        plc_class="cc100",
        out_dir=Path("tests/cassettes"),
    )

The helper fetches every relevant WDA endpoint, scrubs sensitive data, and
writes one JSON file per endpoint under ``out_dir/<plc_class>/``.

Scrubbing
─────────
``scrub(blob)`` is a pure function (no I/O) so it can be unit-tested without
hardware.  It replaces any dict value whose key matches a sensitive pattern
with a placeholder string.  Operates recursively through nested dicts and
lists.

Patterns scrubbed
~~~~~~~~~~~~~~~~~
- Keys containing: password, token, serial, ordernumber, order_number,
  hostname, Authorization (case-insensitive)
- Keys whose value looks like a bearer JWT (starts with "ey")
- Specific top-level WDA fields: ``hostname`` inside attributes, ``orderNumber``

The scrubber never removes keys — it replaces values with ``"REDACTED"`` so
the shape is preserved for shape-testing.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

# ── sensitive key patterns ────────────────────────────────────────────────────

_SENSITIVE_KEYS: re.Pattern = re.compile(
    r"password|token|serial|ordernumber|order_number|hostname|authorization",
    re.IGNORECASE,
)

_BEARER_RE: re.Pattern = re.compile(r"^ey[A-Za-z0-9_-]{10,}")

_REDACTED = "REDACTED"


def scrub(blob: Any) -> Any:
    """Recursively scrub sensitive data from a decoded JSON structure.

    Returns a new object — the input is never mutated.

    Rules
    ─────
    1. If *blob* is a dict, iterate key/value pairs:
       a. If the key matches ``_SENSITIVE_KEYS``, replace the value with
          ``"REDACTED"`` (recurse into nested dicts/lists first for shape).
       b. If the value is a string that looks like a JWT bearer token, replace
          it with ``"REDACTED"`` regardless of key name.
       c. Otherwise recurse into the value.
    2. If *blob* is a list, recurse into each element.
    3. Scalars pass through unchanged.
    """
    if isinstance(blob, dict):
        result: dict[str, Any] = {}
        for k, v in blob.items():
            if _SENSITIVE_KEYS.search(k):
                # Replace the value but recurse for nested structure shape.
                result[k] = _REDACTED
            elif isinstance(v, str) and _BEARER_RE.match(v):
                result[k] = _REDACTED
            else:
                result[k] = scrub(v)
        return result

    if isinstance(blob, list):
        return [scrub(item) for item in blob]

    return blob


# ── cassette writer ───────────────────────────────────────────────────────────


def _cassette(
    *,
    plc_class: str,
    firmware: str,
    note: str,
    status: int,
    headers: dict[str, str],
    body: Any,
) -> dict:
    """Build a cassette dict in the standard shape."""
    return {
        "_meta": {
            "class": plc_class,
            "firmware": firmware,
            "recorded": "live",
            "note": note,
        },
        "status": status,
        "headers": headers,
        "body": body,
    }


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        json.dump(data, fh, indent=2)
    print(f"  wrote {path}")


# ── live recording (requires httpx + a reachable PLC) ────────────────────────


async def record_class(
    ip: str,
    username: str,
    password: str,
    plc_class: str,
    out_dir: Path,
    page_limit: int = 500,
    ssl_verify: bool = False,
) -> None:
    """Fetch every WDA endpoint and write scrubbed cassettes to *out_dir/<plc_class>/*.

    Requires a live PLC at *ip*.  Credentials are used only in-flight and are
    NOT written to any file (the scrubber removes them from response bodies).

    Cassettes produced
    ──────────────────
    service_identity.json   GET /wda
    parameters_page*.json   GET /wda/parameters (one file per page)
    parameter_definitions.json
    devices.json
    features.json
    methods.json
    enum_definitions.json
    monitoring_list.json    (create + immediate read with ?include=parameters)
    """
    import httpx  # only needed when running live

    base = f"https://{ip}"
    auth = (username, password)
    headers_base = {"Accept": "application/vnd.api+json"}
    class_dir = out_dir / plc_class

    async with httpx.AsyncClient(verify=ssl_verify) as client:

        # ── service identity ──────────────────────────────────────────────────
        r = await client.get(f"{base}/wda", auth=auth, headers=headers_base)
        r.raise_for_status()
        resp_headers = dict(r.headers)
        firmware = r.json().get("data", {}).get("attributes", {}).get("firmware", "unknown")

        _write(
            class_dir / "service_identity.json",
            _cassette(
                plc_class=plc_class,
                firmware=firmware,
                note="GET /wda — service identity + auth token header",
                status=r.status_code,
                headers=scrub(resp_headers),
                body=scrub(r.json()),
            ),
        )

        # Derive bearer token if provided.
        token = resp_headers.get("wago-wdx-auth-token") or resp_headers.get("WAGO-WDX-Auth-Token")
        if token:
            headers_base = {**headers_base, "Authorization": f"Bearer {token}"}

        # ── paginated helper ──────────────────────────────────────────────────

        async def _fetch_pages(path: str, base_name: str) -> list[dict]:
            """Fetch all pages and write one cassette per page.  Returns all items."""
            all_items: list[dict] = []
            sep = "&" if "?" in path else "?"
            next_url: str | None = (
                f"{base}{path}{sep}page[limit]={page_limit}&page[offset]=0"
            )
            page_num = 1
            while next_url:
                r2 = await client.get(next_url, auth=auth, headers=headers_base)
                r2.raise_for_status()
                body2 = r2.json()
                all_items.extend(body2.get("data", []))

                suffix = f"_page{page_num}" if page_num > 1 else "_page1"
                # Always use _page1 suffix for consistency.
                file_name = f"{base_name}{suffix}.json"

                _write(
                    class_dir / file_name,
                    _cassette(
                        plc_class=plc_class,
                        firmware=firmware,
                        note=f"{next_url} (page {page_num})",
                        status=r2.status_code,
                        headers=dict(r2.headers),
                        body=scrub(body2),
                    ),
                )
                next_url = body2.get("links", {}).get("next")
                page_num += 1
            return all_items

        # ── single-page helper ────────────────────────────────────────────────

        async def _fetch_single(path: str, file_name: str, note: str) -> dict:
            url = f"{base}{path}?page[limit]={page_limit}&page[offset]=0"
            r3 = await client.get(url, auth=auth, headers=headers_base)
            r3.raise_for_status()
            data = _cassette(
                plc_class=plc_class,
                firmware=firmware,
                note=note,
                status=r3.status_code,
                headers=dict(r3.headers),
                body=scrub(r3.json()),
            )
            _write(class_dir / file_name, data)
            return r3.json()

        # ── fetch all resources ───────────────────────────────────────────────

        await _fetch_pages(
            "/wda/parameters?parameter-errors-as-data-attributes=true",
            "parameters",
        )
        await _fetch_single(
            "/wda/parameter-definitions", "parameter_definitions.json",
            "GET /wda/parameter-definitions",
        )
        await _fetch_single("/wda/devices", "devices.json", "GET /wda/devices")
        await _fetch_single("/wda/features", "features.json", "GET /wda/features")
        await _fetch_single("/wda/methods", "methods.json", "GET /wda/methods")
        await _fetch_single(
            "/wda/enum-definitions", "enum_definitions.json",
            "GET /wda/enum-definitions",
        )

        # ── monitoring-list: create + read ────────────────────────────────────
        # Use the first parameter ID available from the parameters page.
        params_r = await client.get(
            f"{base}/wda/parameters?page[limit]=1&page[offset]=0",
            auth=auth,
            headers=headers_base,
        )
        params_r.raise_for_status()
        first_params = params_r.json().get("data", [])
        if first_params:
            pid = first_params[0]["id"]
            payload = {
                "data": {
                    "type": "monitoring-lists",
                    "attributes": {"timeout": 60},
                    "relationships": {
                        "parameters": {"data": [{"id": pid, "type": "parameters"}]}
                    },
                }
            }
            create_r = await client.post(
                f"{base}/wda/monitoring-lists?parameter-errors-as-data-attributes=true",
                auth=auth,
                headers={**headers_base, "Content-Type": "application/vnd.api+json"},
                json=payload,
            )
            create_r.raise_for_status()
            ml_id = create_r.json().get("data", {}).get("id")

            if ml_id:
                get_r = await client.get(
                    f"{base}/wda/monitoring-lists/{ml_id}",
                    auth=auth,
                    headers=headers_base,
                    params={
                        "include": "parameters",
                        "parameter-errors-as-data-attributes": "true",
                    },
                )
                get_r.raise_for_status()

                ml_cassette: dict = {
                    "_meta": {
                        "class": plc_class,
                        "firmware": firmware,
                        "recorded": "live",
                        "note": "POST /wda/monitoring-lists + GET with ?include=parameters",
                    },
                    "create_status": create_r.status_code,
                    "create_headers": scrub(dict(create_r.headers)),
                    "create_body": scrub(create_r.json()),
                    "get_status": get_r.status_code,
                    "get_headers": dict(get_r.headers),
                    "get_body": scrub(get_r.json()),
                }
                _write(class_dir / "monitoring_list.json", ml_cassette)

                # Clean up.
                await client.delete(
                    f"{base}/wda/monitoring-lists/{ml_id}",
                    auth=auth,
                    headers=headers_base,
                )
