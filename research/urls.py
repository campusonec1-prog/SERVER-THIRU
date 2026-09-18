from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FacultyResearchProjectViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r'projects', FacultyResearchProjectViewSet, basename='research-project')

urlpatterns = [
    path('', include(router.urls)),
]
