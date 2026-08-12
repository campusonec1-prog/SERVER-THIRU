from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from .models import User, UserDetails
from .serializers import UserSerializer, UserDetailsSerializer
from .permissions import IsAdminUser, UserPermission, UserDetailsPermission

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by('id')
    serializer_class = UserSerializer
    permission_classes = [UserPermission]

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

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


class UserDetailsViewSet(viewsets.ModelViewSet):
    queryset = UserDetails.objects.all().order_by('id')
    serializer_class = UserDetailsSerializer
    permission_classes = [UserDetailsPermission]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return UserDetails.objects.none()

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if is_admin:
            return UserDetails.objects.all().order_by('id')

        if isinstance(user, User):
            return UserDetails.objects.filter(user=user).order_by('id')

        return UserDetails.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        tracking_user = user if isinstance(user, User) else None

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin and isinstance(user, User):
            serializer.save(user=user, created_by=tracking_user, updated_by=tracking_user)
        else:
            serializer.save(created_by=tracking_user, updated_by=tracking_user)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            if instance.user != user:
                raise PermissionDenied("You do not have permission to update these user details.")

        tracking_user = user if isinstance(user, User) else None
        serializer.save(updated_by=tracking_user)

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            if instance.user != user:
                raise PermissionDenied("You do not have permission to delete these user details.")

        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details deleted successfully"
        }, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "User details created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "User details not found"
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

        if isinstance(exc, ValidationError):
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)


