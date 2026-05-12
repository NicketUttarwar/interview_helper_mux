"""AWS SDK entrypoints (region + credentials from env / ``config/secrets``)."""

from aws_mux.session import get_boto3_session

__all__ = ["get_boto3_session"]
