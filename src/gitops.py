"""Generate GitOps YAML fragments for the config repo (default: wago-plc-config,
overridable via WAGO_GITOPS_REPO - see src/main.py).

set_parameters  → desired_state_fragment() → agent merges into plcs/<ip>.yaml
invoke_method   → ops_fragment()           → agent commits to ops/<id>.yaml
"""
import uuid
import yaml
from datetime import datetime, timezone


def cloud_params(client_id: str, host: str, cloudtype: int = 2, protocol: int = 4) -> list[dict]:
    """Return the minimal parameter set to configure a WDA cloud connection.

    Must include transport-host: WDA validates host against cloudtype in the same
    PATCH call and returns code-41 if they conflict (e.g. Azure host + cloudtype=2).

    cloudtype 2 = Any Cloud (generic MQTT broker)
    protocol  4 = Native MQTT
    """
    return [
        {"id": "0-0-cloudconnections-1-transport-host",              "value": host},
        {"id": "0-0-cloudconnections-1-cloudtype",                   "value": cloudtype},
        {"id": "0-0-cloudconnections-1-identification-clientid",     "value": client_id},
        {"id": "0-0-cloudconnections-1-messaging-messagingprotocol", "value": protocol},
        {"id": "0-0-cloudconnections-1-enabled",                     "value": True},
    ]


def ntp_params(servers: list[str], update_interval: int = 300) -> list[dict]:
    """NTP client config. servers: list of NTP server IPs/hostnames."""
    return [
        {"id": "0-0-ntpclient-enabled",              "value": True},
        {"id": "0-0-ntpclient-configuredtimeservers", "value": servers},
        {"id": "0-0-ntpclient-updateinterval",        "value": update_interval},
    ]


def snmp_params(
    enabled: bool = True,
    community: str = "public",
    location: str = "",
    contact: str = "",
) -> list[dict]:
    """SNMP v1/v2c config. community sets the read community string."""
    return [
        {"id": "0-0-snmp-enable",                "value": enabled},
        {"id": "0-0-snmp-communities-1-name",    "value": community},
        {"id": "0-0-snmp-location",              "value": location},
        {"id": "0-0-snmp-contact",               "value": contact},
    ]


def serial_params(assigned_mode: int, assigned_owner: int | None = None) -> list[dict]:
    """Serial interface X3 config.
    assigned_mode: 0=unassigned, 1=RS232, 2=RS485 (device-specific enum).
    assigned_owner: 0=None, 1=CODESYS, 2=Service — omit to leave unchanged.
    """
    params = [{"id": "0-0-serialinterfaces-1-assignedmode", "value": assigned_mode}]
    if assigned_owner is not None:
        params.append({"id": "0-0-serialinterfaces-1-assignedowner", "value": assigned_owner})
    return params


def openvpn_params(
    enabled: bool = False,
    config_description: str = "",
    cert_description: str = "",
) -> list[dict]:
    """OpenVPN config metadata (descriptions only — cert/key/config upload is out-of-band)."""
    return [
        {"id": "0-0-openvpn-enabled",                  "value": enabled},
        {"id": "0-0-openvpn-configurationdescription", "value": config_description},
        {"id": "0-0-openvpn-certificatedescription",   "value": cert_description},
    ]


def browser_params(startpage_mode: int = 0, startpage_favorite: int = 1) -> list[dict]:
    """Integrated web browser config (WP400/TP600 HMI panels).
    startpage_mode: 0=blank, 1=favorites (pick via startpage_favorite index).
    """
    return [
        {"id": "0-0-integratedwebbrowser-startpage",         "value": startpage_mode},
        {"id": "0-0-integratedwebbrowser-startpagefavorite", "value": startpage_favorite},
    ]


def desired_state_fragment(plc_ip: str, parameters: list[dict], repo: str = "wago-plc-config") -> dict:
    """Return the YAML the agent should merge into plcs/<ip>.yaml.

    repo: the config repo name/path shown in `next_step`, configurable via
    WAGO_GITOPS_REPO for deployments that fork or rename the default repo.
    """
    managed = {p["id"]: p["value"] for p in parameters}
    data = {"plc_ip": plc_ip, "managed_parameters": managed}
    return {
        "status": "proposed",
        "config_file": f"plcs/{plc_ip}.yaml",
        "desired_state_yaml": yaml.dump(data, sort_keys=False),
        "next_step": (
            f"Merge desired_state_yaml into {repo}/plcs/{plc_ip}.yaml "
            f"(add/update keys under managed_parameters) and open a PR. "
            f"apply.py will read current PLC state, diff against desired, and apply only what changed."
        ),
    }


def ops_fragment(
    plc_ip: str,
    method_id: str,
    arguments: dict,
    agent_id: str,
    dangerous: bool = False,
    repo: str = "wago-plc-config",
) -> dict:
    """Return the YAML the agent should commit to ops/<id>.yaml.

    dangerous=True (reboot/reset/firmware) adds a CRITICAL flag and an empty
    `approved_by` field that a human MUST fill during PR review — apply.py refuses
    to execute the op until it is set.

    repo: the config repo name/path shown in `next_step`, configurable via
    WAGO_GITOPS_REPO for deployments that fork or rename the default repo.
    """
    op_id = uuid.uuid4().hex[:8]
    data = {
        "id": op_id,
        "proposed_at": datetime.now(timezone.utc).isoformat(),
        "proposed_by": agent_id,
        "plc_ip": plc_ip,
        "action": "invoke_method",
        "method_id": method_id,
        "arguments": arguments or {},
    }
    if dangerous:
        data["requires_human"] = "CRITICAL"
        data["approved_by"] = ""  # human fills this during PR review
    out = {
        "status": "proposed",
        "config_file": f"ops/{op_id}.yaml",
        "ops_yaml": yaml.dump(data, sort_keys=False),
        "next_step": (
            f"Commit ops_yaml to {repo}/ops/{op_id}.yaml and open a PR. "
            f"apply.py will invoke the method on merge and delete the file."
        ),
    }
    if dangerous:
        out["warning"] = (
            "CRITICAL: dangerous method (reboot/reset/firmware). apply.py will REFUSE "
            "to execute until a human sets `approved_by` in the ops file. Do not fill it "
            "yourself — a human reviewer must approve the PR."
        )
    return out
