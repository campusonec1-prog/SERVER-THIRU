from unittest.mock import patch
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

from role.models import Role
from users.models import User, UserDetails
from institution.models import Department, Program
from research.models import FacultyResearchProject


class FacultyResearchProjectTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Roles
        self.admin_role = Role.objects.create(role_name='ADMIN')
        self.faculty_role = Role.objects.create(role_name='FACULTY')
        self.student_role = Role.objects.create(role_name='STUDENT')

        # Users
        self.admin_user = User.objects.create(
            name='Admin User',
            username='admin_user',
            password='password123',
            mobile_number='9876543210',
            mail='admin@college.edu',
            role=self.admin_role
        )

        self.faculty_user1 = User.objects.create(
            name='Dr. Smith',
            username='dr_smith',
            password='password123',
            mobile_number='9876543211',
            mail='smith@college.edu',
            role=self.faculty_role
        )

        self.faculty_user2 = User.objects.create(
            name='Dr. Jones',
            username='dr_jones',
            password='password123',
            mobile_number='9876543212',
            mail='jones@college.edu',
            role=self.faculty_role
        )

        self.student_user = User.objects.create(
            name='Student One',
            username='student_one',
            password='password123',
            mobile_number='9876543213',
            mail='student@college.edu',
            role=self.student_role
        )

        # Department setup
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

        # Faculty Details (users.UserDetails)
        self.faculty_details1 = UserDetails.objects.create(
            user=self.faculty_user1,
            faculty_code='FAC001',
            qualification='Ph.D. in Computer Science',
            designation='Professor',
            date_of_joining=date(2018, 1, 1),
            gender='Male',
            department=self.department
        )

        self.faculty_details2 = UserDetails.objects.create(
            user=self.faculty_user2,
            faculty_code='FAC002',
            qualification='Ph.D. in Information Technology',
            designation='Associate Professor',
            date_of_joining=date(2020, 6, 1),
            gender='Female',
            department=self.department
        )

    @patch('research.views.broadcast_research_project_event')
    def test_create_research_project_success(self, mock_broadcast):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'project_title': 'AI in Healthcare Analytics',
            'project_code': 'PROJ-AI-01',
            'principal_investigator': self.faculty_details1.id,
            'co_investigators': [self.faculty_details2.id],
            'site_name': 'DST Portal',
            'reference_url': 'https://dst.gov.in/projects/101',
            'research_area': 'Artificial Intelligence',
            'project_type': 'Funded',
            'funding_agency': 'DST',
            'sanctioned_amount': '500000.00',
            'project_start_date': str(date.today()),
            'project_end_date': str(date.today() + timedelta(days=365)),
            'status': 'Ongoing',
            'description': 'AI models for clinical diagnosis',
            'objectives': 'Build high accuracy models',
            'outcomes': 'Published papers and dataset'
        }

        response = self.client.post('/api/research/projects', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data.get('success'))
        self.assertEqual(response.data.get('message'), 'Research project created successfully.')
        self.assertEqual(FacultyResearchProject.objects.count(), 1)

        project = FacultyResearchProject.objects.get()
        self.assertEqual(project.project_title, 'AI in Healthcare Analytics')
        self.assertEqual(project.principal_investigator, self.faculty_details1)
        self.assertIn(self.faculty_details2, project.co_investigators.all())

        # Verify WebSocket event broadcast
        mock_broadcast.assert_called_once()
        self.assertEqual(mock_broadcast.call_args[0][0], 'research_project_created')

    def test_create_project_pi_as_co_investigator_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'project_title': 'Quantum Computing Lab',
            'principal_investigator': self.faculty_details1.id,
            'co_investigators': [self.faculty_details1.id],
            'research_area': 'Quantum',
            'project_type': 'Non-Funded',
            'project_start_date': str(date.today()),
        }

        response = self.client.post('/api/research/projects', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Principal investigator cannot also be a co-investigator', str(response.data))

    def test_invalid_dates_validation_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'project_title': 'Robotics Research',
            'principal_investigator': self.faculty_details1.id,
            'research_area': 'Robotics',
            'project_type': 'Non-Funded',
            'project_start_date': str(date.today()),
            'project_end_date': str(date.today() - timedelta(days=10)),
        }

        response = self.client.post('/api/research/projects', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Project end date cannot be before the start date', str(response.data))

    def test_negative_sanctioned_amount_validation_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'project_title': 'Cyber Security Framework',
            'principal_investigator': self.faculty_details1.id,
            'research_area': 'Security',
            'project_type': 'Non-Funded',
            'sanctioned_amount': '-1000.00',
            'project_start_date': str(date.today()),
        }

        response = self.client.post('/api/research/projects', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_funded_project_requires_funding_agency_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'project_title': 'Cloud Computing Optimization',
            'principal_investigator': self.faculty_details1.id,
            'research_area': 'Cloud',
            'project_type': 'Funded',
            'funding_agency': '',
            'project_start_date': str(date.today()),
        }

        response = self.client.post('/api/research/projects', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('research.views.broadcast_research_project_event')
    def test_update_research_project_success(self, mock_broadcast):
        self.client.force_authenticate(user=self.admin_user)
        project = FacultyResearchProject.objects.create(
            project_title='Initial Project',
            principal_investigator=self.faculty_details1,
            research_area='IoT',
            project_type='Non-Funded',
            project_start_date=date.today(),
            status='Proposed'
        )

        update_payload = {
            'project_title': 'Updated IoT Smart Grid Project',
            'status': 'Ongoing'
        }

        response = self.client.patch(f'/api/research/projects/{project.id}', update_payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertEqual(response.data.get('message'), 'Research project updated successfully.')

        project.refresh_from_db()
        self.assertEqual(project.project_title, 'Updated IoT Smart Grid Project')
        self.assertEqual(project.status, 'Ongoing')

        mock_broadcast.assert_called_once()
        self.assertEqual(mock_broadcast.call_args[0][0], 'research_project_updated')

    @patch('research.views.broadcast_research_project_event')
    def test_delete_research_project_success(self, mock_broadcast):
        self.client.force_authenticate(user=self.admin_user)
        project = FacultyResearchProject.objects.create(
            project_title='Project to delete',
            principal_investigator=self.faculty_details1,
            research_area='Data Mining',
            project_type='Non-Funded',
            project_start_date=date.today()
        )

        response = self.client.delete(f'/api/research/projects/{project.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        self.assertEqual(response.data.get('message'), 'Research project deleted successfully.')
        self.assertEqual(FacultyResearchProject.objects.count(), 0)

        mock_broadcast.assert_called_once()
        self.assertEqual(mock_broadcast.call_args[0][0], 'research_project_deleted')

    def test_faculty_specific_projects_endpoint(self):
        self.client.force_authenticate(user=self.admin_user)
        p1 = FacultyResearchProject.objects.create(
            project_title='Smith Project 1',
            principal_investigator=self.faculty_details1,
            research_area='AI',
            project_type='Non-Funded',
            project_start_date=date.today()
        )
        p2 = FacultyResearchProject.objects.create(
            project_title='Jones Project 1',
            principal_investigator=self.faculty_details2,
            research_area='VLSI',
            project_type='Non-Funded',
            project_start_date=date.today()
        )

        response = self.client.get(f'/api/research/projects/faculty/{self.faculty_details1.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('success'))
        results = response.data['data'].get('results', response.data['data'])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], p1.id)

    def test_search_and_filter_projects(self):
        self.client.force_authenticate(user=self.admin_user)
        FacultyResearchProject.objects.create(
            project_title='Deep Learning for Vision',
            project_code='DL-101',
            principal_investigator=self.faculty_details1,
            research_area='Computer Vision',
            project_type='Funded',
            funding_agency='SERB',
            project_start_date=date.today(),
            status='Ongoing'
        )

        FacultyResearchProject.objects.create(
            project_title='Blockchain Security',
            project_code='BC-202',
            principal_investigator=self.faculty_details2,
            research_area='Cryptography',
            project_type='Consultancy',
            funding_agency='Industry Partner',
            project_start_date=date.today(),
            status='Proposed'
        )

        # Search test
        response = self.client.get('/api/research/projects?search=Vision')
        results = response.data['data'].get('results', response.data['data'])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['project_code'], 'DL-101')

        # Filter test
        response = self.client.get('/api/research/projects?status=Proposed')
        results = response.data['data'].get('results', response.data['data'])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['project_code'], 'BC-202')

    def test_faculty_only_sees_own_projects(self):
        # Create project for Faculty 1
        p1 = FacultyResearchProject.objects.create(
            project_title='Smith AI Research',
            principal_investigator=self.faculty_details1,
            research_area='AI',
            project_type='Non-Funded',
            project_start_date=date.today()
        )
        # Create project for Faculty 2
        p2 = FacultyResearchProject.objects.create(
            project_title='Jones VLSI Research',
            principal_investigator=self.faculty_details2,
            research_area='VLSI',
            project_type='Non-Funded',
            project_start_date=date.today()
        )

        # Authenticate as Faculty 1 (Smith)
        self.client.force_authenticate(user=self.faculty_user1)
        res1 = self.client.get('/api/research/projects')
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        results1 = res1.data['data'].get('results', res1.data['data'])
        self.assertEqual(len(results1), 1)
        self.assertEqual(results1[0]['id'], p1.id)

        # Authenticate as Faculty 2 (Jones)
        self.client.force_authenticate(user=self.faculty_user2)
        res2 = self.client.get('/api/research/projects')
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        results2 = res2.data['data'].get('results', res2.data['data'])
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]['id'], p2.id)

        # Authenticate as Admin (Admin sees both)
        self.client.force_authenticate(user=self.admin_user)
        res_admin = self.client.get('/api/research/projects')
        self.assertEqual(res_admin.status_code, status.HTTP_200_OK)
        results_admin = res_admin.data['data'].get('results', res_admin.data['data'])
        self.assertEqual(len(results_admin), 2)

    def test_hod_only_sees_own_projects(self):
        hod_role = Role.objects.create(role_name='HOD')
        hod_user = User.objects.create(
            name='Dr. HOD',
            username='dr_hod',
            password='password123',
            mobile_number='9876543299',
            mail='hod@college.edu',
            role=hod_role
        )
        hod_details = UserDetails.objects.create(
            user=hod_user,
            faculty_code='HOD001',
            qualification='Ph.D.',
            designation='HOD',
            date_of_joining=date(2015, 1, 1),
            gender='Male',
            department=self.department
        )

        # Project owned by HOD
        p_hod = FacultyResearchProject.objects.create(
            project_title='HOD Research Project',
            principal_investigator=hod_details,
            research_area='Management',
            project_type='Non-Funded',
            project_start_date=date.today()
        )
        # Project owned by Faculty in same department
        p_fac = FacultyResearchProject.objects.create(
            project_title='Faculty Research Project in same Dept',
            principal_investigator=self.faculty_details1,
            research_area='AI',
            project_type='Non-Funded',
            project_start_date=date.today()
        )

        self.client.force_authenticate(user=hod_user)
        res = self.client.get('/api/research/projects')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['data'].get('results', res.data['data'])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], p_hod.id)
