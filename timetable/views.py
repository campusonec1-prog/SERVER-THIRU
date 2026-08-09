from rest_framework import viewsets, status
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from .models import ExamTimetable
from .serializers import ExamTimetableSerializer
from .permissions import IsTimetableManager

class ExamTimetableViewSet(viewsets.ModelViewSet):
    queryset = ExamTimetable.objects.all().order_by('id')
    serializer_class = ExamTimetableSerializer
    model_label = "Exam timetable"

    def get_permissions(self):
        # Write operations require HOD, Admin, or Exam Cell roles.
        # Get operations require the user to be authenticated (token).
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsTimetableManager()]
        return [IsAuthenticated()]

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
