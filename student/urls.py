from django.urls import path
from .views import StudentStatusViewSet, StudentViewSet, MarksViewSet, CounsellingReportViewSet

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
    path('bulk-import', StudentViewSet.as_view({'post': 'bulk_import'}), name='student-bulk-import'),
    path('admission-slip/save', StudentViewSet.as_view({'post': 'admission_slip_save'}), name='admission-slip-save'),
    path('admission-slip/data/<int:pk>', StudentViewSet.as_view({'get': 'admission_slip_data'}), name='admission-slip-data'),
    path('admission-slip/pdf/<int:pk>', StudentViewSet.as_view({'get': 'admission_slip_pdf'}), name='admission-slip-pdf'),
    path('fees/save', StudentViewSet.as_view({'post': 'fees_save'}), name='fees-save'),

    # Marks endpoints
    path('marks/create', MarksViewSet.as_view({'post': 'create'}), name='marks-create'),
    path('marks/list', MarksViewSet.as_view({'get': 'list'}), name='marks-list'),
    path('marks/get/<int:pk>', MarksViewSet.as_view({'get': 'retrieve'}), name='marks-detail'),
    path('marks/edit', MarksViewSet.as_view({'put': 'update'}), name='marks-edit'),

    # Counselling Report endpoints
    path('counselling/create', CounsellingReportViewSet.as_view({'post': 'create'}), name='counselling-create'),
    path('counselling/list', CounsellingReportViewSet.as_view({'get': 'list'}), name='counselling-list'),
    path('counselling/get/<int:pk>', CounsellingReportViewSet.as_view({'get': 'retrieve'}), name='counselling-detail'),
    path('counselling/edit/<int:pk>', CounsellingReportViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='counselling-edit'),
    path('counselling/remove/<int:pk>', CounsellingReportViewSet.as_view({'delete': 'destroy'}), name='counselling-remove'),
]

