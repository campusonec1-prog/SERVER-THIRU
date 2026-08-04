from django.urls import path
from .views import StudentStatusViewSet

urlpatterns = [
    path('statuses/create', StudentStatusViewSet.as_view({'post': 'create'}), name='student-status-create'),
    path('statuses/list', StudentStatusViewSet.as_view({'get': 'list'}), name='student-status-list'),
    path('statuses/get/<int:pk>', StudentStatusViewSet.as_view({'get': 'retrieve'}), name='student-status-detail'),
    path('statuses/edit/<int:pk>', StudentStatusViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='student-status-edit'),
    path('statuses/remove/<int:pk>', StudentStatusViewSet.as_view({'delete': 'destroy'}), name='student-status-remove'),
]
