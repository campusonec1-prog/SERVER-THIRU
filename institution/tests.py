from django.test import TestCase
from rest_framework.exceptions import ValidationError
from institution.models import AcademicYear, Program, Department, Batch, Regulation
from institution.serializers import AcademicYearSerializer, BatchSerializer, RegulationSerializer


class AcademicYearIsDisplayTest(TestCase):
    def setUp(self):
        self.year1 = AcademicYear.objects.create(
            academic_year="2024-2025",
            is_display=True
        )

    def test_single_is_display_true_allowed(self):
        self.assertTrue(self.year1.is_display)

    def test_second_is_display_true_validation_fails(self):
        data = {
            'academic_year': '2025-2026',
            'is_display': True
        }
        serializer = AcademicYearSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('is_display', serializer.errors)
        self.assertEqual(
            str(serializer.errors['is_display'][0]),
            "Only one academic year can be set as display."
        )

    def test_second_is_display_false_allowed(self):
        data = {
            'academic_year': '2025-2026',
            'is_display': False
        }
        serializer = AcademicYearSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_update_same_instance_is_display_true_allowed(self):
        data = {
            'academic_year': '2024-2025 UPDATED',
            'is_display': True
        }
        serializer = AcademicYearSerializer(instance=self.year1, data=data, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class BatchDepartmentUniquenessTest(TestCase):
    def setUp(self):
        self.program = Program.objects.create(
            program_name="Computer Science Engineering",
            program_level="UG",
            duration=4
        )
        self.dept1 = Department.objects.create(
            program=self.program,
            department_name="Computer Science",
            department_code="CSE",
            short_name="CS"
        )
        self.dept2 = Department.objects.create(
            program=self.program,
            department_name="Information Technology",
            department_code="IT",
            short_name="IT"
        )
        self.batch1 = Batch.objects.create(
            department=self.dept1,
            batch="2023-2027",
            is_active=True
        )

    def test_duplicate_batch_same_department_fails(self):
        data = {
            'department_id': self.dept1.id,
            'batch': '2023-2027',
            'is_active': True
        }
        serializer = BatchSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('batch', serializer.errors)
        self.assertEqual(
            str(serializer.errors['batch'][0]),
            "This batch already exists for the selected department."
        )

    def test_same_batch_different_department_allowed(self):
        data = {
            'department_id': self.dept2.id,
            'batch': '2023-2027',
            'is_active': True
        }
        serializer = BatchSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)


class RegulationEffectiveFromYearTest(TestCase):
    def test_valid_regulation(self):
        data = {
            'regulation_code': 'R2024',
            'effective_from_year': 2024,
            'is_active': True
        }
        serializer = RegulationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        reg = serializer.save()
        self.assertEqual(reg.effective_from_year, 2024)

    def test_invalid_effective_from_year(self):
        data = {
            'regulation_code': 'R2024',
            'effective_from_year': 0,
            'is_active': True
        }
        serializer = RegulationSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('effective_from_year', serializer.errors)
