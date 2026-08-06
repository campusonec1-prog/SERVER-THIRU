from django.test import TestCase
from student.models import Student, StudentStatus
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
