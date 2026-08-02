from django.urls import path
from .views import ProgramViewSet, DepartmentViewSet, AcademicYearViewSet, BatchViewSet, RegulationViewSet, SemesterViewSet, SectionViewSet, CollegeHeaderViewSet, ExamTypeViewSet, ExamViewSet

urlpatterns = [
    # Program endpoints
    path('programs/list', ProgramViewSet.as_view({'get': 'list'}), name='program-list'),
    path('programs/create', ProgramViewSet.as_view({'post': 'create'}), name='program-create'),
    path('programs/get/<int:pk>', ProgramViewSet.as_view({'get': 'retrieve'}), name='program-detail'),
    path('programs/edit/<int:pk>', ProgramViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='program-edit'),
    path('programs/remove/<int:pk>', ProgramViewSet.as_view({'delete': 'destroy'}), name='program-remove'),

    # Department endpoints
    path('departments/list', DepartmentViewSet.as_view({'get': 'list'}), name='department-list'),
    path('departments/create', DepartmentViewSet.as_view({'post': 'create'}), name='department-create'),
    path('departments/get/<int:pk>', DepartmentViewSet.as_view({'get': 'retrieve'}), name='department-detail'),
    path('departments/edit/<int:pk>', DepartmentViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='department-edit'),
    path('departments/remove/<int:pk>', DepartmentViewSet.as_view({'delete': 'destroy'}), name='department-remove'),

    # Academic Year endpoints
    path('academic-years/list', AcademicYearViewSet.as_view({'get': 'list'}), name='academic-year-list'),
    path('academic-years/create', AcademicYearViewSet.as_view({'post': 'create'}), name='academic-year-create'),
    path('academic-years/get/<int:pk>', AcademicYearViewSet.as_view({'get': 'retrieve'}), name='academic-year-detail'),
    path('academic-years/edit/<int:pk>', AcademicYearViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='academic-year-edit'),
    path('academic-years/remove/<int:pk>', AcademicYearViewSet.as_view({'delete': 'destroy'}), name='academic-year-remove'),

    # Batch endpoints
    path('batches/list', BatchViewSet.as_view({'get': 'list'}), name='batch-list'),
    path('batches/create', BatchViewSet.as_view({'post': 'create'}), name='batch-create'),
    path('batches/get/<int:pk>', BatchViewSet.as_view({'get': 'retrieve'}), name='batch-detail'),
    path('batches/edit/<int:pk>', BatchViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='batch-edit'),
    path('batches/remove/<int:pk>', BatchViewSet.as_view({'delete': 'destroy'}), name='batch-remove'),

    # Regulation endpoints
    path('regulations/list', RegulationViewSet.as_view({'get': 'list'}), name='regulation-list'),
    path('regulations/create', RegulationViewSet.as_view({'post': 'create'}), name='regulation-create'),
    path('regulations/get/<int:pk>', RegulationViewSet.as_view({'get': 'retrieve'}), name='regulation-detail'),
    path('regulations/edit/<int:pk>', RegulationViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='regulation-edit'),
    path('regulations/remove/<int:pk>', RegulationViewSet.as_view({'delete': 'destroy'}), name='regulation-remove'),

    # Semester endpoints
    path('semesters/list', SemesterViewSet.as_view({'get': 'list'}), name='semester-list'),
    path('semesters/create', SemesterViewSet.as_view({'post': 'create'}), name='semester-create'),
    path('semesters/get/<int:pk>', SemesterViewSet.as_view({'get': 'retrieve'}), name='semester-detail'),
    path('semesters/edit/<int:pk>', SemesterViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='semester-edit'),
    path('semesters/remove/<int:pk>', SemesterViewSet.as_view({'delete': 'destroy'}), name='semester-remove'),

    # Section endpoints
    path('sections/list', SectionViewSet.as_view({'get': 'list'}), name='section-list'),
    path('sections/create', SectionViewSet.as_view({'post': 'create'}), name='section-create'),
    path('sections/get/<int:pk>', SectionViewSet.as_view({'get': 'retrieve'}), name='section-detail'),
    path('sections/edit/<int:pk>', SectionViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='section-edit'),
    path('sections/remove/<int:pk>', SectionViewSet.as_view({'delete': 'destroy'}), name='section-remove'),

    # College Header endpoints
    path('college-headers/list', CollegeHeaderViewSet.as_view({'get': 'list'}), name='college-header-list'),
    path('college-headers/create', CollegeHeaderViewSet.as_view({'post': 'create'}), name='college-header-create'),
    path('college-headers/get/<int:pk>', CollegeHeaderViewSet.as_view({'get': 'retrieve'}), name='college-header-detail'),
    path('college-headers/edit/<int:pk>', CollegeHeaderViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='college-header-edit'),
    path('college-headers/remove/<int:pk>', CollegeHeaderViewSet.as_view({'delete': 'destroy'}), name='college-header-remove'),

    # Exam Type endpoints
    path('exam-types/list', ExamTypeViewSet.as_view({'get': 'list'}), name='exam-type-list'),
    path('exam-types/create', ExamTypeViewSet.as_view({'post': 'create'}), name='exam-type-create'),
    path('exam-types/get/<int:pk>', ExamTypeViewSet.as_view({'get': 'retrieve'}), name='exam-type-detail'),
    path('exam-types/edit/<int:pk>', ExamTypeViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='exam-type-edit'),
    path('exam-types/remove/<int:pk>', ExamTypeViewSet.as_view({'delete': 'destroy'}), name='exam-type-remove'),

    # Exam endpoints
    path('exams/list', ExamViewSet.as_view({'get': 'list'}), name='exam-list'),
    path('exams/create', ExamViewSet.as_view({'post': 'create'}), name='exam-create'),
    path('exams/get/<int:pk>', ExamViewSet.as_view({'get': 'retrieve'}), name='exam-detail'),
    path('exams/edit/<int:pk>', ExamViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='exam-edit'),
    path('exams/remove/<int:pk>', ExamViewSet.as_view({'delete': 'destroy'}), name='exam-remove'),
]
