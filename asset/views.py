from django.http import Http404
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from django_filters.rest_framework import DjangoFilterBackend
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from common.pagination import CustomPageNumberPagination
from .models import (
    AssetCategory, Asset, AssetCondition, AssetAllocation, AssetStatus, AssetTransfer,
    AssetMaintenance, MaintenanceStatus, PreviousAssetStatus,
    AssetDisposal, DisposalStatus, DisposalType
)
from .serializers import (
    AssetCategorySerializer, AssetSerializer, AssetAllocationSerializer,
    AssetTransferSerializer, AssetMaintenanceSerializer,
    AssetDisposalSerializer, AssetDisposalCreateSerializer
)
from .permissions import (
    AssetCategoryPermission, AssetPermission, AssetAllocationPermission,
    AssetTransferPermission, AssetMaintenancePermission,
    AssetDisposalPermission
)
from users.models import User
from institution.models import Department


def broadcast_custom_ws_event(event_name, data):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': 'AssetAllocation',
                        'event': event_name,
                        'data': data
                    }
                }
            )
        except Exception:
            pass


class AssetCategoryViewSet(viewsets.ModelViewSet):
    queryset = AssetCategory.objects.all().order_by('-created_at')
    serializer_class = AssetCategorySerializer
    permission_classes = [AssetCategoryPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['name', 'description']
    filterset_fields = ['is_active']

    def get_queryset(self):
        qs = super().get_queryset()
        is_active_param = self.request.query_params.get('is_active', None)
        if is_active_param is not None and is_active_param != '':
            val = is_active_param.lower()
            if val in ['true', '1']:
                qs = qs.filter(is_active=True)
            elif val in ['false', '0']:
                qs = qs.filter(is_active=False)
        return qs

    def handle_exception(self, exc):
        if isinstance(exc, models.ProtectedError):
            return Response({
                "code": 400,
                "message": "Cannot delete asset category because assets are associated with it."
            }, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset category not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have permission to perform this action."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, IntegrityError):
            return Response({
                "code": 400,
                "message": "An asset category with this name already exists.",
                "errors": {"name": ["An asset category with this name already exists."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset categories retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset category retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Asset category created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset category updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset category deleted successfully."
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['patch', 'post'], url_path='toggle-status')
    def toggle_status(self, request, pk=None):
        category = self.get_object()
        is_active = request.data.get('is_active', not category.is_active)
        if isinstance(is_active, str):
            is_active = is_active.lower() in ['true', '1']
        
        category.is_active = bool(is_active)
        category.save()

        action_msg = "activated" if category.is_active else "deactivated"
        serializer = self.get_serializer(category)
        return Response({
            "code": 200,
            "message": f"Asset category {action_msg} successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class AssetViewSet(viewsets.ModelViewSet):
    queryset = Asset.objects.select_related('category').prefetch_related('allocations__assigned_to', 'allocations__department__program').all().order_by('-created_at')
    serializer_class = AssetSerializer
    permission_classes = [AssetPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset_code',
        'asset_name',
        'brand',
        'model_number',
        'serial_number',
        'vendor_name',
    ]
    filterset_fields = ['category', 'status', 'condition']

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have permission to perform this action."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, IntegrityError):
            err_str = str(exc).lower()
            if 'asset_code' in err_str:
                msg = "An asset with this asset code already exists."
                err_dict = {"asset_code": [msg]}
            elif 'serial_number' in err_str:
                msg = "An asset with this serial number already exists."
                err_dict = {"serial_number": [msg]}
            else:
                msg = "Database integrity violation."
                err_dict = {}

            return Response({
                "code": 400,
                "message": msg,
                "errors": err_dict
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Assets retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Asset created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset deleted successfully."
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        import datetime
        from decimal import Decimal
        from users.models import User
        from institution.models import Department

        assets_data = (
            request.data.get('assets') or
            request.data.get('data') or
            request.data.get('rows') or
            request.data.get('users') or
            []
        )
        if isinstance(request.data, list):
            assets_data = request.data

        if not assets_data or not isinstance(assets_data, list):
            return Response({
                "code": 400,
                "message": "No asset data provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Cache category lookups
        categories = list(AssetCategory.objects.all())
        cat_name_map = {c.name.strip().upper(): c for c in categories}
        cat_id_map = {str(c.id): c for c in categories}

        # Cache User (HOD / Staff) lookups with Roles
        all_users = list(User.objects.select_related('role').all())
        user_name_map = {}
        user_username_map = {}
        user_id_map = {}
        user_label_map = {}
        for u in all_users:
            r_name = (u.role.role_name if getattr(u, 'role', None) and getattr(u.role, 'role_name', None) else '').strip()
            if u.name:
                u_name_clean = u.name.strip().upper()
                user_name_map[u_name_clean] = u
                if r_name:
                    user_label_map[f"{u_name_clean} ({r_name.upper()})"] = u
            if u.username:
                u_uname_clean = u.username.strip().upper()
                user_username_map[u_uname_clean] = u
                if r_name:
                    user_label_map[f"{u_uname_clean} ({r_name.upper()})"] = u
            user_id_map[str(u.id)] = u

        # Cache Department lookups with Program Levels (UG/PG)
        all_depts = list(Department.objects.select_related('program').all())
        dept_name_map = {}
        dept_code_map = {}
        dept_id_map = {}
        dept_level_map = {}
        for d in all_depts:
            d_name_clean = (d.department_name or '').strip().upper()
            prog_level = (d.program.program_level if getattr(d, 'program', None) and getattr(d.program, 'program_level', None) else '').strip().upper()
            if d_name_clean:
                dept_name_map[d_name_clean] = d
                if prog_level:
                    dept_level_map[f"{d_name_clean} ({prog_level})"] = d
            if d.department_code:
                dept_code_map[d.department_code.strip().upper()] = d
            dept_id_map[str(d.id)] = d

        seen_codes = set()
        seen_serials = set()
        existing_codes = set(Asset.objects.values_list('asset_code', flat=True))
        existing_codes_upper = {c.upper() for c in existing_codes if c}
        existing_serials = set(Asset.objects.exclude(serial_number__isnull=True).exclude(serial_number='').values_list('serial_number', flat=True))
        existing_serials_upper = {s.upper() for s in existing_serials if s}

        errors = []
        validated_assets = []

        def parse_date_val(raw_val):
            if raw_val is None:
                return None
            val_str = str(raw_val).strip()
            if not val_str or val_str.lower() in ('none', 'null', '—', '-', 'n/a', 'na'):
                return None
            if isinstance(raw_val, datetime.datetime):
                return raw_val.date()
            if isinstance(raw_val, datetime.date):
                return raw_val

            # 1. Handle numeric Excel serial date numbers (e.g. 45332 for 2024-02-10)
            try:
                numeric_val = float(val_str)
                if 1000 <= numeric_val <= 100000:
                    excel_base = datetime.date(1899, 12, 30)
                    return excel_base + datetime.timedelta(days=int(numeric_val))
            except (ValueError, TypeError):
                pass

            # 2. Standard string format parsing
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y', '%d.%m.%Y', '%Y.%m.%d'):
                try:
                    clean_str = val_str.split('T')[0].split(' ')[0]
                    return datetime.datetime.strptime(clean_str, fmt).date()
                except ValueError:
                    pass

            # 3. Fallback dateutil parser
            try:
                from dateutil import parser
                return parser.parse(val_str, dayfirst=True).date()
            except Exception:
                return 'INVALID_DATE'

        def normalize_condition(val):
            if not val:
                return AssetCondition.NEW
            clean = str(val).strip().lower()
            if 'new' in clean:
                return AssetCondition.NEW
            if 'good' in clean:
                return AssetCondition.GOOD
            if 'fair' in clean:
                return AssetCondition.FAIR
            if 'poor' in clean:
                return AssetCondition.POOR
            if 'damag' in clean:
                return AssetCondition.DAMAGED
            for code, label in AssetCondition.choices:
                if clean == code.lower() or clean == label.lower():
                    return code
            return AssetCondition.NEW

        def normalize_status(val):
            if not val:
                return None
            clean = str(val).strip().lower()
            if 'avail' in clean:
                return AssetStatus.AVAILABLE
            if 'assign' in clean or 'allocat' in clean:
                return AssetStatus.ASSIGNED
            if 'maint' in clean:
                return AssetStatus.MAINTENANCE
            if 'damag' in clean:
                return AssetStatus.DAMAGED
            if 'lost' in clean or 'miss' in clean:
                return AssetStatus.LOST
            if 'dispos' in clean or 'scrap' in clean:
                return AssetStatus.DISPOSED
            for code, label in AssetStatus.choices:
                if clean == code.lower() or clean == label.lower():
                    return code
            return None

        for idx, a in enumerate(assets_data):
            row_num = a.get('s_no', idx + 1)
            asset_code = str(a.get('asset_code', '') or a.get('code', '')).strip()
            asset_name = str(a.get('asset_name', '') or a.get('name', '')).strip()
            category_raw = str(a.get('category', '') or a.get('category_name', '') or a.get('category_id', '')).strip()
            brand = str(a.get('brand', '') or '').strip() or None
            model_number = str(a.get('model_number', '') or a.get('model', '')).strip() or None
            serial_number = str(a.get('serial_number', '') or a.get('serial', '') or a.get('serial_no', '')).strip() or None
            purchase_date_raw = a.get('purchase_date')
            purchase_price_raw = a.get('purchase_price') or a.get('price')
            vendor_name = str(a.get('vendor_name', '') or a.get('vendor', '')).strip() or None
            invoice_number = str(a.get('invoice_number', '') or a.get('invoice', '') or a.get('invoice_no', '')).strip() or None
            warranty_expiry_raw = a.get('warranty_expiry') or a.get('warranty_date')
            condition_raw = a.get('condition')
            status_raw = a.get('status')
            
            # Allocation fields
            assigned_hod_raw = str(
                a.get('assigned_hod', '') or
                a.get('assigned_to', '') or
                a.get('hod', '') or
                a.get('staff', '') or
                a.get('assigned_user', '') or
                ''
            ).strip()
            dept_raw = str(
                a.get('assigned_department', '') or
                a.get('department', '') or
                a.get('dept', '') or
                a.get('department_name', '') or
                a.get('department_code', '') or
                ''
            ).strip()
            alloc_loc_raw = str(
                a.get('allocation_location', '') or
                a.get('location', '') or
                a.get('room', '') or
                a.get('lab', '') or
                ''
            ).strip() or None
            
            description = str(a.get('description', '') or a.get('remarks', '')).strip() or None

            # Skip completely empty rows
            has_content = any([
                asset_code, asset_name, category_raw, brand, model_number,
                serial_number, purchase_date_raw, purchase_price_raw,
                vendor_name, invoice_number, warranty_expiry_raw,
                assigned_hod_raw, dept_raw, alloc_loc_raw, description
            ])
            if not has_content:
                continue

            row_errors = []

            # Asset Code Validation
            if not asset_code:
                row_errors.append("Asset code is required.")
            else:
                if len(asset_code) > 50:
                    row_errors.append("Asset code must not exceed 50 characters.")
                code_upper = asset_code.upper()
                if code_upper in seen_codes:
                    row_errors.append(f"Duplicate asset code '{asset_code}' in sheet.")
                else:
                    seen_codes.add(code_upper)
                    if code_upper in existing_codes_upper:
                        row_errors.append(f"Asset code '{asset_code}' already exists in database.")

            # Asset Name Validation
            if not asset_name:
                row_errors.append("Asset name is required.")
            elif len(asset_name) > 200:
                row_errors.append("Asset name must not exceed 200 characters.")

            # Category Resolution (Optional - defaults to 'General')
            category_obj = None
            cat_raw_to_use = category_raw.strip() if category_raw and category_raw.strip() else "General"
            cat_upper = cat_raw_to_use.upper()

            if cat_upper in cat_name_map:
                category_obj = cat_name_map[cat_upper]
            elif cat_raw_to_use in cat_id_map:
                category_obj = cat_id_map[cat_raw_to_use]
            else:
                try:
                    category_obj, _ = AssetCategory.objects.get_or_create(
                        name=cat_raw_to_use,
                        defaults={'is_active': True, 'description': f'Auto-created category on {timezone.now().strftime("%Y-%m-%d")}'}
                    )
                    cat_name_map[cat_upper] = category_obj
                    cat_id_map[str(category_obj.id)] = category_obj
                except Exception as cat_err:
                    row_errors.append(f"Failed to resolve category '{cat_raw_to_use}': {str(cat_err)}")

            # Serial Number Validation
            if serial_number:
                if len(serial_number) > 150:
                    row_errors.append("Serial number must not exceed 150 characters.")
                serial_upper = serial_number.upper()
                if serial_upper in seen_serials:
                    row_errors.append(f"Duplicate serial number '{serial_number}' in sheet.")
                else:
                    seen_serials.add(serial_upper)
                    if serial_upper in existing_serials_upper:
                        row_errors.append(f"Serial number '{serial_number}' already exists in database.")

            # Purchase Date Validation
            purchase_date = None
            if purchase_date_raw:
                res_pdate = parse_date_val(purchase_date_raw)
                if res_pdate == 'INVALID_DATE':
                    row_errors.append(f"Invalid purchase date format: '{purchase_date_raw}'. Expected YYYY-MM-DD.")
                else:
                    purchase_date = res_pdate

            # Warranty Expiry Validation
            warranty_expiry = None
            if warranty_expiry_raw:
                res_wdate = parse_date_val(warranty_expiry_raw)
                if res_wdate == 'INVALID_DATE':
                    row_errors.append(f"Invalid warranty expiry format: '{warranty_expiry_raw}'. Expected YYYY-MM-DD.")
                else:
                    warranty_expiry = res_wdate

            # Purchase Price Validation
            purchase_price = None
            if purchase_price_raw is not None and str(purchase_price_raw).strip() not in ('', 'None', 'null', '—', '-'):
                clean_price = str(purchase_price_raw).replace(',', '').replace('$', '').replace('₹', '').strip()
                try:
                    price_val = Decimal(clean_price)
                    if price_val < 0:
                        row_errors.append("Purchase price cannot be negative.")
                    else:
                        purchase_price = price_val
                except Exception:
                    row_errors.append(f"Invalid purchase price: '{purchase_price_raw}'. Must be a valid number.")

            # Strings Length Check
            if brand and len(brand) > 100:
                row_errors.append("Brand name must not exceed 100 characters.")
            if model_number and len(model_number) > 100:
                row_errors.append("Model number must not exceed 100 characters.")
            if vendor_name and len(vendor_name) > 200:
                row_errors.append("Vendor name must not exceed 200 characters.")
            if invoice_number and len(invoice_number) > 100:
                row_errors.append("Invoice number must not exceed 100 characters.")
            if alloc_loc_raw and len(alloc_loc_raw) > 200:
                row_errors.append("Allocation location must not exceed 200 characters.")

            condition = normalize_condition(condition_raw)
            status_val = normalize_status(status_raw)

            # Resolve Assigned HOD User
            import re
            assigned_user_obj = None
            if assigned_hod_raw and assigned_hod_raw.lower() not in ('none', 'null', '—', '-', 'unassigned'):
                hod_clean = assigned_hod_raw.strip()
                hod_upper = hod_clean.upper()
                hod_stripped = re.sub(r'\(.*?\)', '', hod_clean).strip().upper()

                if hod_upper in user_label_map:
                    assigned_user_obj = user_label_map[hod_upper]
                elif hod_upper in user_name_map:
                    assigned_user_obj = user_name_map[hod_upper]
                elif hod_upper in user_username_map:
                    assigned_user_obj = user_username_map[hod_upper]
                elif hod_stripped in user_name_map:
                    assigned_user_obj = user_name_map[hod_stripped]
                elif hod_stripped in user_username_map:
                    assigned_user_obj = user_username_map[hod_stripped]
                elif hod_clean in user_id_map:
                    assigned_user_obj = user_id_map[hod_clean]
                else:
                    # Fuzzy match
                    matched_user = None
                    for uname, uobj in user_name_map.items():
                        if uname in hod_upper or hod_upper in uname or (hod_stripped and (uname in hod_stripped or hod_stripped in uname)):
                            matched_user = uobj
                            break
                    if matched_user:
                        assigned_user_obj = matched_user
                    else:
                        row_errors.append(f"Assigned user / HOD '{assigned_hod_raw}' not found.")

            # Resolve Assigned Department (with UG/PG support)
            dept_obj = None
            if dept_raw and dept_raw.lower() not in ('none', 'null', '—', '-', 'unassigned'):
                dept_clean = dept_raw.strip()
                dept_upper = dept_clean.upper()
                dept_stripped = re.sub(r'\(.*?\)', '', dept_clean).strip().upper()

                if dept_upper in dept_level_map:
                    dept_obj = dept_level_map[dept_upper]
                elif dept_upper in dept_name_map:
                    dept_obj = dept_name_map[dept_upper]
                elif dept_upper in dept_code_map:
                    dept_obj = dept_code_map[dept_upper]
                elif dept_stripped in dept_name_map:
                    dept_obj = dept_name_map[dept_stripped]
                elif dept_stripped in dept_code_map:
                    dept_obj = dept_code_map[dept_stripped]
                elif dept_clean in dept_id_map:
                    dept_obj = dept_id_map[dept_clean]
                else:
                    # Fuzzy match
                    matched_dept = None
                    for dname, dobj in dept_name_map.items():
                        if dname in dept_upper or dept_upper in dname or (dept_stripped and (dname in dept_stripped or dept_stripped in dname)):
                            matched_dept = dobj
                            break
                    if matched_dept:
                        dept_obj = matched_dept
                    else:
                        row_errors.append(f"Department '{dept_raw}' not found.")

            # Final status resolution
            if assigned_user_obj or dept_obj:
                status_val = AssetStatus.ASSIGNED
            elif not status_val:
                status_val = AssetStatus.AVAILABLE

            if row_errors:
                errors.append({
                    "row": row_num,
                    "asset_code": asset_code or "Unknown",
                    "errors": row_errors
                })
            else:
                validated_assets.append({
                    "asset_code": asset_code,
                    "asset_name": asset_name,
                    "category": category_obj,
                    "brand": brand,
                    "model_number": model_number,
                    "serial_number": serial_number,
                    "purchase_date": purchase_date,
                    "purchase_price": purchase_price,
                    "vendor_name": vendor_name,
                    "invoice_number": invoice_number,
                    "warranty_expiry": warranty_expiry,
                    "condition": condition,
                    "status": status_val,
                    "assigned_to": assigned_user_obj,
                    "department": dept_obj,
                    "allocation_location": alloc_loc_raw,
                    "description": description
                })

        if errors:
            return Response({
                "code": 400,
                "message": "Validation failed for some rows.",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Atomic Save
        created_assets = []
        try:
            with transaction.atomic():
                for item in validated_assets:
                    asset = Asset.objects.create(
                        asset_code=item["asset_code"],
                        asset_name=item["asset_name"],
                        category=item["category"],
                        brand=item["brand"],
                        model_number=item["model_number"],
                        serial_number=item["serial_number"],
                        purchase_date=item["purchase_date"],
                        purchase_price=item["purchase_price"],
                        vendor_name=item["vendor_name"],
                        invoice_number=item["invoice_number"],
                        warranty_expiry=item["warranty_expiry"],
                        condition=item["condition"],
                        status=item["status"],
                        description=item["description"]
                    )
                    created_assets.append(asset)

                    # Create Allocation if assigned to user / department / location
                    if item["assigned_to"] or item["department"] or item["allocation_location"] or item["status"] == AssetStatus.ASSIGNED:
                        AssetAllocation.objects.create(
                            asset=asset,
                            assigned_to=item["assigned_to"],
                            department=item["department"],
                            location=item["allocation_location"],
                            is_current=True,
                            remarks="Allocated via bulk Excel import"
                        )

                    # Real-time WebSocket event
                    try:
                        channel_layer = get_channel_layer()
                        if channel_layer:
                            async_to_sync(channel_layer.group_send)(
                                'realtime_updates',
                                {
                                    'type': 'broadcast_update',
                                    'data': {
                                        'model': 'Asset',
                                        'event': 'asset_created',
                                        'data': AssetSerializer(asset).data
                                    }
                                }
                            )
                    except Exception:
                        pass
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Database save failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "code": 201,
            "message": f"Successfully imported {len(created_assets)} assets.",
            "data": {
                "count": len(created_assets)
            }
        }, status=status.HTTP_201_CREATED)


class AssetAllocationViewSet(viewsets.ModelViewSet):
    queryset = AssetAllocation.objects.select_related(
        'asset', 'asset__category', 'assigned_to', 'department'
    ).all().order_by('-assigned_date')
    serializer_class = AssetAllocationSerializer
    permission_classes = [AssetAllocationPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset__asset_code',
        'asset__asset_name',
        'asset__serial_number',
        'location',
        'assigned_to__name',
        'assigned_to__username',
        'department__department_name',
        'department__department_code',
    ]
    filterset_fields = ['department', 'asset', 'assigned_to']

    def get_queryset(self):
        qs = super().get_queryset()
        
        my_assets_param = self.request.query_params.get('my_assets', None)
        assigned_to_param = self.request.query_params.get('assigned_to', None)
        if my_assets_param in ['true', '1', True] or str(assigned_to_param).lower() == 'me':
            if self.request.user and self.request.user.is_authenticated:
                qs = qs.filter(assigned_to=self.request.user)

        is_current_param = self.request.query_params.get('is_current', None)
        if is_current_param is not None and is_current_param != '' and is_current_param.lower() != 'all':
            val = is_current_param.lower()
            if val in ['true', '1']:
                qs = qs.filter(is_current=True)
            elif val in ['false', '0']:
                qs = qs.filter(is_current=False)
        return qs

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset allocation record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have permission to perform this action."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, IntegrityError):
            return Response({
                "code": 400,
                "message": "Asset is already assigned.",
                "errors": {
                    "asset": ["This asset already has an active allocation."]
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset allocations retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset allocation retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='assign')
    def assign_asset(self, request):
        asset_id = request.data.get('asset')
        if not asset_id:
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": {"asset": ["Asset is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # 1. Status validation
        if asset.status != AssetStatus.AVAILABLE:
            status_labels = {
                AssetStatus.ASSIGNED: "assigned",
                AssetStatus.MAINTENANCE: "under maintenance",
                AssetStatus.DAMAGED: "damaged",
                AssetStatus.LOST: "lost",
                AssetStatus.DISPOSED: "disposed",
            }
            label = status_labels.get(asset.status, asset.get_status_display().lower())
            return Response({
                "code": 400,
                "message": f"Asset cannot be assigned because it is currently {label}."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Check active allocation
        if AssetAllocation.objects.filter(asset=asset, is_current=True).exists():
            return Response({
                "code": 400,
                "message": "Asset is already assigned.",
                "errors": {
                    "asset": ["This asset already has an active allocation."]
                }
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            allocation = serializer.save(is_current=True)
            asset.status = AssetStatus.ASSIGNED
            asset.save(update_fields=['status', 'updated_at'])

        broadcast_custom_ws_event('asset_assigned', serializer.data)

        return Response({
            "code": 201,
            "message": "Asset assigned successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post', 'patch'], url_path='return')
    def return_asset(self, request):
        allocation_id = request.data.get('allocation_id') or request.data.get('id')
        asset_id = request.data.get('asset_id') or request.data.get('asset')

        allocation = None
        if allocation_id:
            allocation = AssetAllocation.objects.filter(pk=allocation_id, is_current=True).first()
        elif asset_id:
            allocation = AssetAllocation.objects.filter(asset_id=asset_id, is_current=True).first()

        if not allocation:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            allocation.is_current = False
            allocation.returned_date = timezone.now()
            allocation.save(update_fields=['is_current', 'returned_date'])

            asset = allocation.asset
            asset.status = AssetStatus.AVAILABLE
            asset.save(update_fields=['status', 'updated_at'])

        result_serializer = self.get_serializer(allocation)
        broadcast_custom_ws_event('asset_returned', result_serializer.data)

        return Response({
            "code": 200,
            "message": "Asset returned successfully.",
            "data": result_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post', 'patch'], url_path='return-by-id')
    def return_asset_by_id(self, request, pk=None):
        allocation = AssetAllocation.objects.filter(pk=pk, is_current=True).first()
        if not allocation:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            allocation.is_current = False
            allocation.returned_date = timezone.now()
            allocation.save(update_fields=['is_current', 'returned_date'])

            asset = allocation.asset
            asset.status = AssetStatus.AVAILABLE
            asset.save(update_fields=['status', 'updated_at'])

        result_serializer = self.get_serializer(allocation)
        broadcast_custom_ws_event('asset_returned', result_serializer.data)

        return Response({
            "code": 200,
            "message": "Asset returned successfully.",
            "data": result_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='history/(?P<asset_id>\\d+)')
    def asset_history(self, request, asset_id=None):
        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        allocations = self.get_queryset().filter(asset_id=asset_id)
        page = self.paginate_queryset(allocations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Asset allocation history retrieved successfully.",
                "data": paginated_res.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(allocations, many=True)
        return Response({
            "code": 200,
            "message": "Asset allocation history retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)


class AssetTransferViewSet(viewsets.ModelViewSet):
    queryset = AssetTransfer.objects.select_related(
        'asset', 'from_user', 'to_user', 'from_department', 'to_department'
    ).all().order_by('-transfer_date')
    serializer_class = AssetTransferSerializer
    permission_classes = [AssetTransferPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset__asset_code',
        'asset__asset_name',
        'asset__serial_number',
        'from_user__name',
        'from_user__username',
        'to_user__name',
        'to_user__username',
        'from_department__department_name',
        'from_department__department_code',
        'to_department__department_name',
        'to_department__department_code',
        'from_location',
        'to_location'
    ]
    filterset_fields = ['asset', 'from_department', 'to_department', 'from_user', 'to_user']

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset transfer record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have permission to perform this action."
            }, status=status.HTTP_403_FORBIDDEN)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset transfers retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset transfer retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='transfer')
    def transfer_asset(self, request):
        asset_id = request.data.get('asset')
        if not asset_id:
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": {"asset": ["Asset is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # 1. Validate asset status
        if asset.status == AssetStatus.AVAILABLE:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is currently available."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.MAINTENANCE:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is under maintenance."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.DAMAGED:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is damaged."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.LOST:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it is lost."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status == AssetStatus.DISPOSED:
            return Response({
                "code": 400,
                "message": "Asset cannot be transferred because it has been disposed."
            }, status=status.HTTP_400_BAD_REQUEST)
        elif asset.status != AssetStatus.ASSIGNED:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Find active allocation
        active_alloc = AssetAllocation.objects.filter(asset=asset, is_current=True).first()
        if not active_alloc:
            return Response({
                "code": 400,
                "message": "Asset is not currently assigned."
            }, status=status.HTTP_400_BAD_REQUEST)

        from_user = active_alloc.assigned_to
        from_department = active_alloc.department
        from_location = active_alloc.location

        to_user_id = request.data.get('to_user') or None
        to_dept_id = request.data.get('to_department') or None
        to_location = request.data.get('to_location') or None
        remarks = request.data.get('remarks') or None

        if not to_user_id and not to_dept_id and not to_location:
            return Response({
                "code": 400,
                "message": "Destination user, department, or location is required.",
                "errors": {"to_user": ["Must select a destination User or Department or Location."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        # 3. Check if destination is different from current source assignment
        curr_user_id = from_user.id if from_user else None
        curr_dept_id = from_department.id if from_department else None
        curr_loc = (from_location or '').strip()
        new_loc = (to_location or '').strip()

        target_user_id = int(to_user_id) if to_user_id else None
        target_dept_id = int(to_dept_id) if to_dept_id else None

        if target_user_id == curr_user_id and target_dept_id == curr_dept_id and (not new_loc or new_loc == curr_loc):
            return Response({
                "code": 400,
                "message": "Destination must be different from the current assignment.",
                "errors": {"to_user": ["Destination must be different from the current assignment."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        now = timezone.now()

        with transaction.atomic():
            transfer = AssetTransfer.objects.create(
                asset=asset,
                from_user=from_user,
                to_user_id=target_user_id,
                from_department=from_department,
                to_department_id=target_dept_id,
                from_location=from_location,
                to_location=new_loc or None,
                remarks=remarks.strip() if remarks else None,
            )

            active_alloc.is_current = False
            active_alloc.returned_date = now
            active_alloc.save(update_fields=['is_current', 'returned_date'])

            AssetAllocation.objects.create(
                asset=asset,
                assigned_to_id=target_user_id,
                department_id=target_dept_id,
                location=new_loc or from_location or None,
                assigned_date=now,
                is_current=True,
                remarks=f"Transferred from previous allocation" + (f": {remarks}" if remarks else ""),
            )

        serializer = self.get_serializer(transfer)
        broadcast_custom_ws_event('asset_transferred', serializer.data)

        return Response({
            "code": 201,
            "message": "Asset transferred successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='history/(?P<asset_id>\\d+)')
    def asset_transfer_history(self, request, asset_id=None):
        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        transfers = self.get_queryset().filter(asset_id=asset_id)
        page = self.paginate_queryset(transfers)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Asset transfer history retrieved successfully.",
                "data": paginated_res.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(transfers, many=True)
        return Response({
            "code": 200,
            "message": "Asset transfer history retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

class AssetMaintenanceViewSet(viewsets.ModelViewSet):
    queryset = AssetMaintenance.objects.select_related(
        'asset', 'asset__category'
    ).all().order_by('-created_at')
    serializer_class = AssetMaintenanceSerializer
    permission_classes = [AssetMaintenancePermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset__asset_code',
        'asset__asset_name',
        'asset__serial_number',
        'maintenance_type',
        'issue_description',
        'vendor_name',
        'technician_name',
    ]
    filterset_fields = ['status', 'maintenance_type', 'asset']

    def get_queryset(self):
        qs = super().get_queryset()
        # Date range filter
        date_from = self.request.query_params.get('date_from', None)
        date_to = self.request.query_params.get('date_to', None)
        vendor = self.request.query_params.get('vendor', None)
        if date_from:
            qs = qs.filter(maintenance_date__gte=date_from)
        if date_to:
            qs = qs.filter(maintenance_date__lte=date_to)
        if vendor:
            qs = qs.filter(vendor_name__icontains=vendor)
        return qs

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Maintenance record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You are not authorized to manage asset maintenance."
            }, status=status.HTTP_403_FORBIDDEN)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Maintenance records retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Maintenance record retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        asset_id = request.data.get('asset')
        if not asset_id:
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": {"asset": ["Asset is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate asset eligibility for maintenance
        if asset.status == AssetStatus.MAINTENANCE:
            return Response({
                "code": 400,
                "message": "Asset is already under maintenance."
            }, status=status.HTTP_400_BAD_REQUEST)
        if asset.status == AssetStatus.DISPOSED:
            return Response({
                "code": 400,
                "message": "Asset cannot be sent for maintenance because it has been disposed."
            }, status=status.HTTP_400_BAD_REQUEST)
        if asset.status == AssetStatus.LOST:
            return Response({
                "code": 400,
                "message": "Asset cannot be sent for maintenance because it is lost."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check for existing active maintenance
        active_maintenance = AssetMaintenance.objects.filter(
            asset=asset,
            status__in=[MaintenanceStatus.PENDING, MaintenanceStatus.IN_PROGRESS]
        ).first()
        if active_maintenance:
            return Response({
                "code": 400,
                "message": "Active maintenance already exists for this asset."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # Determine previous status before changing asset status
        prev_status = asset.status  # available or assigned

        with transaction.atomic():
            maintenance = serializer.save(
                status=MaintenanceStatus.PENDING,
                previous_status=prev_status
            )
            asset.status = AssetStatus.MAINTENANCE
            asset.save(update_fields=['status', 'updated_at'])

        broadcast_custom_ws_event('asset_maintenance_created', {
            'model': 'AssetMaintenance',
            'id': maintenance.id,
            'asset_id': asset.id,
        })

        return Response({
            "code": 201,
            "message": "Maintenance record created successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        """Partial update of non-lifecycle fields only."""
        maintenance = self.get_object()
        if maintenance.status in [MaintenanceStatus.COMPLETED, MaintenanceStatus.CANCELLED]:
            return Response({
                "code": 400,
                "message": "Maintenance record is already {}.".format(maintenance.get_status_display().lower())
            }, status=status.HTTP_400_BAD_REQUEST)

        # Allow updating: vendor_name, technician_name, cost, remarks, maintenance_date, maintenance_type, issue_description
        allowed_fields = {'vendor_name', 'technician_name', 'cost', 'remarks',
                          'maintenance_date', 'maintenance_type', 'issue_description'}
        update_data = {k: v for k, v in request.data.items() if k in allowed_fields}

        serializer = self.get_serializer(maintenance, data=update_data, partial=True)
        if not serializer.is_valid():
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        broadcast_custom_ws_event('asset_maintenance_updated', {
            'model': 'AssetMaintenance',
            'id': maintenance.id,
        })
        return Response({
            "code": 200,
            "message": "Maintenance record updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        return Response({
            "code": 405,
            "message": "Maintenance records cannot be deleted."
        }, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    @action(detail=True, methods=['post'], url_path='start')
    def start_maintenance(self, request, pk=None):
        maintenance = self.get_object()

        if maintenance.status == MaintenanceStatus.COMPLETED:
            return Response({
                "code": 400,
                "message": "Maintenance record is already completed."
            }, status=status.HTTP_400_BAD_REQUEST)
        if maintenance.status == MaintenanceStatus.CANCELLED:
            return Response({
                "code": 400,
                "message": "Maintenance record is already cancelled."
            }, status=status.HTTP_400_BAD_REQUEST)
        if maintenance.status == MaintenanceStatus.IN_PROGRESS:
            return Response({
                "code": 400,
                "message": "Maintenance is already in progress."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            maintenance.status = MaintenanceStatus.IN_PROGRESS
            maintenance.save(update_fields=['status', 'updated_at'])
            # Ensure asset is still in maintenance status
            asset = maintenance.asset
            if asset.status != AssetStatus.MAINTENANCE:
                asset.status = AssetStatus.MAINTENANCE
                asset.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(maintenance)
        broadcast_custom_ws_event('asset_maintenance_started', {
            'model': 'AssetMaintenance',
            'id': maintenance.id,
            'asset_id': asset.id,
        })
        return Response({
            "code": 200,
            "message": "Maintenance started successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='complete')
    def complete_maintenance(self, request, pk=None):
        maintenance = self.get_object()

        if maintenance.status == MaintenanceStatus.COMPLETED:
            return Response({
                "code": 400,
                "message": "Maintenance record is already completed."
            }, status=status.HTTP_400_BAD_REQUEST)
        if maintenance.status == MaintenanceStatus.CANCELLED:
            return Response({
                "code": 400,
                "message": "Maintenance record is already cancelled."
            }, status=status.HTTP_400_BAD_REQUEST)

        completion_date = request.data.get('completion_date')
        cost = request.data.get('cost', maintenance.cost)
        remarks = request.data.get('remarks', maintenance.remarks)

        if not completion_date:
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": {"completion_date": ["Completion date is required."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        from datetime import date as dt_date
        try:
            from django.utils.dateparse import parse_date
            comp_date = parse_date(str(completion_date))
            if not comp_date:
                raise ValueError()
        except (ValueError, TypeError):
            return Response({
                "code": 400,
                "message": "Please correct the highlighted fields.",
                "errors": {"completion_date": ["Enter a valid date."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        if comp_date < maintenance.maintenance_date:
            return Response({
                "code": 400,
                "message": "Completion date cannot be before maintenance date.",
                "errors": {"completion_date": ["Completion date cannot be before maintenance date."]}
            }, status=status.HTTP_400_BAD_REQUEST)

        if cost is not None:
            try:
                from decimal import Decimal
                cost_val = Decimal(str(cost))
                if cost_val < 0:
                    return Response({
                        "code": 400,
                        "message": "Cost cannot be negative.",
                        "errors": {"cost": ["Cost cannot be negative."]}
                    }, status=status.HTTP_400_BAD_REQUEST)
            except Exception:
                return Response({
                    "code": 400,
                    "message": "Please correct the highlighted fields.",
                    "errors": {"cost": ["Enter a valid number."]}
                }, status=status.HTTP_400_BAD_REQUEST)

        asset = maintenance.asset

        with transaction.atomic():
            maintenance.status = MaintenanceStatus.COMPLETED
            maintenance.completion_date = comp_date
            if cost is not None:
                from decimal import Decimal
                maintenance.cost = Decimal(str(cost))
            if remarks is not None:
                maintenance.remarks = str(remarks).strip() or None
            maintenance.save(update_fields=['status', 'completion_date', 'cost', 'remarks', 'updated_at'])

            # Restore asset status based on previous_status
            # Check if there is still an active allocation
            has_active_alloc = AssetAllocation.objects.filter(asset=asset, is_current=True).exists()
            if has_active_alloc or maintenance.previous_status == PreviousAssetStatus.ASSIGNED:
                restored_status = AssetStatus.ASSIGNED
            else:
                restored_status = AssetStatus.AVAILABLE
            asset.status = restored_status
            asset.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(maintenance)
        broadcast_custom_ws_event('asset_maintenance_completed', {
            'model': 'AssetMaintenance',
            'id': maintenance.id,
            'asset_id': asset.id,
            'restored_status': asset.status,
        })
        return Response({
            "code": 200,
            "message": "Maintenance completed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='cancel')
    def cancel_maintenance(self, request, pk=None):
        maintenance = self.get_object()

        if maintenance.status == MaintenanceStatus.COMPLETED:
            return Response({
                "code": 400,
                "message": "Maintenance record is already completed."
            }, status=status.HTTP_400_BAD_REQUEST)
        if maintenance.status == MaintenanceStatus.CANCELLED:
            return Response({
                "code": 400,
                "message": "Maintenance record is already cancelled."
            }, status=status.HTTP_400_BAD_REQUEST)

        asset = maintenance.asset

        with transaction.atomic():
            maintenance.status = MaintenanceStatus.CANCELLED
            maintenance.save(update_fields=['status', 'updated_at'])

            # Restore asset status
            has_active_alloc = AssetAllocation.objects.filter(asset=asset, is_current=True).exists()
            if has_active_alloc or maintenance.previous_status == PreviousAssetStatus.ASSIGNED:
                restored_status = AssetStatus.ASSIGNED
            else:
                restored_status = AssetStatus.AVAILABLE
            asset.status = restored_status
            asset.save(update_fields=['status', 'updated_at'])

        serializer = self.get_serializer(maintenance)
        broadcast_custom_ws_event('asset_maintenance_cancelled', {
            'model': 'AssetMaintenance',
            'id': maintenance.id,
            'asset_id': asset.id,
            'restored_status': asset.status,
        })
        return Response({
            "code": 200,
            "message": "Maintenance cancelled successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path=r'history/(?P<asset_id>\d+)')
    def asset_maintenance_history(self, request, asset_id=None):
        asset = Asset.objects.filter(pk=asset_id).first()
        if not asset:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        records = self.get_queryset().filter(asset_id=asset_id)
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Asset maintenance history retrieved successfully.",
                "data": paginated_res.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(records, many=True)
        return Response({
            "code": 200,
            "message": "Asset maintenance history retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)



class AssetDisposalViewSet(viewsets.ModelViewSet):
    queryset = AssetDisposal.objects.select_related(
        'asset', 'asset__category', 'approved_by'
    ).all().order_by('-created_at')
    serializer_class = AssetDisposalSerializer
    permission_classes = [AssetDisposalPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = [
        'asset__asset_code', 'asset__asset_name', 'asset__serial_number',
        'disposal_type', 'reason', 'approval_reference', 'approved_by__name'
    ]

    def get_queryset(self):
        qs = super().get_queryset()

        status_param = self.request.query_params.get('status', None)
        if status_param:
            qs = qs.filter(status=status_param)

        disposal_type_param = self.request.query_params.get('disposal_type', None)
        if disposal_type_param:
            qs = qs.filter(disposal_type=disposal_type_param)

        asset_param = self.request.query_params.get('asset', None)
        if asset_param:
            qs = qs.filter(asset_id=asset_param)

        approved_by_param = self.request.query_params.get('approved_by', None)
        if approved_by_param:
            qs = qs.filter(approved_by_id=approved_by_param)

        date_from = self.request.query_params.get('date_from', None)
        if date_from:
            qs = qs.filter(disposal_date__gte=date_from)

        date_to = self.request.query_params.get('date_to', None)
        if date_to:
            qs = qs.filter(disposal_date__lte=date_to)

        return qs

    def handle_exception(self, exc):
        if isinstance(exc, models.ProtectedError):
            return Response({
                "code": 400,
                "message": "Cannot delete asset disposal record because related objects exist."
            }, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Asset disposal record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You are not authorized to manage asset disposal."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, ValidationError):
            err_dict = exc.detail if isinstance(exc.detail, dict) else {}
            first_msg = "Validation error."
            if isinstance(exc.detail, list) and exc.detail:
                first_msg = str(exc.detail[0])
            elif isinstance(exc.detail, dict) and exc.detail:
                for k, v in exc.detail.items():
                    if isinstance(v, list) and v:
                        first_msg = str(v[0])
                        break
                    elif isinstance(v, str):
                        first_msg = v
                        break
            return Response({
                "code": 400,
                "message": first_msg,
                "errors": err_dict
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset disposal records retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Asset disposal record retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = AssetDisposalCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            disposal = serializer.save()

        detail_serializer = AssetDisposalSerializer(disposal)
        broadcast_custom_ws_event('asset_disposal_created', {
            'model': 'AssetDisposal',
            'action': 'created',
            'record': detail_serializer.data
        })

        return Response({
            "code": 201,
            "message": "Disposal request created successfully.",
            "data": detail_serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch', 'put'])
    def update_request(self, request, pk=None):
        try:
            disposal = AssetDisposal.objects.select_related('asset').get(pk=pk)
        except AssetDisposal.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Asset disposal record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if disposal.status != DisposalStatus.PENDING:
            return Response({
                "code": 400,
                "message": "Only pending disposal requests can be updated."
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = AssetDisposalCreateSerializer(disposal, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            updated_disposal = serializer.save()

        detail_serializer = AssetDisposalSerializer(updated_disposal)
        broadcast_custom_ws_event('asset_disposal_updated', {
            'model': 'AssetDisposal',
            'action': 'updated',
            'record': detail_serializer.data
        })

        return Response({
            "code": 200,
            "message": "Disposal request updated successfully.",
            "data": detail_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        try:
            disposal = AssetDisposal.objects.select_related('asset').get(pk=pk)
        except AssetDisposal.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Asset disposal record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if disposal.status != DisposalStatus.PENDING:
            return Response({
                "code": 400,
                "message": "This disposal request has already been processed."
            }, status=status.HTTP_400_BAD_REQUEST)

        approval_ref = request.data.get('approval_reference', disposal.approval_reference)

        with transaction.atomic():
            disposal.status = DisposalStatus.APPROVED
            if request.user and request.user.is_authenticated:
                disposal.approved_by = request.user
            if approval_ref:
                disposal.approval_reference = str(approval_ref).strip()
            disposal.save()

        detail_serializer = AssetDisposalSerializer(disposal)
        broadcast_custom_ws_event('asset_disposal_approved', {
            'model': 'AssetDisposal',
            'action': 'approved',
            'record': detail_serializer.data
        })

        return Response({
            "code": 200,
            "message": "Disposal request approved successfully.",
            "data": detail_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        try:
            disposal = AssetDisposal.objects.select_related('asset').get(pk=pk)
        except AssetDisposal.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Asset disposal record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if disposal.status != DisposalStatus.PENDING:
            return Response({
                "code": 400,
                "message": "This disposal request has already been processed."
            }, status=status.HTTP_400_BAD_REQUEST)

        remarks = request.data.get('remarks', None)

        with transaction.atomic():
            disposal.status = DisposalStatus.REJECTED
            if remarks:
                disposal.remarks = str(remarks).strip()
            disposal.save()

        detail_serializer = AssetDisposalSerializer(disposal)
        broadcast_custom_ws_event('asset_disposal_rejected', {
            'model': 'AssetDisposal',
            'action': 'rejected',
            'record': detail_serializer.data
        })

        return Response({
            "code": 200,
            "message": "Disposal request rejected successfully.",
            "data": detail_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        try:
            disposal = AssetDisposal.objects.select_related('asset').get(pk=pk)
        except AssetDisposal.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Asset disposal record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if disposal.status != DisposalStatus.PENDING:
            return Response({
                "code": 400,
                "message": "This disposal request has already been processed."
            }, status=status.HTTP_400_BAD_REQUEST)

        remarks = request.data.get('remarks', None)

        with transaction.atomic():
            disposal.status = DisposalStatus.CANCELLED
            if remarks:
                disposal.remarks = str(remarks).strip()
            disposal.save()

        detail_serializer = AssetDisposalSerializer(disposal)
        broadcast_custom_ws_event('asset_disposal_cancelled', {
            'model': 'AssetDisposal',
            'action': 'cancelled',
            'record': detail_serializer.data
        })

        return Response({
            "code": 200,
            "message": "Disposal request cancelled successfully.",
            "data": detail_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        try:
            disposal = AssetDisposal.objects.select_related('asset').get(pk=pk)
        except AssetDisposal.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Asset disposal record not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if disposal.status != DisposalStatus.APPROVED:
            return Response({
                "code": 400,
                "message": "Only approved disposal requests can be completed."
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            asset = Asset.objects.select_for_update().get(pk=disposal.asset_id)

            if asset.status == AssetStatus.DISPOSED:
                return Response({
                    "code": 400,
                    "message": "Asset is already disposed."
                }, status=status.HTTP_400_BAD_REQUEST)

            if asset.status == AssetStatus.MAINTENANCE:
                return Response({
                    "code": 400,
                    "message": "Asset is currently under maintenance."
                }, status=status.HTTP_400_BAD_REQUEST)

            if asset.status == AssetStatus.ASSIGNED or AssetAllocation.objects.filter(asset=asset, is_current=True).exists():
                return Response({
                    "code": 400,
                    "message": "Asset is currently assigned and cannot be disposed."
                }, status=status.HTTP_400_BAD_REQUEST)

            disposal.status = DisposalStatus.COMPLETED
            disposal.completed_at = timezone.now()
            disposal.save()

            asset.status = AssetStatus.DISPOSED
            asset.save()

        detail_serializer = AssetDisposalSerializer(disposal)
        broadcast_custom_ws_event('asset_disposal_completed', {
            'model': 'AssetDisposal',
            'action': 'completed',
            'record': detail_serializer.data
        })

        return Response({
            "code": 200,
            "message": "Asset disposal completed successfully.",
            "data": detail_serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='history/(?P<asset_id>[^/.]+)')
    def history(self, request, asset_id=None):
        try:
            asset = Asset.objects.get(pk=asset_id)
        except Asset.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Asset not found."
            }, status=status.HTTP_404_NOT_FOUND)

        records = self.get_queryset().filter(asset=asset)
        page = self.paginate_queryset(records)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Asset disposal history retrieved successfully.",
                "data": paginated_res.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(records, many=True)
        return Response({
            "code": 200,
            "message": "Asset disposal history retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)
