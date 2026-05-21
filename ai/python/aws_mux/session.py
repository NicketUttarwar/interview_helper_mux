from __future__ import annotations

from pathlib import Path

from aws_mux.cli import run_aws_cli, sts_get_caller_identity

__all__ = ["run_aws_cli", "sts_get_caller_identity"]


def get_boto3_session(*, repo_root: Path | None = None):
    """Deprecated: AWS integration uses AWS CLI only. Use ``run_aws_cli`` or ``sts_get_caller_identity``."""
    raise RuntimeError(
        "aws_mux no longer uses boto3. Use run_aws_cli() or sts_get_caller_identity() "
        "(AWS CLI subprocess + JSON parse). See .cursor/rules/aws-cli-only.mdc."
    )
