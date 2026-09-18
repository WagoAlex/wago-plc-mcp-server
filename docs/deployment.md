# Deployment

## Deployment options

| Path | Use for | Requirements |
|---|---|---|
| [Claude Desktop extension](claude-desktop.md#quick-start) | One engineer, a small number of PLCs | Claude Desktop |
| [Docker](#docker-recommended-for-teams) | A plant server that many users share | Docker host on the OT network |
| [Portainer](#portainer) | A Docker host that you manage in Portainer | Portainer connected to the Docker host |
| [MCP Registry](#mcp-registry) | Clients that install servers from the official registry | `uv` or Docker |
| [uvx / PyPI](#uvx--pypi) | A developer computer on any OS | `uv` |
| [IDE](#ide-cursor-and-vs-code) | Cursor, VS Code with Copilot | `uv` |
| [HTTP remote](#http-remote-openai-and-n8n) | ChatGPT, OpenAI API, n8n | A server that the client can reach on the network |

The [`deploy/configs/`](../deploy/configs) folder has a configuration example for each path.

### Docker (recommended for teams)

One server supports many clients. The PLCs register one time at startup and stay connected.

**1. Clone the repository and make the `.env` file:**

```bash
git clone https://github.com/WagoAlex/wago-plc-mcp-server.git
cd wago-plc-mcp-server
cp _env .env
```

**2. Edit `.env`:**

```env
WAGO_PLC_HOSTS=192.168.1.10,192.168.1.11,192.168.1.12
DEFAULT_PLC_USERNAME=admin
PORT=6042
WAGO_TIMEOUT_SECONDS=45
```

`WAGO_TIMEOUT_SECONDS` applies to all PLCs. Set it for the slowest device class in the fleet.
CC100 needs 45 or more. Most other classes work with 15.
IEC 62443 hardened units have approximately 3 times more parameters, and we did not tune their timeout.
If the registration of such a unit takes more than 45 seconds, open an issue.

> [!TIP]
> For a large fleet, set `WAGO_PLC_HOSTS_FILE=/app/data/fleet.txt`. The file has one IP per line and supports `#` comments.
> You can also use `WAGO_PLC_HOSTS` at the same time. The server merges the IPs.

```
# data/fleet.txt
# Production floor A
192.168.1.10
192.168.1.11

# Production floor B
192.168.2.10
# 192.168.2.11   decommissioned
```

To change the fleet, edit the file and restart the container.
The audit log stays on the `./data` volume after a restart.

**3. Set the PLC passwords.** You can use the two methods together.

For one shared password:

```bash
mkdir -p secrets
echo "your-plc-password" > secrets/plc_default_password.txt
chmod 600 secrets/plc_default_password.txt
```

For a PLC with its own password, add a secret with its IP in the name.
Then remove the comment marks from the related lines in `docker-compose.yml` (the `secrets:` block and the `secrets:` list of the service).

```bash
echo "that-unit-password" > secrets/plc_password_192_168_2_85.txt
chmod 600 secrets/plc_password_192_168_2_85.txt
```

A per-PLC secret has priority over the shared password. All other PLCs use `plc_default_password.txt`.

> [!IMPORTANT]
> **IEC 62443-4-2 hardened units (CC100-IEC62443, and later PFC400)**
> - These units use the same WDA API and the same tools as other PLCs.
> - They usually have their own credentials. Use a per-PLC secret, not the shared password.
> - **CC100-IEC62443** (`751-9412`) registers as `device_class: "CC100"`. It has approximately 1056 parameters, not 360. The additional parameters are security groups, for example firewall rules, certificates, and accounts.
> - **PFC400** (`750-8400`) registers as `device_class: "PFC400"`. We did not verify it on real hardware.
> - This project does not state that these devices are "IEC 62443 compliant" or "certified". Only a third-party assessment of the device can make that statement.

**4. Start the server:**

```bash
docker compose up -d
docker logs wmcp -f
```

At the first start, the server makes an API key and shows its fingerprint.
The server does not write the key to the container logs.

```
════════════════════════════════════════════════════════════════════════
  NEW MCP API KEY GENERATED  (fingerprint: 7290f42b…)

  Stored in ./data/mcp_api_key - retrieve it with:
    docker exec wmcp cat /app/data/mcp_api_key

  .mcp.json:
    "headers": {"Authorization": "Bearer <key>"}

  Regenerate:  docker exec wmcp python src/mcp_keygen.py
════════════════════════════════════════════════════════════════════════

Registration: 3/3 ready
MCP server listening on http://0.0.0.0:6042/mcp (Streamable HTTP)
```

**5. Get the API key:**

```bash
docker exec wmcp cat /app/data/mcp_api_key
```

> [!TIP]
> For production, supply the key as a Docker Secret. See [API key management](security.md#api-key-management).

**6. Connect a client** to `http://<host>:6042/mcp` with the header `Authorization: Bearer <key>`.

Claude Code:

```bash
claude mcp add --transport http --header "Authorization: Bearer <key>" wago-plc http://localhost:6042/mcp
```

Claude Desktop: add this to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "wago-plc": {
      "type": "http",
      "url": "http://localhost:6042/mcp",
      "headers": { "Authorization": "Bearer <your-api-key>" }
    }
  }
}
```

Quit Claude Desktop fully and start it again. Claude Desktop shows 29 tools:

![wago-plc connected in Claude Desktop](media/claude-desktop-connected.png)

### Portainer

This path uses the same image. You deploy and manage it in the Portainer UI.
Use it when Portainer runs on a different machine and cannot access the Docker host file system.
In this setup, `env_file` and Docker Secrets are not available. The compose file header tells why.

1. Edit the volume path in [`docker-compose.portainer.yml`](../docker-compose.portainer.yml).
   The file uses the absolute path `/home/wago/Documents/mcp/wago-plc-mcp-server/data`, because Portainer does not resolve relative paths from your checkout.
   Change it to the repository location on the Docker host.
   If you do not change it, the audit log and API key go to the wrong location.
2. In Portainer, go to **Stacks → Add stack** and paste the edited compose file.
3. In the **Environment variables** panel, set the values from the compose file header.
   You can also load [`portainer.env.example`](../portainer.env.example) with *Load variables from a .env file*.
4. Deploy the stack. The endpoint is `http://<host>:6042/mcp`.

> [!NOTE]
> In Portainer, `MCP_API_KEY` replaces the Docker Secret `secrets/mcp_api_key.txt`.
> Portainer stores the key in its database, not in a file. This is less secure than the Docker Secret.

### MCP Registry

The server is in the official [MCP Registry](https://registry.modelcontextprotocol.io) as `io.github.WagoAlex/wago-plc-mcp-server`.
Registry clients offer two packages.
Both packages ask for the PLC IPs, the password, and `WAGO_ALLOW_WRITES`. The default is `false`, so all PLCs are read-only.

| Package | Runs as | Requirements |
|---|---|---|
| PyPI `wago-plc-mcp-server` | `uvx wago-plc-mcp-server` over stdio | [`uv`](https://docs.astral.sh/uv/getting-started/installation/) |
| Docker `wagoalex/wago-plc-mcp-server` | `docker run -i --network host ...` over stdio | Docker on a machine that can reach the PLCs |

### uvx / PyPI

This path runs the full server locally in stdio mode. You do not need Docker or a background process.
The server starts again for each Claude session, and the PLCs register again. This adds a few seconds.
For more than 20 PLCs, use Docker.

**Requirement:** [`uv`](https://docs.astral.sh/uv/getting-started/installation/)

Add this to `%APPDATA%\Claude\claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "wago-plc": {
      "command": "uvx",
      "args": ["wago-plc-mcp-server"],
      "env": {
        "TRANSPORT": "stdio",
        "WAGO_PLC_HOSTS": "192.168.1.10,192.168.1.11",
        "DEFAULT_PLC_USERNAME": "admin",
        "DEFAULT_PLC_PASSWORD": "wago",
        "WAGO_TIMEOUT_SECONDS": "45",
        "LOG_LEVEL": "WARNING"
      }
    }
  }
}
```

To make all PLCs read-only, add `"WAGO_ALLOW_WRITES": "false"` to `env`. See [Safety gates](how-it-works.md#safety-gates).

### IDE (Cursor and VS Code)

Cursor: add this to `.cursor/mcp.json` in the project root.
VS Code with Copilot: use the same structure in `.vscode/mcp.json`.

```json
{
  "servers": {
    "wago-plc": {
      "command": "uvx",
      "args": ["wago-plc-mcp-server"],
      "env": {
        "TRANSPORT": "stdio",
        "WAGO_PLC_HOSTS": "192.168.1.10",
        "DEFAULT_PLC_USERNAME": "admin",
        "DEFAULT_PLC_PASSWORD": "wago"
      }
    }
  }
}
```

### HTTP remote (OpenAI and n8n)

A client that supports MCP over HTTP connects to `http://<host>:6042/mcp` with `Authorization: Bearer <key>`.
For an old SSE client, set `TRANSPORT=sse` in `.env` and use `/sse`.

OpenAI Responses API:

```python
response = client.responses.create(
    model="gpt-4o",
    tools=[{
        "type": "mcp",
        "server_url": "http://plc-gateway.plant.internal:6042/mcp",
        "server_label": "wago-plc",
        "headers": {"Authorization": "Bearer <your-api-key>"}
    }],
    input="List all PLCs and their firmware versions."
)
```

## WAGO skill

[`wago-plc-skill/SKILL.md`](../wago-plc-skill/SKILL.md) is for two audiences:

- **Users of Claude Desktop and Claude Code:** plain-English use, safety rules, troubleshooting, and device generations (PTXdist and Yocto).
- **Autonomous agents and pipelines:** tool input and output contracts, error shapes, retry rules, and the watchlist lifecycle.

The skill uses only the frontmatter fields of the [Agent Skills standard](https://agentskills.io).
You install it the same way on all platforms that support the standard:

| Platform | Installation |
|---|---|
| Claude Desktop | Add the `.skill` file from the release in **Settings → Skills**. |
| Claude Code / Claude plugins | `mkdir -p ~/.claude/skills && cp -r wago-plc-skill ~/.claude/skills/` |
| claude.ai / Claude Developer Platform (Skills API) | Run `python package_skill.py wago-plc-skill`, then upload the `.skill` file. |
| Agent SDK | Add the `.skill` file or the folder to your SDK configuration. |

`package_skill.py` is in [anthropics/skills](https://github.com/anthropics/skills). Any tool that zips the folder also works.

The skill needs access to a running `wago-plc` MCP server. See [Deployment options](#deployment-options).
