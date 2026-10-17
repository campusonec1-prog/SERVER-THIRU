import logging
from io import BytesIO
from django.http import Http404, HttpResponse
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.lib.styles import ParagraphStyle

from common.report_utils import build_standard_college_header, build_centered_report_title
from ..models import CounsellingReport, Student
from ..serializers import CounsellingReportSerializer
from ..permissions import CounsellingReportPermission

logger = logging.getLogger(__name__)


class CounsellingReportViewSet(viewsets.ModelViewSet):
    queryset = CounsellingReport.objects.all().order_by('-report_date', '-id')
    serializer_class = CounsellingReportSerializer
    permission_classes = [CounsellingReportPermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Counselling report not found"
            }, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, NotAuthenticated):
            return Response({
                "code": 401,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_401_UNAUTHORIZED)

        if isinstance(exc, PermissionDenied):
            return Response({
                "code": 403,
                "message": "You don't have access to this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        if isinstance(exc, ValidationError):
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        self._broadcast_change(instance, 'counselling_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'counselling_updated')

    def perform_destroy(self, instance):
        report_id = instance.id
        student_id = instance.student.id
        instance.delete()
        self._broadcast_delete(report_id, student_id)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        student_id = request.query_params.get('student_id')
        semester_id = request.query_params.get('semester_id')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Counselling reports listed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Counselling report created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report deleted successfully."
        }, status=status.HTTP_200_OK)

    def _broadcast_change(self, instance, event_name):
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
                            'event': event_name,
                            'payload': CounsellingReportSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, report_id, student_id):
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
                            'event': 'counselling_deleted',
                            'payload': {
                                'id': report_id,
                                'student_id': student_id
                            }
                        }
                    }
                )
        except Exception:
            pass

    def counselling_report_pdf(self, request, *args, **kwargs):
        """Generates and streams a PDF counselling report for the selected cohort and semester."""
        req_data = getattr(request, 'data', None) or {}
        req_params = getattr(request, 'query_params', None) or getattr(request, 'GET', {})

        dept_id = req_data.get('department') or req_params.get('department')
        batch_id = req_data.get('batch') or req_params.get('batch')
        section_id = req_data.get('section') or req_params.get('section')
        program_id = req_data.get('program') or req_params.get('program')
        sem_param = req_data.get('semester') or req_params.get('semester') or 1
        header_type = req_data.get('report_header') or req_params.get('report_header')
        only_counselled_param = req_data.get('only_counselled') or req_params.get('only_counselled')

        only_counselled = str(only_counselled_param).lower() in ['true', '1', 'yes'] if only_counselled_param is not None else False

        from institution.models import Department, Batch, Section, Program, CollegeHeader, Semester
        from student.models import Student, CounsellingReport

        try:
            sem_num = int(sem_param)
        except (ValueError, TypeError):
            sem_num = 1

        department = None
        if dept_id:
            if str(dept_id).isdigit():
                department = Department.objects.filter(id=int(dept_id)).first()
            if not department:
                department = Department.objects.filter(department_code=dept_id).first()
            if not department:
                department = Department.objects.filter(department_name__iexact=dept_id).first()

        batch = None
        if batch_id:
            if str(batch_id).isdigit():
                batch = Batch.objects.filter(id=int(batch_id)).first()
            if not batch:
                batch = Batch.objects.filter(batch=batch_id).first()

        section_obj = None
        if section_id:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=int(section_id)).first()
            if not section_obj:
                section_obj = Section.objects.filter(sections__iexact=section_id).first()

        program_obj = None
        if program_id:
            if str(program_id).isdigit():
                program_obj = Program.objects.filter(id=int(program_id)).first()
            if not program_obj:
                program_obj = Program.objects.filter(program_name__iexact=program_id).first()
        elif department and getattr(department, 'program', None):
            program_obj = department.program

        college_header_obj = None
        if header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type=header_type).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        students_qs = Student.objects.select_related(
            'department', 'department__program', 'batch', 'section'
        ).filter(status__is_active=True)

        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)
        elif section_id:
            students_qs = students_qs.filter(section__sections__iexact=str(section_id))
        if program_obj:
            students_qs = students_qs.filter(department__program=program_obj)

        students = list(students_qs.order_by('roll_number', 'register_number', 'student_name'))

        records = []
        for st in students:
            cr_list = list(CounsellingReport.objects.filter(
                student=st,
                semester__semester_number=sem_num
            ).order_by('report_date', 'id'))

            if not cr_list and only_counselled:
                continue

            records.append({
                'student': st,
                'counselling_sessions': cr_list
            })

        if not records:
            return HttpResponse("No student records found matching the selected criteria.", status=400)

        # Document setup
        buffer = BytesIO()
        page_size = A4
        doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)
        story = []
        page_w = page_size[0] - 40  # 555.27 pt

        # 1. College Header (only if configured in database)
        header_table = build_standard_college_header(college_header_obj, page_w=page_w, logo_size=62)
        if header_table:
            story.append(header_table)
            story.append(Spacer(1, 6))

        # 2. Centered Report Title
        story.append(build_centered_report_title(f"STUDENT COUNSELLING REPORT — SEMESTER {sem_num}", font_size=12, leading=15))
        story.append(Spacer(1, 6))

        # 3. Metadata Table
        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'All Sections')
        batch_str = batch.batch if batch else 'All Batches'
        dept_str = department.department_name if department else 'All Departments'
        prog_str = program_obj.program_name if program_obj else (department.program.program_name if department and department.program else 'All Programs')

        lbl_bold = ParagraphStyle(name='CRLbl', fontName='Times-Bold', fontSize=9, leading=12, textColor=colors.black)
        val_norm = ParagraphStyle(name='CRVal', fontName='Times-Roman', fontSize=9, leading=12, textColor=colors.black)

        total_sessions = sum(len(r['counselling_sessions']) for r in records)
        counselled_students_count = sum(1 for r in records if len(r['counselling_sessions']) > 0)

        meta_data = [
            [Paragraph("<b>Program:</b>", lbl_bold), Paragraph(str(prog_str), val_norm),
             Paragraph("<b>Department:</b>", lbl_bold), Paragraph(str(dept_str), val_norm)],
            [Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(str(batch_str), val_norm),
             Paragraph("<b>Section:</b>", lbl_bold), Paragraph(str(sec_name), val_norm)],
            [Paragraph("<b>Semester:</b>", lbl_bold), Paragraph(f"Semester {sem_num}", val_norm),
             Paragraph("<b>Counselled Students:</b>", lbl_bold), Paragraph(f"{counselled_students_count} / {len(students)} (Total Sessions: {total_sessions})", val_norm)],
        ]
        meta_table = Table(meta_data, colWidths=[90, 185, 95, 185])
        meta_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        # 4. Data Table
        # Columns: S.No (35), Register No (100), Student Name (145), Date of Counselling (95), Remarks (180) -> Sum = 555 pt
        col_widths = [35, 100, 145, 95, 180]
        tbl_hdr_style = ParagraphStyle(name='CRTH', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1, textColor=colors.black)
        tbl_cell_center = ParagraphStyle(name='CRCC', fontName='Times-Roman', fontSize=9, leading=12, alignment=1, textColor=colors.black)
        tbl_cell_left = ParagraphStyle(name='CRCL', fontName='Times-Roman', fontSize=9, leading=12, alignment=0, textColor=colors.black)
        tbl_cell_remarks = ParagraphStyle(name='CRCRem', fontName='Times-Roman', fontSize=8.5, leading=11, alignment=0, textColor=colors.black)

        header_row = [
            Paragraph("<b>S.No</b>", tbl_hdr_style),
            Paragraph("<b>Register No</b>", tbl_hdr_style),
            Paragraph("<b>Student Name</b>", tbl_hdr_style),
            Paragraph("<b>Date of Counselling</b>", tbl_hdr_style),
            Paragraph("<b>Remarks</b>", tbl_hdr_style),
        ]
        table_rows = [header_row]

        table_styles = [
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#64748B')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ]

        current_row_idx = 1
        for i, rec in enumerate(records, start=1):
            st = rec['student']
            st_name = (st.name if hasattr(st, 'name') and st.name else (st.student_name or 'Student')).upper()
            reg_no = st.register_number or st.roll_number or '—'
            sessions = rec['counselling_sessions']

            student_start_row = current_row_idx

            if sessions:
                for k, cr in enumerate(sessions):
                    dt_str = cr.report_date.strftime('%d-%m-%Y') if cr.report_date else '—'
                    rem_str = cr.remarks or '—'
                    session_label = f"<b>[{k+1}/{len(sessions)}]</b> {dt_str}" if len(sessions) > 1 else dt_str
                    
                    if k == 0:
                        row = [
                            Paragraph(str(i), tbl_cell_center),
                            Paragraph(reg_no, tbl_cell_center),
                            Paragraph(st_name, tbl_cell_left),
                            Paragraph(session_label, tbl_cell_center),
                            Paragraph(rem_str, tbl_cell_remarks),
                        ]
                    else:
                        row = [
                            Paragraph("", tbl_cell_center),
                            Paragraph("", tbl_cell_center),
                            Paragraph("", tbl_cell_left),
                            Paragraph(session_label, tbl_cell_center),
                            Paragraph(rem_str, tbl_cell_remarks),
                        ]
                    table_rows.append(row)
                    current_row_idx += 1
            else:
                row = [
                    Paragraph(str(i), tbl_cell_center),
                    Paragraph(reg_no, tbl_cell_center),
                    Paragraph(st_name, tbl_cell_left),
                    Paragraph("—", tbl_cell_center),
                    Paragraph("<font color='#64748B'><i>No counselling recorded</i></font>", tbl_cell_remarks),
                ]
                table_rows.append(row)
                current_row_idx += 1

            student_end_row = current_row_idx - 1

            # Give subtle alternating background per student
            bg_color = colors.HexColor('#F8FAFC') if i % 2 == 0 else colors.white
            table_styles.append(('BACKGROUND', (0, student_start_row), (-1, student_end_row), bg_color))
            # Separating line below each student's sessions
            table_styles.append(('LINEBELOW', (0, student_end_row), (-1, student_end_row), 1.0, colors.HexColor('#475569')))

        report_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        report_table.setStyle(TableStyle(table_styles))
        story.append(report_table)

        # 5. Signatures Block
        story.append(Spacer(1, 26))
        sig_data = [[
            Paragraph("<b>Class In-Charge</b>", val_norm),
            Paragraph("<b>Counsellor / Mentor</b>", ParagraphStyle(name='CRSigCouns', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1)),
            Paragraph("<b>HOD / Principal</b>", ParagraphStyle(name='CRSigHOD', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2))
        ]]
        sig_table = Table(sig_data, colWidths=[185, 185, 185])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether(sig_table))

        doc.build(story)
        buffer.seek(0)

        dept_str_clean = (department.department_code or department.department_name or 'Dept').replace(' ', '_') if department else 'All'
        batch_str_clean = str(batch.batch if batch else 'Batch').replace(' ', '_')
        filename = f"Counselling_Report_Sem_{sem_num}_{dept_str_clean}_{batch_str_clean}.pdf"

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
