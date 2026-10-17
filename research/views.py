from django.db.models import Q
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, PermissionDenied, NotAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.http import Http404
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from common.pagination import CustomPageNumberPagination
from .models import FacultyResearchProject
from .serializers import FacultyResearchProjectSerializer
from .permissions import ResearchProjectPermission
from users.models import UserDetails


def broadcast_research_project_event(event_name, data):
    channel_layer = get_channel_layer()
    if channel_layer:
        try:
            async_to_sync(channel_layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': 'FacultyResearchProject',
                        'event': event_name,
                        'data': data
                    }
                }
            )
        except Exception:
            pass


class FacultyResearchProjectViewSet(viewsets.ModelViewSet):
    serializer_class = FacultyResearchProjectSerializer
    permission_classes = [ResearchProjectPermission]
    pagination_class = CustomPageNumberPagination
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    
    search_fields = [
        'project_title',
        'project_code',
        'principal_investigator__user__name',
        'co_investigators__user__name',
        'research_area',
        'funding_agency',
        'site_name'
    ]

    filterset_fields = [
        'status',
        'project_type',
        'principal_investigator',
        'funding_agency',
        'project_start_date',
        'project_end_date'
    ]

    def get_queryset(self):
        user = self.request.user
        qs = FacultyResearchProject.objects.select_related(
            'principal_investigator',
            'principal_investigator__user',
            'principal_investigator__department',
            'created_by',
            'created_by__role',
            'updated_by',
            'updated_by__role',
        ).prefetch_related(
            'co_investigators',
            'co_investigators__user',
            'co_investigators__department'
        ).all().order_by('-created_at')

        if not user or not user.is_authenticated:
            return qs.none()

        role_name = getattr(user.role, 'role_name', '').upper() if hasattr(user, 'role') and user.role else ''

        # Admin / Superuser / Principal / Vice Principal view all
        if user.is_superuser or role_name in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'PRINCIPAL', 'VICE_PRINCIPAL']:
            return qs

        # Faculty & HOD: ONLY see research projects where they are PI, Co-Investigator, or Creator
        user_details = UserDetails.objects.filter(user=user).first()
        if user_details:
            return qs.filter(
                Q(principal_investigator=user_details) |
                Q(co_investigators=user_details) |
                Q(created_by=user)
            ).distinct()

        return qs.filter(created_by=user).distinct()

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "success": False,
                "message": "Research project not found.",
                "errors": {"detail": "Research project not found."}
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "success": False,
                "message": "Authentication credentials were not provided.",
                "errors": {"detail": "Authentication credentials were not provided."}
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "success": False,
                "message": "You are not authorized to manage research projects.",
                "errors": {"detail": "You are not authorized to manage research projects."}
            }, status=status.HTTP_403_FORBIDDEN)

        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        
        # Support faculty filter if passed via query params
        faculty_id = request.query_params.get('faculty_id') or request.query_params.get('principal_investigator')
        if faculty_id:
            queryset = queryset.filter(principal_investigator_id=faculty_id)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "success": True,
                "message": "Research projects retrieved successfully.",
                "data": paginated_res.data
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "success": True,
            "message": "Research projects retrieved successfully.",
            "data": serializer.data
        })

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            "success": True,
            "message": "Research project details retrieved successfully.",
            "data": serializer.data
        })

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            user = request.user if request.user and request.user.is_authenticated else None
            instance = serializer.save(created_by=user, updated_by=user)

        broadcast_research_project_event('research_project_created', {
            'id': instance.id,
            'title': instance.project_title,
            'status': instance.status
        })

        return Response({
            "success": True,
            "message": "Research project created successfully.",
            "data": self.get_serializer(instance).data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        with transaction.atomic():
            user = request.user if request.user and request.user.is_authenticated else None
            instance = serializer.save(updated_by=user)

        broadcast_research_project_event('research_project_updated', {
            'id': instance.id,
            'title': instance.project_title,
            'status': instance.status
        })

        return Response({
            "success": True,
            "message": "Research project updated successfully.",
            "data": self.get_serializer(instance).data
        })

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        project_id = instance.id
        project_title = instance.project_title
        
        with transaction.atomic():
            instance.delete()

        broadcast_research_project_event('research_project_deleted', {
            'id': project_id,
            'title': project_title
        })

        return Response({
            "success": True,
            "message": "Research project deleted successfully.",
            "data": {"id": project_id}
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path=r'faculty/(?P<faculty_id>\d+)')
    def faculty_projects(self, request, faculty_id=None):
        try:
            faculty = UserDetails.objects.get(pk=faculty_id)
        except UserDetails.DoesNotExist:
            return Response({
                "success": False,
                "message": "Principal investigator not found.",
                "errors": {"detail": "Principal investigator not found."}
            }, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        role_name = getattr(user.role, 'role_name', '').upper() if hasattr(user, 'role') and user.role else ''
        is_admin_user = user.is_superuser or role_name in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'PRINCIPAL', 'VICE_PRINCIPAL']
        if not is_admin_user:
            my_details = UserDetails.objects.filter(user=user).first()
            if my_details and my_details.id != faculty.id:
                return Response({
                    "success": False,
                    "message": "You are not authorized to view research projects of another faculty.",
                    "errors": {"detail": "You are not authorized to view research projects of another faculty."}
                }, status=status.HTTP_403_FORBIDDEN)

        queryset = self.filter_queryset(
            self.get_queryset().filter(principal_investigator=faculty)
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_res = self.get_paginated_response(serializer.data)
            return Response({
                "success": True,
                "message": f"Research projects for faculty {faculty.user.name if faculty.user else faculty.faculty_code} retrieved successfully.",
                "data": paginated_res.data
            })

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "success": True,
            "message": f"Research projects for faculty {faculty.user.name if faculty.user else faculty.faculty_code} retrieved successfully.",
            "data": serializer.data
        })

    def _filter_report_queryset(self, request):
        req_data = getattr(request, 'data', None) or {}
        req_params = getattr(request, 'query_params', None) or getattr(request, 'GET', {})

        dept_param = (
            req_data.get('department') or
            req_params.get('department') or
            req_data.get('department_id') or
            req_params.get('department_id')
        )

        faculty_param = (
            req_data.get('faculty_id') or
            req_params.get('faculty_id') or
            req_data.get('principal_investigator') or
            req_params.get('principal_investigator') or
            req_data.get('faculty') or
            req_params.get('faculty')
        )

        status_param = req_data.get('status') or req_params.get('status')
        type_param = (
            req_data.get('project_type') or
            req_params.get('project_type') or
            req_data.get('type') or
            req_params.get('type')
        )

        qs = FacultyResearchProject.objects.select_related(
            'principal_investigator',
            'principal_investigator__user',
            'principal_investigator__department'
        ).prefetch_related(
            'co_investigators',
            'co_investigators__user',
            'co_investigators__department'
        ).all()

        current_user = request.user if hasattr(request, 'user') and request.user.is_authenticated else None
        role_name = getattr(getattr(current_user, 'role', None), 'role_name', '').upper() if current_user else ''
        is_admin_user = current_user and (current_user.is_superuser or role_name in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'PRINCIPAL', 'VICE_PRINCIPAL'])

        from institution.models import Department
        department_obj = None
        if dept_param and str(dept_param).strip() and str(dept_param).lower() not in ['all', '']:
            dept_str = str(dept_param).strip()
            if dept_str.isdigit():
                department_obj = Department.objects.filter(id=int(dept_str)).first()
            if not department_obj:
                department_obj = Department.objects.filter(department_code=dept_str).first()
            if not department_obj:
                department_obj = Department.objects.filter(department_name__iexact=dept_str).first()

        # Authorization: HOD confinement
        if not is_admin_user and role_name == 'HOD' and current_user:
            hod_first_detail = getattr(current_user, 'user_details', None)
            hod_dept_id = getattr(hod_first_detail.first(), 'department_id', None) if hod_first_detail and hasattr(hod_first_detail, 'first') else None
            hod_depts = Department.objects.filter(Q(hod=current_user) | (Q(id=hod_dept_id) if hod_dept_id else Q()))
            hod_dept_ids = list(hod_depts.values_list('id', flat=True))

            if department_obj:
                if department_obj.id not in hod_dept_ids:
                    return None, department_obj, None, "You are not authorized to view reports for this department."
                qs = qs.filter(principal_investigator__department=department_obj)
            elif hod_dept_ids:
                qs = qs.filter(principal_investigator__department_id__in=hod_dept_ids)
        elif department_obj:
            qs = qs.filter(principal_investigator__department=department_obj)

        # Faculty filter
        faculty_obj = None
        if faculty_param and str(faculty_param).strip() and str(faculty_param).lower() not in ['all', '']:
            fac_str = str(faculty_param).strip()
            if fac_str.isdigit():
                faculty_obj = UserDetails.objects.filter(id=int(fac_str)).select_related('user', 'department').first()
            if not faculty_obj:
                faculty_obj = UserDetails.objects.filter(faculty_code=fac_str).select_related('user', 'department').first()
            if not faculty_obj:
                faculty_obj = UserDetails.objects.filter(user__name__iexact=fac_str).select_related('user', 'department').first()
            if faculty_obj:
                qs = qs.filter(Q(principal_investigator=faculty_obj) | Q(co_investigators=faculty_obj)).distinct()

        # Status filter
        if status_param and str(status_param).strip() and str(status_param).lower() not in ['all', '']:
            qs = qs.filter(status__iexact=str(status_param).strip())

        # Type filter
        if type_param and str(type_param).strip() and str(type_param).lower() not in ['all', '']:
            qs = qs.filter(project_type__iexact=str(type_param).strip())

        qs = qs.order_by('principal_investigator__department__department_name', 'principal_investigator__user__name', '-project_start_date')
        return qs, department_obj, faculty_obj, None

    @action(detail=False, methods=['get', 'post'], url_path='report/data')
    def report_data(self, request, *args, **kwargs):
        qs, department_obj, faculty_obj, error_msg = self._filter_report_queryset(request)
        if error_msg:
            return Response({"success": False, "message": error_msg}, status=status.HTTP_403_FORBIDDEN)
        
        projects = list(qs)
        total_sanctioned = sum([p.sanctioned_amount or 0 for p in projects])
        unique_depts = set([p.principal_investigator.department_id for p in projects if p.principal_investigator and p.principal_investigator.department_id])
        unique_faculty = set([p.principal_investigator_id for p in projects if p.principal_investigator_id])

        data = []
        for p in projects:
            pi = p.principal_investigator
            co_list = [co.user.name for co in p.co_investigators.all() if co.user]
            data.append({
                'id': p.id,
                'project_code': p.project_code,
                'project_title': p.project_title,
                'faculty_name': pi.user.name if pi and pi.user else (pi.faculty_code if pi else '—'),
                'faculty_code': pi.faculty_code if pi else '—',
                'department_name': pi.department.department_name if pi and pi.department else '—',
                'designation': pi.designation if pi else '—',
                'co_investigators': co_list,
                'external_co_investigators': p.external_co_investigators or [],
                'research_area': p.research_area,
                'project_type': p.project_type,
                'funding_agency': p.funding_agency or '—',
                'sanctioned_amount': float(p.sanctioned_amount or 0),
                'project_start_date': str(p.project_start_date) if p.project_start_date else '—',
                'project_end_date': str(p.project_end_date) if p.project_end_date else 'Ongoing',
                'status': p.status,
                'reference_url': p.reference_url or '',
            })

        return Response({
            "success": True,
            "data": {
                "projects": data,
                "stats": {
                    "total_count": len(projects),
                    "total_sanctioned_amount": float(total_sanctioned),
                    "department_count": len(unique_depts),
                    "faculty_count": len(unique_faculty)
                }
            }
        })

    @action(detail=False, methods=['get', 'post'], url_path='report/pdf')
    def report_pdf(self, request, *args, **kwargs):
        import datetime
        from io import BytesIO
        from django.http import HttpResponse
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from common.report_utils import build_standard_college_header, build_centered_report_title
        from institution.models import CollegeHeader

        req_data = getattr(request, 'data', None) or {}
        req_params = getattr(request, 'query_params', None) or getattr(request, 'GET', {})

        qs, department_obj, faculty_obj, error_msg = self._filter_report_queryset(request)
        if error_msg:
            return HttpResponse(error_msg, status=403)

        projects = list(qs)
        if not projects:
            return HttpResponse("No research & development projects found matching the selected criteria.", status=400)

        # College Header resolution
        header_type = (
            req_data.get('report_header') or
            req_params.get('report_header') or
            req_data.get('header_id') or
            req_params.get('header_id')
        )
        college_header_obj = None
        if header_type:
            if str(header_type).isdigit():
                college_header_obj = CollegeHeader.objects.filter(id=int(header_type)).first()
            if not college_header_obj:
                college_header_obj = CollegeHeader.objects.filter(header_type=header_type).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        # ── PDF Setup (Standard Portrait A4) ──
        buffer = BytesIO()
        page_size = A4
        doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
        story = []
        page_w = page_size[0] - 40  # 555.27 pt

        # 1. College Header Box
        header_table = build_standard_college_header(college_header_obj, page_w=page_w, logo_size=60)
        if header_table:
            story.append(header_table)
            story.append(Spacer(1, 6))

        # 2. Report Title
        story.append(build_centered_report_title("FACULTY RESEARCH & DEVELOPMENT (R & D) REPORT", font_size=12, leading=15))
        story.append(Spacer(1, 6))

        # 3. Report Metadata & Criteria Box
        status_param = req_data.get('status') or req_params.get('status')
        type_param = req_data.get('project_type') or req_params.get('project_type') or req_data.get('type') or req_params.get('type')

        dept_display = department_obj.department_name if department_obj else "All Departments"
        fac_display = f"{faculty_obj.user.name} ({faculty_obj.faculty_code})" if faculty_obj and faculty_obj.user else ("All Faculty Members" if not faculty_obj else faculty_obj.faculty_code)
        status_display = str(status_param).title() if status_param and str(status_param).lower() != 'all' else "All Statuses"
        type_display = str(type_param).title() if type_param and str(type_param).lower() != 'all' else "All Project Types"
        total_sanctioned = sum([p.sanctioned_amount or 0 for p in projects])

        lbl_bold = ParagraphStyle('RDMetaLbl', fontName='Times-Bold', fontSize=8, leading=10.5, textColor=colors.HexColor('#0F172A'))
        val_norm = ParagraphStyle('RDMetaVal', fontName='Times-Roman', fontSize=8, leading=10.5, textColor=colors.HexColor('#1E293B'))

        meta_data = [
            [
                Paragraph("<b>Department:</b>", lbl_bold), Paragraph(dept_display, val_norm),
                Paragraph("<b>Project Status:</b>", lbl_bold), Paragraph(status_display, val_norm),
                Paragraph("<b>Total Projects:</b>", lbl_bold), Paragraph(f"<b>{len(projects)}</b>", val_norm)
            ],
            [
                Paragraph("<b>Faculty / PI:</b>", lbl_bold), Paragraph(fac_display, val_norm),
                Paragraph("<b>Project Type:</b>", lbl_bold), Paragraph(type_display, val_norm),
                Paragraph("<b>Total Grants:</b>", lbl_bold), Paragraph(f"<b>Rs. {total_sanctioned:,.2f}</b>", val_norm)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[70, 135, 75, 110, 80, 85])
        meta_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (4, 0), (4, -1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        # 4. Table Styles
        tbl_hdr = ParagraphStyle('RDTH', fontName='Times-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.black)
        tbl_cell_center = ParagraphStyle('RDTCC', fontName='Times-Roman', fontSize=7.5, leading=9.5, alignment=1, textColor=colors.black)
        tbl_cell_left = ParagraphStyle('RDTCL', fontName='Times-Roman', fontSize=7.5, leading=9.5, alignment=0, textColor=colors.black)
        tbl_cell_right = ParagraphStyle('RDTCR', fontName='Times-Roman', fontSize=7.5, leading=9.5, alignment=2, textColor=colors.black)

        # 5. Columns & Widths for Standard Portrait A4 (Total = 555 pt)
        # S.No (25), Faculty/PI (105), Dept (80), Title & Area (185), Type & Agency (85), Amount & Status (75)
        col_widths = [25, 105, 80, 185, 85, 75]

        header_row = [
            Paragraph("<b>S.No</b>", tbl_hdr),
            Paragraph("<b>Faculty / PI & Code</b>", tbl_hdr),
            Paragraph("<b>Department</b>", tbl_hdr),
            Paragraph("<b>Project / Paper Title & Area</b>", tbl_hdr),
            Paragraph("<b>Type & Agency</b>", tbl_hdr),
            Paragraph("<b>Amount & Status</b>", tbl_hdr),
        ]
        table_rows = [header_row]

        status_colors = {
            'COMPLETED': '#15803D',
            'ONGOING': '#1D4ED8',
            'PROPOSED': '#B45309',
            'CANCELLED': '#B91C1C',
        }

        for idx, p in enumerate(projects, start=1):
            pi = p.principal_investigator
            pi_name = (pi.user.name.upper() if pi and pi.user else (pi.faculty_code if pi else '—'))
            pi_code = f"Code: {pi.faculty_code}" if pi and pi.faculty_code else ""
            pi_desig = f"<font color='#64748B'>{pi.designation}</font>" if pi and pi.designation else ""
            pi_cell_text = f"<b>{pi_name}</b>" + (f"<br/>{pi_code}" if pi_code else "") + (f"<br/>{pi_desig}" if pi_desig else "")

            dept_name = pi.department.department_name if pi and pi.department else '—'

            # Project / Paper Title with Code & Area
            p_code_str = f"<font color='#4F46E5'>[{p.project_code}]</font> " if p.project_code else ""
            area_str = f"<br/><font color='#475569'>Area: {p.research_area}</font>" if p.research_area else ""
            title_cell_text = f"{p_code_str}<b>{p.project_title}</b>{area_str}"

            # Type & Agency
            type_str = f"<b>{p.project_type}</b>"
            agency_str = f"<br/><font color='#475569'>{p.funding_agency}</font>" if p.funding_agency else ""
            type_agency_cell = f"{type_str}{agency_str}"

            # Amount & Status
            amt_val = p.sanctioned_amount or 0
            amt_str = f"Rs. {amt_val:,.2f}" if amt_val > 0 else "Non-Funded"
            st_upper = (p.status or 'Proposed').upper()
            st_color = status_colors.get(st_upper, '#334155')
            status_badge = f"<br/><font color='{st_color}'><b>● {p.status}</b></font>"
            amt_status_cell = f"{amt_str}{status_badge}"

            table_rows.append([
                Paragraph(str(idx), tbl_cell_center),
                Paragraph(pi_cell_text, tbl_cell_left),
                Paragraph(dept_name, tbl_cell_left),
                Paragraph(title_cell_text, tbl_cell_left),
                Paragraph(type_agency_cell, tbl_cell_left),
                Paragraph(amt_status_cell, tbl_cell_center),
            ])

        # Total Summary Row at bottom
        summary_row = [
            Paragraph("", tbl_cell_center),
            Paragraph("<b>TOTAL</b>", tbl_hdr),
            Paragraph(f"<b>{len(projects)} Items</b>", tbl_hdr),
            Paragraph("", tbl_cell_left),
            Paragraph("", tbl_cell_left),
            Paragraph(f"<b>Rs. {total_sanctioned:,.2f}</b>", tbl_hdr),
        ]
        table_rows.append(summary_row)

        rd_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        ts = [
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#64748B')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            # Summary row styling
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F1F5F9')),
            ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#0F172A')),
        ]
        for r in range(1, len(table_rows) - 1):
            if r % 2 == 0:
                ts.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor('#F8FAFC')))
        rd_table.setStyle(TableStyle(ts))
        story.append(rd_table)

        doc.build(story)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        filename = f"Faculty_RD_Report_{dept_display.replace(' ', '_')}.pdf" if department_obj else "Faculty_RD_Report.pdf"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
