from django.urls import path
from .views import ExamTimetableViewSet, ClassTimetableViewSet

urlpatterns = [
    # Exam Timetable endpoints
    path('exam/list', ExamTimetableViewSet.as_view({'get': 'list'}), name='timetable-list'),
    path('exam/create', ExamTimetableViewSet.as_view({'post': 'create'}), name='timetable-create'),
    path('exam/get/<int:pk>', ExamTimetableViewSet.as_view({'get': 'retrieve'}), name='timetable-detail'),
    path('exam/edit/<int:pk>', ExamTimetableViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='timetable-edit'),
    path('exam/remove/<int:pk>', ExamTimetableViewSet.as_view({'delete': 'destroy'}), name='timetable-remove'),

    # Class Timetable endpoints
    path('class/list', ClassTimetableViewSet.as_view({'get': 'list'}), name='class-timetable-list'),
    path('class/create', ClassTimetableViewSet.as_view({'post': 'create'}), name='class-timetable-create'),
    path('class/assign', ClassTimetableViewSet.as_view({'post': 'assign_slot'}), name='class-timetable-assign'),
    path('class/get/<int:pk>', ClassTimetableViewSet.as_view({'get': 'retrieve'}), name='class-timetable-detail'),
    path('class/edit/<int:pk>', ClassTimetableViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='class-timetable-edit'),
    path('class/remove/<int:pk>', ClassTimetableViewSet.as_view({'delete': 'destroy'}), name='class-timetable-remove'),
]
