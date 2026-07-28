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
