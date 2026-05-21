"""AWS integrations via AWS CLI subprocess (no boto3)."""

from aws_mux.cli import run_aws_cli, sts_get_caller_identity

__all__ = ["run_aws_cli", "sts_get_caller_identity"]
