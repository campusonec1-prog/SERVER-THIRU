from django.urls import path
from .views import NoticeBoardViewSet

urlpatterns = [
    path('notices/list', NoticeBoardViewSet.as_view({'get': 'list'}), name='notice-list'),
    path('notices/create', NoticeBoardViewSet.as_view({'post': 'create'}), name='notice-create'),
    path('notices/get/<int:pk>', NoticeBoardViewSet.as_view({'get': 'retrieve'}), name='notice-detail'),
    path('notices/edit/<int:pk>', NoticeBoardViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='notice-edit'),
    path('notices/remove/<int:pk>', NoticeBoardViewSet.as_view({'delete': 'destroy'}), name='notice-remove'),
]
