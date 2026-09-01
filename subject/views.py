from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import Subject, SharedNotes
from .serializers import SubjectSerializer, SharedNotesSerializer
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
                val_str = str(semester_raw).strip().upper()
                roman_map = {
                    'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8,
                    'IX': 9, 'X': 10
                }
                semester_num = None
                if val_str in roman_map:
                    semester_num = roman_map[val_str]
                else:
                    try:
                        semester_num = int(float(val_str))
                    except (ValueError, TypeError):
                        pass
                
                if semester_num is None or semester_num <= 0:
                    row_errors.append(f"Invalid semester number: '{semester_raw}'. Must be an integer or Roman numeral (I, II, etc.).")
                else:
                    if department_obj:
                        semester_objs = Semester.objects.filter(department=department_obj)
                        is_valid_sem = False
                        for sem_rec in semester_objs:
                            if isinstance(sem_rec.semesters, list) and (semester_num in sem_rec.semesters or str(semester_num) in sem_rec.semesters):
                                is_valid_sem = True
                                break
                        
                        if is_valid_sem:
                            try:
                                semester_obj = Semester.objects.get(id=semester_num)
                            except Semester.DoesNotExist:
                                row_errors.append(f"Semester '{semester_num}' is not configured in the system.")
                        else:
                            row_errors.append(f"Semester '{semester_num}' is not configured for department '{department_raw}'.")
                    else:
                        row_errors.append("Department must be valid to map semester.")

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


