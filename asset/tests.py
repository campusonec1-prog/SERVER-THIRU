from datetime import date, timedelta
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from role.models import Role
from users.models import User
from asset.models import AssetCategory, Asset, AssetCondition, AssetStatus, AssetAllocation, AssetTransfer, AssetMaintenance, AssetDisposal, DisposalStatus, DisposalType
from institution.models import Department, Program


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


class AssetAllocationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Create role & admin user
        self.admin_role, _ = Role.objects.get_or_create(role_name='Admin')
        self.admin_user = User.objects.create(
            name='Allocation Admin',
            username='alloc_admin',
            mail='alloc_admin@test.com',
            mobile_number='9876543230',
            password='Password123!',
            role=self.admin_role
        )

        # Create target user to allocate asset to
        self.target_user = User.objects.create(
            name='Target Staff User',
            username='target_staff',
            mail='target_staff@test.com',
            mobile_number='9876543231',
            password='Password123!',
            role=self.admin_role
        )

        # Create program & department
        self.program = Program.objects.create(
            program_name='B.Tech CS',
            program_level='UG',
            duration=4
        )
        self.dept = Department.objects.create(
            department_name='Computer Science',
            department_code='CSE',
            short_name='CS',
            program=self.program
        )

        # Authenticate admin
        self.client.force_authenticate(user=self.admin_user)

        # Create category and available asset
        self.category = AssetCategory.objects.create(name='Hardware', is_active=True)
        self.asset = Asset.objects.create(
            asset_code='AST-ALLOC-01',
            asset_name='Dell Workstation',
            category=self.category,
            status=AssetStatus.AVAILABLE
        )

    def test_assign_asset_success(self):
        url = '/api/asset-allocations/assign'
        payload = {
            'asset': self.asset.id,
            'assigned_to': self.target_user.id,
            'department': self.dept.id,
            'remarks': 'Assigned for AI lab research'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 201)
        self.assertTrue(response.data['data']['is_current'])
        self.assertEqual(response.data['data']['asset_code'], 'AST-ALLOC-01')

        # Verify asset status updated to 'assigned'
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ASSIGNED)

    def test_assign_non_available_asset_fails(self):
        # Update asset to assigned
        self.asset.status = AssetStatus.ASSIGNED
        self.asset.save()

        url = '/api/asset-allocations/assign'
        payload = {
            'asset': self.asset.id,
            'assigned_to': self.target_user.id,
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be assigned', response.data['message'].lower())

    def test_return_asset_success(self):
        # Create active allocation first
        alloc = AssetAllocation.objects.create(
            asset=self.asset,
            assigned_to=self.target_user,
            department=self.dept,
            is_current=True
        )
        self.asset.status = AssetStatus.ASSIGNED
        self.asset.save()

        url = f'/api/asset-allocations/return/{alloc.id}'
        payload = {
            'remarks': 'Returned after project completion'
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['data']['is_current'])
        self.assertIsNotNone(response.data['data']['returned_date'])

        # Verify asset status reset to 'available'
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_return_already_returned_asset_fails(self):
        alloc = AssetAllocation.objects.create(
            asset=self.asset,
            assigned_to=self.target_user,
            is_current=False
        )

        url = f'/api/asset-allocations/return/{alloc.id}'
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('not currently assigned', response.data['message'].lower())

    def test_reassign_returned_asset_success(self):
        # Step 1: Assign and Return
        alloc1 = AssetAllocation.objects.create(
            asset=self.asset,
            assigned_to=self.target_user,
            is_current=False
        )
        self.asset.status = AssetStatus.AVAILABLE
        self.asset.save()

        # Step 2: Assign again
        url = '/api/asset-allocations/assign'
        payload = {
            'asset': self.asset.id,
            'assigned_to': self.target_user.id
        }
        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Check total allocation history count is 2
        self.assertEqual(AssetAllocation.objects.filter(asset=self.asset).count(), 2)

    def test_list_and_filter_allocations(self):
        AssetAllocation.objects.create(
            asset=self.asset,
            assigned_to=self.target_user,
            is_current=True
        )

        url = f'/api/asset-allocations/list?is_current=true&asset={self.asset.id}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['data']['results']), 1)


class AssetTransferTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin_role, _ = Role.objects.get_or_create(role_name='Admin')
        self.student_role, _ = Role.objects.get_or_create(role_name='Student')

        self.admin_user = User.objects.create(
            name='Admin User',
            username='admin_transfer_test',
            mail='admin_transfer@test.com',
            mobile_number='9876543230',
            password='Password123!',
            role=self.admin_role
        )

        self.user_a = User.objects.create(
            name='User Alpha',
            username='user_a',
            mail='user_a@test.com',
            mobile_number='9876543231',
            password='Password123!',
            role=self.admin_role
        )

        self.user_b = User.objects.create(
            name='User Beta',
            username='user_b',
            mail='user_b@test.com',
            mobile_number='9876543232',
            password='Password123!',
            role=self.admin_role
        )

        self.student_user = User.objects.create(
            name='Student User',
            username='student_transfer',
            mail='student_transfer@test.com',
            mobile_number='9876543233',
            password='Password123!',
            role=self.student_role
        )

        self.program = Program.objects.create(
            program_name='B.Tech Engineering',
            program_level='UG',
            duration=4
        )

        self.dept_a = Department.objects.create(
            department_name='Computer Science & Engineering',
            department_code='CSE',
            short_name='CSE',
            program=self.program
        )

        self.dept_b = Department.objects.create(
            department_name='Electrical & Electronics Engineering',
            department_code='EEE',
            short_name='EEE',
            program=self.program
        )

        self.category = AssetCategory.objects.create(
            name='Laptops & Computers',
            description='High performance workstations'
        )

        self.asset = Asset.objects.create(
            asset_code='AST-TRF-001',
            asset_name='Dell XPS 15',
            category=self.category,
            status=AssetStatus.ASSIGNED,
            location='Room 101'
        )

        self.active_alloc = AssetAllocation.objects.create(
            asset=self.asset,
            assigned_to=self.user_a,
            department=self.dept_a,
            is_current=True
        )

        self.client.force_authenticate(user=self.admin_user)

    def test_transfer_asset_success(self):
        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id,
            'to_department': self.dept_b.id,
            'to_location': 'Room 202',
            'remarks': 'Transferring laptop for new project requirement'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['code'], 201)
        self.assertEqual(response.data['message'], 'Asset transferred successfully.')

        # 1. Old allocation closed
        self.active_alloc.refresh_from_db()
        self.assertFalse(self.active_alloc.is_current)
        self.assertIsNotNone(self.active_alloc.returned_date)

        # 2. New allocation active
        new_alloc = AssetAllocation.objects.get(asset=self.asset, is_current=True)
        self.assertEqual(new_alloc.assigned_to, self.user_b)
        self.assertEqual(new_alloc.department, self.dept_b)

        # 3. Asset status remains assigned & location updated
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ASSIGNED)
        self.assertEqual(self.asset.location, 'Room 202')

        # 4. AssetTransfer record created
        transfer = AssetTransfer.objects.get(id=response.data['data']['id'])
        self.assertEqual(transfer.asset, self.asset)
        self.assertEqual(transfer.from_user, self.user_a)
        self.assertEqual(transfer.to_user, self.user_b)
        self.assertEqual(transfer.from_department, self.dept_a)
        self.assertEqual(transfer.to_department, self.dept_b)

    def test_transfer_unassigned_available_asset_fails(self):
        self.asset.status = AssetStatus.AVAILABLE
        self.asset.save()
        self.active_alloc.delete()

        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('currently available', response.data['message'].lower())

    def test_transfer_maintenance_asset_fails(self):
        self.asset.status = AssetStatus.MAINTENANCE
        self.asset.save()

        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('under maintenance', response.data['message'].lower())

    def test_transfer_damaged_asset_fails(self):
        self.asset.status = AssetStatus.DAMAGED
        self.asset.save()

        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('damaged', response.data['message'].lower())

    def test_transfer_lost_asset_fails(self):
        self.asset.status = AssetStatus.LOST
        self.asset.save()

        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('lost', response.data['message'].lower())

    def test_transfer_disposed_asset_fails(self):
        self.asset.status = AssetStatus.DISPOSED
        self.asset.save()

        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('disposed', response.data['message'].lower())

    def test_transfer_same_source_and_destination_fails(self):
        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_a.id,
            'to_department': self.dept_a.id,
            'to_location': 'Room 101'
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('different from the current assignment', response.data['message'].lower())

    def test_transfer_list_and_history(self):
        # Perform transfer
        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id,
            'to_department': self.dept_b.id
        }
        self.client.post(url, payload, format='json')

        # Test list endpoint
        list_url = '/api/asset-transfers/list?search=AST-TRF-001'
        res_list = self.client.get(list_url)
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res_list.data['data']['results']), 1)

        # Test history endpoint
        hist_url = f'/api/asset-transfers/history/{self.asset.id}'
        res_hist = self.client.get(hist_url)
        self.assertEqual(res_hist.status_code, status.HTTP_200_OK)

    def test_student_permission_denied(self):
        self.client.force_authenticate(user=self.student_user)

        url = '/api/asset-transfers/transfer'
        payload = {
            'asset': self.asset.id,
            'to_user': self.user_b.id
        }

        response = self.client.post(url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

class AssetMaintenanceTests(TestCase):
    """Tests for the AssetMaintenance lifecycle."""

    def setUp(self):
        self.client = APIClient()

        self.admin_role, _ = Role.objects.get_or_create(role_name='Admin')
        self.student_role, _ = Role.objects.get_or_create(role_name='Student')

        self.admin_user = User.objects.create(
            name='Admin User',
            username='maint_admin',
            mail='maint_admin@test.com',
            mobile_number='9000000001',
            password='Password123!',
            role=self.admin_role
        )
        self.student_user = User.objects.create(
            name='Student User',
            username='maint_student',
            mail='maint_student@test.com',
            mobile_number='9000000002',
            password='Password123!',
            role=self.student_role
        )

        self.category = AssetCategory.objects.create(name='Electronics Test')
        self.asset = Asset.objects.create(
            asset_code='MAINT-001',
            asset_name='Test Laptop',
            category=self.category,
            status=AssetStatus.AVAILABLE
        )
        self.today = date.today()
        self.client.force_authenticate(user=self.admin_user)

    def _create_maintenance(self, asset=None, extra=None):
        """Helper to create a maintenance record."""
        payload = {
            'asset': (asset or self.asset).id,
            'maintenance_type': 'repair',
            'issue_description': 'Screen cracked',
            'maintenance_date': str(self.today),
        }
        if extra:
            payload.update(extra)
        return self.client.post('/api/asset-maintenance/create', payload, format='json')

    # --- Create Maintenance ---
    def test_create_maintenance_success(self):
        resp = self._create_maintenance()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['code'], 201)
        self.assertIn('created successfully', resp.data['message'].lower())
        self.assertEqual(resp.data['data']['status'], 'pending')
        # Asset status should now be maintenance
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)

    def test_create_maintenance_asset_not_found(self):
        payload = {
            'asset': 99999,
            'maintenance_type': 'repair',
            'issue_description': 'Screen',
            'maintenance_date': str(self.today),
        }
        resp = self.client.post('/api/asset-maintenance/create', payload, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_create_maintenance_missing_issue_fails(self):
        payload = {
            'asset': self.asset.id,
            'maintenance_type': 'repair',
            'issue_description': '',
            'maintenance_date': str(self.today),
        }
        resp = self.client.post('/api/asset-maintenance/create', payload, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_create_maintenance_negative_cost_fails(self):
        resp = self._create_maintenance(extra={'cost': -100})
        self.assertEqual(resp.status_code, 400)
        self.assertIn('errors', resp.data)

    def test_create_maintenance_disposed_asset_fails(self):
        self.asset.status = AssetStatus.DISPOSED
        self.asset.save()
        resp = self._create_maintenance()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('disposed', resp.data['message'].lower())

    def test_create_maintenance_lost_asset_fails(self):
        self.asset.status = AssetStatus.LOST
        self.asset.save()
        resp = self._create_maintenance()
        self.assertEqual(resp.status_code, 400)
        self.assertIn('lost', resp.data['message'].lower())

    def test_create_maintenance_already_under_maintenance_fails(self):
        self._create_maintenance()
        # Try to create another maintenance for the same asset
        asset2 = Asset.objects.create(
            asset_code='MAINT-002', asset_name='Laptop 2',
            category=self.category, status=AssetStatus.MAINTENANCE
        )
        resp = self._create_maintenance(asset=asset2)
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already under maintenance', resp.data['message'].lower())

    def test_duplicate_active_maintenance_fails(self):
        self._create_maintenance()
        # asset is now under maintenance, try to create another
        resp = self._create_maintenance()
        self.assertEqual(resp.status_code, 400)

    # --- Previous Status ---
    def test_previous_status_available_stored(self):
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)
        resp = self._create_maintenance()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['previous_status'], 'available')

    def test_previous_status_assigned_stored(self):
        self.asset.status = AssetStatus.ASSIGNED
        self.asset.save()
        resp = self._create_maintenance()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['data']['previous_status'], 'assigned')

    # --- Start Maintenance ---
    def test_start_maintenance_success(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/start/{maint_id}', format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['status'], 'in_progress')
        self.assertIn('started successfully', resp.data['message'].lower())

    def test_start_completed_maintenance_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        self.client.post(f'/api/asset-maintenance/start/{maint_id}', format='json')
        self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today)
        }, format='json')
        resp = self.client.post(f'/api/asset-maintenance/start/{maint_id}', format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('completed', resp.data['message'].lower())

    def test_start_cancelled_maintenance_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        self.client.post(f'/api/asset-maintenance/cancel/{maint_id}', format='json')
        resp = self.client.post(f'/api/asset-maintenance/start/{maint_id}', format='json')
        self.assertEqual(resp.status_code, 400)

    # --- Complete Maintenance ---
    def test_complete_maintenance_success(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today),
            'cost': '1500.00',
        }, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['status'], 'completed')
        self.assertIn('completed successfully', resp.data['message'].lower())
        # Asset should be restored to available
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_complete_maintenance_restores_assigned_status(self):
        """Assigned → maintenance → assigned"""
        self.asset.status = AssetStatus.ASSIGNED
        self.asset.save()
        # Create an active allocation
        alloc = AssetAllocation.objects.create(
            asset=self.asset, is_current=True
        )
        resp = self._create_maintenance()
        maint_id = resp.data['data']['id']
        self.assertEqual(resp.data['data']['previous_status'], 'assigned')

        complete_resp = self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today),
        }, format='json')
        self.assertEqual(complete_resp.status_code, 200)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.ASSIGNED)

    def test_complete_maintenance_without_completion_date_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {}, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('completion_date', resp.data.get('errors', {}))

    def test_complete_maintenance_invalid_date_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today - timedelta(days=10)),
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('cannot be before', resp.data['message'].lower())

    def test_complete_maintenance_negative_cost_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today),
            'cost': '-500',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_complete_already_completed_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today)
        }, format='json')
        resp = self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today)
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('already completed', resp.data['message'].lower())

    # --- Cancel Maintenance ---
    def test_cancel_maintenance_success(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/cancel/{maint_id}', format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['data']['status'], 'cancelled')
        self.assertIn('cancelled successfully', resp.data['message'].lower())
        # Asset should be restored to available
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_cancel_already_cancelled_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        self.client.post(f'/api/asset-maintenance/cancel/{maint_id}', format='json')
        resp = self.client.post(f'/api/asset-maintenance/cancel/{maint_id}', format='json')
        self.assertEqual(resp.status_code, 400)

    def test_cancel_completed_fails(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today)
        }, format='json')
        resp = self.client.post(f'/api/asset-maintenance/cancel/{maint_id}', format='json')
        self.assertEqual(resp.status_code, 400)

    # --- Allocation Blocked During Maintenance ---
    def test_allocation_blocked_during_maintenance(self):
        self._create_maintenance()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)
        resp = self.client.post('/api/asset-allocations/assign', {
            'asset': self.asset.id,
            'assigned_to': self.admin_user.id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('maintenance', resp.data['message'].lower())

    # --- Transfer Blocked During Maintenance ---
    def test_transfer_blocked_during_maintenance(self):
        self._create_maintenance()
        resp = self.client.post('/api/asset-transfers/transfer', {
            'asset': self.asset.id,
            'to_user': self.admin_user.id,
        }, format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertIn('maintenance', resp.data['message'].lower())

    # --- History Preserved ---
    def test_maintenance_history_not_deleted_on_lifecycle(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today)
        }, format='json')
        from asset.models import AssetMaintenance
        self.assertTrue(AssetMaintenance.objects.filter(id=maint_id).exists())

    # --- History Endpoint ---
    def test_asset_maintenance_history(self):
        self._create_maintenance()
        resp = self.client.get(f'/api/asset-maintenance/history/{self.asset.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('data', resp.data)

    # --- Pagination ---
    def test_maintenance_list_pagination(self):
        resp = self.client.get('/api/asset-maintenance/list?page=1&page_size=5')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('data', resp.data)

    # --- Search ---
    def test_maintenance_list_search(self):
        self._create_maintenance()
        resp = self.client.get('/api/asset-maintenance/list?search=MAINT-001')
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.data['data']['results']), 1)

    # --- Filter by status ---
    def test_maintenance_list_filter_by_status(self):
        self._create_maintenance()
        resp = self.client.get('/api/asset-maintenance/list?status=pending')
        self.assertEqual(resp.status_code, 200)
        results = resp.data['data']['results']
        for r in results:
            self.assertEqual(r['status'], 'pending')

    # --- Permissions ---
    def test_student_cannot_create_maintenance(self):
        self.client.force_authenticate(user=self.student_user)
        resp = self._create_maintenance()
        self.assertEqual(resp.status_code, 403)

    def test_student_can_read_maintenance(self):
        self.client.force_authenticate(user=self.student_user)
        resp = self.client.get('/api/asset-maintenance/list')
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_cannot_access(self):
        self.client.force_authenticate(user=None)
        resp = self.client.get('/api/asset-maintenance/list')
        self.assertEqual(resp.status_code, 401)

    # --- Messages ---
    def test_create_success_message(self):
        resp = self._create_maintenance()
        self.assertIn('created successfully', resp.data['message'].lower())

    def test_start_success_message(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/start/{maint_id}', format='json')
        self.assertIn('started successfully', resp.data['message'].lower())

    def test_complete_success_message(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today)
        }, format='json')
        self.assertIn('completed successfully', resp.data['message'].lower())

    def test_cancel_success_message(self):
        create_resp = self._create_maintenance()
        maint_id = create_resp.data['data']['id']
        resp = self.client.post(f'/api/asset-maintenance/cancel/{maint_id}', format='json')
        self.assertIn('cancelled successfully', resp.data['message'].lower())

    # --- Transaction Rollback ---
    def test_invalid_maintenance_date_rolls_back(self):
        """Creating with bad date should not change asset status"""
        original_status = self.asset.status
        payload = {
            'asset': self.asset.id,
            'maintenance_type': 'repair',
            'issue_description': 'Issue',
            'maintenance_date': 'not-a-date',
        }
        resp = self.client.post('/api/asset-maintenance/create', payload, format='json')
        self.assertEqual(resp.status_code, 400)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, original_status)

    # --- Available → Maintenance → Available Flow ---
    def test_available_maintenance_available_flow(self):
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)
        create_resp = self._create_maintenance()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.MAINTENANCE)

        maint_id = create_resp.data['data']['id']
        self.client.post(f'/api/asset-maintenance/complete/{maint_id}', {
            'completion_date': str(self.today)
        }, format='json')
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)




