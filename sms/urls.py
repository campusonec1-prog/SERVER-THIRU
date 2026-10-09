from django.urls import path
from .views import (
    FullDayAbsenteesListView,
    SendFullDayAbsentSMSView,
    AfternoonAbsenteesListView,
    SendAfternoonAbsentSMSView,
    SMSLogViewSet,
    SMSBalanceView,
    SMSDashboardStatsView
)

urlpatterns = [
    path('balance', SMSBalanceView.as_view(), name='sms-balance'),
    path('dashboard', SMSDashboardStatsView.as_view(), name='sms-dashboard'),
    path('absentees/full-day', FullDayAbsenteesListView.as_view(), name='sms-full-day-absentees'),
    path('send-full-day-absent', SendFullDayAbsentSMSView.as_view(), name='sms-send-full-day-absent'),
    path('absentees/afternoon', AfternoonAbsenteesListView.as_view(), name='sms-afternoon-absentees'),
    path('send-afternoon-absent', SendAfternoonAbsentSMSView.as_view(), name='sms-send-afternoon-absent'),
    path('logs', SMSLogViewSet.as_view({'get': 'list'}), name='sms-logs-list'),
    path('logs/<int:pk>', SMSLogViewSet.as_view({'get': 'retrieve'}), name='sms-logs-detail'),
]

