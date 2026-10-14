from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import User

class CustomJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # First try standard header-based authentication
        result = super().authenticate(request)
        if result is not None:
            return result

        # Fallback: read token from ?token= query param (for browser-tab PDF downloads)
        raw_token = request.query_params.get('token')
        if not raw_token:
            return None

        try:
            validated_token = self.get_validated_token(raw_token)
            user = self.get_user(validated_token)
            return (user, validated_token)
        except Exception:
            return None

    def get_user(self, validated_token):
        from django.core.cache import cache
        try:
            user_id = validated_token['user_id']
            if validated_token.get('user_type') == 'candidate':
                from dynamic_forms.models import ApplicationUser
                return ApplicationUser.objects.get(id=user_id)

            cache_key = f'jwt_auth_user_{user_id}'
            cached_user = cache.get(cache_key)
            if cached_user is not None:
                return cached_user

            user = User.objects.select_related('role').get(id=user_id)
            cache.set(cache_key, user, timeout=60)
            return user
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found', code='user_not_found')
        except Exception:
            try:
                from dynamic_forms.models import ApplicationUser
                return ApplicationUser.objects.get(id=user_id)
            except Exception:
                raise AuthenticationFailed('User not found', code='user_not_found')
