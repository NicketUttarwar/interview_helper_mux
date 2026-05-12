#!/usr/bin/env python3
"""Verify AWS credentials and default region (STS GetCallerIdentity)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "ai" / "python"))

    p = argparse.ArgumentParser(description="Call STS GetCallerIdentity using AWS settings from config/secrets/.")
    p.add_argument("--repo", default=str(repo), help="Repository root")
    args = p.parse_args()
    repo_root = Path(args.repo).resolve()

    from aws_mux import get_boto3_session

    try:
        session = get_boto3_session(repo_root=repo_root)
        sts = session.client("sts")
        ident = sts.get_caller_identity()
    except Exception as e:
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

        if isinstance(e, (NoCredentialsError, BotoCoreError)) or (
            isinstance(e, ClientError) and e.response["Error"]["Code"] in ("InvalidClientTokenId", "SignatureDoesNotMatch")
        ):
            print(
                "AWS credentials missing or invalid. Set AWS_PROFILE or "
                "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION "
                "in config/secrets/secrets.env (see config/templates/secrets.env.example).",
                file=sys.stderr,
            )
            return 1
        raise

    print(json.dumps({k: ident[k] for k in ("UserId", "Account", "Arn") if k in ident}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
