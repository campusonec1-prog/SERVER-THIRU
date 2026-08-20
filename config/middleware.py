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


class ErrorLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == 400:
            try:
                import json
                import os
                
                log_data = {
                    "path": request.path,
                    "method": request.method,
                    "response_content": json.loads(response.content.decode('utf-8')) if hasattr(response, 'content') else None
                }
                
                # Write to a debug file in the project folder
                log_file_path = os.path.join(settings.BASE_DIR, "debug_errors.txt")
                with open(log_file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_data, indent=2) + "\n\n")
            except Exception as e:
                pass
        return response

