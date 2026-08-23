from django.test import TestCase
from student.models import Student, StudentStatus, CounsellingReport
from student.serializers import StudentSerializer
from dynamic_forms.models import ApplicationUser
from institution.models import Program, Department, Batch


class StudentUserUniquenessTest(TestCase):
    def setUp(self):
        self.status = StudentStatus.objects.create(status_name="Active")
        self.program = Program.objects.create(
            program_name="Computer Science Engineering",
            program_level="UG",
            duration=4
        )
        self.department = Department.objects.create(
            program=self.program,
            department_name="Computer Science",
            department_code="CSE",
            short_name="CS"
        )
        self.batch = Batch.objects.create(
            department=self.department,
            batch="2022-2026"
        )
        self.user1 = ApplicationUser.objects.create(
            name="User One",
            email="user1@example.com",
            phone_number="1234567890",
            password="pass"
        )
        self.user2 = ApplicationUser.objects.create(
            name="User Two",
            email="user2@example.com",
            phone_number="0987654321",
            password="pass"
        )

        self.student1 = Student.objects.create(
            roll_number="1001",
            register_number="REG1001",
            department=self.department,
            batch=self.batch,
            user=self.user1,
            status=self.status
        )

    def test_duplicate_user_id_validation_fails(self):
        data = {
            'roll_number': '1002',
            'register_number': 'REG1002',
            'department_id': self.department.id,
            'batch_id': self.batch.id,
            'user_id': self.user1.id,  # Duplicate user_id!
            'status_id': self.status.id
        }
        serializer = StudentSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('user_id', serializer.errors)
        self.assertEqual(str(serializer.errors['user_id'][0]), "This user is already assigned to a student.")

    def test_unique_user_id_validation_passes(self):
        data = {
            'roll_number': '1002',
            'register_number': 'REG1002',
            'department_id': self.department.id,
            'batch_id': self.batch.id,
            'user_id': self.user2.id,  # Unique user_id
            'status_id': self.status.id
        }
        serializer = StudentSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)


from unittest.mock import patch
from django.urls import reverse
from rest_framework.test import APITestCase
from role.models import Role
from users.models import User as StandardUser
from institution.models import ExamType, Exam
from subject.models import Subject
from student.models import Marks

