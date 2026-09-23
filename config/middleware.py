from django.http import JsonResponse
from django.conf import settings

class CorsBlockMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get('HTTP_ORIGIN')
        if origin:
            allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', [])
            if origin not in allowed_origins:
                return JsonResponse({'message': 'access denied'}, status=403)
        return self.get_response(request)


import logging

logger = logging.getLogger(__name__)

class ErrorLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code >= 400 and response.status_code < 500:
            try:
                # Log 4xx errors safely without blocking I/O or logging credentials
                logger.warning(f"Client error {response.status_code} on {request.method} {request.path}")
            except Exception:
                pass
        return response

