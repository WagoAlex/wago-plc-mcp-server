"""
Git-gated authorization for firmware updates.

Flashing firmware is irreversible-ish and fleet-wide, so the decision of
"which device may go to which revision" does not live in an env var that
anyone can pass on a command line. It lives in a YAML file that is committed
to git, and this module refuses to authorize anything unless:

  1. the policy file is tracked by git, and
  2. the working-tree copy is identical to the committed one (no local edits), and
  3. it explicitly lists this device's IP with this exact target revision, and
  4. (optional, FW_REQUIRE_SIGNED_COMMIT=true) HEAD carries a good signature.

An entry may be either a bare revision string - the commit itself is the
approval - or a mapping that adds the same manual review gate the ops/ files
in wago-plc-config use, where a human must fill approved_by during PR review:

    approvals:
      192.168.42.110: "4.9.1"                    # commit is the approval
      192.168.42.115:                            # + explicit human sign-off
        version: "4.9.1"
        requires_human: CRITICAL
        approved_by: ""                          # fill this before merging

An empty approved_by is refused even though the file is committed, which is
what makes an unapproved PR safe to open.

A firmware update can also be authorized by a one-shot ops file, the same shape
the config repo already uses for a reboot - set FW_OPS_FILE to it. The ops file
IS the approval, so it must carry approved_by, and the same git checks apply:

    id: fw-pfc300-119
    plc_ip: 192.168.42.119
    action: firmware_update
    target_version: "4.9.1"
    requires_human: CRITICAL
    approved_by: ""          # fill this before merging

The commit sha that authorized the run is returned so it can be printed and
written to the audit log - "who approved this flash" is answerable afterwards
by `git show <sha>`.
"""
import os
import subprocess
from pathlib import Path

import yaml


