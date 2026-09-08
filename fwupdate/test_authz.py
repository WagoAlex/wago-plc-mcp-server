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


def test_approves_committed_host_and_revision(repo, monkeypatch):
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    p = write_policy(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve 10.0.0.1")

    policy, commit = authz.load_policy(p)
    sha, approved_by = authz.authorize(policy, commit, "10.0.0.1", "4.9.1")
    assert sha == commit and "t@example.com" in approved_by
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


def test_empty_approved_by_is_filled_from_the_commit_author(repo, monkeypatch):
    """Nobody types their own name: an empty approved_by resolves to whoever git
    recorded as the author of the approving commit."""
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    version: "4.9.1"\n'
                           '    requires_human: CRITICAL\n    approved_by: ""\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    _, approved_by = authz.authorize(policy, commit, "10.0.0.1", "4.9.1")
    assert "t@example.com" in approved_by
    assert "commit author" in approved_by


def test_authenticated_actor_outranks_the_file(repo, monkeypatch):
    """CI injects the authenticated actor; a name typed in the YAML must not win."""
    monkeypatch.setenv("WAGO_APPROVED_BY", "ci-actor")
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    version: "4.9.1"\n'
                           '    requires_human: CRITICAL\n    approved_by: "typed-name"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    _, approved_by = authz.authorize(policy, commit, "10.0.0.1", "4.9.1")
    assert "ci-actor" in approved_by and "typed-name" not in approved_by


def test_mapping_entry_with_human_approval_passes(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    version: "4.9.1"\n'
                           '    requires_human: CRITICAL\n    approved_by: "ALEX"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    _, approved_by = authz.authorize(policy, commit, "10.0.0.1", "4.9.1")
    assert "ALEX" not in approved_by or "commit author" in approved_by


def test_ci_can_inject_approved_by(repo, monkeypatch):
    """Same escape hatch scripts/apply.py gives CI for dangerous methods."""
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    version: "4.9.1"\n'
                           '    requires_human: CRITICAL\n    approved_by: ""\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    policy, commit = authz.load_policy(p)
    monkeypatch.setenv("WAGO_APPROVED_BY", "ci-pipeline")
    assert "ci-pipeline" in authz.authorize(policy, commit, "10.0.0.1", "4.9.1")[1]


def test_mapping_entry_without_version_refused(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    approved_by: "ALEX"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "broken")
    policy, _ = authz.load_policy(p)
    with pytest.raises(authz.NotAuthorized, match="neither 'allowed:' nor 'version:'"):
        authz.approved_hosts(policy)


# --- ops-file authorization: firmware treated exactly like a reboot ----------

def write_ops(repo, approved_by='""', version='"4.9.1"', ip="10.0.0.1", action="firmware_update"):
    p = repo / "fw-test.yaml"
    p.write_text(f'id: fw-test\nplc_ip: {ip}\naction: {action}\n'
                 f'target_version: {version}\nrequires_human: CRITICAL\napproved_by: {approved_by}\n')
    return p


def test_ops_file_authorizes_and_names_the_approver(repo, monkeypatch):
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    p = write_ops(repo, approved_by='"ALEX"')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    commit, approved_by = authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")
    assert len(commit) == 40 and "t@example.com" in approved_by


def test_ops_file_without_signoff_is_self_approved_and_marked(repo, monkeypatch):
    """Self-approval is allowed - one engineer, one rack - but the audit record
    has to say so, or a later review cannot tell it from a four-eyes change."""
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    p = write_ops(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    _, approved_by = authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")
    assert "t@example.com" in approved_by
    assert "self-approved" in approved_by


def test_two_authors_are_not_marked_self_approved(repo, monkeypatch):
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    p = write_ops(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    p.write_text(p.read_text().replace('approved_by: ""', 'approved_by: "reviewed"'))
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=reviewer@example.com", "-c", "user.name=rev",
        "commit", "-qm", "approve")
    _, approved_by = authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")
    assert "self-approved" not in approved_by


def test_separate_approver_can_be_required(repo, monkeypatch):
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    monkeypatch.setenv("FW_REQUIRE_SEPARATE_APPROVER", "true")
    p = write_ops(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    with pytest.raises(authz.NotAuthorized, match="must not be the one who approves"):
        authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")


def test_ops_file_is_bound_to_one_device(repo):  # noqa: D103
    """A merged ops file must not be reusable against a different controller."""
    p = write_ops(repo, approved_by='"ALEX"', ip="10.0.0.1")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    with pytest.raises(authz.NotAuthorized, match="one ops file, one device"):
        authz.load_ops_authorization(p, "10.0.0.99", "4.9.1")


def test_ops_file_is_bound_to_one_revision(repo):
    p = write_ops(repo, approved_by='"ALEX"', version='"4.9.1"')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    with pytest.raises(authz.NotAuthorized, match="authorizes firmware"):
        authz.load_ops_authorization(p, "10.0.0.1", "4.9.50")


def test_reboot_ops_file_cannot_authorize_a_flash(repo):
    p = write_ops(repo, approved_by='"ALEX"', action="invoke_method")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "reboot")
    with pytest.raises(authz.NotAuthorized, match="not a firmware_update ops file"):
        authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")


def test_uncommitted_ops_edit_refused(repo):
    p = write_ops(repo, approved_by='""')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    p.write_text(p.read_text().replace('approved_by: ""', 'approved_by: "self"'))
    with pytest.raises(authz.NotAuthorized, match="uncommitted"):
        authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")


def test_authorization_file_in_a_subdirectory(repo, monkeypatch):
    """git resolves a pathspec relative to the cwd, so running git from the
    file's own directory reports every ops/ file as untracked."""
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    (repo / "ops").mkdir()
    p = repo / "ops" / "fw-1.yaml"
    p.write_text('id: fw-1\nplc_ip: 10.0.0.1\naction: firmware_update\n'
                 'target_version: "4.9.1"\nrequires_human: CRITICAL\napproved_by: "ALEX"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")

    commit, approved_by = authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")
    assert len(commit) == 40 and "t@example.com" in approved_by


def test_uncommitted_edit_detected_in_a_subdirectory(repo):
    (repo / "ops").mkdir()
    p = repo / "ops" / "fw-1.yaml"
    p.write_text('id: fw-1\nplc_ip: 10.0.0.1\naction: firmware_update\n'
                 'target_version: "4.9.1"\nrequires_human: CRITICAL\napproved_by: ""\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    p.write_text(p.read_text().replace('approved_by: ""', 'approved_by: "self"'))
    with pytest.raises(authz.NotAuthorized, match="uncommitted"):
        authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")


def test_pr_review_outranks_and_names_the_pull_request(repo, monkeypatch):
    """The approval event is the PR review, not the commit. A merge or squash
    commit is authored by the platform, so the commit author is the wrong
    anchor exactly where it matters."""
    monkeypatch.setenv("WAGO_APPROVED_BY", "alice")
    monkeypatch.setenv("WAGO_APPROVAL_REF", "wago-plc-config#4 approved by alice, merged by bob")
    p = write_ops(repo, approved_by='""')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")

    _, approved_by = authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")
    assert "alice" in approved_by
    assert "PR review" in approved_by and "#4" in approved_by
    assert "self-approved" not in approved_by, "an external reviewer is not self-approval"


def test_without_a_pr_ref_the_actor_is_still_used(repo, monkeypatch):
    monkeypatch.setenv("WAGO_APPROVED_BY", "ci-actor")
    monkeypatch.delenv("WAGO_APPROVAL_REF", raising=False)
    p = write_ops(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "propose")
    _, approved_by = authz.load_ops_authorization(p, "10.0.0.1", "4.9.1")
    assert "ci-actor" in approved_by and "authenticated actor" in approved_by


# --- allowed version lists, newest is the default ---------------------------

def test_allowed_list_permits_every_listed_revision(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    allowed: ["4.9.1", "4.9.50"]\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)

    assert authz.allowed_versions_for(policy, "10.0.0.1") == ["4.9.1", "4.9.50"]
    for v in ("4.9.1", "4.9.50"):
        authz.authorize(policy, commit, "10.0.0.1", v)


def test_default_is_the_newest_allowed(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    allowed: ["4.9.1", "4.9.50", "4.8.9"]\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, _ = authz.load_policy(p)
    assert authz.approved_hosts(policy) == {"10.0.0.1": "4.9.50"}, "newest wins, not last-listed"


def test_an_explicit_default_overrides_newest(repo):
    """A device held back on purpose: newest allowed, but not the default."""
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    allowed: ["4.9.1", "4.9.50"]\n    default: "4.9.1"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, _ = authz.load_policy(p)
    assert authz.approved_hosts(policy) == {"10.0.0.1": "4.9.1"}


def test_a_default_outside_the_allowed_list_is_refused(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    allowed: ["4.9.1"]\n    default: "4.9.50"\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "broken")
    policy, _ = authz.load_policy(p)
    with pytest.raises(authz.NotAuthorized, match="not in its allowed list"):
        authz.approved_hosts(policy)


def test_a_revision_outside_the_allowed_list_is_refused(repo):
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    allowed: ["4.9.1"]\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    with pytest.raises(authz.NotAuthorized, match="approved for firmware 4.9.1"):
        authz.authorize(policy, commit, "10.0.0.1", "4.9.50")


def test_bare_revision_still_works(repo):
    p = write_policy(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    assert authz.approved_hosts(policy) == {"10.0.0.1": "4.9.1"}
    authz.authorize(policy, commit, "10.0.0.1", "4.9.1")


def test_a_bare_revision_entry_still_names_an_approver(repo, monkeypatch):
    """A record that says a flash happened but not who stood behind it is the
    one thing an audit trail must not produce."""
    monkeypatch.delenv("WAGO_APPROVED_BY", raising=False)
    p = write_policy(repo)  # bare "10.0.0.1: 4.9.1"
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)

    _, approved_by = authz.authorize(policy, commit, "10.0.0.1", "4.9.1")
    assert approved_by, "bare-revision entries must still record an approver"
    assert "t@example.com" in approved_by
    assert "self-approved" in approved_by


def test_allowed_list_entry_names_an_approver(repo, monkeypatch):
    monkeypatch.setenv("WAGO_APPROVED_BY", "alice")
    p = write_policy(repo, 'approvals:\n  10.0.0.1:\n    allowed: ["4.9.1"]\n')
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "approve")
    policy, commit = authz.load_policy(p)
    _, approved_by = authz.authorize(policy, commit, "10.0.0.1", "4.9.1")
    assert "alice" in approved_by
