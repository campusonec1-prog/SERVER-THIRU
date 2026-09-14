from django.urls import path
from .views import (
    StudentStatusViewSet, 
    StudentViewSet, 
    MarksViewSet, 
    CounsellingReportViewSet, 
    FacultyActivityViewSet, 
    StudentAttendanceViewSet,
    GradeSystemViewSet,
    HostelVisitorLogViewSet
)

urlpatterns = [
    # Student Status endpoints
    path('statuses/create', StudentStatusViewSet.as_view({'post': 'create'}), name='student-status-create'),
    path('statuses/list', StudentStatusViewSet.as_view({'get': 'list'}), name='student-status-list'),
    path('statuses/get/<int:pk>', StudentStatusViewSet.as_view({'get': 'retrieve'}), name='student-status-detail'),
    path('statuses/edit/<int:pk>', StudentStatusViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='student-status-edit'),
    path('statuses/remove/<int:pk>', StudentStatusViewSet.as_view({'delete': 'destroy'}), name='student-status-remove'),

    # Hostel Visitor Log endpoints
    path('hostel/visitor-logs/create', HostelVisitorLogViewSet.as_view({'post': 'create'}), name='hostel-visitor-log-create'),
    path('hostel/visitor-logs/list', HostelVisitorLogViewSet.as_view({'get': 'list'}), name='hostel-visitor-log-list'),
    path('hostel/visitor-logs/get/<int:pk>', HostelVisitorLogViewSet.as_view({'get': 'retrieve'}), name='hostel-visitor-log-detail'),
    path('hostel/visitor-logs/edit/<int:pk>', HostelVisitorLogViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='hostel-visitor-log-edit'),
    path('hostel/visitor-logs/remove/<int:pk>', HostelVisitorLogViewSet.as_view({'delete': 'destroy'}), name='hostel-visitor-log-remove'),
    path('hostel/visitor-logs/checkout/<int:pk>', HostelVisitorLogViewSet.as_view({'post': 'checkout'}), name='hostel-visitor-log-checkout'),

    # Grade System endpoints
    path('grade-systems/create', GradeSystemViewSet.as_view({'post': 'create'}), name='grade-system-create'),
    path('grade-systems/list', GradeSystemViewSet.as_view({'get': 'list'}), name='grade-system-list'),
    path('grade-systems/get/<int:pk>', GradeSystemViewSet.as_view({'get': 'retrieve'}), name='grade-system-detail'),
    path('grade-systems/edit/<int:pk>', GradeSystemViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='grade-system-edit'),
    path('grade-systems/remove/<int:pk>', GradeSystemViewSet.as_view({'delete': 'destroy'}), name='grade-system-remove'),

    # Grade System endpoints
    path('grade-systems/create', GradeSystemViewSet.as_view({'post': 'create'}), name='grade-system-create'),
    path('grade-systems/list', GradeSystemViewSet.as_view({'get': 'list'}), name='grade-system-list'),
    path('grade-systems/get/<int:pk>', GradeSystemViewSet.as_view({'get': 'retrieve'}), name='grade-system-detail'),
    path('grade-systems/edit/<int:pk>', GradeSystemViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='grade-system-edit'),
    path('grade-systems/remove/<int:pk>', GradeSystemViewSet.as_view({'delete': 'destroy'}), name='grade-system-remove'),

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
    path('comprehensive-view', StudentViewSet.as_view({'get': 'comprehensive_view'}), name='student-comprehensive-view'),

    # Marks endpoints
    path('marks/create', MarksViewSet.as_view({'post': 'create'}), name='marks-create'),
    path('marks/list', MarksViewSet.as_view({'get': 'list'}), name='marks-list'),
    path('marks/get/<int:pk>', MarksViewSet.as_view({'get': 'retrieve'}), name='marks-detail'),
    path('marks/edit', MarksViewSet.as_view({'put': 'update'}), name='marks-edit'),
    path('marks/marksheet-report/pdf', MarksViewSet.as_view({'post': 'marksheet_report_pdf', 'get': 'marksheet_report_pdf'}), name='marksheet-report-pdf'),
    path('marks/consolidated-marksheet-report/pdf', MarksViewSet.as_view({'post': 'consolidated_marksheet_report_pdf', 'get': 'consolidated_marksheet_report_pdf'}), name='consolidated-marksheet-report-pdf'),
    path('marks/progress-report/pdf', MarksViewSet.as_view({'post': 'progress_report_pdf', 'get': 'progress_report_pdf'}), name='progress-report-pdf'),
    path('marks/internal-exam-result-analysis-report/pdf', MarksViewSet.as_view({'post': 'internal_exam_result_analysis_report_pdf', 'get': 'internal_exam_result_analysis_report_pdf'}), name='internal-exam-result-analysis-report-pdf'),
    path('marks/consolidated-exam-result-analysis-report/pdf', MarksViewSet.as_view({'post': 'consolidated_exam_result_analysis_report_pdf', 'get': 'consolidated_exam_result_analysis_report_pdf'}), name='consolidated-exam-result-analysis-report-pdf'),
    path('marks/capa-report/pdf', MarksViewSet.as_view({'post': 'capa_report_pdf', 'get': 'capa_report_pdf'}), name='capa-report-pdf'),
    path('marks/student-performance-report/pdf', MarksViewSet.as_view({'post': 'student_performance_report_pdf', 'get': 'student_performance_report_pdf'}), name='student-performance-report-pdf'),


    # Attendance endpoints
    path('attendance/activity/create', FacultyActivityViewSet.as_view({'post': 'create'}), name='attendance-activity-create'),
    path('attendance/activity/list', FacultyActivityViewSet.as_view({'get': 'list'}), name='attendance-activity-list'),
    path('attendance/activity/get/<int:pk>', FacultyActivityViewSet.as_view({'get': 'retrieve'}), name='attendance-activity-detail'),
    path('attendance/activity/edit/<int:pk>', FacultyActivityViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='attendance-activity-edit'),
    path('attendance/activity/remove/<int:pk>', FacultyActivityViewSet.as_view({'delete': 'destroy'}), name='attendance-activity-remove'),
    path('attendance/submit', StudentAttendanceViewSet.as_view({'post': 'bulk_submit'}), name='attendance-submit'),
    path('attendance/list', StudentAttendanceViewSet.as_view({'get': 'list'}), name='attendance-list'),
    path('attendance/subject-wise-report/pdf', StudentAttendanceViewSet.as_view({'post': 'subject_wise_attendance_report_pdf', 'get': 'subject_wise_attendance_report_pdf'}), name='subject-wise-attendance-report-pdf'),
    path('attendance/consolidated-report/pdf', StudentAttendanceViewSet.as_view({'post': 'consolidated_attendance_report_pdf', 'get': 'consolidated_attendance_report_pdf'}), name='consolidated-attendance-report-pdf'),

    # Counselling Report endpoints
    path('counselling/create', CounsellingReportViewSet.as_view({'post': 'create'}), name='counselling-create'),
    path('counselling/list', CounsellingReportViewSet.as_view({'get': 'list'}), name='counselling-list'),
    path('counselling/get/<int:pk>', CounsellingReportViewSet.as_view({'get': 'retrieve'}), name='counselling-detail'),
    path('counselling/edit/<int:pk>', CounsellingReportViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='counselling-edit'),
    path('counselling/remove/<int:pk>', CounsellingReportViewSet.as_view({'delete': 'destroy'}), name='counselling-remove'),
]


