from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
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
                "code": 400,
                "message": "Invalid username or password."
            }, status=status.HTTP_400_BAD_REQUEST)

        import bcrypt
        if not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return Response({
                "code": 400,
                "message": "Invalid username or password."
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

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        import bcrypt
        from django.db import transaction
        from role.models import Role
        from institution.models import Department
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        from datetime import datetime
        import datetime as dt

        def parse_date(date_str):
            if not date_str:
                return None
            if isinstance(date_str, datetime):
                return date_str.date()
            if isinstance(date_str, dt.date):
                return date_str
            date_str = str(date_str).strip()
            if not date_str:
                return None
            # Strip time portion if present (e.g. "2024-05-12T00:00:00.000Z" -> "2024-05-12")
            if 'T' in date_str:
                date_str = date_str.split('T')[0]
            elif ' ' in date_str:
                date_str = date_str.split(' ')[0]
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y'):
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    pass
            return None

        users_data = request.data.get('users', [])
        if not users_data:
            return Response({
                "code": 400,
                "message": "No user data provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Cache roles and departments for fast lookup
        roles_map = {r.role_name.upper(): r.role_id for r in Role.objects.all()}
        depts_map = {d.department_code.upper(): d for d in Department.objects.all()}
        depts_name_map = {d.department_name.upper(): d for d in Department.objects.all()}

        # Track uniqueness of values within the upload sheet
        seen_usernames = set()
        seen_emails = set()
        seen_faculty_codes = set()

        errors = []
        validated_users = []

        # 1. Validation Phase (No DB writes)
        for idx, u in enumerate(users_data):
            row_num = u.get('s_no', idx + 1)
            name = str(u.get('name', '')).strip()
            faculty_code = str(u.get('faculty_code', '')).strip()
            mail = str(u.get('mail', '')).strip()
            mobile_number = str(u.get('mobile_number', '')).strip()
            role_name = str(u.get('role', '')).strip().upper()
            qualification = str(u.get('qualification', '')).strip()
            designation = str(u.get('designation', '')).strip()
            gender = str(u.get('gender', '')).strip()

            raw_doj = u.get('date_of_joining') or u.get('doj')
            raw_dob = u.get('dob')

            department_name = str(u.get('department', '')).strip()
            password = str(u.get('password', '')).strip()
            if not password:
                password = mobile_number

            row_errors = []

            # Check required fields
            if not name:
                row_errors.append("Name is required.")
            if not faculty_code:
                row_errors.append("Faculty code is required.")
            if not mail:
                row_errors.append("Email is required.")
            else:
                try:
                    validate_email(mail)
                except DjangoValidationError:
                    row_errors.append("Invalid email address format.")

            if not mobile_number:
                row_errors.append("Mobile number is required.")
            elif not (mobile_number.isdigit() and len(mobile_number) == 10):
                row_errors.append("Mobile number must be exactly 10 digits.")

            if not role_name:
                row_errors.append("Role is required.")
            elif role_name not in roles_map:
                row_errors.append(f"Role '{role_name}' does not exist in the system.")

            if not qualification:
                row_errors.append("Qualification is required.")
            if not designation:
                row_errors.append("Designation is required.")
            if not gender:
                row_errors.append("Gender is required.")
            elif gender.capitalize() not in ['Male', 'Female', 'Other']:
                row_errors.append("Gender must be 'Male', 'Female', or 'Other'.")

            # Parse and validate dates
            parsed_doj = parse_date(raw_doj)
            if not raw_doj:
                row_errors.append("Date of joining (DOJ) is required.")
            elif not parsed_doj:
                row_errors.append(f"Invalid date format for DOJ: '{raw_doj}'. Expected YYYY-MM-DD.")

            parsed_dob = parse_date(raw_dob) if raw_dob else None
            if raw_dob and not parsed_dob:
                row_errors.append(f"Invalid date format for DOB: '{raw_dob}'. Expected YYYY-MM-DD.")

            # Resolve Department
            dept_instance = None
            if department_name:
                dept_key = department_name.upper()
                if dept_key in depts_map:
                    dept_instance = depts_map[dept_key]
                elif dept_key in depts_name_map:
                    dept_instance = depts_name_map[dept_key]
                else:
                    matched_dept = Department.objects.filter(short_name__iexact=department_name).first()
                    if matched_dept:
                        dept_instance = matched_dept
                    else:
                        row_errors.append(f"Department '{department_name}' does not exist in the system.")

            # Check database-level uniqueness if no errors so far
            if not row_errors:
                username = faculty_code

                # Check for duplicates in the current uploaded batch
                if username in seen_usernames:
                    row_errors.append(f"Duplicate Faculty Code '{username}' inside this sheet.")
                if mail in seen_emails:
                    row_errors.append(f"Duplicate Email '{mail}' inside this sheet.")
                if faculty_code in seen_faculty_codes:
                    row_errors.append(f"Duplicate Faculty Code '{faculty_code}' inside this sheet.")

                # Check database records
                if User.objects.filter(username=username).exists():
                    row_errors.append(f"Username/Faculty Code '{username}' is already in use.")
                if User.objects.filter(mail=mail).exists():
                    row_errors.append(f"Email '{mail}' is already registered.")
                if UserDetails.objects.filter(faculty_code=faculty_code).exists():
                    row_errors.append(f"Faculty Code '{faculty_code}' is already registered.")

                if not row_errors:
                    seen_usernames.add(username)
                    seen_emails.add(mail)
                    seen_faculty_codes.add(faculty_code)

                    validated_users.append({
                        "name": name,
                        "username": username,
                        "mail": mail,
                        "mobile_number": mobile_number,
                        "password": password,
                        "role_id": roles_map[role_name],
                        "faculty_code": faculty_code,
                        "qualification": qualification,
                        "designation": designation,
                        "gender": gender.capitalize(),
                        "date_of_joining": parsed_doj,
                        "dob": parsed_dob,
                        "department": dept_instance
                    })

            if row_errors:
                errors.append({
                    "row": row_num,
                    "faculty_code": faculty_code,
                    "name": name,
                    "errors": row_errors
                })

        # If any validation errors exist, fail and do not write to the DB
        if errors:
            return Response({
                "code": 400,
                "message": "Validation errors found in the import data.",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Writing Phase (Inside transaction for atomicity)
        tracking_user = request.user if request.user and request.user.is_authenticated else None

        try:
            with transaction.atomic():
                for item in validated_users:
                    # Set password defaults to mobile_number if not provided
                    default_pass = item.get("password") or item["mobile_number"]
                    hashed_pass = bcrypt.hashpw(default_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

                    user = User.objects.create(
                        name=item["name"],
                        username=item["username"],
                        password=hashed_pass,
                        mobile_number=item["mobile_number"],
                        mail=item["mail"],
                        role_id=item["role_id"],
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    UserDetails.objects.create(
                        user=user,
                        faculty_code=item["faculty_code"],
                        qualification=item["qualification"],
                        designation=item["designation"],
                        date_of_joining=item["date_of_joining"],
                        gender=item["gender"],
                        dob=item["dob"],
                        department=item["department"],
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Database error during import: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "code": 201,
            "message": f"Successfully imported {len(validated_users)} faculty members.",
            "data": {
                "count": len(validated_users)
            }
        }, status=status.HTTP_201_CREATED)


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

        # Handle image upload to R2
        image_file = serializer.validated_data.pop('user_image_file', None)
        image_url = None
        if image_file:
            from common.r2 import upload_file_to_r2
            image_url = upload_file_to_r2(image_file, folder_name='user')

        save_kwargs = {'created_by': tracking_user, 'updated_by': tracking_user}
        if image_url:
            save_kwargs['user_image'] = image_url
        if not is_admin and isinstance(user, User):
            save_kwargs['user'] = user

        serializer.save(**save_kwargs)

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

        # Handle image upload to R2
        image_file = serializer.validated_data.pop('user_image_file', None)
        image_url = None
        if image_file:
            from common.r2 import upload_file_to_r2
            image_url = upload_file_to_r2(image_file, folder_name='user')

        tracking_user = user if isinstance(user, User) else None
        save_kwargs = {'updated_by': tracking_user}
        if image_url:
            save_kwargs['user_image'] = image_url

        serializer.save(**save_kwargs)

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


