from django.urls import path, re_path, include
from rest_framework.routers import DefaultRouter
from .views import FacultyResearchProjectViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r'projects', FacultyResearchProjectViewSet, basename='research-project')

urlpatterns = [
    re_path(r'^projects/report/pdf/?$', FacultyResearchProjectViewSet.as_view({'post': 'report_pdf', 'get': 'report_pdf'}), name='research-report-pdf'),
    re_path(r'^projects/report/data/?$', FacultyResearchProjectViewSet.as_view({'post': 'report_data', 'get': 'report_data'}), name='research-report-data'),
    path('', include(router.urls)),
]
