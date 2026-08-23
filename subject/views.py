from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import Subject
from .serializers import SubjectSerializer
from .permissions import SubjectPermission


class SubjectViewSet(viewsets.ModelViewSet):
    queryset = Subject.objects.all().order_by('id')
    serializer_class = SubjectSerializer
    permission_classes = [SubjectPermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Subject not found"
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

        # Standard DRF ValidationError handles status 400 automatically, but let's format it nicely if it has detail dict
        from rest_framework.exceptions import ValidationError
        if isinstance(exc, ValidationError):
            # Extract first error message
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
                first_msg = errors[0]
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        self._broadcast_change(instance, 'subject_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'subject_updated')

    def perform_destroy(self, instance):
        subject_id = instance.id
        instance.delete()
        self._broadcast_delete(subject_id)

    def _broadcast_change(self, instance, event_name):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': event_name,
                            'payload': SubjectSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, subject_id):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': 'subject_deleted',
                            'payload': {
                                'id': subject_id
                            }
                        }
                    }
                )
        except Exception:
            pass

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Filtering parameters
        department_id = request.query_params.get('department_id')
        regulation_id = request.query_params.get('regulation_id')
        semester_id = request.query_params.get('semester_id')
        is_theory = request.query_params.get('is_theory')
        is_lab = request.query_params.get('is_lab')
        is_active = request.query_params.get('is_active')
        search = request.query_params.get('search')

        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if regulation_id:
            queryset = queryset.filter(regulation_id=regulation_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)
        if is_theory:
            queryset = queryset.filter(is_theory=is_theory.lower() in ['true', 'yes', '1'])
        if is_lab:
            queryset = queryset.filter(is_lab=is_lab.lower() in ['true', 'yes', '1'])
        if is_active:
            queryset = queryset.filter(is_active=is_active.lower() in ['true', 'yes', '1'])
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(subject_code__icontains=search) |
                Q(subject_name__icontains=search)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Subjects listed successfully",
                "data": paginated_response.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Subjects listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Subject retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Subject created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Subject updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Subject deleted successfully"
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        from django.db import transaction
        from institution.models import Regulation, Department, Semester
        
        subjects_data = request.data.get('subjects', [])
        if not subjects_data:
            return Response({
                "code": 400,
                "message": "No subject data provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Cache lookups
        regs_map = {r.regulation_code.upper(): r for r in Regulation.objects.all()}
        depts_code_map = {d.department_code.upper(): d for d in Department.objects.all()}
        depts_short_map = {d.short_name.upper(): d for d in Department.objects.all()}
        depts_name_map = {d.department_name.upper(): d for d in Department.objects.all()}
        
        seen_codes = set()
        errors = []
        validated_subjects = []

        for idx, s in enumerate(subjects_data):
            row_num = s.get('s_no', idx + 1)
            subject_code = str(s.get('subject_code', '')).strip().upper()
            subject_name = str(s.get('subject_name', '')).strip()
            credits_raw = s.get('credits')
            regulation_raw = str(s.get('regulation', '')).strip().upper()
            department_raw = str(s.get('department', '')).strip().upper()
            semester_raw = s.get('semester')
            
            is_theory_raw = s.get('is_theory', True)
            is_lab_raw = s.get('is_lab', False)
            is_active_raw = s.get('is_active', True)

            row_errors = []

            if not subject_code:
                row_errors.append("Subject code is required.")
            else:
                if subject_code in seen_codes:
                    row_errors.append(f"Duplicate subject code '{subject_code}' in sheet.")
                else:
                    seen_codes.add(subject_code)
                    if Subject.objects.filter(subject_code__iexact=subject_code).exists():
                        row_errors.append(f"Subject code '{subject_code}' already exists in database.")

            if not subject_name:
                row_errors.append("Subject name is required.")

            # Validate credits
            try:
                credits_val = float(credits_raw)
                if credits_val <= 0:
                    row_errors.append("Credits must be a positive number.")
            except (ValueError, TypeError):
                row_errors.append(f"Invalid credits: '{credits_raw}'. Must be a positive number.")

            # Validate regulation
            regulation_obj = None
            if not regulation_raw:
                row_errors.append("Regulation code is required.")
            else:
                regulation_obj = regs_map.get(regulation_raw)
                if not regulation_obj:
                    row_errors.append(f"Regulation '{regulation_raw}' does not exist.")

            # Validate department
            department_obj = None
            if not department_raw:
                row_errors.append("Department is required.")
            else:
                department_obj = (
                    depts_code_map.get(department_raw) or 
                    depts_short_map.get(department_raw) or 
                    depts_name_map.get(department_raw)
                )
                if not department_obj:
                    row_errors.append(f"Department '{department_raw}' does not exist.")

            # Validate semester
            semester_obj = None
            if semester_raw is None or str(semester_raw).strip() == "":
                row_errors.append("Semester is required.")
            else:
                try:
                    semester_num = int(float(str(semester_raw).strip()))
                    if semester_num <= 0:
                        row_errors.append("Semester must be a positive integer.")
                    else:
                        try:
                            semester_obj = Semester.objects.get(id=semester_num)
                        except Semester.DoesNotExist:
                            row_errors.append(f"Semester '{semester_num}' is not configured in the system.")
                except (ValueError, TypeError):
                    row_errors.append(f"Invalid semester number: '{semester_raw}'. Must be an integer.")

            # Handle booleans
            def parse_bool(val, default):
                if val is None or str(val).strip() == "":
                    return default
                val_str = str(val).strip().lower()
                if val_str in ('true', 'yes', 'y', '1'):
                    return True
                if val_str in ('false', 'no', 'n', '0'):
                    return False
                return default

            is_theory = parse_bool(is_theory_raw, True)
            is_lab = parse_bool(is_lab_raw, False)
            is_active = parse_bool(is_active_raw, True)

            if row_errors:
                errors.append({
                    "row": row_num,
                    "subject_code": subject_code or "Unknown",
                    "errors": row_errors
                })
            else:
                validated_subjects.append({
                    "subject_code": subject_code,
                    "subject_name": subject_name,
                    "credits": credits_val,
                    "regulation": regulation_obj,
                    "department": department_obj,
                    "semester": semester_obj,
                    "is_theory": is_theory,
                    "is_lab": is_lab,
                    "is_active": is_active
                })

        if errors:
            return Response({
                "code": 400,
                "message": "Validation failed for some rows.",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Save Phase
        user = request.user if request.user and request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        created_subjects = []
        try:
            with transaction.atomic():
                for s_data in validated_subjects:
                    subject = Subject.objects.create(
                        subject_code=s_data["subject_code"],
                        subject_name=s_data["subject_name"],
                        credits=s_data["credits"],
                        regulation=s_data["regulation"],
                        department=s_data["department"],
                        semester=s_data["semester"],
                        is_theory=s_data["is_theory"],
                        is_lab=s_data["is_lab"],
                        is_active=s_data["is_active"],
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )
                    created_subjects.append(subject)
                    
                    # Broadcast create event
                    try:
                        from asgiref.sync import async_to_sync
                        from channels.layers import get_channel_layer
                        channel_layer = get_channel_layer()
                        if channel_layer:
                            async_to_sync(channel_layer.group_send)(
                                'realtime_updates',
                                {
                                    'type': 'broadcast_update',
                                    'data': {
                                        'event': 'subject_created',
                                        'payload': SubjectSerializer(subject).data
                                    }
                                }
                            )
                    except Exception:
                        pass
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Database save failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "code": 201,
            "message": f"Successfully imported {len(created_subjects)} subjects."
        }, status=status.HTTP_201_CREATED)
