"""Git-gated authorization. Every one of these is a refusal path that has to
hold - if the gate can be bypassed, the feature is theater."""
import subprocess

import pytest

import authz


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    return tmp_path


def write_policy(repo, body='approvals:\n  10.0.0.1: "4.9.1"\n'):
    p = repo / "firmware-policy.yaml"
    p.write_text(body)
    return p


def test_approves_committed_host_and_revision(repo):
    p = write_policy(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve 10.0.0.1")

    policy, commit = authz.load_policy(p)
    assert authz.authorize(policy, commit, "10.0.0.1", "4.9.1") == (commit, "")
    assert authz.approved_hosts(policy) == {"10.0.0.1": "4.9.1"}


def test_refuses_untracked_policy(repo):
    p = write_policy(repo)
    git(repo, "commit", "-qm", "empty", "--allow-empty")
    with pytest.raises(authz.NotAuthorized):
        authz.load_policy(p)


def test_refuses_uncommitted_edit(repo):
    """The whole point: editing the file locally must not authorize anything."""
    p = write_policy(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    p.write_text('approvals:\n  10.0.0.1: "4.9.1"\n  10.0.0.99: "4.9.1"\n')
    with pytest.raises(authz.NotAuthorized, match="uncommitted"):
        authz.load_policy(p)


def test_refuses_unlisted_host(repo):
    p = write_policy(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    with pytest.raises(authz.NotAuthorized, match="not listed"):
        authz.authorize(policy, commit, "10.0.0.2", "4.9.1")


def test_refuses_revision_mismatch(repo):
    p = write_policy(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    with pytest.raises(authz.NotAuthorized, match="approved for firmware 4.9.1"):
        authz.authorize(policy, commit, "10.0.0.1", "4.9.50")


def test_refuses_missing_file(tmp_path):
    with pytest.raises(authz.NotAuthorized, match="not found"):
        authz.load_policy(tmp_path / "nope.yaml")


def test_refuses_outside_git(tmp_path):
    p = tmp_path / "firmware-policy.yaml"
    p.write_text('approvals:\n  10.0.0.1: "4.9.1"\n')
    with pytest.raises(authz.NotAuthorized):
        authz.load_policy(p)


def test_mapping_entry_requires_human_approval(repo):
    """An unapproved PR must be safe to open: committed, but approved_by empty."""
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    version: "4.9.1"\n'
                           '    requires_human: CRITICAL\n    approved_by: ""\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    policy, commit = authz.load_policy(p)
    assert authz.approved_hosts(policy) == {"10.0.0.1": "4.9.1"}
    with pytest.raises(authz.NotAuthorized, match="approved_by is empty"):
        authz.authorize(policy, commit, "10.0.0.1", "4.9.1")


def test_mapping_entry_with_human_approval_passes(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    version: "4.9.1"\n'
                           '    requires_human: CRITICAL\n    approved_by: "ALEX"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    assert authz.authorize(policy, commit, "10.0.0.1", "4.9.1") == (commit, "ALEX")


def test_ci_can_inject_approved_by(repo, monkeypatch):
    """Same escape hatch scripts/apply.py gives CI for dangerous methods."""
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    version: "4.9.1"\n'
                           '    requires_human: CRITICAL\n    approved_by: ""\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    policy, commit = authz.load_policy(p)
    monkeypatch.setenv("WAGO_APPROVED_BY", "ci-pipeline")
    assert authz.authorize(policy, commit, "10.0.0.1", "4.9.1")[1] == "ci-pipeline"


def test_mapping_entry_without_version_refused(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    approved_by: "ALEX"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "broken")
    policy, _ = authz.load_policy(p)
    with pytest.raises(authz.NotAuthorized, match="no 'version:'"):
        authz.approved_hosts(policy)
