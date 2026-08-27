from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from .models import ExamTimetable, ClassTimetable
from .serializers import ExamTimetableSerializer, ClassTimetableSerializer
from .permissions import ExamTimetablePermission, ClassTimetablePermission
from schedule.models import Day, Period
from users.models import User as FacultyUser

class ExamTimetableViewSet(viewsets.ModelViewSet):
    queryset = ExamTimetable.objects.all().order_by('id')
    serializer_class = ExamTimetableSerializer
    permission_classes = [ExamTimetablePermission]
    model_label = "Exam timetable"

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return ExamTimetable.objects.none()
            
        queryset = ExamTimetable.objects.all().order_by('id')
        
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
            queryset = queryset.filter(section_id=section_id)
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
            # 1. Check for duplicate subject in list of entries
            seen_subjects = set()
            for record in data:
                subject_id = record.get('subject_id')
                if subject_id:
                    from subject.models import Subject
                    try:
                        subject_obj = Subject.objects.get(pk=subject_id)
                        subject_display = f"{subject_obj.subject_code} - {subject_obj.subject_name}"
                    except Subject.DoesNotExist:
                        subject_display = f"ID {subject_id}"

                    if subject_id in seen_subjects:
                        raise ValidationError(f"Duplicate subject '{subject_display}' is scheduled multiple times in the timetable.")
                    seen_subjects.add(subject_id)

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
    queryset = ClassTimetable.objects.all().order_by('day__id', 'period__period_no')
    serializer_class = ClassTimetableSerializer
    permission_classes = [ClassTimetablePermission]
    model_label = "Class timetable"

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return ClassTimetable.objects.none()
            
        queryset = ClassTimetable.objects.all().order_by('day__id', 'period__period_no')
        
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
        
        if academic_year_id:
            queryset = queryset.filter(academic_year_id=academic_year_id)
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)
        if section_id:
            queryset = queryset.filter(section_id=section_id)
        if day_id:
            queryset = queryset.filter(day_id=day_id)
        if period_id:
            queryset = queryset.filter(period_id=period_id)
        if faculty_id:
            queryset = queryset.filter(faculty_id=faculty_id)
            
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

            if not all([academic_year_id, department_id, batch_id, semester_id, section_id]):
                raise ValidationError("academic_year_id, department_id, batch_id, semester_id, and section_id are required in the root payload.")

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
                        'is_lab': item.get('is_lab', False),
                        'room_no': item.get('room_no', '')
                    }
                    flat_records.append(record)

            # ── Faculty double-booking validation ──────────────────────────────────
            # For each slot being saved, check whether the chosen faculty is already
            # assigned to that same (academic_year, day, period) in ANY OTHER
            # class timetable group (different dept / batch / semester / section).

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
                # Delete existing weekly timetable slots matching the filters
                delete_query = ClassTimetable.objects.filter(
                    academic_year_id=academic_year_id,
                    department_id=department_id,
                    batch_id=batch_id,
                    semester_id=semester_id,
                    section_id=section_id
                )
                if not is_admin and user:
                    delete_query = delete_query.filter(created_by=user)
                delete_query.delete()

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
        Immediately persist one or more selected slots (no bulk-delete of other slots).
        Payload:
        {
          "academic_year_id": <int>,
          "department_id":    <int>,
          "batch_id":         <int>,
          "semester_id":      <int>,
          "section_id":       <int>,
          "room_no":          <str|null>,
          "slots": [
            { "day_id": <int>, "period_id": <int>, "subject_id": <int>,
              "faculty_id": <int>, "is_lab": <bool> },
            ...
          ]
        }
        """
        data = request.data
        academic_year_id = data.get('academic_year_id')
        department_id    = data.get('department_id')
        batch_id         = data.get('batch_id')
        semester_id      = data.get('semester_id')
        section_id       = data.get('section_id')
        room_no          = data.get('room_no', '')
        slots            = data.get('slots', [])

        if not all([academic_year_id, department_id, batch_id, semester_id, section_id]):
            raise ValidationError(
                "academic_year_id, department_id, batch_id, semester_id, and section_id are required."
            )
        if not slots or not isinstance(slots, list):
            raise ValidationError("slots must be a non-empty list.")

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

        saved_slots = []
        with transaction.atomic():
            for slot in slots:
                day_id     = slot.get('day_id')
                period_id  = slot.get('period_id')
                subject_id = slot.get('subject_id')
                faculty_id = slot.get('faculty_id')
                is_lab     = slot.get('is_lab', False)

                if not all([day_id, period_id, subject_id, faculty_id]):
                    raise ValidationError(
                        "Each slot must include day_id, period_id, subject_id, and faculty_id."
                    )

                defaults = {
                    'subject_id':  subject_id,
                    'faculty_id':  faculty_id,
                    'is_lab':      is_lab,
                    'room_no':     room_no or '',
                    'updated_by':  request.user if request.user.is_authenticated else None,
                }
                
                # Check if it already exists and belongs to someone else
                existing = ClassTimetable.objects.filter(
                    academic_year_id=academic_year_id,
                    department_id=department_id,
                    batch_id=batch_id,
                    semester_id=semester_id,
                    section_id=section_id,
                    day_id=day_id,
                    period_id=period_id,
                ).first()
                
                if existing:
                    if not is_admin and existing.created_by != request.user:
                        raise ValidationError("This slot is already scheduled by another user and you do not have permission to overwrite it.")
                else:
                    defaults['created_by'] = request.user if request.user.is_authenticated else None

                instance, _ = ClassTimetable.objects.update_or_create(
                    academic_year_id=academic_year_id,
                    department_id=department_id,
                    batch_id=batch_id,
                    semester_id=semester_id,
                    section_id=section_id,
                    day_id=day_id,
                    period_id=period_id,
                    defaults=defaults
                )
                serializer = self.get_serializer(instance)
                saved_slots.append(serializer.data)

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
