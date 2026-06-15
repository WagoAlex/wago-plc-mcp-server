"""Unit tests for pure helpers in main.py — L0, no network, no PLC.

Import strategy: `import main` at module-level runs bootstrap (load_dotenv,
setup_logging, setup_audit_logging, PLCManager(), FastMCP()). That is fine
in-container — the side effects are benign (loguru config, empty PLCManager).
We isolate only the pieces that would touch real secrets / real files.
"""
import hashlib
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger

# Ensure src/ is importable (pyproject.toml pythonpath = ["src"] handles this,
# but be explicit as a guard in case pytest is invoked without it)
_SRC = str(Path(__file__).parent.parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import main  # noqa: E402  (must come after sys.path setup above)


# ─────────────────────────── _score ───────────────────────────


class TestScore:
    def test_exact_match_returns_1000(self) -> None:
        assert main._score("ntpclient-updatetime", "ntpclient-updatetime") == 1000

    def test_prefix_match_returns_100(self) -> None:
        assert main._score("ntpclient-updatetime", "ntpclient") == 100

    def test_substring_match_returns_10(self) -> None:
        assert main._score("0-0-ntpclient-updatetime", "ntpclient") == 10

    def test_no_match_returns_0(self) -> None:
        assert main._score("some-parameter", "xyz") == 0

    def test_empty_query_returns_1(self) -> None:
        assert main._score("anything", "") == 1

    def test_case_insensitive_exact(self) -> None:
        assert main._score("NtpClient", "ntpclient") == 1000

    def test_case_insensitive_prefix(self) -> None:
        assert main._score("NtpClient-Update", "ntpclient") == 100

    def test_case_insensitive_substring(self) -> None:
        assert main._score("0-0-NtpClient-Update", "ntpclient") == 10


# ─────────────────────────── _filter_search ───────────────────────────


class TestFilterSearch:
    def _items(self) -> set[str]:
        return {
            "0-0-ntpclient-updatetime",
            "0-0-ntpclient-serveraddress",
            "0-0-webserver-enable",
            "0-0-firewall-active",
            "0-0-hostname-config",
        }

    def test_exact_match_ranks_first(self) -> None:
        items = {"0-0-ntpclient-updatetime", "other-ntpclient-updatetime-2"}
        result = main._filter_search(items, "0-0-ntpclient-updatetime", 10)
        assert result[0] == "0-0-ntpclient-updatetime"

    def test_prefix_matches_rank_above_substring(self) -> None:
        items = {"ntpclient-x", "0-0-ntpclient-y", "other"}
        result = main._filter_search(items, "ntpclient", 10)
        assert result[0] == "ntpclient-x"

    def test_no_substring_hit_uses_fuzzy_fallback(self) -> None:
        items = {"ntpclient-updatetime", "webserver-enable"}
        # "ntpclientupdatetyme" is close enough to "ntpclient-updatetime" via difflib
        result = main._filter_search(items, "ntpclientupdatetyme", 10)
        # Fuzzy fallback should return ntpclient-updatetime
        assert "ntpclient-updatetime" in result

    def test_empty_query_returns_sorted_alphabetically(self) -> None:
        items = {"b-item", "a-item", "c-item"}
        result = main._filter_search(items, "", 10)
        assert result == ["a-item", "b-item", "c-item"]

    def test_limit_capped_at_FIND_LIMIT_MAX(self) -> None:
        items = {f"param-{i}" for i in range(200)}
        result = main._filter_search(items, "", 9999)
        assert len(result) <= main.FIND_LIMIT_MAX

    def test_limit_1_returns_one_result(self) -> None:
        items = {"a", "b", "c"}
        result = main._filter_search(items, "", 1)
        assert len(result) == 1

    def test_no_match_no_fuzzy_hit_returns_empty(self) -> None:
        items = {"webserver-enable", "firewall-active"}
        result = main._filter_search(items, "zzzzzzzzzzz", 10)
        assert result == []

    def test_substring_hits_sorted_by_score_then_alpha(self) -> None:
        items = {"ntpclient-update", "prefix-ntpclient", "0-ntpclient-x"}
        result = main._filter_search(items, "ntpclient", 10)
        # "ntpclient-update" starts with query → score 100
        # others are substrings → score 10
        assert result[0] == "ntpclient-update"


# ─────────────────────────── _check_key_entropy ───────────────────────────


class TestCheckKeyEntropy:
    def test_key_shorter_than_32_raises_systemexit(self) -> None:
        with pytest.raises(SystemExit):
            main._check_key_entropy("short_key", "test")

    def test_key_of_31_chars_raises_systemexit(self) -> None:
        with pytest.raises(SystemExit):
            main._check_key_entropy("a" * 31, "test")

    def test_key_of_exactly_32_chars_does_not_raise(self) -> None:
        main._check_key_entropy("a" * 32, "test")  # must not raise

    def test_key_of_64_chars_does_not_raise(self) -> None:
        main._check_key_entropy("a" * 64, "test")

    def test_empty_key_raises_systemexit(self) -> None:
        with pytest.raises(SystemExit):
            main._check_key_entropy("", "test")

    def test_exit_code_is_1(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main._check_key_entropy("tooshort", "test")
        assert exc.value.code == 1


# ─────────────────────────── _audit_log + _seed_audit_hash ───────────────────────────


@pytest.fixture(autouse=False)
def reset_audit_hash():
    """Reset _AUDIT_PREV_HASH to genesis before and after each audit test."""
    genesis = "0" * 64
    original = main._AUDIT_PREV_HASH
    main._AUDIT_PREV_HASH = genesis
    yield
    main._AUDIT_PREV_HASH = original


@pytest.fixture()
def audit_sink():
    """Capture AUDIT-level loguru messages into a list of raw strings."""
    captured: list[str] = []

    def _sink(message):
        captured.append(message.record["message"])

    sink_id = logger.add(_sink, level="AUDIT", format="{message}")
    yield captured
    logger.remove(sink_id)


class TestAuditLog:
    def test_emits_valid_json(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("test_action", "10.0.0.1", {"key": "val"}, "ok")
        assert len(audit_sink) == 1
        entry = json.loads(audit_sink[0])
        assert isinstance(entry, dict)

    def test_entry_has_required_fields(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("set_parameters", "10.0.0.2", {"params": []}, "ok")
        entry = json.loads(audit_sink[0])
        for field in ("ts", "action", "plc", "agent", "result", "prev"):
            assert field in entry, f"missing field: {field}"

    def test_action_field_correct(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("invoke_method", "10.0.0.1", {}, "done")
        entry = json.loads(audit_sink[0])
        assert entry["action"] == "invoke_method"

    def test_plc_field_correct(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("set_parameters", "192.168.1.1", {}, "ok")
        entry = json.loads(audit_sink[0])
        assert entry["plc"] == "192.168.1.1"

    def test_result_field_correct(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("set_parameters", "10.0.0.1", {}, "error: timeout")
        entry = json.loads(audit_sink[0])
        assert entry["result"] == "error: timeout"

    def test_prev_of_first_entry_is_genesis(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("set_parameters", "10.0.0.1", {}, "ok")
        entry = json.loads(audit_sink[0])
        assert entry["prev"] == "0" * 64

    def test_hash_chain_prev_of_entry_n_equals_sha256_of_entry_n_minus_1(
        self, reset_audit_hash, audit_sink
    ) -> None:
        main._audit_log("action_a", "10.0.0.1", {}, "ok")
        main._audit_log("action_b", "10.0.0.1", {}, "ok")
        line0 = audit_sink[0]
        entry1 = json.loads(audit_sink[1])
        expected_prev = hashlib.sha256(line0.encode()).hexdigest()
        assert entry1["prev"] == expected_prev

    def test_hash_chain_three_entries(self, reset_audit_hash, audit_sink) -> None:
        for i in range(3):
            main._audit_log(f"action_{i}", "10.0.0.1", {}, "ok")
        # Verify chain: entry[n]["prev"] == sha256(raw_line[n-1])
        for n in range(1, 3):
            prev_line = audit_sink[n - 1]
            entry = json.loads(audit_sink[n])
            expected = hashlib.sha256(prev_line.encode()).hexdigest()
            assert entry["prev"] == expected, f"chain broken at entry {n}"

    def test_details_dict_merged_into_entry(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("set_parameters", "10.0.0.1", {"params": [{"id": "p1", "value": 42}]}, "ok")
        entry = json.loads(audit_sink[0])
        assert entry["params"] == [{"id": "p1", "value": 42}]

    def test_global_prev_hash_updated_after_call(self, reset_audit_hash, audit_sink) -> None:
        main._audit_log("set_parameters", "10.0.0.1", {}, "ok")
        expected = hashlib.sha256(audit_sink[0].encode()).hexdigest()
        assert main._AUDIT_PREV_HASH == expected


class TestSeedAuditHash:
    def test_missing_file_leaves_genesis_hash(self, reset_audit_hash) -> None:
        genesis = "0" * 64
        main._AUDIT_PREV_HASH = genesis
        main._seed_audit_hash("/nonexistent/path/audit.log")
        assert main._AUDIT_PREV_HASH == genesis

    def test_existing_log_seeds_from_last_line(self, reset_audit_hash, tmp_path) -> None:
        # Write a valid JSON audit line
        line = json.dumps({"ts": "2026-01-01T00:00:00+00:00", "action": "boot", "prev": "0" * 64})
        log_file = tmp_path / "audit.log"
        log_file.write_text(line + "\n")

        main._seed_audit_hash(str(log_file))

        expected = hashlib.sha256(line.encode()).hexdigest()
        assert main._AUDIT_PREV_HASH == expected

    def test_non_json_tail_leaves_genesis_and_no_crash(self, reset_audit_hash, tmp_path) -> None:
        genesis = "0" * 64
        main._AUDIT_PREV_HASH = genesis
        log_file = tmp_path / "audit.log"
        log_file.write_text("this is not json\n")

        main._seed_audit_hash(str(log_file))  # must not raise

        assert main._AUDIT_PREV_HASH == genesis

    def test_empty_file_leaves_genesis(self, reset_audit_hash, tmp_path) -> None:
        genesis = "0" * 64
        main._AUDIT_PREV_HASH = genesis
        log_file = tmp_path / "audit.log"
        log_file.write_text("")

        main._seed_audit_hash(str(log_file))

        assert main._AUDIT_PREV_HASH == genesis

    def test_multi_line_log_seeds_from_last_valid_json_line(self, reset_audit_hash, tmp_path) -> None:
        lines = [
            json.dumps({"ts": f"2026-01-0{i}T00:00:00+00:00", "action": "op", "prev": "0" * 64})
            for i in range(1, 4)
        ]
        log_file = tmp_path / "audit.log"
        log_file.write_text("\n".join(lines) + "\n")

        main._seed_audit_hash(str(log_file))

        expected = hashlib.sha256(lines[-1].encode()).hexdigest()
        assert main._AUDIT_PREV_HASH == expected


# ─────────────────────────── _parse_plcs_from_env ───────────────────────────
#
# Strategy: monkeypatch env vars and patch _read_secret / _load_per_plc_secrets
# so we NEVER touch the real /run/secrets/ directory.


class TestParsePlcsFromEnv:
    def _call(self, env: dict, per_plc_secrets: dict | None = None, shared_secret: str | None = None):
        """Run _parse_plcs_from_env with patched env and secrets, return result as sorted list."""
        per_plc = per_plc_secrets or {}

        def fake_read_secret(name: str) -> str | None:
            if name == "plc_default_password":
                return shared_secret
            if name.startswith("plc_password_"):
                ip = name.removeprefix("plc_password_").replace("_", ".")
                return per_plc.get(ip)
            return None

        with patch.dict(os.environ, env, clear=False), \
             patch("main._read_secret", side_effect=fake_read_secret), \
             patch("main._load_per_plc_secrets", return_value=per_plc):
            # Remove any env keys not in our dict that might bleed from parent env
            keys_to_remove = [
                "WAGO_PLC_HOSTS", "DEFAULT_PLC_USERNAME", "DEFAULT_PLC_PASSWORD"
            ]
            # Build a clean environment for the call
            clean_env = {k: v for k, v in os.environ.items() if not k.startswith("PLC_PASSWORDS_")}
            for k in keys_to_remove:
                clean_env.pop(k, None)
            clean_env.update(env)

            with patch.dict(os.environ, clean_env, clear=True), \
                 patch("main._read_secret", side_effect=fake_read_secret), \
                 patch("main._load_per_plc_secrets", return_value=per_plc):
                return sorted(main._parse_plcs_from_env())

    def test_csv_hosts_parsed_correctly(self) -> None:
        result = self._call({"WAGO_PLC_HOSTS": "10.0.0.1,10.0.0.2", "DEFAULT_PLC_PASSWORD": "secret123456789012345678901234567"})
        ips = [r[0] for r in result]
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips

    def test_username_from_env(self) -> None:
        result = self._call({
            "WAGO_PLC_HOSTS": "10.0.0.1",
            "DEFAULT_PLC_USERNAME": "myuser",
            "DEFAULT_PLC_PASSWORD": "mypassword_long_enough_32chars_ok",
        })
        assert result[0][1] == "myuser"

    def test_fallback_5_hardcoded_wago(self) -> None:
        """No secret, no env password → falls back to 'wago'."""
        result = self._call({"WAGO_PLC_HOSTS": "10.0.0.1"})
        assert result[0][2] == "wago"

    def test_fallback_4_shared_env_DEFAULT_PLC_PASSWORD(self) -> None:
        result = self._call({
            "WAGO_PLC_HOSTS": "10.0.0.1",
            "DEFAULT_PLC_PASSWORD": "shared_env_password_long_enough_ok",
        })
        assert result[0][2] == "shared_env_password_long_enough_ok"

    def test_fallback_3_shared_docker_secret_wins_over_env(self) -> None:
        result = self._call(
            env={"WAGO_PLC_HOSTS": "10.0.0.1", "DEFAULT_PLC_PASSWORD": "env_default"},
            shared_secret="secret_from_docker_secret_file",
        )
        assert result[0][2] == "secret_from_docker_secret_file"

    def test_fallback_2_per_plc_env_PLC_PASSWORDS(self) -> None:
        result = self._call({
            "WAGO_PLC_HOSTS": "10.0.0.1",
            "PLC_PASSWORDS_10_0_0_1": "per_plc_env_password",
            "DEFAULT_PLC_PASSWORD": "should_not_use",
        })
        # per_plc_secrets is empty (no docker secret), but env has PLC_PASSWORDS_
        # The function picks up PLC_PASSWORDS_ via os.environ loop
        assert result[0][2] == "per_plc_env_password"

    def test_fallback_1_per_plc_docker_secret_highest_priority(self) -> None:
        result = self._call(
            env={
                "WAGO_PLC_HOSTS": "10.0.0.1",
                "DEFAULT_PLC_PASSWORD": "env_default",
                "PLC_PASSWORDS_10_0_0_1": "per_plc_env",
            },
            per_plc_secrets={"10.0.0.1": "per_plc_secret"},
            shared_secret="shared_secret",
        )
        assert result[0][2] == "per_plc_secret"

    def test_per_plc_env_extends_host_list(self) -> None:
        """PLC_PASSWORDS_<ip> env adds the IP to the PLC list even without WAGO_PLC_HOSTS."""
        result = self._call({
            "PLC_PASSWORDS_10_0_0_5": "per_plc_password",
        })
        ips = [r[0] for r in result]
        assert "10.0.0.5" in ips

    def test_per_plc_env_and_csv_combined(self) -> None:
        result = self._call({
            "WAGO_PLC_HOSTS": "10.0.0.1",
            "PLC_PASSWORDS_10_0_0_2": "specific_pw",
        })
        ips = [r[0] for r in result]
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips

    def test_empty_env_returns_empty_list(self) -> None:
        result = self._call({})
        assert result == []

    def test_csv_with_spaces_stripped(self) -> None:
        result = self._call({"WAGO_PLC_HOSTS": " 10.0.0.1 , 10.0.0.2 "})
        ips = [r[0] for r in result]
        assert "10.0.0.1" in ips
        assert "10.0.0.2" in ips

    def test_does_not_read_real_secrets_dir(self) -> None:
        """Verify _load_per_plc_secrets is patched — real /run/secrets/ never accessed."""
        accessed_real = []

        def guarded_load():
            # If this were the real function, it would access /run/secrets/
            # Since we're patching, this should never be called
            accessed_real.append(True)
            return {}

        with patch.dict(os.environ, {"WAGO_PLC_HOSTS": "10.0.0.1"}, clear=True), \
             patch("main._read_secret", return_value=None), \
             patch("main._load_per_plc_secrets", side_effect=guarded_load):
            main._parse_plcs_from_env()

        # guarded_load was called (our mock), but it never touched real /run/secrets/
        # The real _load_per_plc_secrets was NOT called
        assert accessed_real == [True]  # our mock was called exactly once
