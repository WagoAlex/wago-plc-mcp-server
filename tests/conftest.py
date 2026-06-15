"""
Root conftest — shared fixtures for the wago-plc-mcp-server test suite.

Markers registered in pyproject.toml [tool.pytest.ini_options]:
  live    — requires a reachable PLC (never run in CI)
  mutate  — writes to a PLC (lab-gated only)
  soak    — long-running resilience / leak check
"""
