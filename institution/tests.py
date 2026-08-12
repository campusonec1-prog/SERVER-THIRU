from django.test import TestCase
from rest_framework.exceptions import ValidationError
from institution.models import AcademicYear, Program, Department, Batch, Regulation, Quota, FeesStructure
from institution.serializers import AcademicYearSerializer, BatchSerializer, RegulationSerializer, QuotaSerializer, FeesStructureSerializer


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


class QuotaModelAndSerializerTest(TestCase):
    def test_quota_creation_success(self):
        data = {
            'quota_name': 'Sports Quota',
            'is_active': True
        }
        serializer = QuotaSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        quota = serializer.save()
        self.assertEqual(quota.quota_name, 'Sports Quota')
        self.assertTrue(quota.is_active)

    def test_quota_validation_empty_name(self):
        data = {
            'quota_name': '   ',
            'is_active': True
        }
        serializer = QuotaSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('quota_name', serializer.errors)
        self.assertEqual(
            str(serializer.errors['quota_name'][0]),
            "Quota name cannot be empty."
        )

    def test_quota_uniqueness(self):
        from institution.models import Quota
        Quota.objects.create(quota_name='Management Quota')
        data = {
            'quota_name': 'Management Quota',
            'is_active': True
        }
        serializer = QuotaSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('quota_name', serializer.errors)
        self.assertEqual(
            str(serializer.errors['quota_name'][0]),
            "This quota already exists."
        )


class FeesStructureModelAndSerializerTest(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            academic_year="2024-2025",
            is_display=True
        )
        self.program = Program.objects.create(
            program_name="Engineering",
            program_level="UG",
            duration=4
        )
        self.dept = Department.objects.create(
            program=self.program,
            department_name="Computer Science",
            department_code="CSE",
            short_name="CS"
        )
        self.batch = Batch.objects.create(
            department=self.dept,
            batch="2024-2028",
            is_active=True
        )
        self.quota = Quota.objects.create(
            quota_name="Government Quota"
        )

    def test_fees_structure_creation_success(self):
        data = {
            'academic_year_id': self.year.id,
            'department_id': self.dept.id,
            'batch_id': self.batch.id,
            'quota_id': self.quota.id,
            'fees': 75000.00
        }
        serializer = FeesStructureSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        fees_struct = serializer.save()
        self.assertEqual(float(fees_struct.fees), 75000.00)
        self.assertEqual(fees_struct.academic_year, self.year)

    def test_fees_structure_invalid_fees(self):
        data = {
            'academic_year_id': self.year.id,
            'department_id': self.dept.id,
            'batch_id': self.batch.id,
            'quota_id': self.quota.id,
            'fees': -100.00
        }
        serializer = FeesStructureSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('fees', serializer.errors)
        self.assertEqual(
            str(serializer.errors['fees'][0]),
            "Fees must be a positive number."
        )

    def test_fees_structure_duplicate_uniqueness(self):
        from institution.models import FeesStructure
        FeesStructure.objects.create(
            academic_year=self.year,
            department=self.dept,
            batch=self.batch,
            quota=self.quota,
            fees=50000.00
        )
        data = {
            'academic_year_id': self.year.id,
            'department_id': self.dept.id,
            'batch_id': self.batch.id,
            'quota_id': self.quota.id,
            'fees': 60000.00
        }
        serializer = FeesStructureSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)
        self.assertEqual(
            str(serializer.errors['non_field_errors'][0]),
            "Fees structure for this academic year, department, batch, and quota already exists."
        )


