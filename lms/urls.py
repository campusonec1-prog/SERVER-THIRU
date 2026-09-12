from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LMSAssignmentViewSet, LMSSubmissionViewSet

router = DefaultRouter()
router.register(r'assignments', LMSAssignmentViewSet, basename='lms-assignments')
router.register(r'submissions', LMSSubmissionViewSet, basename='lms-submissions')

urlpatterns = [
    # Router endpoints
    path('', include(router.urls)),

    # ── Explicit API Aliases for 8 LMS CRUD Endpoints ─────────────────────────
    # 1. List Assignments
    path('assignments/list', LMSAssignmentViewSet.as_view({'get': 'list'}), name='lms-assignment-list'),
    # 2. Create Assignment
    path('assignments/create', LMSAssignmentViewSet.as_view({'post': 'create'}), name='lms-assignment-create'),
    # 3. Assignment Detail
    path('assignments/detail/<int:pk>', LMSAssignmentViewSet.as_view({'get': 'retrieve'}), name='lms-assignment-detail'),
    # 4. Update Assignment
    path('assignments/update/<int:pk>', LMSAssignmentViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='lms-assignment-update'),
    # 5. Delete Assignment
    path('assignments/delete/<int:pk>', LMSAssignmentViewSet.as_view({'delete': 'destroy'}), name='lms-assignment-delete'),

    # 6. List Submissions
    path('submissions/list', LMSSubmissionViewSet.as_view({'get': 'list'}), name='lms-submission-list'),
    # 7. Submit Work (Student Upload)
    path('submissions/submit', LMSSubmissionViewSet.as_view({'post': 'submit_work'}), name='lms-submission-submit'),
    # 8. Evaluate Submission (Faculty Grade)
    path('submissions/evaluate/<int:pk>', LMSSubmissionViewSet.as_view({'post': 'evaluate'}), name='lms-submission-evaluate'),
]
