from django.urls import path
from .views import ExamTimetableViewSet, ClassTimetableViewSet, ActivityTypeViewSet

urlpatterns = [
    # Exam Timetable endpoints
    path('exam/list', ExamTimetableViewSet.as_view({'get': 'list'}), name='timetable-list'),
    path('exam/create', ExamTimetableViewSet.as_view({'post': 'create'}), name='timetable-create'),
    path('exam/get/<int:pk>', ExamTimetableViewSet.as_view({'get': 'retrieve'}), name='timetable-detail'),
    path('exam/edit/<int:pk>', ExamTimetableViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='timetable-edit'),
    path('exam/remove/<int:pk>', ExamTimetableViewSet.as_view({'delete': 'destroy'}), name='timetable-remove'),

    # Class Timetable endpoints
    path('class/list', ClassTimetableViewSet.as_view({'get': 'list'}), name='class-timetable-list'),
    path('class/daily-schedule', ClassTimetableViewSet.as_view({'get': 'resolve_daily_schedule'}), name='class-timetable-daily-schedule'),
    path('class/create', ClassTimetableViewSet.as_view({'post': 'create'}), name='class-timetable-create'),
    path('class/assign', ClassTimetableViewSet.as_view({'post': 'assign_slot'}), name='class-timetable-assign'),
    path('class/get/<int:pk>', ClassTimetableViewSet.as_view({'get': 'retrieve'}), name='class-timetable-detail'),
    path('class/edit/<int:pk>', ClassTimetableViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='class-timetable-edit'),
    path('class/remove/<int:pk>', ClassTimetableViewSet.as_view({'delete': 'destroy'}), name='class-timetable-remove'),


    # Activity Type endpoints
    path('activity-types/list', ActivityTypeViewSet.as_view({'get': 'list'}), name='activity-type-list'),
    path('activity-types/create', ActivityTypeViewSet.as_view({'post': 'create'}), name='activity-type-create'),
    path('activity-types/get/<int:pk>', ActivityTypeViewSet.as_view({'get': 'retrieve'}), name='activity-type-detail'),
    path('activity-types/edit/<int:pk>', ActivityTypeViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='activity-type-edit'),
    path('activity-types/remove/<int:pk>', ActivityTypeViewSet.as_view({'delete': 'destroy'}), name='activity-type-remove'),
]
