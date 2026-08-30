from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from datetime import date

from users.models import User
from role.models import Role
from institution.models import AcademicYear, Department, Program, Batch, Regulation, Semester, Section

from schedule.models import Day, Period, Session

from subject.models import Subject
from timetable.models import ClassTimetable
from leave.models import LeavePolicy, FacultyLeave, ClassSubstitution, Notification


class LeaveManagementTest(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Roles
        self.role_admin = Role.objects.create(role_name='Admin')
        self.role_faculty = Role.objects.create(role_name='Faculty')
        self.role_hod = Role.objects.create(role_name='HOD')

        # Academic Year
        self.academic_year = AcademicYear.objects.create(
            academic_year='2026-2027',
            start_date=date(2026, 6, 1),
            end_date=date(2027, 5, 31),
            is_active=True,
            is_display=True
        )

        # Program & Department
        self.program = Program.objects.create(program_name='B.Tech CSE', program_level='UG', duration=4)
        
        self.fac_hod_user = User.objects.create(
            name='HOD CSE',
            username='hod_user',
            password='password123',
            mobile_number='9876543210',
            mail='hod@example.com',
            role=self.role_hod
        )

        self.dept_cse = Department.objects.create(
            department_name='Computer Science',
            department_code='CSE',
            short_name='CSE',
            program=self.program,
            hod=self.fac_hod_user
        )

        # Faculty 1 (Applicant)
        self.faculty_1 = User.objects.create(
            name='Faculty One',
            username='fac1',
            password='password123',
            mobile_number='9876543211',
            mail='fac1@example.com',
            role=self.role_faculty
        )

        # Faculty 2 (Substitute)
        self.faculty_2 = User.objects.create(
            name='Faculty Two',
            username='fac2',
            password='password123',
            mobile_number='9876543212',
            mail='fac2@example.com',
            role=self.role_faculty
        )



        # Batch, Regulation, Semester, Section, Subject, Day, Period
        self.batch = Batch.objects.create(department=self.dept_cse, batch='2023-2027')
        self.regulation = Regulation.objects.create(regulation_code='R2024', effective_from_year=2024)
        self.semester = Semester.objects.create(department=self.dept_cse, semesters=[1, 2, 3, 4, 5, 6, 7, 8])
        self.section = Section.objects.create(department=self.dept_cse, sections='A')
        self.subject = Subject.objects.create(subject_code='CS101', subject_name='Data Structures', department=self.dept_cse, regulation=self.regulation, semester=self.semester, credits=3)



        # Session, Day, Period
        self.session = Session.objects.create(session_name='Forenoon')

        self.day_wed = Day.objects.create(day_code='WED', day_name='Wednesday')
        self.period_1 = Period.objects.create(session=self.session, period_no=1, start_time='09:00:00', end_time='09:50:00')


        # Timetable for Faculty 1 on Wednesday P1
        self.timetable = ClassTimetable.objects.create(
            academic_year=self.academic_year,
            day=self.day_wed,
            period=self.period_1,
            department=self.dept_cse,
            faculty=self.faculty_1,
            section=self.section,
            semester=self.semester,
            subject=self.subject,
            batch=self.batch,
            from_date=date(2026, 6, 1)
        )

    def test_leave_policy_creation(self):
        policy = LeavePolicy.objects.create(
            academic_year=self.academic_year,
            total_cl=12,
            total_od=6,
            total_permissions=12
        )
        self.assertEqual(policy.total_cl, 12)

    def test_faculty_leave_and_substitution_response(self):
        self.client.force_authenticate(user=self.faculty_1)

        leave_app = FacultyLeave.objects.create(
            applicant=self.faculty_1,
            department=self.dept_cse,
            academic_year=self.academic_year,
            leave_type='FULL_DAY',
            from_date=date(2026, 9, 2),
            to_date=date(2026, 9, 2),
            total_days=1.0,
            reason='Medical Emergency',
            status='PENDING_SUBSTITUTION'
        )

        sub = ClassSubstitution.objects.create(
            leave_application=leave_app,
            date=date(2026, 9, 2),
            period=self.period_1,
            day=self.day_wed,
            original_faculty=self.faculty_1,
            substitute_faculty=self.faculty_2,
            class_timetable=self.timetable,
            department=self.dept_cse,
            batch=self.batch,
            semester=self.semester,
            section=self.section,
            subject=self.subject,
            status='PENDING'
        )

        notif = Notification.objects.create(
            user=self.faculty_2,
            sender=self.faculty_1,
            title="Substitution Request",
            message="Please substitute for WED P1",
            notification_type='SUBSTITUTION_REQUEST',
            related_substitution=sub,
            related_leave=leave_app
        )

        # Faculty 2 accepts substitution
        self.client.force_authenticate(user=self.faculty_2)
        res = self.client.post(f"/api/leave/substitutions/{sub.id}/respond", {"action": "ACCEPT"})
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        sub.refresh_from_db()
        leave_app.refresh_from_db()
        self.assertEqual(sub.status, 'ACCEPTED')
        self.assertEqual(leave_app.status, 'PENDING_APPROVAL')
