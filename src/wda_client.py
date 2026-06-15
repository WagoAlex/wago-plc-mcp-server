"""Thin async wrapper around the WAGO WDA/WDX REST API (v1.4.1)."""
import asyncio
from typing import Any

import httpx
from loguru import logger


class WDAClient:
    """One client per PLC. All endpoints under /wda/*.

    Auth strategy: first request uses Basic Auth and caches the returned
    WAGO-WDX-Auth-Token as a Bearer token. All subsequent requests use Bearer.
    On 401 the token is refreshed once with Basic Auth before failing.
    ping() always uses Basic Auth (it is the auth probe itself).
    """

    JSON_API = "application/vnd.api+json"
    DEFAULT_PAGE_LIMIT = 500

    def __init__(
        self,
        ip: str,
        username: str,
        password: str,
        timeout: float = 5.0,
        page_limit: int = DEFAULT_PAGE_LIMIT,
        ssl_verify: bool | str = False,
    ):
        self.ip = ip
        self.username = username
        self.password = password
        self.page_limit = page_limit
        self.client = httpx.AsyncClient(
            base_url=f"https://{ip}",
            verify=ssl_verify,
            timeout=timeout,
            headers={"Accept": self.JSON_API},
        )
        # None = not yet fetched; "" = WDA has no Bearer support → Basic Auth only
        self._token: str | None = None
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        await self.client.aclose()

    async def _acquire_token(self) -> None:
        """Authenticate with Basic Auth and cache the returned Bearer token.

        Must be called while holding self._lock.
        """
        r = await self.client.get("/wda", auth=(self.username, self.password))
        if r.status_code == 401:
            raise httpx.HTTPStatusError(
                "WDA Basic Auth failed — check credentials",
                request=r.request,
                response=r,
            )
        r.raise_for_status()
        token = r.headers.get("WAGO-WDX-Auth-Token")
        if token:
            self._token = token
            logger.info(f"[{self.ip}] WDA token acquired")
        else:
            self._token = ""  # WDA does not issue Bearer tokens — stay on Basic Auth
            logger.info(f"[{self.ip}] WDA Bearer auth not supported — using Basic Auth")

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Send an authenticated request; refresh Bearer token reactively on 401."""
        if self._token is None:
            async with self._lock:
                if self._token is None:
                    await self._acquire_token()

        req_headers: dict = kwargs.pop("headers", {})

        if self._token:
            req_headers["Authorization"] = f"Bearer {self._token}"
            r = await self.client.request(method, url, headers=req_headers, **kwargs)
            if r.status_code == 401:
                async with self._lock:
                    await self._acquire_token()
                if self._token:
                    req_headers["Authorization"] = f"Bearer {self._token}"
                    r = await self.client.request(method, url, headers=req_headers, **kwargs)
                else:
                    req_headers.pop("Authorization", None)
                    r = await self.client.request(
                        method, url, headers=req_headers,
                        auth=(self.username, self.password), **kwargs
                    )
        else:
            r = await self.client.request(
                method, url, headers=req_headers,
                auth=(self.username, self.password), **kwargs
            )

        return r

    async def ping(self) -> dict:
        """GET /wda with Basic Auth. Returns {ok, reason}."""
        try:
            r = await self.client.get(
                "/wda", auth=(self.username, self.password), timeout=3.0
            )
            if r.status_code == 200:
                return {"ok": True, "reason": "ok"}
            if r.status_code == 401:
                return {"ok": False, "reason": "auth failed (wrong creds or WDX disabled)"}
            if r.status_code == 503:
                return {"ok": False, "reason": "WDA service unavailable (503)"}
            if r.status_code == 426:
                return {"ok": False, "reason": "HTTPS required (426)"}
            return {"ok": False, "reason": f"unexpected status {r.status_code}"}
        except Exception as e:
            msg = str(e) or repr(e) or "no detail"
            return {"ok": False, "reason": f"{type(e).__name__}: {msg}"}

    async def _paginate(self, path: str) -> list[dict]:
        """Walk all pages via JSON:API links.next."""
        items: list[dict] = []
        # Ensure unreadable parameters surface as error attributes rather than 500ing the page.
        if "/wda/parameters" in path and "parameter-errors-as-data-attributes" not in path:
            sep = "&" if "?" in path else "?"
            path = f"{path}{sep}parameter-errors-as-data-attributes=true"
        sep = "&" if "?" in path else "?"
        next_url: str | None = f"{path}{sep}page[limit]={self.page_limit}&page[offset]=0"
        while next_url:
            r = await self._request("GET", next_url)
            r.raise_for_status()
            body = r.json()
            page_data = body.get("data", [])
            items.extend(page_data)
            if len(page_data) < self.page_limit:
                break  # shorter-than-full page → last page; guards against corrupt links.next
            next_url = body.get("links", {}).get("next")
        return items

    async def list_parameters(self) -> list[dict]:
        return await self._paginate("/wda/parameters?parameter-errors-as-data-attributes=true")

    async def get_parameter(self, pid: str) -> dict:
        r = await self._request("GET", f"/wda/parameters/{pid}")
        r.raise_for_status()
        return r.json()["data"]["attributes"]

    async def set_parameters(self, items: list[dict]) -> dict:
        payload = {
            "data": [
                {"id": p["id"], "type": "parameters", "attributes": {"value": p["value"]}}
                for p in items
            ]
        }
        r = await self._request(
            "PATCH", "/wda/parameters",
            json=payload, headers={"Content-Type": self.JSON_API},
        )
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {"status": "ok"}
        return r.json()

    async def set_parameter(self, pid: str, value: Any) -> dict:
        payload = {"data": {"type": "parameters", "id": pid, "attributes": {"value": value}}}
        r = await self._request(
            "PATCH", f"/wda/parameters/{pid}",
            json=payload, headers={"Content-Type": self.JSON_API},
        )
        r.raise_for_status()
        if r.status_code == 204 or not r.content:
            return {"status": "ok"}
        return r.json()

    async def list_parameter_definitions(self, filters: dict | None = None) -> list[dict]:
        qs = ""
        if filters:
            qs = "?" + "&".join(f"filter[{k}]={v}" for k, v in filters.items())
        return await self._paginate(f"/wda/parameter-definitions{qs}")

    async def get_parameter_definition(self, pdid: str) -> dict:
        r = await self._request("GET", f"/wda/parameter-definitions/{pdid}")
        r.raise_for_status()
        return r.json()["data"]

    async def list_devices(self) -> list[dict]:
        return await self._paginate("/wda/devices")

    async def get_device(self, did: str) -> dict:
        r = await self._request("GET", f"/wda/devices/{did}")
        r.raise_for_status()
        return r.json()["data"]

    async def list_features(self) -> list[dict]:
        return await self._paginate("/wda/features")

    async def get_feature(self, fid: str) -> dict:
        r = await self._request("GET", f"/wda/features/{fid}")
        r.raise_for_status()
        return r.json()["data"]

    async def list_methods(self) -> list[dict]:
        return await self._paginate("/wda/methods")

    async def get_method(self, mid: str) -> dict:
        r = await self._request("GET", f"/wda/methods/{mid}")
        r.raise_for_status()
        return r.json()["data"]

    async def get_method_inargs(self, mid: str) -> list[dict]:
        r = await self._request("GET", f"/wda/method-definitions/{mid}/inargs")
        r.raise_for_status()
        return r.json().get("data", [])

    async def get_method_outargs(self, mid: str) -> list[dict]:
        r = await self._request("GET", f"/wda/method-definitions/{mid}/outargs")
        r.raise_for_status()
        return r.json().get("data", [])

    async def invoke_method(
        self,
        mid: str,
        arguments: dict[str, Any] | None = None,
        sync: bool = True,
    ) -> dict:
        in_args = {k: {"value": v} for k, v in (arguments or {}).items()}
        payload = {"data": {"type": "runs", "attributes": {"inArgs": in_args}}}
        r = await self._request(
            "POST", f"/wda/methods/{mid}/runs",
            json=payload,
            params={"result-behavior": "sync" if sync else "async"},
            headers={"Content-Type": self.JSON_API},
        )
        r.raise_for_status()
        return r.json().get("data", {})

    async def get_method_run(self, mid: str, run_id: str) -> dict:
        r = await self._request("GET", f"/wda/methods/{mid}/runs/{run_id}")
        r.raise_for_status()
        return r.json()["data"]

    async def delete_method_run(self, mid: str, run_id: str) -> bool:
        r = await self._request("DELETE", f"/wda/methods/{mid}/runs/{run_id}")
        return r.status_code in (200, 204)

    async def list_enum_definitions(self) -> list[dict]:
        return await self._paginate("/wda/enum-definitions")

    async def get_enum_definition(self, eid: str) -> dict:
        r = await self._request("GET", f"/wda/enum-definitions/{eid}")
        r.raise_for_status()
        return r.json()["data"]

    async def create_monitoring_list(
        self, parameter_ids: list[str], timeout: int = 300
    ) -> dict:
        payload = {
            "data": {
                "type": "monitoring-lists",
                "attributes": {"timeout": timeout},
                "relationships": {
                    "parameters": {
                        "data": [{"id": pid, "type": "parameters"} for pid in parameter_ids]
                    }
                },
            }
        }
        r = await self._request(
            "POST", "/wda/monitoring-lists",
            json=payload,
            params={"parameter-errors-as-data-attributes": "true"},
            headers={"Content-Type": self.JSON_API},
        )
        r.raise_for_status()
        return r.json().get("data", {})

    async def list_monitoring_lists(self) -> list[dict]:
        return await self._paginate("/wda/monitoring-lists")

    async def get_monitoring_list(self, mlid: str, include_parameters: bool = True) -> dict:
        params = {"parameter-errors-as-data-attributes": "true"}
        if include_parameters:
            params["include"] = "parameters"
        r = await self._request("GET", f"/wda/monitoring-lists/{mlid}", params=params)
        r.raise_for_status()
        return r.json()

    async def read_monitoring_list_parameters(self, mlid: str) -> list[dict]:
        return await self._paginate(
            f"/wda/monitoring-lists/{mlid}/parameters?parameter-errors-as-data-attributes=true"
        )

    async def delete_monitoring_list(self, mlid: str) -> bool:
        r = await self._request("DELETE", f"/wda/monitoring-lists/{mlid}")
        return r.status_code in (200, 204)
