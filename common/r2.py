import boto3
from django.conf import settings
import uuid
import os

def get_r2_client():
    return boto3.client(
        's3',
        endpoint_url=settings.CLOUDFLARE_R2_ENDPOINT,
        aws_access_key_id=settings.CLOUDFLARE_R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.CLOUDFLARE_R2_SECRET_ACCESS_KEY,
        region_name='auto'
    )

def upload_file_to_r2(file_obj, folder_name="college_headers"):
    """
    Uploads a file object to Cloudflare R2 and returns its public URL.
    """
    client = get_r2_client()
    
    # Get extension
    ext = os.path.splitext(file_obj.name)[1]
    # Use folder_name dynamically to isolate headers vs documents
    unique_filename = f"{folder_name}/{uuid.uuid4()}{ext}"
    
    # Try to guess content type if not present
    content_type = getattr(file_obj, 'content_type', 'application/octet-stream')
    
    client.upload_fileobj(
        file_obj,
        settings.CLOUDFLARE_R2_BUCKET_NAME,
        unique_filename,
        ExtraArgs={
            'ContentType': content_type
        }
    )
    
    # Combine with public URL base
    public_url_base = settings.CLOUDFLARE_R2_PUBLIC_URL.rstrip('/')
    return f"{public_url_base}/{unique_filename}"

def delete_file_from_r2(public_url):
    """
    Deletes a file from Cloudflare R2 given its public URL.
    """
    if not public_url:
        return
    
    public_url_base = settings.CLOUDFLARE_R2_PUBLIC_URL.rstrip('/')
    if public_url.startswith(public_url_base):
        key = public_url[len(public_url_base):].lstrip('/')
        client = get_r2_client()
        try:
            client.delete_object(
                Bucket=settings.CLOUDFLARE_R2_BUCKET_NAME,
                Key=key
            )
            print(f"[R2] Deleted file: {key}")
        except Exception as e:
            print(f"[R2] Failed to delete file {key}: {e}")
