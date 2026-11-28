from django.urls import path
from .views import (
    ExamAttendanceImportViewSet, UniversityExamScheduleViewSet,
    UniversityExamCandidateViewSet, UniversityExamAttendanceViewSet,
    ExamHallAllocationViewSet, ExamSeatAllocationViewSet, UniversityExamHallViewSet
)
from .views_results import UniversityResultPublishViewSet
from .views_preview import UniversityRegistrationPreviewViewSet

urlpatterns = [
    # Registration Preview Import (Anna University Student Registration PDF)
    path('preview-import/preview', UniversityRegistrationPreviewViewSet.as_view({'post': 'preview_pdf'}), name='univ-exam-reg-preview'),
    path('preview-import/quick-add-student', UniversityRegistrationPreviewViewSet.as_view({'post': 'quick_add_student'}), name='univ-exam-reg-quick-add-student'),
    path('preview-import/quick-add-all-students', UniversityRegistrationPreviewViewSet.as_view({'post': 'quick_add_all_students'}), name='univ-exam-reg-quick-add-all-students'),
    path('preview-import/quick-add-subject', UniversityRegistrationPreviewViewSet.as_view({'post': 'quick_add_subject'}), name='univ-exam-reg-quick-add-subject'),
    path('preview-import/quick-add-all-subjects', UniversityRegistrationPreviewViewSet.as_view({'post': 'quick_add_all_subjects'}), name='univ-exam-reg-quick-add-all-subjects'),
    path('preview-import/quick-add-department', UniversityRegistrationPreviewViewSet.as_view({'post': 'quick_add_department'}), name='univ-exam-reg-quick-add-department'),
    path('preview-import/confirm-save', UniversityRegistrationPreviewViewSet.as_view({'post': 'confirm_save'}), name='univ-exam-reg-confirm-save'),
    # Exam Halls (University Exam Configuration)
    path('exam-halls/list', UniversityExamHallViewSet.as_view({'get': 'list'}), name='univ-exam-hall-list'),
    path('exam-halls/create', UniversityExamHallViewSet.as_view({'post': 'create'}), name='univ-exam-hall-create'),
    path('exam-halls/get/<int:pk>', UniversityExamHallViewSet.as_view({'get': 'retrieve'}), name='univ-exam-hall-detail'),
    path('exam-halls/edit/<int:pk>', UniversityExamHallViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-hall-edit'),
    path('exam-halls/remove/<int:pk>', UniversityExamHallViewSet.as_view({'delete': 'destroy'}), name='univ-exam-hall-remove'),

    # Attendance Import
    path('import/preview', ExamAttendanceImportViewSet.as_view({'post': 'preview_pdf'}), name='univ-exam-import-preview'),
    path('import/quick-add-dept', ExamAttendanceImportViewSet.as_view({'post': 'quick_add_dept'}), name='univ-exam-import-quick-add-dept'),
    path('import/quick-add-subject', ExamAttendanceImportViewSet.as_view({'post': 'quick_add_subject'}), name='univ-exam-import-quick-add-subject'),
    path('import/quick-add-student', ExamAttendanceImportViewSet.as_view({'post': 'quick_add_student'}), name='univ-exam-import-quick-add-student'),
    path('import/quick-add-all-students', ExamAttendanceImportViewSet.as_view({'post': 'quick_add_all_students'}), name='univ-exam-import-quick-add-all-students'),
    path('import/confirm-save', ExamAttendanceImportViewSet.as_view({'post': 'confirm_save'}), name='univ-exam-import-confirm-save'),

    # Exam Schedules
    path('schedules/list', UniversityExamScheduleViewSet.as_view({'get': 'list'}), name='univ-exam-schedule-list'),
    path('schedules/create', UniversityExamScheduleViewSet.as_view({'post': 'create'}), name='univ-exam-schedule-create'),
    path('schedules/get/<int:pk>', UniversityExamScheduleViewSet.as_view({'get': 'retrieve'}), name='univ-exam-schedule-detail'),
    path('schedules/edit/<int:pk>', UniversityExamScheduleViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-schedule-edit'),
    path('schedules/remove/<int:pk>', UniversityExamScheduleViewSet.as_view({'delete': 'destroy'}), name='univ-exam-schedule-remove'),
    path('schedules/generate-seating', UniversityExamScheduleViewSet.as_view({'post': 'generate_seating'}), name='univ-exam-generate-seating'),

    # Candidates (Replaces legacy Attendance table)
    path('candidates/list', UniversityExamCandidateViewSet.as_view({'get': 'list'}), name='univ-exam-candidate-list'),
    path('candidates/create', UniversityExamCandidateViewSet.as_view({'post': 'create'}), name='univ-exam-candidate-create'),
    path('candidates/get/<int:pk>', UniversityExamCandidateViewSet.as_view({'get': 'retrieve'}), name='univ-exam-candidate-detail'),
    path('candidates/edit/<int:pk>', UniversityExamCandidateViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-candidate-edit'),
    path('candidates/remove/<int:pk>', UniversityExamCandidateViewSet.as_view({'delete': 'destroy'}), name='univ-exam-candidate-remove'),

    # Attendances (Legacy compatibility)
    path('attendances/list', UniversityExamAttendanceViewSet.as_view({'get': 'list'}), name='univ-exam-attendance-list'),
    path('attendances/create', UniversityExamAttendanceViewSet.as_view({'post': 'create'}), name='univ-exam-attendance-create'),
    path('attendances/get/<int:pk>', UniversityExamAttendanceViewSet.as_view({'get': 'retrieve'}), name='univ-exam-attendance-detail'),
    path('attendances/edit/<int:pk>', UniversityExamAttendanceViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-attendance-edit'),
    path('attendances/remove/<int:pk>', UniversityExamAttendanceViewSet.as_view({'delete': 'destroy'}), name='univ-exam-attendance-remove'),

    # Hall Allocations
    path('hall-allocations/list', ExamHallAllocationViewSet.as_view({'get': 'list'}), name='univ-exam-hall-alloc-list'),
    path('hall-allocations/summary', ExamHallAllocationViewSet.as_view({'get': 'summary'}), name='univ-exam-hall-alloc-summary'),
    path('hall-allocations/create', ExamHallAllocationViewSet.as_view({'post': 'create'}), name='univ-exam-hall-alloc-create'),
    path('hall-allocations/get/<int:pk>', ExamHallAllocationViewSet.as_view({'get': 'retrieve'}), name='univ-exam-hall-alloc-detail'),
    path('hall-allocations/edit/<int:pk>', ExamHallAllocationViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-hall-alloc-edit'),
    path('hall-allocations/remove/<int:pk>', ExamHallAllocationViewSet.as_view({'delete': 'destroy'}), name='univ-exam-hall-alloc-remove'),

    # Seat Allocations
    path('seat-allocations/list', ExamSeatAllocationViewSet.as_view({'get': 'list'}), name='univ-exam-seat-alloc-list'),
    path('seat-allocations/create', ExamSeatAllocationViewSet.as_view({'post': 'create'}), name='univ-exam-seat-alloc-create'),
    path('seat-allocations/get/<int:pk>', ExamSeatAllocationViewSet.as_view({'get': 'retrieve'}), name='univ-exam-seat-alloc-detail'),
    path('seat-allocations/edit/<int:pk>', ExamSeatAllocationViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-seat-alloc-edit'),
    path('seat-allocations/remove/<int:pk>', ExamSeatAllocationViewSet.as_view({'delete': 'destroy'}), name='univ-exam-seat-alloc-remove'),
    path('seat-allocations/by-hall/<int:hall_id>', ExamSeatAllocationViewSet.as_view({'get': 'by_hall'}), name='univ-exam-seat-by-hall'),

    # Anna University Result & Revaluation Publish
    path('results/preview', UniversityResultPublishViewSet.as_view({'post': 'preview_results'}), name='univ-exam-results-preview'),
    path('results/publish', UniversityResultPublishViewSet.as_view({'post': 'publish_results'}), name='univ-exam-results-publish'),
]
