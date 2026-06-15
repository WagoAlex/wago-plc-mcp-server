"""Registry of WDA-capable PLCs. Caches definitions + enums for rich introspection."""
import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from loguru import logger
from wda_client import WDAClient


@dataclass
class PLCEntry:
    ip: str
    client: WDAClient

    # Resource ID sets (cheap membership checks)
    parameters: set[str] = field(default_factory=set)
    devices: set[str] = field(default_factory=set)
    features: set[str] = field(default_factory=set)
    methods: set[str] = field(default_factory=set)

    # Device identity (from first /wda/devices entry)
    device_name: str = ""   # e.g. "PFC200 G2"
    device_class: str = ""  # "CC100" | "PFC200" | "PFC300" | "Edge" | ""

    # Rich metadata for smart agent behavior
    param_path: dict[str, str] = field(default_factory=dict)        # id → human path
    param_writeable: set[str] = field(default_factory=set)
    param_user_setting: set[str] = field(default_factory=set)
    param_to_enum: dict[str, str] = field(default_factory=dict)     # id → enum_id
    enum_cases: dict[str, list[dict]] = field(default_factory=dict) # enum_id → [{value, stringValue}]
    enum_name: dict[str, str] = field(default_factory=dict)         # enum_id → name


def _extract_enum_id(pdef: dict) -> str | None:
    """Find the related enum-definition ID, robust to data/link forms."""
    rel = pdef.get("relationships", {}).get("enum")
    if not rel:
        return None
    data = rel.get("data")
    if isinstance(data, dict) and "id" in data:
        return data["id"]
    link = (rel.get("links") or {}).get("related", "")
    if "/enum-definitions/" in link:
        return link.rsplit("/enum-definitions/", 1)[-1].split("?")[0]
    return None


# Expected parameter counts per device class at FW build 31 (WDA 1.5.2).
# Used by describe_plc to flag incomplete sweeps.
KNOWN_PARAM_COUNTS: dict[str, int] = {
    "CC100": 360,
    "PFC200": 398,
    "PFC300": 393,
    "Edge": 394,
}


def _infer_device_class(name: str) -> str:
    """Map the WDA device name string to a normalised class label."""
    n = name.upper()
    if "CC100" in n:
        return "CC100"
    if "PFC300" in n:
        return "PFC300"
    if "PFC200" in n:
        return "PFC200"
    if "EDGE" in n or n.startswith("EC"):
        return "Edge"
    return ""


