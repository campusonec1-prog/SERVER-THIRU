from django.urls import path
from .views import SubjectViewSet

urlpatterns = [
    path('list', SubjectViewSet.as_view({'get': 'list'}), name='subject-list'),
    path('create', SubjectViewSet.as_view({'post': 'create'}), name='subject-create'),
    path('get/<int:pk>', SubjectViewSet.as_view({'get': 'retrieve'}), name='subject-detail'),
    path('edit/<int:pk>', SubjectViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='subject-edit'),
    path('remove/<int:pk>', SubjectViewSet.as_view({'delete': 'destroy'}), name='subject-remove'),
]