class MarksViewSetTest(APITestCase):
    def setUp(self):
        # Create roles
        self.admin_role = Role.objects.create(role_name="ADMIN")
        self.faculty_role = Role.objects.create(role_name="FACULTY")
        self.student_role = Role.objects.create(role_name="STUDENT")
        
        # Create users
        self.faculty_user = StandardUser.objects.create(
            name="Faculty User",
            username="faculty",
            password="password123",
            mobile_number="1234567890",
            mail="faculty@example.com",
            role=self.faculty_role
        )
        self.student_user = StandardUser.objects.create(
            name="Student User",
            username="student",
            password="password123",
            mobile_number="1234567891",
            mail="student@example.com",
            role=self.student_role
        )

        # Setup standard setup structure
        self.status = StudentStatus.objects.create(status_name="Active")
        self.program = Program.objects.create(
            program_name="Computer Science Engineering",
            program_level="UG",
            duration=4
        )
        self.department = Department.objects.create(
            program=self.program,
            department_name="Computer Science",
            department_code="CSE",
            short_name="CS"
        )
        self.batch = Batch.objects.create(
            department=self.department,
            batch="2022-2026"
        )
        
        # Create student link
        self.app_user = ApplicationUser.objects.create(
            name="Student App User",
            email="studentapp@example.com",
            phone_number="9876543210",
            password="pass"
        )
        self.student = Student.objects.create(
            roll_number="1001",
            register_number="REG1001",
            department=self.department,
            batch=self.batch,
            user=self.app_user,
            status=self.status
        )

        # Create Exam and Subject
        self.exam_type = ExamType.objects.create(exam_type_name="Internal Assessment")
        self.exam = Exam.objects.create(exam_name="IA 1", exam_type=self.exam_type)
        from institution.models import Regulation
        self.regulation = Regulation.objects.create(regulation_code="R2024", effective_from_year=2024)
        from institution.models import Semester
        self.semester = Semester.objects.create(department=self.department, semesters=[1, 2])
        self.subject = Subject.objects.create(
            subject_code="CS301",
            subject_name="Data Structures",
            credits=3,
            regulation=self.regulation,
            department=self.department,
            semester=self.semester
        )

    def test_marks_create_unauthenticated_fails(self):
        url = reverse('marks-create')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_marks_create_unauthorized_role_fails(self):
        # Authenticate as student
        self.client.force_authenticate(user=self.student_user)
        url = reverse('marks-create')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, 403)

    @patch('channels.layers.get_channel_layer')
    def test_marks_create_success(self, mock_channel_layer):
        # Authenticate as faculty
        self.client.force_authenticate(user=self.faculty_user)
        
        payload = {
            "exam_id": self.exam.id,
            "subject_id": self.subject.id,
            "marks_entries": [
                {
                    "student_id": self.student.id,
                    "marks_obtained": "A+"
                }
            ]
        }
        
        url = reverse('marks-create')
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['data'][0]['marks_obtained'], "A+")
        
        # Verify db persistence
        self.assertTrue(Marks.objects.filter(student=self.student, exam=self.exam, subject=self.subject, marks_obtained="A+").exists())

    def test_marks_list_unauthenticated_fails(self):
        url = reverse('marks-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_marks_list_authenticated_success(self):
        self.client.force_authenticate(user=self.student_user)
        url = reverse('marks-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_marks_create_duplicate_in_payload_fails(self):
        # Authenticate as faculty
        self.client.force_authenticate(user=self.faculty_user)
        payload = {
            "exam_id": self.exam.id,
            "subject_id": self.subject.id,
            "marks_entries": [
                {"student_id": self.student.id, "marks_obtained": "85"},
                {"student_id": self.student.id, "marks_obtained": "A+"}
            ]
        }
        url = reverse('marks-create')
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("Duplicate student entry with ID", response.data['message'])

    def test_marks_create_existing_db_record_fails(self):
        # Create an existing record
        Marks.objects.create(
            student=self.student,
            exam=self.exam,
            subject=self.subject,
            marks_obtained="B"
        )
        # Authenticate as faculty
        self.client.force_authenticate(user=self.faculty_user)
        payload = {
            "exam_id": self.exam.id,
            "subject_id": self.subject.id,
            "marks_entries": [
                {"student_id": self.student.id, "marks_obtained": "A"}
            ]
        }
        url = reverse('marks-create')
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("Marks record already exists for student ID", response.data['message'])

    def test_marks_retrieve_by_student_id_success(self):
        # Create a record for student
        mark = Marks.objects.create(
            student=self.student,
            exam=self.exam,
            subject=self.subject,
            marks_obtained="A+"
        )
        self.client.force_authenticate(user=self.student_user)
        url = reverse('marks-detail', kwargs={'pk': self.student.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data'][0]['marks_obtained'], "A+")
        self.assertEqual(response.data['data'][0]['student_id'], self.student.id)


class CounsellingReportViewSetTest(APITestCase):
    def setUp(self):
        # Create roles
        self.admin_role = Role.objects.create(role_name="ADMIN")
        self.faculty_role = Role.objects.create(role_name="FACULTY")
        self.student_role = Role.objects.create(role_name="STUDENT")
        
        # Create users
        self.faculty_user = StandardUser.objects.create(
            name="Faculty User",
            username="faculty",
            password="password123",
            mobile_number="1234567890",
            mail="faculty@example.com",
            role=self.faculty_role
        )
        self.student_user = StandardUser.objects.create(
            name="Student User",
            username="student",
            password="password123",
            mobile_number="1234567891",
            mail="student@example.com",
            role=self.student_role
        )

        # Setup student structure
        self.status = StudentStatus.objects.create(status_name="Active")
        self.program = Program.objects.create(
            program_name="Computer Science Engineering",
            program_level="UG",
            duration=4
        )
        self.department = Department.objects.create(
            program=self.program,
            department_name="Computer Science",
            department_code="CSE",
            short_name="CS"
        )
        self.batch = Batch.objects.create(
            department=self.department,
            batch="2022-2026"
        )
        self.app_user = ApplicationUser.objects.create(
            name="Student App User",
            email="studentapp@example.com",
            phone_number="9876543210",
            password="pass"
        )
        self.student = Student.objects.create(
            roll_number="1001",
            register_number="REG1001",
            department=self.department,
            batch=self.batch,
            user=self.app_user,
            status=self.status
        )

        # Create Semester
        from institution.models import Semester
        self.semester = Semester.objects.create(department=self.department, semesters=[1, 2])

    def test_counselling_create_unauthenticated_fails(self):
        url = reverse('counselling-create')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_counselling_create_unauthorized_role_fails(self):
        # Authenticate as student
        self.client.force_authenticate(user=self.student_user)
        url = reverse('counselling-create')
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, 403)

    @patch('channels.layers.get_channel_layer')
    def test_counselling_create_success(self, mock_channel_layer):
        # Authenticate as faculty
        self.client.force_authenticate(user=self.faculty_user)
        
        payload = {
            "student_id": self.student.id,
            "semester_id": self.semester.id,
            "report_date": "2026-08-07",
            "remarks": "Excellent academic performance."
        }
        
        url = reverse('counselling-create')
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['data']['remarks'], "Excellent academic performance.")
        
        # Verify db persistence
        self.assertTrue(CounsellingReport.objects.filter(student=self.student, semester=self.semester, report_date="2026-08-07").exists())

    def test_counselling_list_authenticated_success(self):
        # Create counselling report
        CounsellingReport.objects.create(
            student=self.student,
            semester=self.semester,
            report_date="2026-08-07",
            remarks="Participative"
        )
        self.client.force_authenticate(user=self.student_user)
        url = reverse('counselling-list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['data']), 1)


class StudentBulkImportTest(APITestCase):
    def setUp(self):
        from role.models import Role
        from users.models import User as StandardUser
        from institution.models import Quota

        # Create roles and admin user
        self.admin_role, _ = Role.objects.get_or_create(role_name="ADMIN")
        self.admin_user = StandardUser.objects.create(
            name="Admin User",
            username="admin_import_test",
            password="password123",
            mobile_number="9998887770",
            mail="admin_import@example.com",
            role=self.admin_role
        )
        
        # Create setup structure
        self.status, _ = StudentStatus.objects.get_or_create(status_name="Active")
        self.program = Program.objects.create(
            program_name="Computer Science Engineering",
            program_level="UG",
            duration=4
        )
        self.department = Department.objects.create(
            program=self.program,
            department_name="Computer Science",
            department_code="CSE",
            short_name="CS"
        )
        self.batch = Batch.objects.create(
            department=self.department,
            batch="2022-2026"
        )
        self.quota = Quota.objects.create(quota_name="Government")

    def test_bulk_import_unauthenticated_fails(self):
        url = reverse('student-bulk-import')
        response = self.client.post(url, {"students": []}, format='json')
        self.assertEqual(response.status_code, 401)

    @patch('channels.layers.get_channel_layer')
    def test_bulk_import_success(self, mock_channel_layer):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "students": [
                {
                    "s_no": 1,
                    "name": "Jane Doe",
                    "email": "janedoe@example.com",
                    "phone_number": "9876543211",
                    "roll_number": "1002",
                    "register_number": "REG1002",
                    "department": "CSE",
                    "batch": "2022-2026",
                    "section": "",
                    "quota": "Government",
                    "lab_batch": "3",
                    "is_hostler": "No",
                    "is_day_scholar": "Yes",
                    "is_bus": "No",
                    "bus_from": "",
                    "bus_to": ""
                }
            ]
        }
        
        url = reverse('student-bulk-import')
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['code'], 201)
        self.assertEqual(response.data['data']['count'], 1)

        # Verify database entities created
        from dynamic_forms.models import Application, ApplicationUser
        self.assertTrue(ApplicationUser.objects.filter(email="janedoe@example.com").exists())
        app_user = ApplicationUser.objects.get(email="janedoe@example.com")
        self.assertEqual(app_user.name, "Jane Doe")
        
        self.assertTrue(Application.objects.filter(candidate=app_user).exists())
        app = Application.objects.get(candidate=app_user)
        self.assertEqual(app.status.status_name, "Approved")
        
        self.assertTrue(Student.objects.filter(user=app_user).exists())
        student = Student.objects.get(user=app_user)
        self.assertEqual(student.roll_number, "1002")
        self.assertEqual(student.register_number, "REG1002")
        self.assertEqual(student.quota, self.quota)
        self.assertEqual(student.is_day_scholar, True)
        self.assertEqual(student.is_hostler, False)

    def test_bulk_import_validation_errors(self):
        self.client.force_authenticate(user=self.admin_user)
        # Test missing email/phone and invalid format
        payload = {
            "students": [
                {
                    "s_no": 1,
                    "name": "Jane Doe",
                    "email": "invalid_email",
                    "phone_number": "123",
                    "roll_number": "1002",
                    "register_number": "REG1002",
                    "department": "CSE",
                    "batch": "2022-2026",
                }
            ]
        }
        url = reverse('student-bulk-import')
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("errors", response.data)
        self.assertTrue(len(response.data['errors']) > 0)
        
        # Verify no database entities were created
        from dynamic_forms.models import ApplicationUser
        self.assertFalse(ApplicationUser.objects.filter(name="Jane Doe").exists())





