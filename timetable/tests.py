from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from role.models import Role
from users.models import User as StandardUser
from schedule.models import Session
from institution.models import AcademicYear, Batch, Department, ExamType, Exam, Section, Semester
from timetable.models import ExamTimetable
from subject.models import Subject
from unittest.mock import patch

class ExamTimetableAPITests(APITestCase):
    def setUp(self):
        # 1. Setup Roles
        self.admin_role, _ = Role.objects.get_or_create(role_name="ADMIN")
        self.hod_role, _ = Role.objects.get_or_create(role_name="HOD")
        self.exam_cell_role, _ = Role.objects.get_or_create(role_name="EXAM_CELL_MEMBER")
        self.student_role, _ = Role.objects.get_or_create(role_name="STUDENT")
        
        # 2. Setup Users
        self.admin_user = StandardUser.objects.create(
            name="Admin User", username="admin", password="adminpassword",
            mobile_number="1234567890", mail="admin@example.com", role=self.admin_role
        )
        self.hod_user = StandardUser.objects.create(
            name="HOD User", username="hod", password="hodpassword",
            mobile_number="1234567891", mail="hod@example.com", role=self.hod_role
        )
        self.exam_cell_user = StandardUser.objects.create(
            name="Exam Cell User", username="examcell", password="cellpassword",
            mobile_number="1234567892", mail="cell@example.com", role=self.exam_cell_role
        )
        self.student_user = StandardUser.objects.create(
            name="Student User", username="student", password="studentpassword",
            mobile_number="9876543210", mail="student@example.com", role=self.student_role
        )
        
        # 3. Setup Models
        # Active Academic Year
        self.active_academic_year = AcademicYear.objects.create(
            academic_year="2025-2026",
            is_active=True
        )
        # Inactive Academic Year
        self.inactive_academic_year = AcademicYear.objects.create(
            academic_year="2024-2025",
            is_active=False
        )
        
        # Session
        self.session_morning = Session.objects.create(session_name="Forenoon")
        
        # Program and Department
        from institution.models import Program
        self.program = Program.objects.create(program_name="Engineering", program_level="UG", duration=4)
        self.department = Department.objects.create(
            program=self.program,
            department_name="Computer Science",
            department_code="CSE",
            short_name="CS"
        )
        
        # Batch
        self.batch = Batch.objects.create(
            department=self.department,
            batch="2022-2026"
        )
        
        # Exam
        self.exam_type = ExamType.objects.create(exam_type_name="Semester Exam")
        self.exam = Exam.objects.create(exam_name="End Semester Nov 2026", exam_type=self.exam_type)
        
        # Section and Semester
        self.section = Section.objects.create(department=self.department, sections=["A", "B"])
        self.semester = Semester.objects.create(department=self.department, semesters=[1, 2, 3])
        
        # Create URLs
        self.list_url = reverse('timetable-list')
        self.create_url = reverse('timetable-create')
        
    def test_list_and_retrieve_unauthenticated_fails(self):
        # No authentication should return 401 for GET operations
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.data['code'], 401)

    def test_list_and_retrieve_authenticated_success(self):
        # Create a record
        timetable_entry = ExamTimetable.objects.create(
            exam_date="2026-10-15", session=self.session_morning,
            start_time="09:30:00", end_time="12:30:00",
            academic_year=self.active_academic_year, batch=self.batch,
            department=self.department, exam=self.exam,
            section=self.section, semester=self.semester
        )
        
        # Authenticate as student
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)
        
        detail_url = reverse('timetable-detail', kwargs={'pk': timetable_entry.id})
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['exam_date'], "2026-10-15")

    @patch('channels.layers.get_channel_layer')
    def test_create_single_success_as_admin(self, mock_get_channel_layer):
        mock_channel_layer = mock_get_channel_layer.return_value
        self.client.force_authenticate(user=self.admin_user)
        
        payload = {
            "exam_date": "2026-11-20",
            "session_id": self.session_morning.id,
            "start_time": "10:00:00",
            "end_time": "13:00:00",
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 201)
        self.assertTrue(ExamTimetable.objects.filter(exam_date="2026-11-20").exists())
        self.assertTrue(mock_channel_layer.group_send.called)

    def test_create_single_success_as_hod(self):
        self.client.force_authenticate(user=self.hod_user)
        payload = {
            "exam_date": "2026-11-20",
            "session_id": self.session_morning.id,
            "start_time": "10:00:00",
            "end_time": "13:00:00",
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_single_success_as_exam_cell(self):
        self.client.force_authenticate(user=self.exam_cell_user)
        payload = {
            "exam_date": "2026-11-20",
            "session_id": self.session_morning.id,
            "start_time": "10:00:00",
            "end_time": "13:00:00",
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_create_unauthorized_for_students(self):
        self.client.force_authenticate(user=self.student_user)
        payload = {
            "exam_date": "2026-11-20",
            "session_id": self.session_morning.id,
            "start_time": "10:00:00",
            "end_time": "13:00:00",
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('channels.layers.get_channel_layer')
    def test_create_bulk_success(self, mock_get_channel_layer):
        mock_channel_layer = mock_get_channel_layer.return_value
        self.client.force_authenticate(user=self.admin_user)
        payload = [
            {
                "exam_date": "2026-11-21",
                "session_id": self.session_morning.id,
                "start_time": "10:00:00",
                "end_time": "13:00:00",
                "academic_year_id": self.active_academic_year.id,
                "batch_id": self.batch.id,
                "department_id": self.department.id,
                "exam_id": self.exam.id,
                "section_id": self.section.id,
                "semester_id": self.semester.id
            },
            {
                "exam_date": "2026-11-22",
                "session_id": self.session_morning.id,
                "start_time": "14:00:00",
                "end_time": "17:00:00",
                "academic_year_id": self.active_academic_year.id,
                "batch_id": self.batch.id,
                "department_id": self.department.id,
                "exam_id": self.exam.id,
                "section_id": self.section.id,
                "semester_id": self.semester.id
            }
        ]
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data['data']), 2)
        self.assertTrue(ExamTimetable.objects.filter(exam_date="2026-11-21").exists())
        self.assertTrue(ExamTimetable.objects.filter(exam_date="2026-11-22").exists())
        self.assertTrue(mock_channel_layer.group_send.called)

    def test_active_academic_year_validation(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "exam_date": "2026-11-20",
            "session_id": self.session_morning.id,
            "start_time": "10:00:00",
            "end_time": "13:00:00",
            "academic_year_id": self.inactive_academic_year.id, # Inactive year!
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 400)
        self.assertEqual(response.data['message'], "Academic year does not exist or is not active.")

    def test_start_end_time_validation(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            "exam_date": "2026-11-20",
            "session_id": self.session_morning.id,
            "start_time": "14:00:00",
            "end_time": "12:00:00", # End time before start time!
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['code'], 400)
        self.assertEqual(response.data['message'], "End time must be after the start time.")

    @patch('channels.layers.get_channel_layer')
    def test_update_and_delete_as_admin(self, mock_get_channel_layer):
        mock_channel_layer = mock_get_channel_layer.return_value
        
        # Create first
        timetable_entry = ExamTimetable.objects.create(
            exam_date="2026-10-15", session=self.session_morning,
            start_time="09:30:00", end_time="12:30:00",
            academic_year=self.active_academic_year, batch=self.batch,
            department=self.department, exam=self.exam,
            section=self.section, semester=self.semester
        )
        
        self.client.force_authenticate(user=self.admin_user)
        edit_url = reverse('timetable-edit', kwargs={'pk': timetable_entry.id})
        
        # Test Put Update
        response = self.client.put(edit_url, {
            "exam_date": "2026-10-25",
            "session_id": self.session_morning.id,
            "start_time": "09:30:00",
            "end_time": "12:30:00",
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        timetable_entry.refresh_from_db()
        self.assertEqual(str(timetable_entry.exam_date), "2026-10-25")
        self.assertTrue(mock_channel_layer.group_send.called)
        
        # Reset mock
        mock_channel_layer.group_send.reset_mock()
        
        # Test Delete
        remove_url = reverse('timetable-remove', kwargs={'pk': timetable_entry.id})
        response = self.client.delete(remove_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(ExamTimetable.objects.filter(id=timetable_entry.id).exists())
        self.assertTrue(mock_channel_layer.group_send.called)

    @patch('channels.layers.get_channel_layer')
    def test_create_nested_payload_success(self, mock_get_channel_layer):
        mock_channel_layer = mock_get_channel_layer.return_value
        self.client.force_authenticate(user=self.admin_user)
        
        payload = {
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id,
            "exams": [
                {
                    "exam_date": "2026-10-25",
                    "session_id": self.session_morning.id,
                    "start_time": "09:30:00",
                    "end_time": "12:30:00"
                }
            ]
        }
        
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 201)
        self.assertTrue(ExamTimetable.objects.filter(exam_date="2026-10-25", academic_year=self.active_academic_year).exists())
        self.assertTrue(mock_channel_layer.group_send.called)

    @patch('channels.layers.get_channel_layer')
    def test_create_nested_payload_with_custom_date_format_success(self, mock_get_channel_layer):
        mock_channel_layer = mock_get_channel_layer.return_value
        self.client.force_authenticate(user=self.admin_user)
        
        payload = {
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id,
            "exams": [
                {
                    "exam_date": "25-10-2026", # DD-MM-YYYY format
                    "session_id": self.session_morning.id,
                    "start_time": "09:30:00",
                    "end_time": "12:30:00"
                }
            ]
        }
        
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 201)
        self.assertTrue(ExamTimetable.objects.filter(exam_date="2026-10-25", academic_year=self.active_academic_year).exists())
        self.assertTrue(mock_channel_layer.group_send.called)

    @patch('channels.layers.get_channel_layer')
    def test_update_nested_payload_success(self, mock_get_channel_layer):
        mock_channel_layer = mock_get_channel_layer.return_value
        
        # Create first
        timetable_entry = ExamTimetable.objects.create(
            exam_date="2026-10-15", session=self.session_morning,
            start_time="09:30:00", end_time="12:30:00",
            academic_year=self.active_academic_year, batch=self.batch,
            department=self.department, exam=self.exam,
            section=self.section, semester=self.semester
        )
        
        self.client.force_authenticate(user=self.admin_user)
        edit_url = reverse('timetable-edit', kwargs={'pk': timetable_entry.id})
        
        # Update using nested payload format and DD-MM-YYYY date format
        payload = {
            "academic_year_id": self.active_academic_year.id,
            "batch_id": self.batch.id,
            "department_id": self.department.id,
            "exam_id": self.exam.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id,
            "exams": [
                {
                    "exam_date": "26-10-2026", # DD-MM-YYYY format
                    "session_id": self.session_morning.id,
                    "start_time": "09:30:00",
                    "end_time": "12:30:00"
                }
            ]
        }
        
        response = self.client.put(edit_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        timetable_entry.refresh_from_db()
        self.assertEqual(str(timetable_entry.exam_date), "2026-10-26")
        self.assertTrue(mock_channel_layer.group_send.called)


from timetable.models import ClassTimetable
from schedule.models import Day, Period

class ClassTimetableAPITests(APITestCase):
    def setUp(self):
        # 1. Setup Roles
        self.admin_role, _ = Role.objects.get_or_create(role_name="ADMIN")
        self.hod_role, _ = Role.objects.get_or_create(role_name="HOD")
        self.student_role, _ = Role.objects.get_or_create(role_name="STUDENT")
        
        # 2. Setup Users
        self.admin_user = StandardUser.objects.create(
            name="Admin User", username="admin2", password="adminpassword",
            mobile_number="1234567895", mail="admin2@example.com", role=self.admin_role
        )
        self.hod_user = StandardUser.objects.create(
            name="HOD User", username="hod2", password="hodpassword",
            mobile_number="1234567896", mail="hod2@example.com", role=self.hod_role
        )
        self.student_user = StandardUser.objects.create(
            name="Student User", username="student2", password="studentpassword",
            mobile_number="9876543212", mail="student2@example.com", role=self.student_role
        )
        
        # 3. Setup Models
        self.active_academic_year = AcademicYear.objects.create(
            academic_year="2026-2027",
            is_active=True
        )
        self.session = Session.objects.create(session_name="Class Session")
        self.day_mon = Day.objects.create(day_name="Monday", day_code="MON")
        self.period_1 = Period.objects.create(period_no=1, session=self.session, start_time="09:00:00", end_time="09:50:00")
        
        from institution.models import Program, Regulation
        self.program = Program.objects.create(program_name="Arts", program_level="UG", duration=3)
        self.regulation = Regulation.objects.create(regulation_code="R2026")
        self.department = Department.objects.create(
            program=self.program,
            department_name="English Literature",
            department_code="ENG",
            short_name="EN"
        )
        self.batch = Batch.objects.create(department=self.department, batch="2024-2027")
        self.section = Section.objects.create(department=self.department, sections=["A"])
        self.semester = Semester.objects.create(department=self.department, semesters=[1, 2])
        
        from subject.models import Subject
        self.subject = Subject.objects.create(
            subject_name="Poetry", subject_code="ENG101",
            department=self.department, semester=self.semester,
            regulation=self.regulation, credits=3.0
        )
        
        # URLs
        self.list_url = reverse('class-timetable-list')
        self.create_url = reverse('class-timetable-create')

    def test_list_unauthenticated_fails(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_authenticated_success(self):
        ClassTimetable.objects.create(
            academic_year=self.active_academic_year, day=self.day_mon, period=self.period_1,
            department=self.department, faculty=self.hod_user, section=self.section,
            semester=self.semester, subject=self.subject, batch=self.batch,
            is_lab=False, room_no="Room 303"
        )
        self.client.force_authenticate(user=self.student_user)
        response = self.client.get(self.list_url + '?pagination=false')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']), 1)

    def test_create_unauthorized_for_students(self):
        self.client.force_authenticate(user=self.student_user)
        payload = {
            "academic_year_id": self.active_academic_year.id,
            "day_id": self.day_mon.id,
            "period_id": self.period_1.id,
            "department_id": self.department.id,
            "faculty_id": self.hod_user.id,
            "section_id": self.section.id,
            "semester_id": self.semester.id,
            "subject_id": self.subject.id,
            "batch_id": self.batch.id,
            "room_no": "Room 303"
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('channels.layers.get_channel_layer')
    def test_create_weekly_timetable_bulk_success_as_hod(self, mock_get_channel_layer):
        mock_channel_layer = mock_get_channel_layer.return_value
        self.client.force_authenticate(user=self.hod_user)
        
        payload = {
            "academic_year_id": self.active_academic_year.id,
            "department_id": self.department.id,
            "batch_id": self.batch.id,
            "semester_id": self.semester.id,
            "section_id": self.section.id,
            "class_timetables": [
                {
                    "day_id": self.day_mon.id,
                    "period_id": self.period_1.id,
                    "subject_id": self.subject.id,
                    "faculty_id": self.hod_user.id,
                    "is_lab": True,
                    "room_no": "Room 305"
                }
            ]
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(ClassTimetable.objects.filter(room_no="Room 305", is_lab=True).exists())
        self.assertTrue(mock_channel_layer.group_send.called)

    @patch('channels.layers.get_channel_layer')
    def test_create_weekly_timetable_faculty_conflict_fails(self, mock_get_channel_layer):
        """Faculty already assigned to same period in another dept should be rejected with server message."""
        mock_get_channel_layer.return_value
        from institution.models import Program, Regulation

        # Create a second department/batch/section/semester/subject to represent another class
        program2 = Program.objects.create(program_name="Science", program_level="UG", duration=3)
        regulation2 = Regulation.objects.create(regulation_code="R2027")
        dept2 = Department.objects.create(
            program=program2,
            department_name="Physics",
            department_code="PHY",
            short_name="PH"
        )
        batch2 = Batch.objects.create(department=dept2, batch="2024-2027")
        section2 = Section.objects.create(department=dept2, sections=["B"])
        semester2 = Semester.objects.create(department=dept2, semesters=[1, 2])
        subject2 = Subject.objects.create(
            subject_name="Mechanics", subject_code="PHY101",
            department=dept2, semester=semester2,
            regulation=regulation2, credits=3.0
        )

        # Pre-assign hod_user to Monday Period 1 for dept2 (a DIFFERENT class)
        ClassTimetable.objects.create(
            academic_year=self.active_academic_year,
            day=self.day_mon,
            period=self.period_1,
            department=dept2,
            faculty=self.hod_user,
            section=section2,
            semester=semester2,
            subject=subject2,
            batch=batch2,
            is_lab=False,
        )

        # Now try to assign the same hod_user to Monday Period 1 for dept1 (conflict!)
        self.client.force_authenticate(user=self.hod_user)
        payload = {
            "academic_year_id": self.active_academic_year.id,
            "department_id": self.department.id,
            "batch_id": self.batch.id,
            "semester_id": self.semester.id,
            "section_id": self.section.id,
            "class_timetables": [
                {
                    "day_id": self.day_mon.id,
                    "period_id": self.period_1.id,
                    "subject_id": self.subject.id,
                    "faculty_id": self.hod_user.id,
                    "is_lab": False,
                    "room_no": "Room 101"
                }
            ]
        }
        response = self.client.post(self.create_url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The error message must come from the server and mention the faculty
        message = response.data.get('message', '')
        self.assertIn("HOD User", message)
        self.assertIn("Monday", message)
        self.assertIn("Period 1", message)
