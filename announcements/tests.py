from datetime import date, timedelta
from django.utils import timezone
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from role.models import Role
from users.models import User
from institution.models import Department, Program
from announcements.models import NoticeBoard


class NoticeBoardEventTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Roles
        self.admin_role = Role.objects.create(role_name='ADMIN')
        self.hod_role = Role.objects.create(role_name='HOD')
        self.faculty_role = Role.objects.create(role_name='FACULTY')
        self.student_role = Role.objects.create(role_name='STUDENT')

        # Users
        self.admin_user = User.objects.create(
            name='Admin User',
            username='admin_ann',
            password='password123',
            mobile_number='9800000001',
            mail='admin_ann@college.edu',
            role=self.admin_role
        )

        self.hod_user = User.objects.create(
            name='Dr. HOD CSE',
            username='hod_cse',
            password='password123',
            mobile_number='9800000002',
            mail='hod_cse@college.edu',
            role=self.hod_role
        )

        self.student_user = User.objects.create(
            name='Student User',
            username='student_user',
            password='password123',
            mobile_number='9800000003',
            mail='student@college.edu',
            role=self.student_role
        )

        # Department
        self.program = Program.objects.create(
            program_name='Computer Science Engineering',
            program_level='UG',
            duration=4
        )
        self.department = Department.objects.create(
            department_name='Computer Science & Engineering',
            department_code='CSE',
            short_name='CSE',
            program=self.program
        )

    def test_create_global_event_notice_success(self):
        self.client.force_authenticate(user=self.hod_user)
        payload = {
            'notice_title': 'Annual Tech Fest 2026',
            'notice_type': 'events',
            'priority': 'high',
            'publish_date': str(timezone.now()),
            'expire_date': str(timezone.now() + timedelta(days=7)),
            'description': 'Grand national level technical symposium open for all departments.',
            'organizer': 'CSE Association & IEEE Student Branch',
            'coordinator': 'Dr. HOD CSE',
            'sub_coordinators': ['Prof. Smith', 'Prof. Jones'],
            'target_audience_type': 'global'
        }

        response = self.client.post('/api/announcements/notices/create', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(NoticeBoard.objects.count(), 1)

        notice = NoticeBoard.objects.get()
        self.assertEqual(notice.notice_title, 'Annual Tech Fest 2026')
        self.assertEqual(notice.organizer, 'CSE Association & IEEE Student Branch')
        self.assertEqual(notice.target_audience_type, 'global')

    def test_create_targeted_event_notice_success(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'notice_title': 'CSE Department Workshop',
            'notice_type': 'academic',
            'priority': 'medium',
            'publish_date': str(timezone.now()),
            'expire_date': str(timezone.now() + timedelta(days=5)),
            'description': 'Special AI/ML Workshop for CSE 2024 Batch',
            'organizer': 'Dept of CSE',
            'coordinator': 'Dr. HOD CSE',
            'target_audience_type': 'targeted',
            'department': self.department.id,
            'batch': '2024',
            'section': 'A'
        }

        response = self.client.post('/api/announcements/notices/create', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        notice = NoticeBoard.objects.get(notice_title='CSE Department Workshop')
        self.assertEqual(notice.department, self.department)
        self.assertEqual(notice.batch, '2024')
        self.assertEqual(notice.section, 'A')

    def test_upcoming_events_endpoint_for_students(self):
        # Create 1 global event and 1 targeted event
        g_evt = NoticeBoard.objects.create(
            notice_title='Global Campus Event',
            notice_type='events',
            priority='high',
            publish_date=timezone.now(),
            expire_date=timezone.now() + timedelta(days=10),
            description='Global hackathon event',
            faculty=self.admin_user,
            target_audience_type='global',
            is_active=True
        )

        t_evt = NoticeBoard.objects.create(
            notice_title='CSE Targeted Seminar',
            notice_type='events',
            priority='medium',
            publish_date=timezone.now(),
            expire_date=timezone.now() + timedelta(days=10),
            description='Seminar for CSE dept',
            faculty=self.hod_user,
            target_audience_type='targeted',
            department=self.department,
            batch='2024',
            section='A',
            is_active=True
        )

        self.client.force_authenticate(user=self.student_user)
        # Query for CSE student in 2024 batch
        response = self.client.get(f'/api/announcements/notices/upcoming-events?department_id={self.department.id}&batch=2024&section=A')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data.get('data', [])
        self.assertEqual(len(data), 2)

    def test_create_and_update_notice_with_poster(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from unittest.mock import patch

        self.client.force_authenticate(user=self.admin_user)
        dummy_image = SimpleUploadedFile("poster.jpg", b"file_content", content_type="image/jpeg")

        with patch('announcements.views.upload_file_to_r2') as mock_upload:
            mock_upload.return_value = 'https://r2.dev/event_posters/poster.jpg'

            payload = {
                'notice_title': 'Event With Poster',
                'notice_type': 'events',
                'priority': 'high',
                'publish_date': str(timezone.now()),
                'expire_date': str(timezone.now() + timedelta(days=5)),
                'description': 'Event poster description',
                'poster': dummy_image
            }

            response = self.client.post('/api/announcements/notices/create', payload, format='multipart')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['data']['poster_url'], 'https://r2.dev/event_posters/poster.jpg')

            notice = NoticeBoard.objects.get(notice_title='Event With Poster')
            self.assertEqual(notice.poster_url, 'https://r2.dev/event_posters/poster.jpg')
