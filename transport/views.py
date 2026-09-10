import io
import logging
from django.http import Http404, HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

from common.pagination import CustomPageNumberPagination
from .models import Driver, Bus, TransportRoute, RouteStop, TransportExpense
from .serializers import (
    DriverSerializer,
    BusSerializer,
    TransportRouteSerializer,
    RouteStopSerializer,
    TransportExpenseSerializer
)

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))
        
        footer_text = "TEC IMS · Transport Operations · Transport Expense Statement Report"
        page_text = f"Page {self._pageNumber} of {page_count}"
        
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(20, 25, 821, 25)
        
        self.drawString(20, 14, footer_text)
        self.drawRightString(821, 14, page_text)
        self.restoreState()


logger = logging.getLogger(__name__)


def broadcast_event(model_name, event_name, payload):
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': model_name,
                        'event': event_name,
                        'payload': payload
                    }
                }
            )
    except Exception:
        pass


def extract_validation_message(exc):
    errors = exc.detail
    if isinstance(errors, dict):
        first_key = next(iter(errors))
        val = errors[first_key]
        if isinstance(val, list):
            return f"{first_key}: {val[0]}"
        return f"{first_key}: {val}"
    elif isinstance(errors, list):
        return str(errors[0])
    return str(errors)


class BaseTransportViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Requested item not found."
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

        if isinstance(exc, ValidationError):
            return Response({
                "code": 400,
                "message": extract_validation_message(exc)
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Deleted successfully."
        }, status=status.HTTP_200_OK)


