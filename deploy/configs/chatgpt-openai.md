# ChatGPT / OpenAI API — Remote HTTP connection

ChatGPT and the OpenAI Responses API connect directly to the running HTTP
server. No proxy, no uvx. The server must be reachable from the client.

## ChatGPT Desktop (Mac/Windows)

Settings → MCP Servers → Add Server:

```
Name:   wago-plc
URL:    http://plc-gateway.plant.internal:6042/mcp
Header: Authorization: Bearer <your-api-key>
```

## OpenAI Responses API

```python
from openai import OpenAI

client = OpenAI()
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

## Requirements

- `wago-mcp-server` running and reachable (Docker deployment recommended)
- `MCP_API_KEY` set in server `.env`
- Port 6042 open between client and server host
