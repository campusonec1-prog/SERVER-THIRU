"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from dynamic_forms.views import DocumentUploadView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/roles/', include('role.urls')),
    path('api/users/', include('users.urls')),
    path('api/institution/', include('institution.urls')),
    path('api/schedule/', include('schedule.urls')),
    path('api/announcements/', include('announcements.urls')),
    path('api/forms/', include('dynamic_forms.urls')),
    path('api/subject/', include('subject.urls')),
    path('api/student/', include('student.urls')),
    path('api/timetable/', include('timetable.urls')),
    path('api/leave/', include('leave.urls')),
    path('api/documents/upload', DocumentUploadView.as_view(), name='document-upload'),
]


