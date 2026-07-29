from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import User

class CustomJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        try:
            user_id = validated_token['user_id']
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise AuthenticationFailed('User not found', code='user_not_found')
        except KeyError:
            raise AuthenticationFailed('Invalid token payload', code='token_not_valid')
