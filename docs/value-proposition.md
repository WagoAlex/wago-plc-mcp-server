# wago-plc-mcp-server - Value Proposition

> Two-slide deck. Slide 1 = the problem and the solution. Slide 2 = how it
> works and what it gives you. Speaker notes follow each slide.

---

## Slide 1 - Your PLC fleet, in plain English

### Headline

**Talk to your WAGO PLC fleet the way you talk to a colleague.**
No scripts. No parameter IDs. No SSH sessions.

### The problem today

- Configuring a fleet of PLCs means SSH sessions, browser tabs, and
  hand-rolled scripts - one controller at a time
- Checking firmware versions, NTP drift, or service states across 16 PLCs
  takes a morning, not a minute
- Every undocumented change is a future incident waiting to happen
- Parameter IDs like `0-0-ntpclient-configuredtimeservers` are not
  something engineers should have to memorize

### The shift

> An AI assistant connected to your PLC fleet via the Model Context Protocol
> turns a morning of manual work into a single sentence.

| You type | What happens |
|---|---|
| "Which PLCs are running firmware older than build 31?" | Reads every controller in parallel, lists the ones behind |
| "Are NTP and Docker running on all Edge Controllers?" | Reads service flags across the fleet, highlights anything stopped |
| "Set NTP to 192.168.42.2 on all PFC200s" | Writes after your confirmation - every change logged |
| "Schedule a reboot of Edge Controller .120 for tonight" | Creates a human-approved GitOps PR - CI executes it on merge |

### Speaker notes

The core idea: MCP (Model Context Protocol) is an open standard that lets AI
assistants call external tools. wago-plc-mcp-server implements that protocol
for the WAGO WDA REST API - the same API the web UI uses. The AI assistant
discovers your fleet, reads and writes parameters, invokes methods, and sets up
server-side monitoring watchlists. The engineer talks; the server does the
WDA plumbing.

---

## Slide 2 - Production-ready, safe by design

### Headline

**Every change is confirmed, logged, and reversible.**
The AI proposes. The engineer decides. The audit trail proves it.

### Three operating modes

| Mode | What the AI can do | Use case |
|---|---|---|
| **Read-only** | Read anything, touch nothing | Fleet health checks, diagnostics, monitoring |
| **Live write** | Read + write after confirmation, dangerous ops blocked | Day-to-day config, NTP sync, service toggles |
| **GitOps** | Returns a PR-ready YAML instead of writing directly | Production environments - every change is a reviewed pull request |

### Safety - enforced in code, not policy

- **Read-only PLC flag** - mark any controller as untouchable; every write
  attempt is refused regardless of what the AI requests
- **Dangerous-method denylist** - reboot, factory reset, firmware update are
  blocked unless explicitly allowlisted
- **Human approval gate** - in GitOps mode, dangerous ops get flagged
  `requires_human: CRITICAL`; `apply.py` refuses to execute until a human
  sets `approved_by` during PR review

### What you get

- **Audit log** - tamper-evident, hash-chained record of every write and
  method invocation; survives container restarts
- **GitOps config repo** - desired state as YAML in Git; every change is a
  PR with a dry-run CI check before anything touches hardware
- **Watchlists** - server-side parameter groups polled in a single HTTP
  request; build a fleet health dashboard without hammering the PLCs
- **Fleet-aware** - 16 device classes supported; parallel registration;
  CC100 / PFC100 G2 / PFC200 G2 / PFC300 / Edge Controller / WP400 / TP600

### Getting started

```
docker run -e WAGO_PLC_HOSTS=192.168.1.10,192.168.1.11 \
           -e DEFAULT_PLC_PASSWORD=wago \
           -p 6042:6042 \
           wagoalex/wago-plc-mcp-server:latest
```

Add to Claude Desktop or Claude Code in one line - see
[github.com/WagoAlex/wago-plc-mcp-server](https://github.com/WagoAlex/wago-plc-mcp-server)

### Speaker notes

The GitOps mode is the production story: `GITOPS_MODE=1` in the environment
turns every `set_parameters` or `invoke_method` call into a YAML fragment the
agent commits to a separate config repo (wago-plc-config). CI runs
`apply.py --dry-run` on PR, `--execute` on merge. Dangerous ops carry an empty
`approved_by` field that CI refuses to clear - a human fills it during PR
review. The config repo is the single source of truth for what every PLC
should look like; Git history is the audit trail.

The safety gates are enforced at the tool boundary in code - not by prompting
the AI to "be careful". An agent going off-script cannot bypass them.
