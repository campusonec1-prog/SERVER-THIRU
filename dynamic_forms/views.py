from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import FormModule, FormField, Application, ApplicationStatus, ApplicationUser
from .serializers import (
    FormModuleSerializer, FormFieldSerializer, ApplicationSerializer, 
    ApplicationStatusSerializer, ApplicationUserSerializer
)
from users.permissions import IsAdminUser


class AdminWriteMixin:
    """Restrict create/update/delete to Admin users; list/retrieve are public."""

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdminUser()]
        return []

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": f"{self.model_label} not found"
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

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(created_by=tracking_user, updated_by=tracking_user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)


class FormModuleViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FormModule.objects.all().order_by('display_order', 'id')
    serializer_class = FormModuleSerializer
    model_label = "Form Module"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Modules listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Form Module created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module deleted successfully"}, status=status.HTTP_200_OK)


class FormFieldViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FormField.objects.all().order_by('display_order', 'id')
    serializer_class = FormFieldSerializer
    model_label = "Form Field"

    def list(self, request, *args, **kwargs):
        # Allow filtering by form_module_id
        module_id = request.query_params.get('form_module_id')
        if module_id:
            self.queryset = self.queryset.filter(form_module_id=module_id)
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Fields listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Form Field created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field deleted successfully"}, status=status.HTTP_200_OK)


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all().order_by('-id')
    serializer_class = ApplicationSerializer
    model_label = "Application"

    def get_permissions(self):
        from rest_framework.permissions import IsAuthenticated
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Application.objects.none()
        
        if user.__class__.__name__ == 'ApplicationUser':
            return Application.objects.filter(candidate=user).order_by('-id')
        
        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if is_admin:
            return Application.objects.all().order_by('-id')
        return Application.objects.none()

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Application not found"
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

    def perform_create(self, serializer):
        program = serializer.validated_data.get('program')
        import datetime
        year = datetime.datetime.now().year
        year_str = str(year)[2:] # E.g. "26"
        prefix = f"{program.program_level}{year_str}"
        
        count = Application.objects.filter(application_no__startswith=prefix).count() + 1
        app_no = f"{prefix}{count:04d}"
        
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        
        # Candidate is automatically assigned via validate method in serializer
        serializer.save(application_no=app_no, created_by=tracking_user, updated_by=tracking_user)

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
            if user.__class__.__name__ != 'ApplicationUser' or instance.candidate != user:
                raise PermissionDenied("You do not have permission to edit this application.")
            
            if instance.status.status_name.lower() != 'draft':
                raise PermissionDenied("You cannot modify a submitted or completed application.")
            
            new_status = serializer.validated_data.get('status')
            if new_status and new_status.status_name.lower() in ['approved', 'rejected']:
                raise PermissionDenied("You do not have permission to approve or reject applications.")

        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            if user.__class__.__name__ != 'ApplicationUser' or instance.candidate != user:
                raise PermissionDenied("You do not have permission to delete this application.")
            if instance.status.status_name.lower() != 'draft':
                raise PermissionDenied("You cannot delete a submitted application.")

        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application deleted successfully"}, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Applications listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Application created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application updated successfully", "data": response.data}, status=status.HTTP_200_OK)


class ApplicationStatusViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = ApplicationStatus.objects.all().order_by('id')
    serializer_class = ApplicationStatusSerializer
    model_label = "Application Status"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Statuses listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Status retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Application Status created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Status updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Status deleted successfully"}, status=status.HTTP_200_OK)


class ApplicationUserViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = ApplicationUser.objects.all().order_by('id')
    serializer_class = ApplicationUserSerializer
    model_label = "Application User"

    def get_permissions(self):
        if self.action in ['list', 'destroy']:
            return [IsAdminUser()]
        elif self.action in ['update', 'partial_update']:
            from rest_framework.permissions import IsAuthenticated
            return [IsAuthenticated()]
        return []

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
            user_email = getattr(user, 'mail', getattr(user, 'email', None))
            if instance.email != user_email:
                raise PermissionDenied("You do not have permission to update this profile.")

        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Users listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application User retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Application User created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application User updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application User deleted successfully"}, status=status.HTTP_200_OK)


class ApplicationUserLoginView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({
                "code": 400,
                "message": "Email and password are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        email = str(email).strip()
        password = str(password).strip()

        try:
            cand = ApplicationUser.objects.get(email=email)
        except ApplicationUser.DoesNotExist:
            return Response({
                "code": 400,
                "message": "Invalid email or password."
            }, status=status.HTTP_400_BAD_REQUEST)

        import bcrypt
        if not bcrypt.checkpw(password.encode('utf-8'), cand.password.encode('utf-8')):
            return Response({
                "code": 400,
                "message": "Invalid email or password."
            }, status=status.HTTP_400_BAD_REQUEST)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken()
        refresh['user_id'] = cand.id
        refresh['email'] = cand.email
        refresh['user_type'] = 'candidate'
        
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return Response({
            "code": 200,
            "message": "Logged in successfully",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": ApplicationUserSerializer(cand).data
            }
        }, status=status.HTTP_200_OK)




