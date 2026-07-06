"""Regenerate the MCP API key.

Usage (inside the running container):
    docker exec wmcp python src/mcp_keygen.py

The new key is written to /app/data/mcp_api_key (requires ./data:/app/data volume mount).
Update .mcp.json and Claude Desktop config with the new Bearer token, then clients
reconnect automatically on the next request (old sessions receive 401 immediately).
"""
import sys
import secrets
from pathlib import Path

_KEY_PATH = Path("/app/data/mcp_api_key")


def main() -> None:
    if len(sys.argv) > 1:
        print(f"mcp_keygen.py takes no arguments (got: {sys.argv[1:]}). "
              "Run it bare - it always regenerates immediately, with no confirmation.")
        raise SystemExit(1)

    key = secrets.token_hex(32)
    try:
        _KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        _KEY_PATH.write_text(key)
        persisted = True
    except OSError as e:
        print(f"WARNING: could not write key ({e}) — key is shown below but NOT persisted")
        persisted = False

    sep = "=" * 72
    print(f"""
{sep}
  MCP API KEY REGENERATED — update .mcp.json / Claude Desktop now

  Bearer {key}

  .mcp.json:
    "headers": {{"Authorization": "Bearer {key}"}}

  {"Key written to: " + str(_KEY_PATH) if persisted else "WARN: key NOT persisted — mount ./data:/app/data"}
  Old sessions will receive 401 immediately.
{sep}
""")


if __name__ == "__main__":
    main()
