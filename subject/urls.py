from django.urls import path
from .views import SubjectViewSet, SharedNotesViewSet

urlpatterns = [
    path('list', SubjectViewSet.as_view({'get': 'list'}), name='subject-list'),
    path('create', SubjectViewSet.as_view({'post': 'create'}), name='subject-create'),
    path('get/<int:pk>', SubjectViewSet.as_view({'get': 'retrieve'}), name='subject-detail'),
    path('edit/<int:pk>', SubjectViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='subject-edit'),
    path('remove/<int:pk>', SubjectViewSet.as_view({'delete': 'destroy'}), name='subject-remove'),
    path('bulk-import', SubjectViewSet.as_view({'post': 'bulk_import'}), name='subject-bulk-import'),

    # Shared Notes Endpoints
    path('notes', SharedNotesViewSet.as_view({'get': 'list'}), name='shared-notes-list'),
    path('notes/upload', SharedNotesViewSet.as_view({'post': 'upload'}), name='shared-notes-upload'),
    path('notes/folders', SharedNotesViewSet.as_view({'get': 'folders'}), name='shared-notes-folders'),
    path('notes/<int:pk>', SharedNotesViewSet.as_view({'delete': 'destroy'}), name='shared-notes-delete'),
]