class AssetDisposalTests(TestCase):
    """Tests for the AssetDisposal lifecycle and validation rules."""

    def setUp(self):
        self.client = APIClient()

        self.admin_role, _ = Role.objects.get_or_create(role_name='Admin')
        self.student_role, _ = Role.objects.get_or_create(role_name='Student')

        self.admin_user = User.objects.create(
            name='Admin User',
            username='admin_disposal',
            mail='admin_disposal@test.com',
            mobile_number='9876543210',
            password='Password123!',
            role=self.admin_role
        )

        self.student_user = User.objects.create(
            name='Student User',
            username='student_disposal',
            mail='student_disposal@test.com',
            mobile_number='9876543211',
            password='Password123!',
            role=self.student_role
        )

        self.category = AssetCategory.objects.create(name='Hardware')
        self.asset = Asset.objects.create(
            asset_code='AST-DISP-001',
            asset_name='Old Monitor',
            category=self.category,
            status=AssetStatus.AVAILABLE
        )

    def test_create_disposal_request_success(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'asset': self.asset.id,
            'disposal_type': 'damaged_beyond_repair',
            'disposal_date': str(date.today()),
            'reason': 'Screen burned and cracked',
            'disposal_value': '50.00',
            'approval_reference': 'REF-101',
            'remarks': 'Inspected by IT tech'
        }
        res = self.client.post('/api/asset-disposals/create', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['code'], 201)
        self.assertEqual(res.data['message'], 'Disposal request created successfully.')
        self.assertEqual(res.data['data']['status'], 'pending')
        # Asset status remains unchanged when pending
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.AVAILABLE)

    def test_create_disposal_disposed_asset_fails(self):
        self.asset.status = AssetStatus.DISPOSED
        self.asset.save()
        self.client.force_authenticate(user=self.admin_user)

        payload = {
            'asset': self.asset.id,
            'disposal_type': 'obsolete',
            'disposal_date': str(date.today()),
            'reason': 'Too old'
        }
        res = self.client.post('/api/asset-disposals/create', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_disposal_asset_under_maintenance_fails(self):
        self.asset.status = AssetStatus.MAINTENANCE
        self.asset.save()
        self.client.force_authenticate(user=self.admin_user)

        payload = {
            'asset': self.asset.id,
            'disposal_type': 'obsolete',
            'disposal_date': str(date.today()),
            'reason': 'Too old'
        }
        res = self.client.post('/api/asset-disposals/create', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_duplicate_active_disposal_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='First request',
            status=DisposalStatus.PENDING
        )

        payload = {
            'asset': self.asset.id,
            'disposal_type': 'sold',
            'disposal_date': str(date.today()),
            'reason': 'Second request'
        }
        res = self.client.post('/api/asset-disposals/create', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_disposal_negative_value_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        payload = {
            'asset': self.asset.id,
            'disposal_type': 'sold',
            'disposal_date': str(date.today()),
            'reason': 'Sold for parts',
            'disposal_value': '-100.00'
        }
        res = self.client.post('/api/asset-disposals/create', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_pending_disposal_success(self):
        self.client.force_authenticate(user=self.admin_user)
        disposal = AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Original reason',
            status=DisposalStatus.PENDING
        )

        res = self.client.patch(
            f'/api/asset-disposals/update/{disposal.id}',
            {'reason': 'Updated reason text'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        disposal.refresh_from_db()
        self.assertEqual(disposal.reason, 'Updated reason text')

    def test_approve_disposal_success(self):
        self.client.force_authenticate(user=self.admin_user)
        disposal = AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Obsolescence',
            status=DisposalStatus.PENDING
        )

        res = self.client.post(f'/api/asset-disposals/approve/{disposal.id}', {'approval_reference': 'BOARD-REF-99'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Disposal request approved successfully.')
        disposal.refresh_from_db()
        self.assertEqual(disposal.status, DisposalStatus.APPROVED)
        self.assertEqual(disposal.approved_by, self.admin_user)
        self.assertEqual(disposal.approval_reference, 'BOARD-REF-99')

    def test_reject_disposal_success(self):
        self.client.force_authenticate(user=self.admin_user)
        disposal = AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Obsolescence',
            status=DisposalStatus.PENDING
        )

        res = self.client.post(f'/api/asset-disposals/reject/{disposal.id}', {'remarks': 'Rejected by board'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Disposal request rejected successfully.')
        disposal.refresh_from_db()
        self.assertEqual(disposal.status, DisposalStatus.REJECTED)

    def test_cancel_disposal_success(self):
        self.client.force_authenticate(user=self.admin_user)
        disposal = AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Obsolescence',
            status=DisposalStatus.PENDING
        )

        res = self.client.post(f'/api/asset-disposals/cancel/{disposal.id}', {'remarks': 'Cancelled by requestor'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Disposal request cancelled successfully.')
        disposal.refresh_from_db()
        self.assertEqual(disposal.status, DisposalStatus.CANCELLED)

    def test_complete_disposal_success_sets_asset_disposed(self):
        self.client.force_authenticate(user=self.admin_user)
        disposal = AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Obsolescence',
            status=DisposalStatus.APPROVED,
            approved_by=self.admin_user
        )

        res = self.client.post(f'/api/asset-disposals/complete/{disposal.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['message'], 'Asset disposal completed successfully.')

        disposal.refresh_from_db()
        self.assertEqual(disposal.status, DisposalStatus.COMPLETED)
        self.assertIsNotNone(disposal.completed_at)

        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, AssetStatus.DISPOSED)

    def test_complete_pending_disposal_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        disposal = AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Obsolescence',
            status=DisposalStatus.PENDING
        )

        res = self.client.post(f'/api/asset-disposals/complete/{disposal.id}')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['message'], 'Only approved disposal requests can be completed.')

    def test_complete_disposal_assigned_asset_fails(self):
        self.client.force_authenticate(user=self.admin_user)
        AssetAllocation.objects.create(
            asset=self.asset,
            assigned_to=self.admin_user,
            is_current=True
        )
        self.asset.status = AssetStatus.ASSIGNED
        self.asset.save()

        disposal = AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Obsolescence',
            status=DisposalStatus.APPROVED,
            approved_by=self.admin_user
        )

        res = self.client.post(f'/api/asset-disposals/complete/{disposal.id}')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_allocation_blocked_on_disposed_asset(self):
        self.asset.status = AssetStatus.DISPOSED
        self.asset.save()
        self.client.force_authenticate(user=self.admin_user)

        payload = {
            'asset': self.asset.id,
            'assigned_to': self.admin_user.id
        }
        res = self.client.post('/api/asset-allocations/assign', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_transfer_blocked_on_disposed_asset(self):
        self.asset.status = AssetStatus.DISPOSED
        self.asset.save()
        self.client.force_authenticate(user=self.admin_user)

        payload = {
            'asset': self.asset.id,
            'to_user': self.admin_user.id
        }
        res = self.client.post('/api/asset-transfers/transfer', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_maintenance_blocked_on_disposed_asset(self):
        self.asset.status = AssetStatus.DISPOSED
        self.asset.save()
        self.client.force_authenticate(user=self.admin_user)

        payload = {
            'asset': self.asset.id,
            'maintenance_type': 'repair',
            'issue_description': 'Broken',
            'maintenance_date': str(date.today())
        }
        res = self.client.post('/api/asset-maintenance/create', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disposal_history_retrieval(self):
        self.client.force_authenticate(user=self.admin_user)
        AssetDisposal.objects.create(
            asset=self.asset,
            disposal_type=DisposalType.OBSOLETE,
            disposal_date=date.today(),
            reason='Record 1',
            status=DisposalStatus.CANCELLED
        )
        res = self.client.get(f'/api/asset-disposals/history/{self.asset.id}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['code'], 200)

    def test_student_cannot_create_or_approve_disposal(self):
        self.client.force_authenticate(user=self.student_user)
        payload = {
            'asset': self.asset.id,
            'disposal_type': 'damaged_beyond_repair',
            'disposal_date': str(date.today()),
            'reason': 'Student request'
        }
        res = self.client.post('/api/asset-disposals/create', payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
