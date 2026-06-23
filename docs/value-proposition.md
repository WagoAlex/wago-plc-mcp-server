# wago-plc-mcp-server - Value Proposition

---

## Slide 1

### Headline
**Your PLC fleet has the answers. Getting them takes too long.**

### The problem
Managing a WAGO PLC fleet today means knowing which parameter IDs to query,
which firmware version to compare against, and which controller to SSH into
first. That knowledge lives in a handful of engineers - and it takes time
every single time.

- A firmware audit across 16 controllers: half a day
- Spotting NTP drift before it causes a timestamp mismatch: only if someone
  remembers to check
- Documenting what changed and when: rarely happens

The data is there. The access is the bottleneck.

### The shift
**wago-plc-mcp-server connects your AI assistant directly to your PLC fleet.**

Ask in plain English. Get answers in seconds. Make changes with a confirmation,
not a script.

> "Which PLCs are running firmware older than build 31?"
> - Reads every controller in parallel. Returns the list in under a minute.

> "Are NTP and Docker running on all Edge Controllers?"
> - Checks service flags across the fleet. Flags anything stopped.

> "Set the NTP server to 192.168.42.2 on all PFC200s."
> - Writes after your confirmation. Logs every change automatically.

---

## Slide 2

### Headline
**The AI proposes. You decide. The audit trail proves it.**

### What changes for your team

| Before | After |
|---|---|
| SSH session per controller | One conversation covers the fleet |
| Parameter IDs to memorize | Ask for what you want |
| Changes tracked in someone's head | Every write in a tamper-evident log |
| Config drift noticed after the fact | Desired state in Git - drift caught on every merge |
| Dangerous ops gated by process | Dangerous ops blocked in code - no workaround |

### Why it is safe for production

The AI cannot write to a PLC without human confirmation. It cannot execute a
reboot without a human setting an approval field in a reviewed pull request.
Read-only controllers reject every write attempt regardless of what the AI
requests. These are code-level constraints - not prompts, not policy.

In GitOps mode every configuration change becomes a pull request. CI runs a
dry-run against the live PLC before anything is touched. The engineer reviews
the diff, merges, and CI applies only what drifted. The Git history is the
audit trail.

### The bottom line

A junior engineer with no WDA knowledge can audit, configure, and monitor a
fleet of WAGO controllers on day one. A senior engineer gets back the hours
they used to spend on routine checks. And production stays safe because the
guardrails are in the server, not in the prompt.

**Open source. Runs in Docker. Works with any MCP-compatible AI assistant.**
[github.com/WagoAlex/wago-plc-mcp-server](https://github.com/WagoAlex/wago-plc-mcp-server)
