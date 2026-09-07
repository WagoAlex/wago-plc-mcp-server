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
IS the approval, and the same git checks apply. approved_by does not have to be
typed: it is resolved from the authenticated actor (WAGO_APPROVED_BY, which CI
sets from github.actor) or, failing that, from the commit author git recorded.

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
    # Where this file lives, so authorize() can ask git who approved it.
    policy["_git_location"] = (repo, rel)
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

    approved_by, source = resolve_approver(repo, rel, str(data.get("approved_by", "")).strip())
    if is_self_approved(repo, rel):
        source += ", self-approved"

    commit = _git(repo, "log", "-1", "--format=%H", "--", str(rel))
    return commit, f"{approved_by} [{source}]"


def approved_hosts(policy: dict) -> dict[str, str]:
    """{ip: target_revision} for every host the policy approves."""
    return {str(host): _entry_version(entry) for host, entry in policy["approvals"].items()}


def resolve_approver(repo: Path, rel: Path, declared: str) -> tuple[str, str]:
    """Who approved this, and how we know.

    Precedence, most authenticated first:
      1. WAGO_APPROVED_BY  - injected by CI from the authenticated actor
                             (github.actor), which cannot be forged in the YAML
      2. the commit author - whoever committed the approval, as git recorded it
      3. the declared value in the file - a typed name, weakest of the three

    Returns (approver, source). Raises only when nothing at all identifies a
    human, which in a git repository means the history is unusable.

    Note what auto-filling costs: an unsigned file no longer refuses on its own,
    because committing it now IS the approval. The two-person property moves to
    who is allowed to merge (branch protection) and to
    FW_REQUIRE_SEPARATE_APPROVER below.
    """
    env_actor = os.environ.get("WAGO_APPROVED_BY", "").strip()
    if env_actor:
        return env_actor, "authenticated actor (WAGO_APPROVED_BY)"

    author = _git(repo, "log", "-1", "--format=%an <%ae>", "--", str(rel))
    if author:
        return author, "commit author"

    if declared:
        return declared, "declared in file"
    raise NotAuthorized(f"cannot determine who approved {rel} - no actor, no commit author, no declared value")


def is_self_approved(repo: Path, rel: Path) -> bool:
    """True when the same person proposed and approved this file.

    Self-approval is allowed - one engineer maintaining a rack should not need a
    second account - but it is recorded in the audit log as such, so a later
    review can tell four-eyes changes from one-person ones without re-reading
    git history. Set FW_REQUIRE_SEPARATE_APPROVER=true to refuse it instead,
    for anything under a change-control requirement.
    """
    authors = {a.strip() for a in _git(repo, "log", "--format=%ae", "--", str(rel)).splitlines() if a.strip()}
    actor = os.environ.get("WAGO_APPROVED_BY", "").strip()
    # An externally authenticated actor (CI's github.actor) counts as a second
    # party only if it is not simply the lone commit author under another name.
    self_approved = len(authors) < 2 and not actor

    if self_approved and os.environ.get("FW_REQUIRE_SEPARATE_APPROVER", "").lower() in ("1", "true", "yes"):
        raise NotAuthorized(
            f"FW_REQUIRE_SEPARATE_APPROVER is set, but {rel} was only ever touched by "
            f"{next(iter(authors), 'one author')}. The person who proposes a firmware update "
            f"must not be the one who approves it."
        )
    return self_approved


def _check_human_approval(plc_ip: str, entry, repo: Path, rel: Path) -> tuple[str, str]:
    """Fleet-policy entries: a mapping carries the review gate. The approver is
    resolved from the authenticated actor or the commit author, so nobody has to
    type their own name into the file."""
    if not isinstance(entry, dict):
        return "", ""
    if not entry.get("requires_human"):
        declared = str(entry.get("approved_by", "")).strip()
        return declared, "declared in file" if declared else ""
    approver, source = resolve_approver(repo, rel, str(entry.get("approved_by", "")).strip())
    if is_self_approved(repo, rel):
        source += ", self-approved"
    return approver, source


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
    repo, rel = policy["_git_location"]
    approved_by, source = _check_human_approval(plc_ip, policy["approvals"][plc_ip], repo, rel)
    return commit, f"{approved_by} [{source}]" if source else approved_by