class NotAuthorized(Exception):
    """Raised for every refusal. The message is meant to be shown verbatim."""


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise NotAuthorized(f"git {' '.join(args)} failed: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def _verify_committed(authorization_file: str | Path) -> tuple[Path, Path, Path]:
    """Prove one file is tracked, unmodified and (optionally) on a signed HEAD.

    Shared by both authorization sources - the fleet policy and a one-shot ops
    file - so there is exactly one implementation of "this was committed".
    Returns (absolute_path, repo_dir, path_relative_to_repo).
    """
    path = Path(authorization_file).resolve()
    if not path.is_file():
        raise NotAuthorized(f"authorization file {path} not found - firmware updates are refused without one")

    try:
        toplevel = Path(_git(path.parent, "rev-parse", "--show-toplevel"))
    except NotAuthorized:
        raise NotAuthorized(f"{path} is not inside a git repository - no authorization possible") from None

    # Every subsequent call runs from the repo ROOT, not the file's directory:
    # git resolves a pathspec relative to the cwd, so running from ops/ would
    # look for ops/ops/<file> and report every ops file as untracked.
    repo = toplevel
    rel = path.relative_to(toplevel)
    _git(repo, "ls-files", "--error-unmatch", str(rel))  # raises if untracked

    if _git(repo, "diff", "HEAD", "--name-only", "--", str(rel)):
        raise NotAuthorized(
            f"{rel} has uncommitted changes. Commit the approval first - an uncommitted "
            f"file is not an authorization."
        )

    if os.environ.get("FW_REQUIRE_SIGNED_COMMIT", "").lower() in ("1", "true", "yes"):
        r = subprocess.run(["git", "-C", str(repo), "verify-commit", "HEAD"], capture_output=True, text=True)
        if r.returncode != 0:
            raise NotAuthorized(
                f"FW_REQUIRE_SIGNED_COMMIT is set but HEAD has no valid signature: {r.stderr.strip()}"
            )
    return path, repo, rel


def load_policy(policy_file: str | Path) -> tuple[dict, str]:
    """Verify the fleet policy is committed and clean; return (policy, commit_sha)."""
    path, repo, rel = _verify_committed(policy_file)
    commit = _git(repo, "log", "-1", "--format=%H", "--", str(rel))
    with open(path) as f:
        policy = yaml.safe_load(f) or {}
    if not isinstance(policy.get("approvals"), dict):
        raise NotAuthorized(f"{rel} has no 'approvals:' mapping of host -> target revision")
    return policy, commit


def _entry_version(entry) -> str:
    """An entry is either a bare revision or a mapping carrying one."""
    if isinstance(entry, dict):
        if "version" not in entry:
            raise NotAuthorized(f"policy entry {entry!r} has no 'version:'")
        return str(entry["version"])
    return str(entry)


def load_ops_authorization(ops_file: str | Path, plc_ip: str, target_revision: str) -> tuple[str, str]:
    """Authorize from a one-shot ops file instead of the fleet policy.

    Same git proof as load_policy: tracked, unmodified, optionally signed. The
    ops file names exactly one device and one revision, so a mismatch against
    what the catalog resolved is a refusal rather than something to reconcile.
    Returns (commit_sha, approved_by).
    """
    path, repo, rel = _verify_committed(ops_file)

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    if data.get("action") != "firmware_update":
        raise NotAuthorized(f"{rel} is not a firmware_update ops file (action={data.get('action')!r})")
    if str(data.get("plc_ip", "")) != plc_ip:
        raise NotAuthorized(
            f"{rel} authorizes {data.get('plc_ip')!r}, not {plc_ip} - one ops file, one device"
        )
    want = str(data.get("target_version", ""))
    if want != str(target_revision):
        raise NotAuthorized(
            f"{rel} authorizes firmware {want!r}, but the resolved bundle is {target_revision}"
        )

    approved_by = os.environ.get("WAGO_APPROVED_BY", "").strip() or str(data.get("approved_by", "")).strip()
    if not approved_by:
        raise NotAuthorized(
            f"{rel} has an empty approved_by. A human must fill it during PR review "
            f"before a firmware update can run."
        )

    commit = _git(repo, "log", "-1", "--format=%H", "--", str(rel))
    return commit, approved_by


def approved_hosts(policy: dict) -> dict[str, str]:
    """{ip: target_revision} for every host the policy approves."""
    return {str(host): _entry_version(entry) for host, entry in policy["approvals"].items()}


def _check_human_approval(plc_ip: str, entry) -> str:
    """Mapping entries carry the ops/-file review gate: requires_human plus an
    approved_by a human fills during PR review. WAGO_APPROVED_BY lets CI inject
    it, exactly as scripts/apply.py does for dangerous methods."""
    if not isinstance(entry, dict):
        return ""
    approved_by = os.environ.get("WAGO_APPROVED_BY", "").strip() or str(entry.get("approved_by", "")).strip()
    if entry.get("requires_human") and not approved_by:
        raise NotAuthorized(
            f"{plc_ip} is marked requires_human: {entry['requires_human']} but approved_by is empty. "
            f"A human must fill approved_by in the policy before this can run."
        )
    return approved_by


def authorize(policy: dict, commit: str, plc_ip: str, target_revision: str) -> tuple[str, str]:
    """Raise NotAuthorized unless this exact (host, revision) pair is approved.
    Returns (commit_sha, approved_by) - approved_by is "" for a bare-revision
    entry, where the commit itself is the approval."""
    approvals = approved_hosts(policy)
    if plc_ip not in approvals:
        raise NotAuthorized(
            f"{plc_ip} is not listed in the firmware policy. Approved hosts: "
            f"{', '.join(sorted(approvals)) or '(none)'}"
        )
    want = approvals[plc_ip]
    if want != str(target_revision):
        raise NotAuthorized(
            f"{plc_ip} is approved for firmware {want}, but the resolved bundle is "
            f"{target_revision}. Commit a policy change if {target_revision} is what you want."
        )
    approved_by = _check_human_approval(plc_ip, policy["approvals"][plc_ip])
    return commit, approved_by
