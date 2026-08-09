from django.urls import path
from .views import ExamTimetableViewSet

urlpatterns = [
    path('exam/list', ExamTimetableViewSet.as_view({'get': 'list'}), name='timetable-list'),
    path('exam/create', ExamTimetableViewSet.as_view({'post': 'create'}), name='timetable-create'),
    path('exam/get/<int:pk>', ExamTimetableViewSet.as_view({'get': 'retrieve'}), name='timetable-detail'),
    path('exam/edit/<int:pk>', ExamTimetableViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='timetable-edit'),
    path('exam/remove/<int:pk>', ExamTimetableViewSet.as_view({'delete': 'destroy'}), name='timetable-remove'),
]
