import boto3
from django.conf import settings
import uuid
import os
import logging

logger = logging.getLogger(__name__)

def get_r2_client():
    endpoint = getattr(settings, 'CLOUDFLARE_R2_ENDPOINT', None) or os.getenv('CLOUDFLARE_R2_ENDPOINT')
    access_key = getattr(settings, 'CLOUDFLARE_R2_ACCESS_KEY_ID', None) or os.getenv('CLOUDFLARE_R2_ACCESS_KEY_ID')
    secret_key = getattr(settings, 'CLOUDFLARE_R2_SECRET_ACCESS_KEY', None) or os.getenv('CLOUDFLARE_R2_SECRET_ACCESS_KEY')
    return boto3.client(
        's3',
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name='auto'
    )

def upload_file_to_r2(file_obj, folder_name="college_headers", folder=None):
    """
    Uploads a file object to Cloudflare R2 and returns its public URL.
    Supports both folder_name and folder keyword arguments.
    """
    target_folder = folder or folder_name or "college_headers"
    client = get_r2_client()
    
    bucket_name = getattr(settings, 'CLOUDFLARE_R2_BUCKET_NAME', None) or os.getenv('CLOUDFLARE_R2_BUCKET_NAME')
    public_url_base = getattr(settings, 'CLOUDFLARE_R2_PUBLIC_URL', None) or os.getenv('CLOUDFLARE_R2_PUBLIC_URL') or ''

    # Get extension
    ext = os.path.splitext(getattr(file_obj, 'name', 'file'))[1] or '.png'
    unique_filename = f"{target_folder}/{uuid.uuid4()}{ext}"
    
    # Try to guess content type if not present
    content_type = getattr(file_obj, 'content_type', 'application/octet-stream')
    
    client.upload_fileobj(
        file_obj,
        bucket_name,
        unique_filename,
        ExtraArgs={
            'ContentType': content_type
        }
    )
    
    # Combine with public URL base
    if public_url_base:
        return f"{public_url_base.rstrip('/')}/{unique_filename}"
    endpoint = getattr(settings, 'CLOUDFLARE_R2_ENDPOINT', None) or os.getenv('CLOUDFLARE_R2_ENDPOINT') or ''
    return f"{endpoint.rstrip('/')}/{bucket_name}/{unique_filename}"

def delete_file_from_r2(public_url):
    """
    Deletes a file from Cloudflare R2 given its public URL.
    """
    if not public_url:
        return
    
    public_url_base = (getattr(settings, 'CLOUDFLARE_R2_PUBLIC_URL', None) or os.getenv('CLOUDFLARE_R2_PUBLIC_URL') or '').rstrip('/')
    bucket_name = getattr(settings, 'CLOUDFLARE_R2_BUCKET_NAME', None) or os.getenv('CLOUDFLARE_R2_BUCKET_NAME')
    
    if public_url_base and public_url.startswith(public_url_base):
        key = public_url[len(public_url_base):].lstrip('/')
        client = get_r2_client()
        try:
            client.delete_object(
                Bucket=bucket_name,
                Key=key
            )
            logger.info(f"[R2] Deleted file: {key}")
        except Exception as e:
            logger.error(f"[R2] Failed to delete file {key}: {e}")

