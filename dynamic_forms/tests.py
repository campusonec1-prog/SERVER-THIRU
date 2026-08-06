from django.test import TestCase
from dynamic_forms.models import FormModule, FormField, ApplicationStatus, ApplicationUser
from dynamic_forms.serializers import FormModuleSerializer, FormFieldSerializer, ApplicationSerializer
from institution.models import Program


class DynamicFormArrayFieldTest(TestCase):
    def setUp(self):
        self.module = FormModule.objects.create(
            module_name="Academic Performance",
            module_key="academic_performance"
        )
        self.program = Program.objects.create(
            program_name="B.Tech Computer Science",
            program_level="UG",
            duration=4
        )
        self.candidate = ApplicationUser.objects.create(
            name="John Doe",
            email="johndoe@example.com",
            phone_number="9876543210",
            password="password123"
        )
        self.submitted_status = ApplicationStatus.objects.create(status_name="Submitted")

    def test_create_array_form_field_serializer(self):
        data = {
            'form_module_id': self.module.id,
            'field_key': 'semester_marks',
            'field_label': 'Semester Marks',
            'field_type': 'array',
            'required': True,
            'choices': [
                {'key': 'semester', 'label': 'Semester', 'type': 'select', 'options': [1, 2, 3]},
                {'key': 'maximum_marks', 'label': 'Maximum Marks', 'type': 'number', 'required': True},
                {'key': 'obtained_marks', 'label': 'Obtained Marks', 'type': 'number', 'required': True},
                {'key': 'percentage', 'label': 'Percentage', 'type': 'number'}
            ]
        }
        serializer = FormFieldSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        field = serializer.save()
        self.assertIsNotNone(field.id)
        self.assertEqual(field.field_type, 'array')
        self.assertEqual(len(field.choices), 4)

    def test_bulk_create_form_fields_without_static_choices_allowed(self):
        data = [
            {
                "form_module_id": self.module.id,
                "field_key": "program",
                "field_label": "Program",
                "field_type": "radio",
                "choices": ["UG", "PG"],
                "required": True,
                "display_order": 1
            },
            {
                "form_module_id": self.module.id,
                "field_key": "department",
                "field_label": "Department",
                "field_type": "select",
                "required": True,
                "display_order": 2
            }
        ]
        serializer = FormFieldSerializer(data=data, many=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        created_fields = serializer.save()
        self.assertEqual(len(created_fields), 2)
        self.assertIsNotNone(created_fields[0].id)
        self.assertIsNotNone(created_fields[1].id)
        self.assertEqual(created_fields[1].field_type, "select")
        self.assertIsNone(created_fields[1].choices)
