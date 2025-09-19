import os
import boto3

S3_REGION = os.getenv("S3_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")

_session = boto3.session.Session()
s3_client = _session.client(
    "s3",
    region_name=S3_REGION,
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
)

def upload_file_preserve(path: str) -> str:
    """Upload file and return presigned URL"""
    key = f"downloads/{path.split('/')[-1]}"
    s3_client.upload_file(path, S3_BUCKET, key)
    url = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=int(os.getenv("RESULT_TTL_SECONDS", "86400")),
    )
    return url
