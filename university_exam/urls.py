from django.urls import path
from .views import (
    ExamAttendanceImportViewSet, UniversityExamScheduleViewSet,
    UniversityExamAttendanceViewSet, ExamHallAllocationViewSet,
    ExamSeatAllocationViewSet, UniversityExamHallViewSet, ExamHallDateViewSet
)

urlpatterns = [
    # Exam Halls (University Exam Configuration)
    path('exam-halls/list', UniversityExamHallViewSet.as_view({'get': 'list'}), name='univ-exam-hall-list'),
    path('exam-halls/create', UniversityExamHallViewSet.as_view({'post': 'create'}), name='univ-exam-hall-create'),
    path('exam-halls/get/<int:pk>', UniversityExamHallViewSet.as_view({'get': 'retrieve'}), name='univ-exam-hall-detail'),
    path('exam-halls/edit/<int:pk>', UniversityExamHallViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-hall-edit'),
    path('exam-halls/remove/<int:pk>', UniversityExamHallViewSet.as_view({'delete': 'destroy'}), name='univ-exam-hall-remove'),

    # Exam Hall Dates
    path('hall-dates/list', ExamHallDateViewSet.as_view({'get': 'list'}), name='univ-exam-hall-date-list'),
    path('hall-dates/create', ExamHallDateViewSet.as_view({'post': 'create'}), name='univ-exam-hall-date-create'),
    path('hall-dates/get/<int:pk>', ExamHallDateViewSet.as_view({'get': 'retrieve'}), name='univ-exam-hall-date-detail'),
    path('hall-dates/edit/<int:pk>', ExamHallDateViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-hall-date-edit'),
    path('hall-dates/remove/<int:pk>', ExamHallDateViewSet.as_view({'delete': 'destroy'}), name='univ-exam-hall-date-remove'),

    # Attendance Import
    path('import/preview', ExamAttendanceImportViewSet.as_view({'post': 'preview_pdf'}), name='univ-exam-import-preview'),
    path('import/quick-add-dept', ExamAttendanceImportViewSet.as_view({'post': 'quick_add_dept'}), name='univ-exam-import-quick-add-dept'),
    path('import/quick-add-subject', ExamAttendanceImportViewSet.as_view({'post': 'quick_add_subject'}), name='univ-exam-import-quick-add-subject'),
    path('import/quick-add-student', ExamAttendanceImportViewSet.as_view({'post': 'quick_add_student'}), name='univ-exam-import-quick-add-student'),
    path('import/confirm-save', ExamAttendanceImportViewSet.as_view({'post': 'confirm_save'}), name='univ-exam-import-confirm-save'),
    path('import/upload', ExamAttendanceImportViewSet.as_view({'post': 'upload_pdf'}), name='univ-exam-import-upload'),
    path('import/process', ExamAttendanceImportViewSet.as_view({'post': 'process_imports'}), name='univ-exam-import-process'),
    path('import/list', ExamAttendanceImportViewSet.as_view({'get': 'list'}), name='univ-exam-import-list'),
    path('import/get/<int:pk>', ExamAttendanceImportViewSet.as_view({'get': 'retrieve'}), name='univ-exam-import-detail'),
    path('import/remove/<int:pk>', ExamAttendanceImportViewSet.as_view({'delete': 'destroy'}), name='univ-exam-import-remove'),
    path('import/clear-pending', ExamAttendanceImportViewSet.as_view({'delete': 'clear_pending'}), name='univ-exam-import-clear-pending'),

    # Exam Schedules
    path('schedules/list', UniversityExamScheduleViewSet.as_view({'get': 'list'}), name='univ-exam-schedule-list'),
    path('schedules/create', UniversityExamScheduleViewSet.as_view({'post': 'create'}), name='univ-exam-schedule-create'),
    path('schedules/get/<int:pk>', UniversityExamScheduleViewSet.as_view({'get': 'retrieve'}), name='univ-exam-schedule-detail'),
    path('schedules/edit/<int:pk>', UniversityExamScheduleViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-schedule-edit'),
    path('schedules/remove/<int:pk>', UniversityExamScheduleViewSet.as_view({'delete': 'destroy'}), name='univ-exam-schedule-remove'),
    path('schedules/generate-seating', UniversityExamScheduleViewSet.as_view({'post': 'generate_seating'}), name='univ-exam-generate-seating'),

    # Attendances
    path('attendances/list', UniversityExamAttendanceViewSet.as_view({'get': 'list'}), name='univ-exam-attendance-list'),
    path('attendances/create', UniversityExamAttendanceViewSet.as_view({'post': 'create'}), name='univ-exam-attendance-create'),
    path('attendances/get/<int:pk>', UniversityExamAttendanceViewSet.as_view({'get': 'retrieve'}), name='univ-exam-attendance-detail'),
    path('attendances/edit/<int:pk>', UniversityExamAttendanceViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='univ-exam-attendance-edit'),
    path('attendances/remove/<int:pk>', UniversityExamAttendanceViewSet.as_view({'delete': 'destroy'}), name='univ-exam-attendance-remove'),

    # Hall Allocations
    path('hall-allocations/list', ExamHallAllocationViewSet.as_view({'get': 'list'}), name='univ-exam-hall-alloc-list'),
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
]