class SharedNotesViewSet(viewsets.ModelViewSet):
    queryset = SharedNotes.objects.all().order_by('-created_at')
    serializer_class = SharedNotesSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        user = request.user

        # Scope visibility: Faculty sees ONLY their own uploaded notes; Admin/HOD/Principal sees all
        role_obj = getattr(user, 'role', None)
        role_name = getattr(role_obj, 'role_name', None) or getattr(role_obj, 'name', None) or str(role_obj or '')
        role_str = str(role_name).upper().replace(' ', '_')

        is_admin_or_hod_or_student = (
            getattr(user, 'is_superuser', False) or 
            getattr(user, 'is_staff', False) or 
            role_str in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'HOD', 'PRINCIPAL', 'VICE_PRINCIPAL', 'STUDENT']
        )

        if not is_admin_or_hod_or_student:
            queryset = queryset.filter(uploaded_by=user)
        
        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        semester_id = request.query_params.get('semester_id')
        section_id = request.query_params.get('section_id')
        subject_id = request.query_params.get('subject_id')
        folder_name = request.query_params.get('folder_name')
        search = request.query_params.get('search')

        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if folder_name:
            queryset = queryset.filter(folder_name__iexact=folder_name)
        if search:
            from django.db.models import Q
            queryset = queryset.filter(
                Q(file_name__icontains=search) |
                Q(folder_name__icontains=search) |
                Q(title__icontains=search) |
                Q(subject__subject_code__icontains=search) |
                Q(subject__subject_name__icontains=search)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Shared notes retrieved successfully",
                "data": paginated_response.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Shared notes retrieved successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='upload')
    def upload(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"code": 401, "message": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)
        
        # Check permissions: HOD, Faculty, Admin, Superadmin
        role_obj = getattr(user, 'role', None)
        role_name = getattr(role_obj, 'role_name', None) or getattr(role_obj, 'name', None) or str(role_obj or '')
        role_str = str(role_name).upper().replace(' ', '_')
        allowed_roles = ['HOD', 'FACULTY', 'TEACHER', 'ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'PRINCIPAL', 'VICE_PRINCIPAL']
        
        is_allowed = (
            getattr(user, 'is_superuser', False) or 
            getattr(user, 'is_staff', False) or 
            role_str in allowed_roles or 
            'FACULTY' in role_str or 
            'HOD' in role_str or 
            'TEACHER' in role_str
        )
        if not is_allowed:
            return Response({
                "code": 403,
                "message": f"Only HOD and Faculty are allowed to upload notes (your role: '{role_name}')."
            }, status=status.HTTP_403_FORBIDDEN)

        department_id = request.data.get('department_id')
        batch_id = request.data.get('batch_id')
        semester_id = request.data.get('semester_id')
        section_id = request.data.get('section_id')
        subject_id = request.data.get('subject_id')
        folder_name = (request.data.get('folder_name') or 'Unit 1').strip()
        title = (request.data.get('title') or '').strip()

        if not (department_id and batch_id and semester_id and section_id and subject_id):
            return Response({
                "code": 400,
                "message": "Department, Batch, Semester, Section, and Subject are all required fields."
            }, status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist('files')
        if not files:
            single_file = request.FILES.get('file')
            if single_file:
                files = [single_file]

        if not files:
            return Response({"code": 400, "message": "No document files provided for upload."}, status=status.HTTP_400_BAD_REQUEST)

        # Requirement 1: Maximum of 5 files in one request
        if len(files) > 5:
            return Response({
                "code": 400,
                "message": "You can upload a maximum of 5 files per request."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Allowed extensions
        allowed_extensions = ['.pdf', '.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt']
        forbidden_image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.tiff']

        import os
        # Validate each file
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext in forbidden_image_extensions:
                return Response({
                    "code": 400,
                    "message": f"Image files are not allowed: '{f.name}'."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            if ext not in allowed_extensions:
                return Response({
                    "code": 400,
                    "message": f"Unsupported file type for '{f.name}'. Only PDF, DOCX, XLSX, PPTX files are allowed."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Requirement 2: Size under 50MB
            if f.size > 50 * 1024 * 1024:
                return Response({
                    "code": 400,
                    "message": f"File '{f.name}' exceeds the 50MB limit."
                }, status=status.HTTP_400_BAD_REQUEST)

        # Upload files to Cloudflare R2
        from common.r2 import upload_file_to_r2
        from subject.models import Subject, SharedNotes
        from institution.models import Department, Batch, Semester, Section

        try:
            dept_obj = Department.objects.get(id=department_id)
            batch_obj = Batch.objects.get(id=batch_id)
            sem_obj = Semester.objects.get(id=semester_id)
            sec_obj = Section.objects.get(id=section_id)
            sub_obj = Subject.objects.get(id=subject_id)
        except Exception as e:
            return Response({"code": 400, "message": f"Invalid reference IDs: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

        created_notes = []
        for f in files:
            ext = os.path.splitext(f.name)[1].lower().lstrip('.')
            folder_path = f"notes/{sub_obj.subject_code}/{folder_name}".replace(' ', '_')
            public_url = upload_file_to_r2(f, folder_name=folder_path)

            note = SharedNotes.objects.create(
                department=dept_obj,
                batch=batch_obj,
                semester=sem_obj,
                section=sec_obj,
                subject=sub_obj,
                folder_name=folder_name,
                title=title or f.name,
                file_name=f.name,
                file_url=public_url,
                file_size=f.size,
                file_type=ext,
                uploaded_by=user
            )
            created_notes.append(note)

            # Broadcast WebSocket event
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
                                'event': 'shared_note_created',
                                'payload': SharedNotesSerializer(note).data
                            }
                        }
                    )
            except Exception:
                pass

        return Response({
            "code": 201,
            "message": f"Successfully uploaded and shared {len(created_notes)} note file(s).",
            "data": SharedNotesSerializer(created_notes, many=True).data
        }, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        
        role_obj = getattr(user, 'role', None)
        role_name = getattr(role_obj, 'role_name', None) or getattr(role_obj, 'name', None) or str(role_obj or '')
        role_str = str(role_name).upper().replace(' ', '_')
        is_admin_or_hod = getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False) or any(r in role_str for r in ['HOD', 'ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'PRINCIPAL'])
        is_owner = instance.uploaded_by_id == user.id

        if not (is_admin_or_hod or is_owner):
            return Response({"code": 403, "message": "You can only delete notes uploaded by yourself."}, status=status.HTTP_403_FORBIDDEN)

        from common.r2 import delete_file_from_r2
        delete_file_from_r2(instance.file_url)

        note_id = instance.id
        instance.delete()

        # Broadcast WebSocket event
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
                            'event': 'shared_note_deleted',
                            'payload': {'id': note_id}
                        }
                    }
                )
        except Exception:
            pass

        return Response({"code": 200, "message": "Shared note deleted successfully."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='folders')
    def folders(self, request):
        user = request.user
        subject_id = request.query_params.get('subject_id')
        from subject.models import SharedNotes
        queryset = SharedNotes.objects.all()

        role_obj = getattr(user, 'role', None)
        role_name = getattr(role_obj, 'role_name', None) or getattr(role_obj, 'name', None) or str(role_obj or '')
        role_str = str(role_name).upper().replace(' ', '_')
        is_admin_or_hod_or_student = (
            getattr(user, 'is_superuser', False) or 
            getattr(user, 'is_staff', False) or 
            role_str in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'HOD', 'PRINCIPAL', 'VICE_PRINCIPAL', 'STUDENT']
        )
        if not is_admin_or_hod_or_student:
            queryset = queryset.filter(uploaded_by=user)

        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        folders_list = queryset.values_list('folder_name', flat=True).distinct()
        
        defaults = ['Unit 1', 'Unit 2', 'Unit 3', 'Unit 4', 'Unit 5', 'Question Bank', 'Lab Manual', 'Reference Notes']
        combined = list(dict.fromkeys(list(folders_list) + defaults))
        
        return Response({"code": 200, "data": combined}, status=status.HTTP_200_OK)

