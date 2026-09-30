from django.urls import path
from .views import (
    PlacementCompanyViewSet,
    PlacementDriveViewSet,
    PlacementDriveEligibilityViewSet
)

urlpatterns = [
    # ── PLACEMENT COMPANIES: Standard 4 CRUD endpoints ──
    path('create', PlacementCompanyViewSet.as_view({'post': 'create'}), name='placement-company-create'),
    path('list', PlacementCompanyViewSet.as_view({'get': 'list'}), name='placement-company-list'),
    path('list/<int:pk>', PlacementCompanyViewSet.as_view({'get': 'retrieve'}), name='placement-company-detail'),
    path('get/<int:pk>', PlacementCompanyViewSet.as_view({'get': 'retrieve'}), name='placement-company-get'),
    path('edit/<int:pk>', PlacementCompanyViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='placement-company-edit'),
    path('remove/<int:pk>', PlacementCompanyViewSet.as_view({'delete': 'destroy'}), name='placement-company-remove'),

    # Placement Company Utilities
    path('toggle-status/<int:pk>', PlacementCompanyViewSet.as_view({'patch': 'toggle_status'}), name='placement-company-toggle-status'),
    path('industry-choices', PlacementCompanyViewSet.as_view({'get': 'industry_choices'}), name='placement-industry-choices'),
    path('summary-stats', PlacementCompanyViewSet.as_view({'get': 'summary_stats'}), name='placement-summary-stats'),
    path('companies', PlacementCompanyViewSet.as_view({'get': 'list', 'post': 'create'})),
    path('companies/<int:pk>', PlacementCompanyViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'})),

    # ── PLACEMENT DRIVES: Standard 4 CRUD endpoints ──
    path('drives/create', PlacementDriveViewSet.as_view({'post': 'create'}), name='placement-drive-create'),
    path('drives/list', PlacementDriveViewSet.as_view({'get': 'list'}), name='placement-drive-list'),
    path('drives/list/<int:pk>', PlacementDriveViewSet.as_view({'get': 'retrieve'}), name='placement-drive-detail'),
    path('drives/get/<int:pk>', PlacementDriveViewSet.as_view({'get': 'retrieve'}), name='placement-drive-get'),
    path('drives/edit/<int:pk>', PlacementDriveViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='placement-drive-edit'),
    path('drives/remove/<int:pk>', PlacementDriveViewSet.as_view({'delete': 'destroy'}), name='placement-drive-remove'),

    # Placement Drive Utilities & Cloudflare R2 Upload
    path('drives/update-status/<int:pk>', PlacementDriveViewSet.as_view({'patch': 'update_status'}), name='placement-drive-update-status'),
    path('drives/type-choices', PlacementDriveViewSet.as_view({'get': 'type_choices'}), name='placement-drive-type-choices'),
    path('drives/status-choices', PlacementDriveViewSet.as_view({'get': 'status_choices'}), name='placement-drive-status-choices'),
    path('drives/summary-stats', PlacementDriveViewSet.as_view({'get': 'summary_stats'}), name='placement-drive-summary-stats'),
    path('drives/upload-document', PlacementDriveViewSet.as_view({'post': 'upload_document'}), name='placement-drive-upload-doc'),

    path('drives/eligible-students/<int:pk>', PlacementDriveViewSet.as_view({'get': 'eligible_students'}), name='placement-drive-eligible-students'),
    path('drives/<int:pk>/eligible-students', PlacementDriveViewSet.as_view({'get': 'eligible_students'})),

    # ── PLACEMENT DRIVE ELIGIBILITY: Standard 4 CRUD endpoints ──
    path('eligibility/create', PlacementDriveEligibilityViewSet.as_view({'post': 'create'}), name='placement-eligibility-create'),
    path('eligibility/list', PlacementDriveEligibilityViewSet.as_view({'get': 'list'}), name='placement-eligibility-list'),
    path('eligibility/list/<int:pk>', PlacementDriveEligibilityViewSet.as_view({'get': 'retrieve'}), name='placement-eligibility-detail'),
    path('eligibility/get/<int:pk>', PlacementDriveEligibilityViewSet.as_view({'get': 'retrieve'}), name='placement-eligibility-get'),
    path('eligibility/edit/<int:pk>', PlacementDriveEligibilityViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='placement-eligibility-edit'),
    path('eligibility/remove/<int:pk>', PlacementDriveEligibilityViewSet.as_view({'delete': 'destroy'}), name='placement-eligibility-remove'),
    path('eligibility/by-drive/<int:drive_id>', PlacementDriveEligibilityViewSet.as_view({'get': 'by_drive'}), name='placement-eligibility-by-drive'),
    path('eligibility/eligible-students/<int:pk>', PlacementDriveEligibilityViewSet.as_view({'get': 'eligible_students'}), name='placement-eligibility-eligible-students'),
    path('eligibility/<int:pk>/eligible-students', PlacementDriveEligibilityViewSet.as_view({'get': 'eligible_students'})),
]