class PLCManager:
    def __init__(
        self,
        timeout_seconds: float = 5.0,
        page_limit: int = 500,
        max_concurrent_registrations: int = 5,
        ssl_verify: bool | str = False,
    ):
        self.plcs: dict[str, PLCEntry] = {}
        self.timeout_seconds = timeout_seconds
        self.page_limit = page_limit
        self.max_concurrent_registrations = max_concurrent_registrations
        self.ssl_verify = ssl_verify
        self._lock = asyncio.Lock()

    async def register(self, ip: str, username: str, password: str) -> PLCEntry | None:
        # Per-PLC cert pinning: Docker Secret plc_cert_<ip_underscored> overrides global ssl_verify
        cert_secret = Path(f"/run/secrets/plc_cert_{ip.replace('.', '_')}")
        verify: bool | str = str(cert_secret) if cert_secret.exists() else self.ssl_verify

        client = WDAClient(
            ip,
            username,
            password,
            timeout=self.timeout_seconds,
            page_limit=self.page_limit,
            ssl_verify=verify,
        )

        probe = await client.ping()
        if not probe["ok"]:
            logger.warning(f"[{ip}] skipped — {probe['reason']}")
            await client.close()
            return None

        entry = PLCEntry(ip=ip, client=client)
        if not await self._cache_resources(entry):
            logger.warning(
                f"[{ip}] skipped — essential cache failed (parameters or methods unreachable)"
            )
            await client.close()
            return None

        async with self._lock:
            self.plcs[ip] = entry

        logger.info(
            f"[{ip}] registered — params={len(entry.parameters)} "
            f"(w={len(entry.param_writeable)}, us={len(entry.param_user_setting)}) "
            f"devices={len(entry.devices)} features={len(entry.features)} "
            f"methods={len(entry.methods)} enums={len(entry.enum_cases)}"
        )
        return entry

    async def _cache_resources(self, entry: PLCEntry) -> bool:
        """Fetch everything in parallel. Returns False if essential resources
        (parameters AND methods) could not be loaded — caller should reject the PLC.
        """
        c = entry.client
        params, devices, features, methods, param_defs, enum_defs = await asyncio.gather(
            c.list_parameters(),
            c.list_devices(),
            c.list_features(),
            c.list_methods(),
            c.list_parameter_definitions(),
            c.list_enum_definitions(),
            return_exceptions=True,
        )

        # Essential gate: parameters list MUST succeed (any error or empty = unusable)
        if isinstance(params, Exception):
            logger.warning(
                f"[{entry.ip}] essential 'parameters' cache failed: "
                f"{type(params).__name__}: {str(params) or 'no detail'}"
            )
            return False
        if not params:
            logger.warning(f"[{entry.ip}] parameters list empty — PLC reports no parameters")
            return False

        # Methods is also considered essential for invoke_method to work
        if isinstance(methods, Exception):
            logger.warning(
                f"[{entry.ip}] essential 'methods' cache failed: "
                f"{type(methods).__name__}: {str(methods) or 'no detail'}"
            )
            return False

        # Simple ID sets (now safe to assign)
        entry.parameters = {item["id"] for item in params if "id" in item}
        entry.methods = {item["id"] for item in methods if "id" in item}

        # Device identity from first /wda/devices entry (non-essential)
        if not isinstance(devices, Exception) and devices:
            first_name = devices[0].get("attributes", {}).get("name", "")
            entry.device_name = first_name
            entry.device_class = _infer_device_class(first_name)

        # Non-essential — log warning but keep PLC
        for attr, result in (("devices", devices), ("features", features)):
            if isinstance(result, Exception):
                logger.warning(
                    f"[{entry.ip}] {attr} cache failed (non-essential): "
                    f"{type(result).__name__}: {str(result) or 'no detail'}"
                )
                continue
            setattr(entry, attr, {item["id"] for item in result if "id" in item})

        # Enum definitions (non-essential, degrades gracefully)
        if not isinstance(enum_defs, Exception):
            for edef in enum_defs:
                eid = edef.get("id")
                if not eid:
                    continue
                attrs = edef.get("attributes", {})
                entry.enum_name[eid] = attrs.get("name", eid)
                entry.enum_cases[eid] = attrs.get("cases", [])
        else:
            logger.warning(
                f"[{entry.ip}] enum_defs cache failed (non-essential): "
                f"{type(enum_defs).__name__}: {str(enum_defs) or 'no detail'}"
            )

        # Parameter definitions (non-essential; without these, writeable-validation is lost)
        if not isinstance(param_defs, Exception):
            for pdef in param_defs:
                pid = pdef.get("id")
                if not pid:
                    continue
                attrs = pdef.get("attributes", {})
                if attrs.get("path"):
                    entry.param_path[pid] = attrs["path"]
                if attrs.get("writeable"):
                    entry.param_writeable.add(pid)
                if attrs.get("userSetting"):
                    entry.param_user_setting.add(pid)
                eid = _extract_enum_id(pdef)
                if eid:
                    entry.param_to_enum[pid] = eid
        else:
            logger.warning(
                f"[{entry.ip}] param_defs cache failed (non-essential, writeable-validation degraded): "
                f"{type(param_defs).__name__}: {str(param_defs) or 'no detail'}"
            )

        return True

    async def register_many(
        self, plcs: list[tuple[str, str, str]]
    ) -> tuple[list[str], list[str]]:
        """Register PLCs with bounded concurrency. Prevents HTTPS pool saturation
        and slow SSL handshakes from triggering ReadTimeouts cascade-style."""
        sem = asyncio.Semaphore(self.max_concurrent_registrations)

        async def task(ip: str, user: str, pwd: str) -> tuple[str, bool]:
            async with sem:
                entry = await self.register(ip, user, pwd)
                return ip, entry is not None

        results = await asyncio.gather(*[task(*p) for p in plcs])
        ok = [ip for ip, success in results if success]
        failed = [ip for ip, success in results if not success]
        return ok, failed

    def get(self, ip: str) -> PLCEntry | None:
        return self.plcs.get(ip)

    def list_ips(self) -> list[str]:
        return sorted(self.plcs.keys())

    async def close_all(self) -> None:
        await asyncio.gather(
            *(e.client.close() for e in self.plcs.values()),
            return_exceptions=True,
        )
