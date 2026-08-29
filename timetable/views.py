from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.http import Http404

from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import ExamTimetable, ClassTimetable, ActivityType
from .serializers import ExamTimetableSerializer, ClassTimetableSerializer, ActivityTypeSerializer
from .permissions import ExamTimetablePermission, ClassTimetablePermission, ActivityTypePermission
from schedule.models import Day, Period
from users.models import User as FacultyUser

class ExamTimetableViewSet(viewsets.ModelViewSet):
    queryset = ExamTimetable.objects.select_related(
        'academic_year', 'department', 'batch', 'section', 'semester', 'exam', 'subject', 'session', 'created_by'
    ).order_by('id')
    serializer_class = ExamTimetableSerializer
    permission_classes = [ExamTimetablePermission]
    model_label = "Exam timetable"

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return ExamTimetable.objects.none()
            
        queryset = ExamTimetable.objects.select_related(
            'academic_year', 'department', 'batch', 'section', 'semester', 'exam', 'subject', 'session', 'created_by'
        ).order_by('id')
        
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)
        if not is_admin:
            try:
                role = getattr(user, 'role', None)
                if role:
                    user_role = role.role_name.upper().replace(' ', '_')
                    if user_role in ['ADMIN', 'ADMINISTRATOR']:
                        is_admin = True
            except AttributeError:
                pass
                
        if not is_admin:
            queryset = queryset.filter(created_by=user)
            
        return queryset

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

        if isinstance(exc, ValidationError):
            errors = exc.detail
            # If errors is a list (e.g. bulk validation list of dicts/lists)
            if isinstance(errors, list):
                for err in errors:
                    if err:
                        errors = err
                        break
            
            # Extract the first clean message string
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list) and len(val) > 0:
                    first_msg = str(val[0])
                else:
                    first_msg = str(val)
            elif isinstance(errors, list) and len(errors) > 0:
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)

            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        academic_year_id = request.query_params.get('academic_year_id')
        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        exam_id = request.query_params.get('exam_id')
        semester_id = request.query_params.get('semester_id')
        section_id = request.query_params.get('section_id')
        exam_date = request.query_params.get('exam_date')
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)
        if section_id:
            if str(section_id).isdigit():
                queryset = queryset.filter(section_id=section_id)
            else:
                queryset = queryset.filter(section__sections__iexact=section_id)
        if exam_date:
            queryset = queryset.filter(exam_date=exam_date)
            
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Exam timetables listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Exam timetable retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        data = request.data
        is_many = isinstance(data, list)
        
        # Support nested structure: root fields with nested "exams" list
        if isinstance(data, dict) and 'exams' in data and isinstance(data['exams'], list):
            common_fields = {
                'academic_year_id': data.get('academic_year_id'),
                'batch_id': data.get('batch_id'),
                'department_id': data.get('department_id'),
                'exam_id': data.get('exam_id'),
                'section_id': data.get('section_id'),
                'semester_id': data.get('semester_id')
            }
            flat_records = []
            for exam_item in data['exams']:
                if isinstance(exam_item, dict):
                    record = {**common_fields, **exam_item}
                    flat_records.append(record)
            data = flat_records
            is_many = True

        if is_many:
            # 1. Check for duplicate (subject_id, subject_category) in list of entries
            seen_subjects = set()
            for record in data:
                subject_id = record.get('subject_id')
                subject_category = record.get('subject_category') or 'THEORY'
                if subject_id:
                    from subject.models import Subject
                    try:
                        subject_obj = Subject.objects.get(pk=subject_id)
                        subject_display = f"{subject_obj.subject_code} - {subject_obj.subject_name}"
                    except Subject.DoesNotExist:
                        subject_display = f"ID {subject_id}"

                    subject_key = (subject_id, subject_category)
                    if subject_key in seen_subjects:
                        cat_display = "Lab" if subject_category == 'LAB' else "Theory"
                        raise ValidationError(f"Duplicate subject '{subject_display}' ({cat_display}) is scheduled multiple times in the timetable.")
                    seen_subjects.add(subject_key)

            # 2. Check for overlapping date and session
            seen_slots = set()
            for record in data:
                date_val = record.get('exam_date')
                session_id = record.get('session_id')
                if date_val and session_id:
                    slot_key = (date_val, session_id)
                    if slot_key in seen_slots:
                        from schedule.models import Session
                        try:
                            session_obj = Session.objects.get(pk=session_id)
                            session_display = session_obj.session_name
                        except Session.DoesNotExist:
                            session_display = f"Session ID {session_id}"
                        raise ValidationError(f"Overlapping schedule: Multiple exams scheduled on {date_val} for session {session_display}.")
                    seen_slots.add(slot_key)

        serializer = self.get_serializer(data=data, many=is_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Broadcast changes to real-time websocket
        self._broadcast_change(serializer.data, 'exam_timetable_created')
        
        return Response({
            "code": 201,
            "message": "Exam timetable created successfully" if not is_many else "Exam timetables created successfully",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data

        # Support nested structure on update by flattening the first exam item
        if isinstance(data, dict) and 'exams' in data and isinstance(data['exams'], list):
            common_fields = {
                'academic_year_id': data.get('academic_year_id'),
                'batch_id': data.get('batch_id'),
                'department_id': data.get('department_id'),
                'exam_id': data.get('exam_id'),
                'section_id': data.get('section_id'),
                'semester_id': data.get('semester_id')
            }
            if len(data['exams']) > 0:
                exam_item = data['exams'][0]
                if isinstance(exam_item, dict):
                    data = {**common_fields, **exam_item}

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        # Broadcast changes to real-time websocket
        self._broadcast_change(serializer.data, 'exam_timetable_updated')

        return Response({
            "code": 200,
            "message": "Exam timetable updated successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_id = instance.id
        super().destroy(request, *args, **kwargs)
        
        # Broadcast deletion to real-time websocket
        self._broadcast_change({'id': instance_id}, 'exam_timetable_deleted')
        
        return Response({
            "code": 200,
            "message": "Exam timetable deleted successfully"
        }, status=status.HTTP_200_OK)

    def _broadcast_change(self, payload, event_name):
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
                            'payload': payload
                        }
                    }
                )
        except Exception:
            pass


class ClassTimetableViewSet(viewsets.ModelViewSet):
    queryset = ClassTimetable.objects.select_related(
        'academic_year', 'department', 'batch', 'section', 'semester', 'day', 'period', 'subject', 'faculty', 'activity_type', 'created_by'
    ).order_by('day__id', 'period__period_no')
    serializer_class = ClassTimetableSerializer
    permission_classes = [ClassTimetablePermission]
    model_label = "Class timetable"

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return ClassTimetable.objects.none()
            
        queryset = ClassTimetable.objects.select_related(
            'academic_year', 'department', 'batch', 'section', 'semester', 'day', 'period', 'subject', 'faculty', 'activity_type', 'created_by'
        ).order_by('day__id', 'period__period_no')
        
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)
        if not is_admin:
            try:
                role = getattr(user, 'role', None)
                if role:
                    user_role = role.role_name.upper().replace(' ', '_')
                    if user_role in ['ADMIN', 'ADMINISTRATOR']:
                        is_admin = True
            except AttributeError:
                pass
                
        if not is_admin:
            faculty_id = self.request.query_params.get('faculty_id')
            department_id = self.request.query_params.get('department_id')
            batch_id = self.request.query_params.get('batch_id')
            section_id = self.request.query_params.get('section_id')
            
            if faculty_id and str(faculty_id) == str(user.id):
                pass
            elif department_id and batch_id and section_id:
                pass
            else:
                queryset = queryset.filter(created_by=user)
            
        return queryset

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

        if isinstance(exc, DjangoValidationError):
            msg = str(exc.message) if hasattr(exc, 'message') else str(exc)
            if hasattr(exc, 'message_dict'):
                msgs = []
                for f, m in exc.message_dict.items():
                    msgs.extend(m)
                msg = msgs[0] if msgs else msg
            return Response({
                "code": 400,
                "message": msg
            }, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(exc, ValidationError):
            errors = exc.detail
            if isinstance(errors, list):
                for err in errors:
                    if err:
                        errors = err
                        break
            
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list) and len(val) > 0:
                    first_msg = str(val[0])
                else:
                    first_msg = str(val)
            elif isinstance(errors, list) and len(errors) > 0:
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)

            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        academic_year_id = request.query_params.get('academic_year_id')
        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        semester_id = request.query_params.get('semester_id')
        section_id = request.query_params.get('section_id')
        day_id = request.query_params.get('day_id')
        period_id = request.query_params.get('period_id')
        faculty_id = request.query_params.get('faculty_id')
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)
        if section_id:
            if str(section_id).isdigit():
                queryset = queryset.filter(section_id=section_id)
            else:
                queryset = queryset.filter(section__sections__iexact=section_id)
        if day_id:
            queryset = queryset.filter(day_id=day_id)
        if period_id:
            queryset = queryset.filter(period_id=period_id)
        if faculty_id:
            queryset = queryset.filter(faculty_id=faculty_id)
        if from_date and to_date:
            queryset = queryset.filter(from_date__lte=to_date, to_date__gte=from_date)
        elif from_date:
            queryset = queryset.filter(to_date__gte=from_date)
        elif to_date:
            queryset = queryset.filter(from_date__lte=to_date)
            
        disable_pagination = request.query_params.get('pagination') == 'false'
        if not disable_pagination:
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                paginated_response = self.get_paginated_response(serializer.data)
                return Response({
                    "code": 200,
                    "message": "Class timetables listed successfully.",
                    "data": paginated_response.data
                }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Class timetables listed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Class timetable slot retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        data = request.data
        
        # Support weekly timetable bulk save format:
        # {
        #   academic_year_id, department_id, batch_id, semester_id, section_id,
        #   class_timetables: [ { day_id, period_id, subject_id, faculty_id, is_lab, room_no }, ... ]
        # }
        if isinstance(data, dict) and 'class_timetables' in data and isinstance(data['class_timetables'], list):
            academic_year_id = data.get('academic_year_id')
            department_id = data.get('department_id')
            batch_id = data.get('batch_id')
            semester_id = data.get('semester_id')
            section_id = data.get('section_id')
            from_date = data.get('from_date')
            to_date = data.get('to_date')

            if not all([academic_year_id, department_id, batch_id, semester_id, section_id]):
                raise ValidationError("academic_year_id, department_id, batch_id, semester_id, and section_id are required in the root payload.")

            if not from_date:
                raise ValidationError("from_date is required.")
            if not to_date:
                raise ValidationError("to_date is required.")

            from django.utils.dateparse import parse_date
            parsed_from = parse_date(str(from_date)) if isinstance(from_date, str) else from_date
            parsed_to = parse_date(str(to_date)) if isinstance(to_date, str) else to_date

            if not parsed_from:
                raise ValidationError("from_date must be a valid date.")
            if not parsed_to:
                raise ValidationError("to_date must be a valid date.")
            if parsed_to < parsed_from:
                raise ValidationError("to_date must be after or equal to from_date.")

            flat_records = []
            for item in data['class_timetables']:
                if isinstance(item, dict):
                    record = {
                        'academic_year_id': academic_year_id,
                        'department_id': department_id,
                        'batch_id': batch_id,
                        'semester_id': semester_id,
                        'section_id': section_id,
                        'day_id': item.get('day_id'),
                        'period_id': item.get('period_id'),
                        'subject_id': item.get('subject_id'),
                        'faculty_id': item.get('faculty_id'),
                        'room_no': item.get('room_no', ''),
                        'from_date': from_date,
                        'to_date': to_date,
                    }
                    flat_records.append(record)

            # ── Faculty double-booking validation ──────────────────────────────────
            # For each slot being saved, check whether the chosen faculty is already
            # assigned to that same (academic_year, day, period) in ANY OTHER
            # class timetable group (different dept / batch / semester / section)
            # during an overlapping date range.

            conflicts = []
            for rec in flat_records:
                f_id   = rec.get('faculty_id')
                d_id   = rec.get('day_id')
                p_id   = rec.get('period_id')
                if not (f_id and d_id and p_id):
                    continue

                clash = ClassTimetable.objects.filter(
                    academic_year_id=academic_year_id,
                    faculty_id=f_id,
                    day_id=d_id,
                    period_id=p_id,
                    from_date__lte=to_date,
                    to_date__gte=from_date
                ).exclude(
                    department_id=department_id,
                    batch_id=batch_id,
                    semester_id=semester_id,
                    section_id=section_id,
                ).select_related('faculty', 'day', 'period', 'department', 'section').first()

                if clash:
                    try:
                        faculty_name = clash.faculty.name
                    except Exception:
                        faculty_name = f"Faculty #{f_id}"
                    try:
                        day_label = clash.day.day_name
                    except Exception:
                        day_label = f"Day #{d_id}"
                    try:
                        period_label = f"Period {clash.period.period_no}"
                    except Exception:
                        period_label = f"Period #{p_id}"
                    try:
                        dept_label = clash.department.short_name
                    except Exception:
                        dept_label = "another department"

                    conflicts.append(
                        f"{faculty_name} is already assigned to {dept_label} on {day_label}, {period_label}."
                    )

            if conflicts:
                raise ValidationError(conflicts[0])
            # ──────────────────────────────────────────────────────────────────────

            user = self.request.user
            is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)
            if not is_admin and user and user.is_authenticated:
                try:
                    role = getattr(user, 'role', None)
                    if role:
                        user_role = role.role_name.upper().replace(' ', '_')
                        if user_role in ['ADMIN', 'ADMINISTRATOR']:
                            is_admin = True
                except AttributeError:
                    pass

            with transaction.atomic():
                from datetime import timedelta
                # Delete or truncate existing weekly timetable slots matching the filters
                overlapping_slots = ClassTimetable.objects.filter(
                    academic_year_id=academic_year_id,
                    department_id=department_id,
                    batch_id=batch_id,
                    semester_id=semester_id,
                    section_id=section_id,
                    to_date__gte=parsed_from
                )
                if not is_admin and user:
                    overlapping_slots = overlapping_slots.filter(created_by=user)

                predecessor_to_date = parsed_from - timedelta(days=1)
                for slot_obj in list(overlapping_slots):
                    if slot_obj.from_date and slot_obj.from_date < parsed_from:
                        slot_obj.to_date = predecessor_to_date
                        slot_obj.save(update_fields=['to_date', 'updated_at'])
                    else:
                        slot_obj.delete()

                if flat_records:
                    serializer = self.get_serializer(data=flat_records, many=True)
                    serializer.is_valid(raise_exception=True)
                    self.perform_create(serializer)
                    saved_data = serializer.data
                else:
                    saved_data = []

            self._broadcast_change(saved_data, 'class_timetable_created')
            return Response({
                "code": 201,
                "message": "Weekly timetable saved successfully.",
                "data": saved_data
            }, status=status.HTTP_201_CREATED)

        # Fallback to single slot create
        is_many = isinstance(data, list)
        serializer = self.get_serializer(data=data, many=is_many)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        self._broadcast_change(serializer.data, 'class_timetable_created')
        return Response({
            "code": 201,
            "message": "Class timetable slot created successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        data = request.data

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        self._broadcast_change(serializer.data, 'class_timetable_updated')
        return Response({
            "code": 200,
            "message": "Class timetable slot updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance_id = instance.id
        super().destroy(request, *args, **kwargs)
        
        self._broadcast_change({'id': instance_id}, 'class_timetable_deleted')
        return Response({
            "code": 200,
            "message": "Class timetable slot deleted successfully."
        }, status=status.HTTP_200_OK)

    def assign_slot(self, request, *args, **kwargs):
        """
        Immediately persist one or more selected slots.
        Supports date-effective slot version splitting for faculty reassignment.
        Payload:
        {
          "academic_year_id": <int>,
          "department_id":    <int>,
          "batch_id":         <int>,
          "semester_id":      <int>,
          "section_id":       <int>,
          "room_no":          <str|null>,
          "from_date":        <str YYYY-MM-DD>,
          "to_date":          <str YYYY-MM-DD>,
          "effective_date":   <str YYYY-MM-DD|null>,
          "slots": [
            { "day_id": <int>, "period_id": <int>, "subject_id": <int>,
              "faculty_id": <int>, "is_lab": <bool> },
            ...
          ]
        }
        """
        data = request.data
        academic_year_id   = data.get('academic_year_id')
        department_id      = data.get('department_id')
        batch_id           = data.get('batch_id')
        semester_id        = data.get('semester_id')
        section_id         = data.get('section_id')
        room_no            = data.get('room_no', '')
        from_date          = data.get('from_date')
        to_date            = data.get('to_date')
        effective_date_raw = data.get('effective_date') or data.get('takeover_date')
        slots              = data.get('slots', [])

        if not all([academic_year_id, department_id, batch_id, semester_id, section_id]):
            raise ValidationError(
                "academic_year_id, department_id, batch_id, semester_id, and section_id are required."
            )
        if not from_date:
            raise ValidationError("from_date is required.")
        if not to_date:
            raise ValidationError("to_date is required.")

        from django.utils.dateparse import parse_date
        from datetime import timedelta
        parsed_from = parse_date(str(from_date)) if isinstance(from_date, str) else from_date
        parsed_to = parse_date(str(to_date)) if isinstance(to_date, str) else to_date
        parsed_effective = parse_date(str(effective_date_raw)) if (effective_date_raw and isinstance(effective_date_raw, str)) else (effective_date_raw or parsed_from)

        if not parsed_from:
            raise ValidationError("from_date must be a valid date.")
        if not parsed_to:
            raise ValidationError("to_date must be a valid date.")
        if parsed_to < parsed_from:
            raise ValidationError("to_date must be after or equal to from_date.")

        # Check if user is admin
        user = request.user
        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)
        if not is_admin and user and user.is_authenticated:
            try:
                role = getattr(user, 'role', None)
                if role:
                    user_role = role.role_name.upper().replace(' ', '_')
                    if user_role in ['ADMIN', 'ADMINISTRATOR']:
                        is_admin = True
            except AttributeError:
                pass

        if not isinstance(slots, list):
            raise ValidationError("slots must be a list.")

        takeover_date = parsed_effective or parsed_from

        # Handle metadata update if slots is empty
        if not slots:
            existing_slots = ClassTimetable.objects.filter(
                academic_year_id=academic_year_id,
                department_id=department_id,
                batch_id=batch_id,
                semester_id=semester_id,
                section_id=section_id,
                to_date__gte=takeover_date
            )
            if not is_admin and user:
                non_owned = existing_slots.exclude(created_by=user)
                if non_owned.exists():
                    raise ValidationError("Some slots in this timetable belong to another user. You do not have permission to modify settings.")

            updated_count = existing_slots.update(
                room_no=room_no or '',
                from_date=parsed_from,
                to_date=parsed_to,
                updated_by=user if user and user.is_authenticated else None
            )
            return Response({
                "code": 200,
                "message": f"Timetable settings updated successfully. Updated {updated_count} slot(s).",
                "data": []
            }, status=status.HTTP_200_OK)

        # ── Faculty double-booking validation ──────────────────────────────────
        for slot in slots:
            f_id = slot.get('faculty_id')
            d_id = slot.get('day_id')
            p_id = slot.get('period_id')
            if not (f_id and d_id and p_id):
                continue

            clash = (
                ClassTimetable.objects
                .filter(
                    academic_year_id=academic_year_id,
                    faculty_id=f_id,
                    day_id=d_id,
                    period_id=p_id,
                    from_date__lte=parsed_to,
                    to_date__gte=takeover_date
                )
                .exclude(
                    department_id=department_id,
                    batch_id=batch_id,
                    semester_id=semester_id,
                    section_id=section_id,
                )
                .select_related('faculty', 'day', 'period', 'department')
                .first()
            )
            if clash:
                try:    faculty_name = clash.faculty.name
                except Exception: faculty_name = f"Faculty #{f_id}"
                try:    day_label = clash.day.day_name
                except Exception: day_label = f"Day #{d_id}"
                try:    period_label = f"Period {clash.period.period_no}"
                except Exception: period_label = f"Period #{p_id}"
                try:    dept_label = clash.department.short_name
                except Exception: dept_label = "another department"

                raise ValidationError(
                    f"{faculty_name} is already assigned to {dept_label} on {day_label}, {period_label}."
                )
        # ──────────────────────────────────────────────────────────────────────

        saved_slots = []
        with transaction.atomic():
            predecessor_to_date = takeover_date - timedelta(days=1)

            for slot in slots:
                day_id           = slot.get('day_id')
                period_id        = slot.get('period_id')
                subject_id       = slot.get('subject_id')
                faculty_id       = slot.get('faculty_id')
                activity_type_id = slot.get('activity_type_id')
                subject_category = slot.get('subject_category', 'THEORY')

                if not all([day_id, period_id, faculty_id]):
                    raise ValidationError(
                        "Each slot must include day_id, period_id, and faculty_id."
                    )

                # Fetch all existing slots for this specific day & period
                existing_qs = ClassTimetable.objects.filter(
                    academic_year_id=academic_year_id,
                    department_id=department_id,
                    batch_id=batch_id,
                    semester_id=semester_id,
                    section_id=section_id,
                    day_id=day_id,
                    period_id=period_id,
                )

                target_instance = None
                slots_to_delete = []

                for existing in list(existing_qs):
                    if not is_admin and existing.created_by != request.user:
                        raise ValidationError("This slot is already scheduled by another user and you do not have permission to modify it.")

                    if existing.from_date and takeover_date and existing.from_date < takeover_date:
                        if existing.to_date and existing.to_date >= takeover_date:
                            # Predecessor slot: truncate its to_date to takeover_date - 1 day
                            existing.to_date = predecessor_to_date
                            existing.save(update_fields=['to_date', 'updated_at'])
                    elif existing.from_date == takeover_date:
                        # Exact matching start date: reuse existing record to update in place
                        target_instance = existing
                    else:
                        # Future slot starting after takeover date
                        if not target_instance:
                            target_instance = existing
                        else:
                            slots_to_delete.append(existing)

                if target_instance:
                    target_instance.subject_id       = subject_id
                    target_instance.faculty_id       = faculty_id
                    target_instance.subject_category = subject_category
                    target_instance.room_no          = room_no or ''
                    target_instance.from_date        = takeover_date
                    target_instance.to_date          = parsed_to
                    target_instance.activity_type_id = activity_type_id
                    target_instance.updated_by       = request.user if request.user.is_authenticated else None
                    target_instance.save()
                    instance = target_instance
                else:
                    instance = ClassTimetable.objects.create(
                        academic_year_id=academic_year_id,
                        department_id=department_id,
                        batch_id=batch_id,
                        semester_id=semester_id,
                        section_id=section_id,
                        day_id=day_id,
                        period_id=period_id,
                        subject_id=subject_id,
                        faculty_id=faculty_id,
                        subject_category=subject_category,
                        room_no=room_no or '',
                        from_date=takeover_date,
                        to_date=parsed_to,
                        activity_type_id=activity_type_id,
                        created_by=request.user if request.user.is_authenticated else None,
                        updated_by=request.user if request.user.is_authenticated else None,
                    )

                for s_del in slots_to_delete:
                    if s_del.pk != instance.pk:
                        s_del.delete()

                serializer = self.get_serializer(instance)
                saved_slots.append(serializer.data)

            # Synchronize metadata (room_no) only across active/future slots
            ClassTimetable.objects.filter(
                academic_year_id=academic_year_id,
                department_id=department_id,
                batch_id=batch_id,
                semester_id=semester_id,
                section_id=section_id,
                to_date__gte=takeover_date
            ).update(
                room_no=room_no or '',
                updated_by=request.user if request.user.is_authenticated else None
            )

        self._broadcast_change(saved_slots, 'class_timetable_assigned')
        return Response({
            "code": 201,
            "message": f"{len(saved_slots)} slot(s) assigned successfully.",
            "data": saved_slots
        }, status=status.HTTP_201_CREATED)


    def _broadcast_change(self, payload, event_name):
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
                            'payload': payload
                        }
                    }
                )
        except Exception:
            pass

    @action(detail=False, methods=['get'], url_path='daily-schedule')
    def resolve_daily_schedule(self, request):
        date_str = request.query_params.get('date')
        if not date_str:
            from datetime import date
            date_str = str(date.today())

        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')
        semester_id = request.query_params.get('semester_id')
        academic_year_id = request.query_params.get('academic_year_id')
        faculty_id = request.query_params.get('faculty_id')

        from schedule.services import resolve_effective_schedule_for_date
        schedule_data = resolve_effective_schedule_for_date(
            target_date=date_str,
            department_id=department_id,
            batch_id=batch_id,
            section_id=section_id,
            semester_id=semester_id,
            academic_year_id=academic_year_id,
            faculty_id=faculty_id
        )


        return Response({
            "code": 200,
            "message": "Daily effective schedule resolved successfully.",
            "data": schedule_data
        }, status=status.HTTP_200_OK)


class ActivityTypeViewSet(viewsets.ModelViewSet):

    queryset = ActivityType.objects.all().order_by('id')
    serializer_class = ActivityTypeSerializer
    permission_classes = [ActivityTypePermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Activity Type not found"
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
            return Response({
                "code": 400,
                "message": str(exc.detail[0] if isinstance(exc.detail, list) else exc.detail)
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(created_by=tracking_user, updated_by=tracking_user)

    def perform_update(self, serializer):
        user = self.request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        active_only = request.query_params.get('active_only')
        if active_only == 'true':
            queryset = queryset.filter(is_active=True)
            
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(activity_name__icontains=search)

        disable_pagination = request.query_params.get('pagination') == 'false'
        if not disable_pagination:
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                paginated_response = self.get_paginated_response(serializer.data)
                return Response({
                    "code": 200,
                    "message": "Activity Types listed successfully.",
                    "data": paginated_response.data
                }, status=status.HTTP_200_OK)
                
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Activity Types listed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Activity Type retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Activity Type created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Activity Type updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Activity Type deleted successfully."
        }, status=status.HTTP_200_OK)
