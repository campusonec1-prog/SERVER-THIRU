from django.urls import path
from .views import StudentStatusViewSet, StudentViewSet, MarksViewSet

urlpatterns = [
    # Student Status endpoints
    path('statuses/create', StudentStatusViewSet.as_view({'post': 'create'}), name='student-status-create'),
    path('statuses/list', StudentStatusViewSet.as_view({'get': 'list'}), name='student-status-list'),
    path('statuses/get/<int:pk>', StudentStatusViewSet.as_view({'get': 'retrieve'}), name='student-status-detail'),
    path('statuses/edit/<int:pk>', StudentStatusViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='student-status-edit'),
    path('statuses/remove/<int:pk>', StudentStatusViewSet.as_view({'delete': 'destroy'}), name='student-status-remove'),

    # Student endpoints (Promotion)
    path('create', StudentViewSet.as_view({'post': 'create'}), name='student-create'),
    path('list', StudentViewSet.as_view({'get': 'list'}), name='student-list'),
    path('get/<int:pk>', StudentViewSet.as_view({'get': 'retrieve'}), name='student-detail'),
    path('edit/<int:pk>', StudentViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='student-edit'),
    path('remove/<int:pk>', StudentViewSet.as_view({'delete': 'destroy'}), name='student-remove'),

    # Marks endpoints
    path('marks/create', MarksViewSet.as_view({'post': 'create'}), name='marks-create'),
    path('marks/list', MarksViewSet.as_view({'get': 'list'}), name='marks-list'),
    path('marks/get/<int:pk>', MarksViewSet.as_view({'get': 'retrieve'}), name='marks-detail'),
    path('marks/edit', MarksViewSet.as_view({'put': 'update'}), name='marks-edit'),
]

