from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LeavePolicyViewSet, FacultyLeaveViewSet,
    ClassSubstitutionViewSet, NotificationViewSet, LeaveHelperViewSet,
    HostelLeaveRequestViewSet
)

router = DefaultRouter(trailing_slash=False)
router.register(r'policies', LeavePolicyViewSet, basename='leave-policy')
router.register(r'applications', FacultyLeaveViewSet, basename='faculty-leave')
router.register(r'substitutions', ClassSubstitutionViewSet, basename='class-substitution')
router.register(r'notifications', NotificationViewSet, basename='leave-notification')
router.register(r'helper', LeaveHelperViewSet, basename='leave-helper')
router.register(r'hostel-requests', HostelLeaveRequestViewSet, basename='hostel-leave-request')

urlpatterns = [
    path('', include(router.urls)),
]
