import json
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.http import Http404
from django.utils import timezone
from django.db.models import Q
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied

from .models import NoticeBoard
from .serializers import NoticeBoardSerializer
from .permissions import NoticeBoardPermission
from common.r2 import upload_file_to_r2, delete_file_from_r2


from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

class NoticeBoardViewSet(viewsets.ModelViewSet):
    serializer_class = NoticeBoardSerializer
    permission_classes = [NoticeBoardPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = NoticeBoard.objects.select_related('faculty', 'department').all().order_by('-id')

        notice_type = self.request.query_params.get('notice_type')
        if notice_type:
            qs = qs.filter(notice_type=notice_type)

        is_global = self.request.query_params.get('is_global')
        if is_global is not None:
            if str(is_global).lower() in ['true', '1']:
                qs = qs.filter(target_audience_type='global')
            elif str(is_global).lower() in ['false', '0']:
                qs = qs.filter(target_audience_type='targeted')

        target_audience_type = self.request.query_params.get('target_audience_type')
        if target_audience_type:
            qs = qs.filter(target_audience_type=target_audience_type)

        department_id = self.request.query_params.get('department_id') or self.request.query_params.get('department')
        if department_id:
            qs = qs.filter(department_id=department_id)

        batch = self.request.query_params.get('batch')
        if batch:
            qs = qs.filter(batch=batch)

        section = self.request.query_params.get('section')
        if section:
            qs = qs.filter(section=section)

        active_only = self.request.query_params.get('active_only')
        if active_only and str(active_only).lower() in ['true', '1']:
            qs = qs.filter(is_active=True, expire_date__gte=timezone.now())

        return qs

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Notice not found"
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

    def _parse_sub_coordinators(self, val):
        if not val:
            return []
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
            return [s.strip() for s in val.split(',') if s.strip()]
        return []

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        poster_file = self.request.FILES.get('poster') or self.request.FILES.get('poster_file') or self.request.FILES.get('poster_url')
        poster_url = self.request.data.get('poster_url')
        
        if poster_file:
            try:
                uploaded_url = upload_file_to_r2(poster_file, folder_name="event_posters")
                if uploaded_url:
                    poster_url = uploaded_url
                    print(f"[NoticeBoard] Poster uploaded to R2: {poster_url}")
            except Exception as e:
                print(f"[NoticeBoard] R2 Poster upload failed: {e}")

        extra = {'faculty': user, 'created_by': user, 'updated_by': user}
        if poster_url:
            extra['poster_url'] = poster_url

        raw_sub = self.request.data.get('sub_coordinators')
        if raw_sub is not None:
            extra['sub_coordinators'] = self._parse_sub_coordinators(raw_sub)

        serializer.save(**extra)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        poster_file = self.request.FILES.get('poster') or self.request.FILES.get('poster_file') or self.request.FILES.get('poster_url')
        remove_poster = str(self.request.data.get('remove_poster', '')).lower() in ['true', '1']

        extra = {'updated_by': user}
        if poster_file:
            try:
                if serializer.instance and serializer.instance.poster_url:
                    delete_file_from_r2(serializer.instance.poster_url)
                new_poster_url = upload_file_to_r2(poster_file, folder_name="event_posters")
                if new_poster_url:
                    extra['poster_url'] = new_poster_url
                    print(f"[NoticeBoard] Updated Poster uploaded to R2: {new_poster_url}")
            except Exception as e:
                print(f"[NoticeBoard] R2 Poster update failed: {e}")
        elif remove_poster:
            if serializer.instance and serializer.instance.poster_url:
                delete_file_from_r2(serializer.instance.poster_url)
            extra['poster_url'] = ''
        elif 'poster_url' in self.request.data and self.request.data.get('poster_url'):
            extra['poster_url'] = self.request.data.get('poster_url')
        elif serializer.instance and serializer.instance.poster_url:
            extra['poster_url'] = serializer.instance.poster_url

        raw_sub = self.request.data.get('sub_coordinators')
        if raw_sub is not None:
            extra['sub_coordinators'] = self._parse_sub_coordinators(raw_sub)

        serializer.save(**extra)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Notices listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Notice retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        serialized_instance = self.get_serializer(serializer.instance).data
        return Response({"code": 201, "message": "Notice created successfully", "data": serialized_instance}, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        serialized_instance = self.get_serializer(serializer.instance).data
        return Response({"code": 200, "message": "Notice updated successfully", "data": serialized_instance}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance and instance.poster_url:
            try:
                delete_file_from_r2(instance.poster_url)
            except Exception:
                pass
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Notice deleted successfully"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='upcoming-events')
    def upcoming_events(self, request):
        now = timezone.now()
        dept_id = request.query_params.get('department_id') or request.query_params.get('department')
        batch = request.query_params.get('batch')
        section = request.query_params.get('section')

        qs = NoticeBoard.objects.select_related('faculty', 'department').filter(
            is_active=True,
            expire_date__gte=now
        )

        if dept_id:
            q_audience = Q(target_audience_type='global') | (
                Q(department_id=dept_id) &
                (Q(batch__isnull=True) | Q(batch='') | Q(batch=batch)) &
                (Q(section__isnull=True) | Q(section='') | Q(section=section))
            )
            qs = qs.filter(q_audience)

        serializer = self.get_serializer(qs.order_by('-publish_date', '-id'), many=True)
        return Response({
            "code": 200,
            "message": "Upcoming events retrieved successfully",
            "data": serializer.data
        })

