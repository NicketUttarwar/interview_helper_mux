from __future__ import annotations

from pathlib import Path

from mux_secrets import get_config_value, load_repo_config, repo_root_from_here


def get_boto3_session(*, repo_root: Path | None = None):
    """
    Build a ``boto3.Session`` using only values from ``config/secrets/secrets.env``
    (and legacy ``openai.env`` for the same keys). Nothing is read from ``os.environ``.

    Recognized keys: ``AWS_PROFILE`` **or** ``AWS_ACCESS_KEY_ID`` + ``AWS_SECRET_ACCESS_KEY``,
    plus ``AWS_DEFAULT_REGION`` or ``AWS_REGION``.
    """
    root = (repo_root or repo_root_from_here()).resolve()
    load_repo_config(root)
    try:
        import boto3
    except ImportError as e:
        raise ImportError("Install boto3: pip install boto3") from e

    profile = get_config_value("AWS_PROFILE")
    if profile:
        region = get_config_value("AWS_DEFAULT_REGION") or get_config_value("AWS_REGION") or None
        return boto3.Session(profile_name=profile, region_name=region)

    access_key = get_config_value("AWS_ACCESS_KEY_ID")
    secret_key = get_config_value("AWS_SECRET_ACCESS_KEY")
    if not access_key or not secret_key:
        raise RuntimeError(
            "AWS is not configured in config/secrets/secrets.env. "
            "Set AWS_PROFILE, or AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, "
            "and AWS_DEFAULT_REGION (see config/templates/secrets.env.example)."
        )
    region = get_config_value("AWS_DEFAULT_REGION") or get_config_value("AWS_REGION") or "us-east-1"
    return boto3.Session(
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )
