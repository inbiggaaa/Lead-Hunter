"""Static regression checks for release-integrity guardrails."""

from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_deploy_workflow_uses_immutable_ci_verified_sha():
    workflow = (ROOT / ".github/workflows/deploy.yml").read_text()

    assert "context.payload.workflow_run.head_sha" in workflow
    assert "deploy_sha:" in workflow
    assert 'workflow_id: "ci.yml"' in workflow
    assert "git checkout --detach" in workflow
    assert "git pull --ff-only origin main" not in workflow
    assert "No successful CI run found" in workflow

def test_deploy_script_fails_closed_on_backup_and_worker_guards():
    script = (ROOT / "scripts/deploy.sh").read_text()

    assert '[[ -n "$DB_CONTAINER" ]]' in script
    assert '[[ -s "$BACKUP_FILE" ]]' in script
    assert "check_worker_stopped" in script
    assert "require_healthy_service" in script
    assert "FloodWait|CRITICAL" in script
