from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from .models import User
from .serializers import UserSerializer
from .permissions import IsAdminUser

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('id')
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return []

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Users listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "User created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "deleted successfully"
        }, status=status.HTTP_200_OK)

    def login(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')

        if username is None or password is None:
            return Response({
                "code": 400,
                "message": "Username and password are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Convert to string to avoid AttributeError if client sends an integer password or username
        username = str(username)
        password = str(password)

        if not username.strip() or not password.strip():
            return Response({
                "code": 400,
                "message": "Username and password cannot be empty."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return Response({
                "code": 404,
                "message": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)

        import bcrypt
        if not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return Response({
                "code": 400,
                "message": "Invalid password"
            }, status=status.HTTP_400_BAD_REQUEST)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return Response({
            "code": 200,
            "message": "Logged in successfully",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": UserSerializer(user).data
            }
        }, status=status.HTTP_200_OK)

    def handle_exception(self, exc):
        from django.http import Http404
        from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied

        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "User not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        return super().handle_exception(exc)

