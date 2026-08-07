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


from unittest.mock import patch
from django.urls import reverse
from rest_framework.test import APITestCase
from django.core.files.uploadedfile import SimpleUploadedFile

class DocumentUploadAndApplicationTest(APITestCase):
    def setUp(self):
        # Create form modules
        self.personal_module = FormModule.objects.create(
            module_name="Personal Information",
            module_key="personal_information",
            display_order=1
        )
        self.course_module = FormModule.objects.create(
            module_name="Course Selection",
            module_key="course_selection",
            display_order=2
        )
        
        # Create fields
        self.applicant_name_field = FormField.objects.create(
            form_module=self.personal_module,
            field_key="applicant_name",
            field_label="Applicant Name",
            field_type="text",
            required=True
        )
        self.photo_field = FormField.objects.create(
            form_module=self.personal_module,
            field_key="photo",
            field_label="Passport Photo",
            field_type="file",
            required=True
        )
        self.dept_field = FormField.objects.create(
            form_module=self.course_module,
            field_key="department",
            field_label="Department",
            field_type="select",
            required=True
        )
        
        # Create programs and departments
        self.program = Program.objects.create(
            program_name="B.Tech CS",
            program_level="UG",
            duration=4
        )
        from institution.models import Department
        self.department = Department.objects.create(
            department_name="Computer Science Engineering",
            department_code="104",
            short_name="CSE",
            program=self.program
        )
        
        # Create user
        self.candidate = ApplicationUser.objects.create(
            name="Alice",
            email="alice@example.com",
            phone_number="9876543210",
            password="password123"
        )
        self.client.force_authenticate(user=self.candidate)

    @patch('common.r2.upload_file_to_r2')
    def test_document_upload_success(self, mock_upload):
        mock_upload.return_value = "https://pub-r2-url.dev/college_headers/mocked_file.jpg"
        
        mock_file = SimpleUploadedFile("photo.jpg", b"file_content", content_type="image/jpeg")
        url = reverse('document-upload')
        response = self.client.post(url, {'file': mock_file, 'docType': 'photo'}, format='multipart')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['data'][0]['file_url'], "https://pub-r2-url.dev/college_headers/mocked_file.jpg")
        mock_upload.assert_called_once()

    @patch('common.r2.upload_file_to_r2')
    def test_document_array_upload_success(self, mock_upload):
        mock_upload.side_effect = [
            "https://pub-r2-url.dev/college_headers/photo.jpg",
            "https://pub-r2-url.dev/college_headers/marksheet.pdf"
        ]
        
        file1 = SimpleUploadedFile("photo.jpg", b"file_content_1", content_type="image/jpeg")
        file2 = SimpleUploadedFile("marksheet.pdf", b"file_content_2", content_type="application/pdf")
        
        url = reverse('document-upload')
        response = self.client.post(
            url, 
            {'files': [file1, file2], 'docType': 'certificates'}, 
            format='multipart'
        )
        
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['data']), 2)
        self.assertEqual(response.data['data'][0]['file_name'], "photo.jpg")
        self.assertEqual(response.data['data'][0]['file_url'], "https://pub-r2-url.dev/college_headers/photo.jpg")
        self.assertEqual(response.data['data'][1]['file_name'], "marksheet.pdf")
        self.assertEqual(response.data['data'][1]['file_url'], "https://pub-r2-url.dev/college_headers/marksheet.pdf")
        self.assertEqual(mock_upload.call_count, 2)

    def test_application_create_with_auto_derived_program(self):
        payload = {
            "form_data": {
                "personal_information": {
                    "applicant_name": "Alice Green",
                    "photo": "https://pub-r2-url.dev/college_headers/mocked_file.jpg"
                },
                "course_selection": {
                    "department": "Computer Science Engineering"
                }
            }
        }
        
        # Send create request
        url = reverse('application-create')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.data['data']['application_no'])
        self.assertEqual(response.data['data']['program_id'], self.program.id)

    def test_application_create_with_multiple_derived_programs(self):
        payload = {
            "form_data": {
                "personal_information": {
                    "applicant_name": "Alice Green",
                    "photo": "https://pub-r2-url.dev/college_headers/mocked_file.jpg"
                },
                "course_selection": {
                    "department": ["Computer Science Engineering", "Information Technology"]
                }
            }
        }
        
        # Send create request
        url = reverse('application-create')
        response = self.client.post(url, payload, format='json')
        
        self.assertEqual(response.status_code, 201)
        self.assertIsNotNone(response.data['data']['application_no'])
        self.assertEqual(response.data['data']['program_id'], self.program.id)


