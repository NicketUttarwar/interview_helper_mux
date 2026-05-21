#!/usr/bin/env python3
"""Verify AWS credentials via ``aws sts get-caller-identity`` (CLI only, no boto3)."""

from __future__ import annotations

import importlib.util
import argparse
import json
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "mux_tools_runtime", Path(__file__).resolve().parent / "_runtime.py"
)
_rt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_rt)
_rt.bootstrap(tools_file=__file__)

from aws_mux import sts_get_caller_identity
from pipeline.common import repo_root


def _hint_for_aws_error(msg: str) -> str:
    lower = msg.lower()
    if "no such file" in lower or ("not found" in lower and "aws" in lower):
        return (
            "AWS CLI not found. Install v2 (e.g. `brew install awscli`), then confirm "
            "`aws --version` works in the same terminal."
        )
    if (
        "credentials" in lower
        or "unable to locate" in lower
        or "invalidclienttokenid" in lower
        or "expired" in lower
        or "reauthenticate" in lower
        or "not authorized" in lower
        or "accessdenied" in lower
    ):
        return (
            "AWS credentials missing or invalid. Authenticate AWS CLI v2 in your shell "
            "(~/.aws) or set AWS_PROFILE / AWS_ACCESS_KEY_ID in config/secrets/secrets.env "
            "(see config/templates/secrets.env.example)."
        )
    return msg


def main() -> int:
    p = argparse.ArgumentParser(
        description="Call STS GetCallerIdentity using AWS CLI + repo secrets (optional overlay)."
    )
    p.add_argument("--repo", default=None, help="Repository root (default: auto-detect)")
    args = p.parse_args()
    repo_root_path = Path(args.repo).resolve() if args.repo else repo_root()

    try:
        ident = sts_get_caller_identity(repo_root=repo_root_path)
    except FileNotFoundError as e:
        print(_hint_for_aws_error(str(e)), file=sys.stderr)
        return 1
    except Exception as e:
        hint = _hint_for_aws_error(str(e))
        if hint != str(e):
            print(hint, file=sys.stderr)
            return 1
        raise

    print(json.dumps({k: ident[k] for k in ("UserId", "Account", "Arn") if k in ident}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
