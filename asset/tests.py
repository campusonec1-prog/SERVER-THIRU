from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from role.models import Role
from users.models import User
from asset.models import AssetCategory


class AssetCategoryTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create roles
        self.admin_role, _ = Role.objects.get_or_create(role_name='Admin')
        self.student_role, _ = Role.objects.get_or_create(role_name='Student')

        # Create admin user
        self.admin_user = User.objects.create(
            name='Admin User',
            username='admin_test',
            mail='admin@test.com',
            mobile_number='9876543210',
            password='Password123!',
            role=self.admin_role
        )

        # Create regular student user
        self.student_user = User.objects.create(
            name='Student User',
            username='student_test',
            mail='student@test.com',
            mobile_number='9876543211',
            password='Password123!',
            role=self.student_role
        )

        # Authenticate as admin by default
        self.client.force_authenticate(user=self.admin_user)

    def test_create_category_success(self):
        url = '/api/asset-categories/create'
        payload = {
            'name': '  Computer Hardware  ',
            'description': 'Laptops, Monitors, Keyboards',
            'is_active': True
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 201)
        self.assertIn('created successfully', response.data['message'].lower())
        self.assertEqual(response.data['data']['name'], 'Computer Hardware')

        # Verify DB entry
        category = AssetCategory.objects.get(id=response.data['data']['id'])
        self.assertEqual(category.name, 'Computer Hardware')

    def test_create_duplicate_category_fails(self):
        AssetCategory.objects.create(name='Electronics')
        url = '/api/asset-categories/create'
        payload = {'name': 'electronics'}  # case-insensitive duplicate check
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_name_fails(self):
        url = '/api/asset-categories/create'
        payload = {'name': ''}
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_whitespace_only_name_fails(self):
        url = '/api/asset-categories/create'
        payload = {'name': '     '}
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_name_exceeds_100_chars_fails(self):
        url = '/api/asset-categories/create'
        payload = {'name': 'A' * 101}
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_category_success(self):
        cat = AssetCategory.objects.create(name='Furniture', description='Old desc')
        url = f'/api/asset-categories/edit/{cat.id}'
        payload = {'name': 'Office Furniture', 'description': 'New desc', 'is_active': True}
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], 'Office Furniture')
        self.assertEqual(response.data['data']['description'], 'New desc')

    def test_update_to_duplicate_name_fails(self):
        AssetCategory.objects.create(name='Lab Equipment')
        cat2 = AssetCategory.objects.create(name='Stationery')
        url = f'/api/asset-categories/edit/{cat2.id}'
        payload = {'name': 'Lab Equipment'}
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_toggle_status_activate_deactivate(self):
        cat = AssetCategory.objects.create(name='Vehicles', is_active=True)
        url = f'/api/asset-categories/toggle-status/{cat.id}'

        # Deactivate
        response = self.client.patch(url, {'is_active': False}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['data']['is_active'])
        self.assertIn('deactivated', response.data['message'])

        # Activate
        response = self.client.patch(url, {'is_active': True}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['data']['is_active'])
        self.assertIn('activated', response.data['message'])

    def test_get_category_detail(self):
        cat = AssetCategory.objects.create(name='Network Devices')
        url = f'/api/asset-categories/get/{cat.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['name'], 'Network Devices')

    def test_missing_category_returns_404(self):
        url = '/api/asset-categories/get/999999'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['code'], 404)

    def test_pagination(self):
        for i in range(15):
            AssetCategory.objects.create(name=f'Category {i+1}')
        
        url = '/api/asset-categories/list?page=1&page_size=10'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['count'], 15)
        self.assertEqual(len(response.data['data']['results']), 10)

    def test_search(self):
        AssetCategory.objects.create(name='Projectors', description='Classroom display')
        AssetCategory.objects.create(name='Air Conditioners', description='HVAC unit')

        url = '/api/asset-categories/list?search=Classroom'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['name'], 'Projectors')

    def test_active_inactive_filtering(self):
        AssetCategory.objects.create(name='Active Item', is_active=True)
        AssetCategory.objects.create(name='Inactive Item', is_active=False)

        # Active filter
        response = self.client.get('/api/asset-categories/list?is_active=true')
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['name'], 'Active Item')

        # Inactive filter
        response = self.client.get('/api/asset-categories/list?is_active=false')
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['name'], 'Inactive Item')

    def test_permission_unauthenticated(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/asset-categories/list')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
