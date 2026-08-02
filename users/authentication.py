from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import User

class CustomJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user_id = validated_token['user_id']
            if validated_token.get('user_type') == 'candidate':
                from dynamic_forms.models import ApplicationUser
                return ApplicationUser.objects.get(id=user_id)
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found', code='user_not_found')
        except Exception:
            try:
                from dynamic_forms.models import ApplicationUser
                return ApplicationUser.objects.get(id=user_id)
            except Exception:
                raise AuthenticationFailed('User not found', code='user_not_found')

