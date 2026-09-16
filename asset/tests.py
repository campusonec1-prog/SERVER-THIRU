from datetime import date, timedelta
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from role.models import Role
from users.models import User
from asset.models import AssetCategory, Asset, AssetCondition, AssetStatus


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


class AssetTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create role & admin user
        self.admin_role, _ = Role.objects.get_or_create(role_name='Admin')
        self.admin_user = User.objects.create(
            name='Asset Admin',
            username='asset_admin',
            mail='asset_admin@test.com',
            mobile_number='9876543220',
            password='Password123!',
            role=self.admin_role
        )

        self.client.force_authenticate(user=self.admin_user)

        # Create active and inactive categories
        self.active_category = AssetCategory.objects.create(name='Computers', is_active=True)
        self.inactive_category = AssetCategory.objects.create(name='Obsolete Items', is_active=False)

    def test_create_asset_success(self):
        url = '/api/assets/create'
        payload = {
            'asset_code': ' AST-001 ',
            'asset_name': ' Dell XPS Laptop ',
            'category': self.active_category.id,
            'brand': 'Dell',
            'model_number': 'XPS 15',
            'serial_number': 'SN-12345678',
            'purchase_date': '2026-01-15',
            'purchase_price': '1500.00',
            'condition': AssetCondition.NEW,
            'status': AssetStatus.AVAILABLE,
            'location': 'Lab 101'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 201)
        self.assertEqual(response.data['data']['asset_code'], 'AST-001')
        self.assertEqual(response.data['data']['asset_name'], 'Dell XPS Laptop')
        self.assertEqual(response.data['data']['category_name'], 'Computers')

    def test_create_duplicate_asset_code_fails(self):
        Asset.objects.create(
            asset_code='AST-002',
            asset_name='Existing Laptop',
            category=self.active_category
        )
        url = '/api/assets/create'
        payload = {
            'asset_code': 'ast-002',  # case-insensitive check
            'asset_name': 'Another Laptop',
            'category': self.active_category.id
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_duplicate_serial_number_fails(self):
        Asset.objects.create(
            asset_code='AST-003',
            asset_name='Existing Laptop',
            category=self.active_category,
            serial_number='SN-DUP-100'
        )
        url = '/api/assets/create'
        payload = {
            'asset_code': 'AST-004',
            'asset_name': 'New Laptop',
            'category': self.active_category.id,
            'serial_number': 'sn-dup-100'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_empty_blank_serial_number_allowed(self):
        # Multiple assets with blank serial numbers should not collide
        url = '/api/assets/create'
        payload1 = {
            'asset_code': 'AST-005',
            'asset_name': 'Chair 1',
            'category': self.active_category.id,
            'serial_number': '   '
        }
        payload2 = {
            'asset_code': 'AST-006',
            'asset_name': 'Chair 2',
            'category': self.active_category.id,
            'serial_number': ''
        }
        res1 = self.client.post(url, payload1, format='json')
        res2 = self.client.post(url, payload2, format='json')
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(res1.data['data']['serial_number'])
        self.assertIsNone(res2.data['data']['serial_number'])

    def test_inactive_category_creation_fails(self):
        url = '/api/assets/create'
        payload = {
            'asset_code': 'AST-007',
            'asset_name': 'Old Monitor',
            'category': self.inactive_category.id
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_negative_purchase_price_fails(self):
        url = '/api/assets/create'
        payload = {
            'asset_code': 'AST-008',
            'asset_name': 'Desk',
            'category': self.active_category.id,
            'purchase_price': '-50.00'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_warranty_expiry_date_fails(self):
        url = '/api/assets/create'
        payload = {
            'asset_code': 'AST-009',
            'asset_name': 'Printer',
            'category': self.active_category.id,
            'purchase_date': '2026-05-10',
            'warranty_expiry': '2025-05-10'  # earlier than purchase date
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_asset_success(self):
        asset = Asset.objects.create(
            asset_code='AST-010',
            asset_name='Original Name',
            category=self.active_category
        )
        url = f'/api/assets/edit/{asset.id}'
        payload = {
            'asset_code': 'AST-010',
            'asset_name': 'Updated Name',
            'category': self.active_category.id,
            'status': AssetStatus.MAINTENANCE
        }
        response = self.client.put(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['data']['asset_name'], 'Updated Name')
        self.assertEqual(response.data['data']['status'], AssetStatus.MAINTENANCE)

    def test_delete_asset_success(self):
        asset = Asset.objects.create(
            asset_code='AST-011',
            asset_name='Asset To Delete',
            category=self.active_category
        )
        url = f'/api/assets/remove/{asset.id}'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(Asset.objects.filter(id=asset.id).exists())

    def test_delete_category_with_assets_protected_fails(self):
        Asset.objects.create(
            asset_code='AST-012',
            asset_name='Protected Category Asset',
            category=self.active_category
        )
        url = f'/api/asset-categories/remove/{self.active_category.id}'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('associated with it', response.data['message'])

    def test_search_assets(self):
        Asset.objects.create(
            asset_code='AST-100',
            asset_name='MacBook Pro 16',
            brand='Apple',
            category=self.active_category
        )
        Asset.objects.create(
            asset_code='AST-200',
            asset_name='ThinkPad T14',
            brand='Lenovo',
            category=self.active_category
        )

        url = '/api/assets/list?search=MacBook'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['results']), 1)
        self.assertEqual(response.data['data']['results'][0]['asset_code'], 'AST-100')

    def test_filter_assets_by_category_status_condition(self):
        other_category = AssetCategory.objects.create(name='Furniture', is_active=True)
        Asset.objects.create(
            asset_code='AST-300',
            asset_name='Computer 1',
            category=self.active_category,
            status=AssetStatus.AVAILABLE,
            condition=AssetCondition.NEW
        )
        Asset.objects.create(
            asset_code='AST-400',
            asset_name='Desk 1',
            category=other_category,
            status=AssetStatus.DAMAGED,
            condition=AssetCondition.DAMAGED
        )

        # Filter by category
        res1 = self.client.get(f'/api/assets/list?category={self.active_category.id}')
        self.assertEqual(len(res1.data['data']['results']), 1)
        self.assertEqual(res1.data['data']['results'][0]['asset_code'], 'AST-300')

        # Filter by status
        res2 = self.client.get('/api/assets/list?status=damaged')
        self.assertEqual(len(res2.data['data']['results']), 1)
        self.assertEqual(res2.data['data']['results'][0]['asset_code'], 'AST-400')
