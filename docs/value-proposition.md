# wago-plc-mcp-server - Value Proposition

---

## Slide 1

### Headline
**Your PLC fleet has the answers. Getting them takes too long.**

### The problem
To manage a WAGO PLC fleet today, you must know which parameter IDs to read,
which firmware version to compare, and which PLC to connect to first.
Only a few engineers have that knowledge. And each check takes time.

- A firmware audit of 16 PLCs: half a day
- NTP drift found before it causes a timestamp mismatch: only if someone
  remembers to check
- A record of what changed and when: often missing

The data is there. The access is the bottleneck.

### The shift
**wago-plc-mcp-server connects your AI assistant directly to your PLC fleet.**

Ask in plain English. Get answers in seconds. Make changes with a confirmation,
not a script.

> "Which PLCs are running firmware older than build 31?"
> - Reads all PLCs in parallel. Returns the list in less than a minute.

> "Are NTP and Docker running on all Edge Controllers?"
> - Reads the service flags of the fleet. Shows each stopped service.

> "Set the NTP server to 192.168.42.2 on all PFC200s."
> - Writes after you confirm. The audit log records each change.

---

## Slide 2

### Headline
**The AI proposes. You decide. The audit trail proves it.**

### What changes for your team

| Before | After |
|---|---|
| One SSH session for each PLC | One conversation for the fleet |
| Parameter IDs to memorize | Ask for what you want |
| Changes tracked in someone's head | Every write in a tamper-evident log |
| Config drift noticed after the fact | Desired state in Git - drift caught on every merge |
| Dangerous operations stopped by a process | Dangerous operations blocked in code |

### Why it is safe for production

The server blocks all writes until an administrator allows them.
It refuses a reboot, a factory reset, or a firmware method, unless an administrator allows that exact method.
In GitOps mode, a reboot runs only after a person approves the pull request.
A read-only PLC refuses every write, for all requests from the AI.
The server enforces these rules in its code. A prompt cannot change them.
Before each write, the assistant also asks you to confirm.

In GitOps mode, each configuration change is a pull request. Before a change,
CI runs a dry run against the live PLC. The engineer reviews the difference and merges it.
Then CI applies only the values that are different. The Git history is the audit trail.

### The bottom line

A junior engineer with no WDA knowledge can audit, configure, and monitor a
fleet of WAGO PLCs on the first day. A senior engineer gets back the hours
of routine checks. Production stays safe, because the safety rules are in the
server, not in the prompt.

**Open source. Runs in Docker. Works with any MCP-compatible AI assistant.**
[github.com/WagoAlex/wago-plc-mcp-server](https://github.com/WagoAlex/wago-plc-mcp-server)