class DriverViewSet(BaseTransportViewSet):
    queryset = Driver.objects.all().order_by('-id')
    serializer_class = DriverSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')

        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == 'true'))
        if search:
            qs = qs.filter(driver_name__icontains=search) | qs.filter(license_number__icontains=search) | qs.filter(phone_number__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('Driver', 'driver_created', DriverSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('Driver', 'driver_updated', DriverSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('Driver', 'driver_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Drivers listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Driver retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Driver profile created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Driver profile updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Driver deleted successfully."
        }, status=status.HTTP_200_OK)


class BusViewSet(BaseTransportViewSet):
    queryset = Bus.objects.select_related('driver', 'route').all().order_by('-id')
    serializer_class = BusSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        fuel_type = self.request.query_params.get('fuel_type')
        driver_id = self.request.query_params.get('driver_id')
        is_active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')

        if status_param:
            qs = qs.filter(status__iexact=status_param)
        if fuel_type:
            qs = qs.filter(fuel_type__iexact=fuel_type)
        if driver_id:
            qs = qs.filter(driver_id=driver_id)
        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == 'true'))
        if search:
            qs = qs.filter(bus_number__icontains=search) | qs.filter(registration_number__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('Bus', 'bus_created', BusSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('Bus', 'bus_updated', BusSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('Bus', 'bus_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Buses listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Bus retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Bus created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Bus updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Bus deleted successfully."
        }, status=status.HTTP_200_OK)


class TransportRouteViewSet(BaseTransportViewSet):
    queryset = TransportRoute.objects.all().order_by('-id')
    serializer_class = TransportRouteSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        is_active = self.request.query_params.get('is_active')
        bus_id = self.request.query_params.get('bus_id')
        search = self.request.query_params.get('search')

        if is_active is not None:
            qs = qs.filter(is_active=(is_active.lower() == 'true'))
        if bus_id:
            qs = qs.filter(bus_id=bus_id)
        if search:
            qs = qs.filter(route_name__icontains=search) | qs.filter(start_location__icontains=search) | qs.filter(end_location__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('TransportRoute', 'route_created', TransportRouteSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('TransportRoute', 'route_updated', TransportRouteSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('TransportRoute', 'route_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Routes listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Transport route created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Transport route updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Transport route deleted successfully."
        }, status=status.HTTP_200_OK)


class RouteStopViewSet(BaseTransportViewSet):
    queryset = RouteStop.objects.select_related('route', 'stop').all().order_by('route', 'stop_order')
    serializer_class = RouteStopSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        route_id = self.request.query_params.get('route_id')
        search = self.request.query_params.get('search')

        if route_id:
            qs = qs.filter(route_id=route_id)
        if search:
            qs = qs.filter(stop_name__icontains=search)
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(created_by=user, updated_by=user)
        broadcast_event('RouteStop', 'stop_created', RouteStopSerializer(instance).data)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        instance = serializer.save(updated_by=user)
        broadcast_event('RouteStop', 'stop_updated', RouteStopSerializer(instance).data)

    def perform_destroy(self, instance):
        inst_id = instance.id
        instance.delete()
        broadcast_event('RouteStop', 'stop_deleted', {'id': inst_id})

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stops listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stop retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Route stop created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stop updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super(BaseTransportViewSet, self).destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Route stop deleted successfully."
        }, status=status.HTTP_200_OK)


class TransportExpenseViewSet(BaseTransportViewSet):
    queryset = TransportExpense.objects.select_related('bus', 'bus__driver', 'incharge_driver').all()
    serializer_class = TransportExpenseSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params

        bus_id = params.get('bus_id') or params.get('vehicle_id')
        if bus_id:
            qs = qs.filter(bus_id=bus_id)

        incharge_driver_id = params.get('incharge_driver_id')
        if incharge_driver_id:
            qs = qs.filter(incharge_driver_id=incharge_driver_id)


        expense_type = params.get('expense_type')
        if expense_type:
            qs = qs.filter(expense_type__iexact=expense_type)

        payment_mode = params.get('payment_mode')
        if payment_mode:
            qs = qs.filter(payment_mode__iexact=payment_mode)

        search = params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(invoice_number__icontains=search) |
                Q(vendor__icontains=search) |
                Q(description__icontains=search) |
                Q(bus__bus_number__icontains=search) |
                Q(bus__registration_number__icontains=search)
            )

        return qs

    def list(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Transport expenses listed successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super(BaseTransportViewSet, self).retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Transport expense details retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        broadcast_event('TransportExpense', 'create', serializer.data)
        return Response({
            "code": 201,
            "message": "Transport expense created successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        broadcast_event('TransportExpense', 'update', serializer.data)
        return Response({
            "code": 200,
            "message": "Transport expense updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        expense_id = instance.id
        self.perform_destroy(instance)
        broadcast_event('TransportExpense', 'delete', {'id': expense_id})
        return Response({
            "code": 200,
            "message": "Transport expense record deleted successfully."
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='export-pdf')
    def export_pdf(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).order_by('-expense_date_time')

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=20,
            rightMargin=20,
            topMargin=20,
            bottomMargin=35
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=18,
            textColor=colors.HexColor('#0f172a')
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            textColor=colors.HexColor('#475569')
        )
        meta_style = ParagraphStyle(
            'ReportMeta',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#475569')
        )
        th_style = ParagraphStyle(
            'TableHeader',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.white,
            alignment=TA_CENTER
        )
        td_style = ParagraphStyle(
            'TableBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor('#1e293b')
        )
        tf_label = ParagraphStyle(
            'TableFooterLabel',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=10.5,
            alignment=TA_RIGHT,
            textColor=colors.HexColor('#0f172a')
        )
        tf_amount = ParagraphStyle(
            'TableFooterAmount',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=10.5,
            textColor=colors.HexColor('#0f172a')
        )

        elements = []

        # Header Title
        elements.append(Paragraph("THIRUMALAI ENGINEERING COLLEGE", subtitle_style))
        elements.append(Paragraph("TRANSPORT OPERATIONS & FLEET EXPENSE REPORT", title_style))
        elements.append(Spacer(1, 4))

        now_str = timezone.localtime(timezone.now()).strftime("%d-%m-%Y %I:%M %p")

        params = request.query_params
        active_filters = []
        if params.get('bus_id'):
            bus_obj = Bus.objects.filter(id=params.get('bus_id')).first()
            if bus_obj:
                active_filters.append(f"Vehicle: {bus_obj.bus_number} ({bus_obj.registration_number})")
        if params.get('incharge_driver_id'):
            drv_obj = Driver.objects.filter(id=params.get('incharge_driver_id')).first()
            if drv_obj:
                active_filters.append(f"Incharge: {drv_obj.driver_name}")
        if params.get('expense_type'):
            active_filters.append(f"Type: {params.get('expense_type').title()}")
        if params.get('payment_mode'):
            active_filters.append(f"Payment: {params.get('payment_mode').upper()}")
        if params.get('search'):
            active_filters.append(f"Search: \"{params.get('search')}\"")

        filter_summary_str = " | ".join(active_filters) if active_filters else "All Records (No Filters)"

        total_count = qs.count()
        total_amount = sum(float(e.amount or 0) for e in qs)

        meta_p = Paragraph(
            f"<b>Generated:</b> {now_str} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Active Filters:</b> {filter_summary_str} &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Total Count:</b> {total_count} records &nbsp;&nbsp;|&nbsp;&nbsp; "
            f"<b>Total Expense:</b> Rs. {total_amount:,.2f}",
            meta_style
        )
        elements.append(meta_p)
        elements.append(Spacer(1, 6))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e1"), spaceBefore=0, spaceAfter=8))

        # Table Header
        table_data = [[
            Paragraph("#", th_style),
            Paragraph("Date & Time", th_style),
            Paragraph("Vehicle Number", th_style),
            Paragraph("Vehicle Driver", th_style),
            Paragraph("Incharge Driver", th_style),
            Paragraph("Expense & Payment", th_style),
            Paragraph("Amount & Bill #", th_style),
            Paragraph("Vendor & Odometer", th_style),
            Paragraph("Description", th_style),
        ]]

        for idx, item in enumerate(qs, start=1):
            if item.expense_date_time:
                local_dt = timezone.localtime(item.expense_date_time) if timezone.is_aware(item.expense_date_time) else item.expense_date_time
                date_time_str = local_dt.strftime("%d-%m-%Y<br/>%I:%M %p")
            else:
                date_time_str = "-"

            bus_num = item.bus.bus_number if item.bus else "-"
            reg_num = item.bus.registration_number if item.bus else ""
            veh_str = f"<b>{bus_num}</b><br/><font color='#64748b'>({reg_num})</font>" if reg_num else f"<b>{bus_num}</b>"

            perm_driver = item.bus.driver if (item.bus and item.bus.driver) else None
            if perm_driver:
                drv_phone = f"<br/><font color='#64748b'>{perm_driver.phone_number}</font>" if perm_driver.phone_number else ""
                veh_driver_str = f"<b>{perm_driver.driver_name}</b>{drv_phone}"
            else:
                veh_driver_str = "<font color='#94a3b8'>Not Assigned</font>"

            inc_driver = item.incharge_driver
            if inc_driver:
                inc_phone = f"<br/><font color='#64748b'>{inc_driver.phone_number}</font>" if inc_driver.phone_number else ""
                veh_inc_str = f"<b>{inc_driver.driver_name}</b>{inc_phone}"
            else:
                veh_inc_str = "-"

            exp_type = (item.expense_type or "-").title()
            pay_mode = (item.payment_mode or "-").upper()
            exp_pay_str = f"<b>{exp_type}</b><br/><font color='#475569'>({pay_mode})</font>"

            amt_str = f"<b>Rs. {float(item.amount or 0):,.2f}</b>"
            inv_str = f"<br/><font color='#64748b'>#{item.invoice_number}</font>" if item.invoice_number else ""
            amt_bill_str = f"{amt_str}{inv_str}"

            vendor_str = item.vendor or "-"
            odo_str = f"<br/><font color='#0284c7'>{float(item.odometer_reading):,.1f} KM</font>" if item.odometer_reading is not None else ""
            vendor_odo_str = f"<b>{vendor_str}</b>{odo_str}"

            desc_str = item.description or "-"

            table_data.append([
                Paragraph(str(idx), td_style),
                Paragraph(date_time_str, td_style),
                Paragraph(veh_str, td_style),
                Paragraph(veh_driver_str, td_style),
                Paragraph(veh_inc_str, td_style),
                Paragraph(exp_pay_str, td_style),
                Paragraph(amt_bill_str, td_style),
                Paragraph(vendor_odo_str, td_style),
                Paragraph(desc_str, td_style),
            ])

        # Footer Row (Totals)
        table_data.append([
            Paragraph("TOTAL EXPENSE AMOUNT:", tf_label),
            Paragraph("", td_style),
            Paragraph("", td_style),
            Paragraph("", td_style),
            Paragraph("", td_style),
            Paragraph("", td_style),
            Paragraph(f"<b>Rs. {total_amount:,.2f}</b>", tf_amount),
            Paragraph("", td_style),
            Paragraph("", td_style),
        ])

        col_widths = [25, 75, 85, 95, 95, 75, 85, 110, 155]

        t_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('SPAN', (0, -1), (5, -1)),
            ('SPAN', (7, -1), (8, -1)),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor("#f1f5f9")),
        ])

        for i in range(1, len(table_data) - 1):
            if i % 2 == 0:
                t_style.add('BACKGROUND', (0, i), (-1, i), colors.HexColor("#f8fafc"))

        t = Table(table_data, colWidths=col_widths, repeatRows=1)
        t.setStyle(t_style)
        elements.append(t)

        doc.build(elements, canvasmaker=NumberedCanvas)

        pdf_value = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf_value, content_type='application/pdf')
        filename = f"Transport_Expense_Report_{timezone.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


