import logging
import os
import io
import math
import urllib.request
import datetime
from io import BytesIO
from django.http import Http404, HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from PIL import Image as PILImage

from ..models import Student, FacultyActivity, StudentAttendance
from ..serializers import FacultyActivitySerializer, StudentAttendanceSerializer
from ..permissions import AttendancePermission

from institution.models import Department, Batch, Section, Semester, Regulation, CollegeHeader
from subject.models import Subject
from timetable.models import ClassTimetable
from .marks_views import generate_report_filename

logger = logging.getLogger(__name__)


class FacultyActivityViewSet(viewsets.ModelViewSet):
    queryset = FacultyActivity.objects.select_related(
        'timetable', 
        'timetable__subject', 
        'timetable__activity_type', 
        'timetable__period', 
        'timetable__department', 
        'timetable__batch', 
        'timetable__section', 
        'timetable__day', 
        'created_by'
    ).all().order_by('-date', '-id')
    serializer_class = FacultyActivitySerializer
    permission_classes = [AttendancePermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Faculty activity not found"
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
            return Response({
                "code": 400,
                "message": str(exc.detail[0] if isinstance(exc.detail, list) else exc.detail)
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        self._broadcast_change(instance, 'activity_created')

    def perform_update(self, serializer):
        user = self.request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'activity_updated')

    def perform_destroy(self, instance):
        activity_id = instance.id
        instance.delete()
        self._broadcast_change({'id': activity_id}, 'activity_deleted')

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        user = request.user
        role_name = ""
        if user and user.is_authenticated and hasattr(user, 'role') and user.role:
            role_name = user.role.role_name.upper().replace(' ', '_')

        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        date = request.query_params.get('date')
        timetable_id = request.query_params.get('timetable_id')
        timetable_ids = request.query_params.get('timetable_ids')

        if role_name not in ['ADMIN', 'ADMINISTRATOR']:
            if not (date_from or date_to or date or timetable_id or timetable_ids):
                queryset = queryset.filter(created_by=user)

        if date:
            queryset = queryset.filter(date=date)
        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)
        if timetable_id:
            queryset = queryset.filter(timetable_id=timetable_id)
        if timetable_ids:
            id_list = [tid.strip() for tid in timetable_ids.split(',') if tid.strip().isdigit()]
            if id_list:
                queryset = queryset.filter(timetable_id__in=id_list)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
            
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Faculty activities listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Faculty activity retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Faculty activity registered successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Faculty activity updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Faculty activity deleted successfully"
        }, status=status.HTTP_200_OK)

    def _broadcast_change(self, instance, event_name):
        try:
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer
            channel_layer = get_channel_layer()
            if channel_layer:
                payload = FacultyActivitySerializer(instance).data if hasattr(instance, 'date') else instance
                async_to_sync(channel_layer.group_send)(
                    'realtime_updates',
                    {
                        'type': 'broadcast_update',
                        'data': {
                            'event': event_name,
                            'payload': payload
                        }
                    }
                )
        except Exception:
            pass


class StudentAttendanceViewSet(viewsets.ModelViewSet):
    queryset = StudentAttendance.objects.select_related('student', 'student__user', 'faculty_activity', 'created_by').all().order_by('id')
    serializer_class = StudentAttendanceSerializer
    permission_classes = [AttendancePermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Attendance record not found"
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
            return Response({
                "code": 400,
                "message": str(exc.detail[0] if isinstance(exc.detail, list) else exc.detail)
            }, status=status.HTTP_400_BAD_REQUEST)
        return super().handle_exception(exc)

    def list(self, request, *args, **kwargs):
        activity_id = request.query_params.get('faculty_activity_id')
        queryset = self.get_queryset()
        if activity_id:
            queryset = queryset.filter(faculty_activity_id=activity_id)
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Student attendance listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='submit')
    def bulk_submit(self, request):
        activity_id = request.data.get('faculty_activity_id')
        attendance_entries = request.data.get('attendance_entries')

        if not activity_id or not isinstance(attendance_entries, list):
            return Response({
                "code": 400,
                "message": "faculty_activity_id and a list of attendance_entries are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            activity = FacultyActivity.objects.get(pk=activity_id)
        except FacultyActivity.DoesNotExist:
            return Response({
                "code": 400,
                "message": f"Faculty activity with ID {activity_id} does not exist."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        saved_entries = []
        from django.db import transaction

        try:
            with transaction.atomic():
                for entry in attendance_entries:
                    student_id = entry.get('student_id')
                    status_val = entry.get('status', 'P').strip().upper()

                    if status_val not in ['P', 'AB', 'OD']:
                        raise ValidationError(f"Invalid status '{status_val}'. Allowed values are P, AB, OD.")

                    try:
                        student = Student.objects.get(pk=student_id)
                    except Student.DoesNotExist:
                        raise ValidationError(f"Student with ID {student_id} does not exist.")

                    attendance_instance, created = StudentAttendance.objects.get_or_create(
                        faculty_activity=activity,
                        student=student,
                        defaults={
                            'status': status_val,
                            'created_by': tracking_user,
                            'updated_by': tracking_user
                        }
                    )

                    if not created:
                        attendance_instance.status = status_val
                        attendance_instance.updated_by = tracking_user
                        attendance_instance.save()

                    saved_entries.append(attendance_instance)
        except ValidationError as e:
            return Response({
                "code": 400,
                "message": str(e.detail[0] if isinstance(e.detail, list) else e.detail)
            }, status=status.HTTP_400_BAD_REQUEST)

        # Websocket Broadcast
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
                            'event': 'attendance_submitted',
                            'payload': {
                                'faculty_activity_id': activity.id,
                                'count': len(saved_entries)
                            }
                        }
                    }
                )
        except Exception:
            pass

        return Response({
            "code": 200,
            "message": f"Successfully registered attendance for {len(saved_entries)} students.",
            "data": StudentAttendanceSerializer(saved_entries, many=True).data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post', 'get'], url_path='consolidated-report/pdf')
    def consolidated_attendance_report_pdf(self, request):
        """
        Consolidated Attendance Report – shows every subject's attendance for each student
        in the selected date range (no subject filter).
        """
        req_data = request.data if request.method == 'POST' else getattr(request, 'query_params', request.GET)
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        start_date_raw = req_data.get('start_date') or req_data.get('date_from')
        end_date_raw = req_data.get('end_date') or req_data.get('date_to')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        department = Department.objects.filter(id=department_id).first() if department_id else None
        batch = Batch.objects.filter(id=batch_id).first() if batch_id else None

        section_obj = None
        if section_id:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=section_id).first()
            else:
                section_obj = Section.objects.filter(sections__iexact=section_id).first()

        semester_obj = Semester.objects.filter(id=semester_id).first() if (semester_id and str(semester_id).isdigit()) else None

        college_header_obj = None
        if str(header_type).isdigit():
            college_header_obj = CollegeHeader.objects.filter(id=header_type).first()
        if not college_header_obj and header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type__iexact=str(header_type)).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        # Build students queryset
        students_qs = Student.objects.all().select_related('user')
        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)

        students = list(students_qs.order_by('roll_number', 'user__name'))
        if not students and department:
            students = list(Student.objects.filter(department=department).order_by('roll_number', 'user__name'))
        if not students:
            return HttpResponse("No students found matching the selected criteria.", status=400)

        # Build all conducted activities (no subject filter – all subjects)
        activities_qs = FacultyActivity.objects.filter(status='CONDUCTED').select_related(
            'timetable', 'timetable__subject', 'timetable__faculty'
        )
        if department:
            activities_qs = activities_qs.filter(timetable__department=department)
        if batch:
            activities_qs = activities_qs.filter(timetable__batch=batch)
        if section_obj:
            activities_qs = activities_qs.filter(timetable__section=section_obj)
        if semester_obj:
            activities_qs = activities_qs.filter(timetable__semester=semester_obj)
        elif semester_id:
            activities_qs = activities_qs.filter(timetable__semester_id=semester_id)
        if start_date_raw:
            activities_qs = activities_qs.filter(date__gte=start_date_raw)
        if end_date_raw:
            activities_qs = activities_qs.filter(date__lte=end_date_raw)

        activities = list(activities_qs.order_by('timetable__subject__subject_code', 'date', 'id'))

        # Group activities by subject, preserving order
        subject_activities = {}
        subject_objs_map = {}
        for act in activities:
            if act.timetable and act.timetable.subject:
                sub = act.timetable.subject
                if sub.id not in subject_activities:
                    subject_activities[sub.id] = []
                    subject_objs_map[sub.id] = sub
                subject_activities[sub.id].append(act)

        subjects_list = [subject_objs_map[sid] for sid in subject_activities.keys()]

        if not subjects_list:
            return HttpResponse("No conducted classes found for the selected criteria and date range.", status=400)

        # Pre-fetch attendance records
        all_act_ids = [act.id for act_list in subject_activities.values() for act in act_list]
        att_records = StudentAttendance.objects.filter(faculty_activity_id__in=all_act_ids, student__in=students)
        att_map = {(r.student_id, r.faculty_activity_id): r.status for r in att_records}

        date_range_str = f"{start_date_raw} to {end_date_raw}" if start_date_raw and end_date_raw else "—"

        # ── PDF Generation ──
        buffer = BytesIO()
        from reportlab.lib.pagesizes import A4, landscape
        page_size = A4
        doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        img_data = resp.read()
                        pil_img = PILImage.open(BytesIO(img_data))
                        out_io = BytesIO()
                        pil_img.save(out_io, format='PNG')
                        out_io.seek(0)
                        logo_flowable = RLImage(out_io, width=45, height=45)
                elif os.path.exists(logo_url):
                    pil_img = PILImage.open(logo_url)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=45, height=45)
            except Exception:
                pass

        story = []
        hdr_style = ParagraphStyle(name='ConAttHdr', fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=1, textColor=colors.black)
        college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
        hdr_parts = []
        if college_name_str:
            hdr_parts.append(college_name_str)
        hdr_parts.append("CONSOLIDATED ATTENDANCE REPORT")
        hdr_paragraph = Paragraph("<br/>".join(f"<b>{p}</b>" for p in hdr_parts), hdr_style)
        page_w = page_size[0] - 40
        if logo_flowable:
            header_table = Table([[logo_flowable, hdr_paragraph]], colWidths=[60, page_w - 60])
        else:
            header_table = Table([[hdr_paragraph]], colWidths=[page_w])
        header_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 8))

        sem_num = 1
        if semester_id and str(semester_id).isdigit():
            sem_num = int(semester_id)
        elif semester_obj and isinstance(semester_obj.id, int):
            sem_num = semester_obj.id
        year_roman = {1: 'I', 2: 'I', 3: 'II', 4: 'II', 5: 'III', 6: 'III', 7: 'IV', 8: 'IV'}.get(sem_num, 'I')
        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'A')
        batch_str = batch.batch if batch else ""
        regulation_str = ""
        if regulation_id:
            reg_obj = Regulation.objects.filter(id=regulation_id).first()
            if reg_obj:
                regulation_str = reg_obj.regulation_code

        lbl_bold = ParagraphStyle(name='ConAttLbl', fontName='Helvetica-Bold', fontSize=8, leading=10)
        val_norm = ParagraphStyle(name='ConAttVal', fontName='Helvetica', fontSize=8, leading=10)
        meta_data = [
            [Paragraph("<b>Department:</b>", lbl_bold), Paragraph(department.department_name.title() if department else "", val_norm),
             Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(batch_str, val_norm)],
            [Paragraph("<b>Year/Sem/Section:</b>", lbl_bold), Paragraph(f"{year_roman} / Sem {sem_num} / Sec {sec_name}", val_norm),
             Paragraph("<b>Regulation:</b>", lbl_bold), Paragraph(regulation_str, val_norm)],
            [Paragraph("<b>Date Range:</b>", lbl_bold), Paragraph(date_range_str, val_norm),
             Paragraph("", lbl_bold), Paragraph("", val_norm)],
        ]
        meta_table = Table(meta_data, colWidths=[95, 175, 90, 180])
        meta_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F8FAFC')),
            ('SPAN', (1, 2), (3, 2)),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        tbl_hdr_style = ParagraphStyle(name='ConAttTH', fontName='Helvetica-Bold', fontSize=6.5, leading=8, alignment=1)
        tbl_cell_center = ParagraphStyle(name='ConAttCC', fontName='Helvetica', fontSize=6.5, leading=8, alignment=1)
        tbl_cell_left = ParagraphStyle(name='ConAttCL', fontName='Helvetica', fontSize=6.5, leading=8, alignment=0)
        tbl_cell_eligible = ParagraphStyle(name='ConAttElig', fontName='Helvetica-Bold', fontSize=6.5, leading=8, alignment=1, textColor=colors.HexColor('#15803D'))
        tbl_cell_shortage = ParagraphStyle(name='ConAttShort', fontName='Helvetica-Bold', fontSize=6.5, leading=8, alignment=1, textColor=colors.HexColor('#B91C1C'))

        # Build header row
        header_row = [
            Paragraph("S.No", tbl_hdr_style),
            Paragraph("Reg. No", tbl_hdr_style),
            Paragraph("Student Name", tbl_hdr_style),
            Paragraph("Total Hrs", tbl_hdr_style),
            Paragraph("Present", tbl_hdr_style),
            Paragraph("Absent", tbl_hdr_style),
            Paragraph("OD", tbl_hdr_style),
            Paragraph("Overall %", tbl_hdr_style),
            Paragraph("Status", tbl_hdr_style),
        ]

        # Column widths
        # We have 9 columns. A4 portrait width = 595. Margins = 20*2 = 40. Usable = 555.
        # Adjusted for ~555 total:
        col_widths = [25, 70, 140, 50, 65, 75, 45, 45, 40] 

        table_rows = [header_row]
        eligible_cnt = 0
        shortage_cnt = 0

        for idx, st in enumerate(students, start=1):
            st_name = (st.user.name if st.user and st.user.name else "") or ""
            reg_no = st.register_number or st.roll_number or ""

            st_total_conducted = 0
            st_total_attended = 0
            st_total_od = 0

            for sub in subjects_list:
                act_list = subject_activities.get(sub.id, [])
                st_total_conducted += len(act_list)
                for act in act_list:
                    status = att_map.get((st.id, act.id))
                    if status in ['P', 'OD']:
                        st_total_attended += 1
                    if status == 'OD':
                        st_total_od += 1
                        
            st_total_not_attended = st_total_conducted - st_total_attended

            overall_pct = (st_total_attended / st_total_conducted * 100) if st_total_conducted > 0 else 100.0
            if overall_pct >= 75.0:
                eligible_cnt += 1
                status_p = Paragraph("OK", tbl_cell_eligible)
            else:
                shortage_cnt += 1
                status_p = Paragraph("Short", tbl_cell_shortage)

            row = [
                Paragraph(str(idx), tbl_cell_center),
                Paragraph(reg_no, tbl_cell_center),
                Paragraph(st_name.upper(), tbl_cell_left),
                Paragraph(str(st_total_conducted), tbl_cell_center),
                Paragraph(str(st_total_attended), tbl_cell_center),
                Paragraph(str(st_total_not_attended), tbl_cell_center),
                Paragraph(str(st_total_od), tbl_cell_center),
                Paragraph(f"<b>{overall_pct:.1f}%</b>", tbl_cell_center),
                status_p,
            ]
            table_rows.append(row)

        att_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        ts = [
            ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING', (0, 0), (-1, -1), 2),
            ('RIGHTPADDING', (0, 0), (-1, -1), 2),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ]
        for i in range(1, len(table_rows)):
            if i % 2 == 0:
                ts.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F8FAFC')))
        att_table.setStyle(TableStyle(ts))
        story.append(att_table)
        story.append(Spacer(1, 15))

        # Summary table
        tot_students = len(students)
        summary_data = [
            [Paragraph("<b>Total Students</b>", tbl_hdr_style), Paragraph("<b>Eligible (>= 75%)</b>", tbl_hdr_style),
             Paragraph("<b>Shortage (< 75%)</b>", tbl_hdr_style), Paragraph("<b>Class Eligibility %</b>", tbl_hdr_style)],
            [Paragraph(str(tot_students), tbl_cell_center), Paragraph(str(eligible_cnt), tbl_cell_eligible),
             Paragraph(str(shortage_cnt), tbl_cell_shortage),
             Paragraph(f"<b>{round(eligible_cnt / tot_students * 100, 2) if tot_students > 0 else 0:.2f}%</b>", tbl_cell_center)],
        ]
        summ_table = Table(summary_data, colWidths=[135, 135, 135, 135])
        summ_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F5F5F5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(summ_table)
        story.append(Spacer(1, 35))

        sig_data = [[
            Paragraph("<b>Class In-Charge</b>", val_norm),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='ConAttSigHOD', fontName='Helvetica-Bold', fontSize=8.5, alignment=1)),
            Paragraph("<b>Principal</b>", ParagraphStyle(name='ConAttSigPrin', fontName='Helvetica-Bold', fontSize=8.5, alignment=2)),
        ]]
        sig_table = Table(sig_data, colWidths=[180, 180, 180])
        sig_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
        story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        filename = generate_report_filename(
            "Consolidated_Attendance_Report",
            None,
            department,
            batch,
            section_obj,
            semester_id or semester_obj,
            None,
        )
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        response.write(pdf)
        return response

    @action(detail=False, methods=['post', 'get'], url_path='subject-wise-report/pdf')
    def subject_wise_attendance_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else getattr(request, 'query_params', request.GET)
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        subject_id = req_data.get('subject_id')
        start_date_raw = req_data.get('start_date') or req_data.get('date_from')
        end_date_raw = req_data.get('end_date') or req_data.get('date_to')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        print(f"DEBUG PAYLOAD: {req_data}")
        print(f"DEBUG VARS: Dept={department_id}, Batch={batch_id}, Sec={section_id}, Sem={semester_id}, Sub={subject_id}, Start={start_date_raw}, End={end_date_raw}")

        department = Department.objects.filter(id=department_id).first() if department_id else None
        batch = Batch.objects.filter(id=batch_id).first() if batch_id else None

        section_obj = None
        if section_id:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=section_id).first()
            else:
                section_obj = Section.objects.filter(sections__iexact=section_id).first()

        semester_obj = Semester.objects.filter(id=semester_id).first() if (semester_id and str(semester_id).isdigit()) else None
        subject_obj = Subject.objects.filter(id=subject_id).first() if subject_id else None

        college_header_obj = None
        if str(header_type).isdigit():
            college_header_obj = CollegeHeader.objects.filter(id=header_type).first()
        if not college_header_obj and header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type__iexact=str(header_type)).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        students_qs = Student.objects.all().select_related('user')
        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)

        students = list(students_qs.order_by('roll_number', 'user__name'))
        if not students and department:
            students = list(Student.objects.filter(department=department).order_by('roll_number', 'user__name'))
        if not students:
            return HttpResponse("No students found matching the selected criteria.", status=400)

        activities_qs = FacultyActivity.objects.filter(status='CONDUCTED').select_related(
            'timetable', 'timetable__subject', 'timetable__faculty'
        )
        if department:
            activities_qs = activities_qs.filter(timetable__department=department)
        if batch:
            activities_qs = activities_qs.filter(timetable__batch=batch)
        if section_obj:
            activities_qs = activities_qs.filter(timetable__section=section_obj)
        if semester_obj:
            activities_qs = activities_qs.filter(timetable__semester=semester_obj)
        elif semester_id:
            activities_qs = activities_qs.filter(timetable__semester_id=semester_id)
        if subject_obj:
            activities_qs = activities_qs.filter(timetable__subject=subject_obj)

        if start_date_raw:
            activities_qs = activities_qs.filter(date__gte=start_date_raw)
        if end_date_raw:
            activities_qs = activities_qs.filter(date__lte=end_date_raw)

        activities = list(activities_qs.order_by('date', 'id'))

        subject_activities = {}
        subject_objs_map = {}
        for act in activities:
            if act.timetable and act.timetable.subject:
                sub = act.timetable.subject
                if sub.id not in subject_activities:
                    subject_activities[sub.id] = []
                    subject_objs_map[sub.id] = sub
                subject_activities[sub.id].append(act)

        if not subject_activities:
            subjects_qs = Subject.objects.all()
            if department:
                subjects_qs = subjects_qs.filter(department=department)
            if semester_obj:
                subjects_qs = subjects_qs.filter(semester=semester_obj)
            elif semester_id:
                subjects_qs = subjects_qs.filter(semester_id=semester_id)
            if subject_obj:
                subjects_qs = subjects_qs.filter(id=subject_obj.id)
            for sub in subjects_qs.order_by('subject_code'):
                subject_activities[sub.id] = []
                subject_objs_map[sub.id] = sub

        subjects_list = [subject_objs_map[sid] for sid in subject_activities.keys()]

        all_act_ids = [act.id for act_list in subject_activities.values() for act in act_list]
        att_records = StudentAttendance.objects.filter(faculty_activity_id__in=all_act_ids, student__in=students)
        att_map = {(r.student_id, r.faculty_activity_id): r.status for r in att_records}

        start_d_str = str(start_date_raw) if start_date_raw else (activities[0].date.strftime('%d/%m/%Y') if activities else "—")
        end_d_str = str(end_date_raw) if end_date_raw else (activities[-1].date.strftime('%d/%m/%Y') if activities else "—")
        date_range_str = f"{start_d_str} to {end_d_str}" if start_d_str != end_d_str else start_d_str

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=25, rightMargin=25, topMargin=25, bottomMargin=25)

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        img_data = resp.read()
                        pil_img = PILImage.open(BytesIO(img_data))
                        out_io = BytesIO()
                        pil_img.save(out_io, format='PNG')
                        out_io.seek(0)
                        logo_flowable = RLImage(out_io, width=45, height=45)
                elif os.path.exists(logo_url):
                    pil_img = PILImage.open(logo_url)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=45, height=45)
            except Exception:
                pass

        story = []
        hdr_style = ParagraphStyle(name='SubAttHdr', fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=1, textColor=colors.black)
        college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""

        hdr_parts = []
        if college_name_str:
            hdr_parts.append(college_name_str)
        hdr_parts.append("SUBJECT-WISE ATTENDANCE REPORT")

        hdr_paragraph = Paragraph("<br/>".join(f"<b>{p}</b>" for p in hdr_parts), hdr_style)
        if logo_flowable:
            header_table = Table([[logo_flowable, hdr_paragraph]], colWidths=[60, 480])
        else:
            header_table = Table([[hdr_paragraph]], colWidths=[540])
        header_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 8))

        sem_num = 1
        if semester_id and str(semester_id).isdigit():
            sem_num = int(semester_id)
        elif semester_obj and isinstance(semester_obj.id, int):
            sem_num = semester_obj.id
        year_roman = {1: 'I', 2: 'I', 3: 'II', 4: 'II', 5: 'III', 6: 'III', 7: 'IV', 8: 'IV'}.get(sem_num, 'I')
        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'A')
        batch_str = batch.batch if batch else ""
        regulation_str = ""
        if regulation_id:
            reg_obj = Regulation.objects.filter(id=regulation_id).first()
            if reg_obj:
                regulation_str = reg_obj.regulation_code

        # Determine Subject & Subject Handler
        if subject_obj:
            subject_name_str = f"{subject_obj.subject_code} - {subject_obj.subject_name}" if subject_obj.subject_code else subject_obj.subject_name
        elif subjects_list:
            if len(subjects_list) == 1:
                sub = subjects_list[0]
                subject_name_str = f"{sub.subject_code} - {sub.subject_name}" if sub.subject_code else sub.subject_name
            else:
                subject_name_str = ", ".join(sub.subject_code for sub in subjects_list if sub.subject_code) or "All Subjects"
        else:
            subject_name_str = "—"

        handler_names = set()
        for act in activities:
            if act.timetable and act.timetable.faculty:
                fac = act.timetable.faculty
                fac_name = getattr(fac, 'name', None) or getattr(fac, 'username', None) or str(fac)
                if fac_name:
                    handler_names.add(fac_name)

        if not handler_names:
            tts_qs = ClassTimetable.objects.all()
            if subject_obj:
                tts_qs = tts_qs.filter(subject=subject_obj)
            elif subjects_list:
                tts_qs = tts_qs.filter(subject__in=subjects_list)
            if department:
                tts_qs = tts_qs.filter(department=department)
            if section_obj:
                tts_qs = tts_qs.filter(section=section_obj)
            if semester_obj:
                tts_qs = tts_qs.filter(semester=semester_obj)

            for tt in tts_qs.select_related('faculty'):
                if tt.faculty:
                    fac = tt.faculty
                    fac_name = getattr(fac, 'name', None) or getattr(fac, 'username', None) or str(fac)
                    if fac_name:
                        handler_names.add(fac_name)

        subject_handler_str = ", ".join(sorted(handler_names)) if handler_names else "—"

        lbl_bold = ParagraphStyle(name='SubAttLbl', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.black)
        val_norm = ParagraphStyle(name='SubAttVal', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.black)

        meta_data = [
            [
                Paragraph("<b>Department:</b>", lbl_bold), Paragraph(department.department_name.title() if department else "", val_norm),
                Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(batch_str, val_norm),
            ],
            [
                Paragraph("<b>Year/Sem/Section:</b>", lbl_bold), Paragraph(f"{year_roman} / Sem {sem_num} / Sec {sec_name}", val_norm),
                Paragraph("<b>Regulation:</b>", lbl_bold), Paragraph(regulation_str, val_norm),
            ],
            [
                Paragraph("<b>Subject:</b>", lbl_bold), Paragraph(subject_name_str, val_norm),
                Paragraph("<b>Subject Handler:</b>", lbl_bold), Paragraph(subject_handler_str, val_norm),
            ],
            [
                Paragraph("<b>Date Range:</b>", lbl_bold), Paragraph(date_range_str, val_norm),
                Paragraph("", lbl_bold), Paragraph("", val_norm),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[95, 175, 90, 180])
        meta_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#F8FAFC')),
            ('SPAN', (1,3), (3,3)),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        tbl_hdr_style = ParagraphStyle(name='SubAttTH', fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1, textColor=colors.black)
        tbl_cell_center = ParagraphStyle(name='SubAttCC', fontName='Helvetica', fontSize=7.5, leading=9, alignment=1, textColor=colors.black)
        tbl_cell_left = ParagraphStyle(name='SubAttCL', fontName='Helvetica', fontSize=7.5, leading=9, alignment=0, textColor=colors.black)
        tbl_cell_eligible = ParagraphStyle(name='SubAttElig', fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor('#15803D'))
        tbl_cell_shortage = ParagraphStyle(name='SubAttShort', fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1, textColor=colors.HexColor('#B91C1C'))

        table_header = [
            Paragraph("S.No", tbl_hdr_style),
            Paragraph("Reg. No", tbl_hdr_style),
            Paragraph("Student Name", tbl_hdr_style),
            Paragraph("Total Hours", tbl_hdr_style),
            Paragraph("Attended Hours", tbl_hdr_style),
            Paragraph("Total OD", tbl_hdr_style),
            Paragraph("Overall %", tbl_hdr_style),
            Paragraph("Status", tbl_hdr_style),
        ]

        table_rows = [table_header]
        col_widths = [25, 75, 155, 55, 60, 50, 55, 65]

        eligible_cnt = 0
        shortage_cnt = 0

        for idx, st in enumerate(students, start=1):
            st_name = (st.user.name if st.user and st.user.name else (st.user.username if st.user else "")) or ""
            reg_no = st.register_number or st.roll_number or ""

            st_total_conducted = 0
            st_total_attended = 0
            st_total_od = 0

            for sub in subjects_list:
                act_list = subject_activities.get(sub.id, [])
                sub_conducted = len(act_list)
                sub_attended = sum(1 for act in act_list if att_map.get((st.id, act.id)) in ['P', 'OD'])
                sub_od = sum(1 for act in act_list if att_map.get((st.id, act.id)) == 'OD')

                st_total_conducted += sub_conducted
                st_total_attended += sub_attended
                st_total_od += sub_od

            overall_pct = (st_total_attended / st_total_conducted * 100) if st_total_conducted > 0 else 100.0
            if overall_pct >= 75.0:
                eligible_cnt += 1
                status_p = Paragraph("Satisfactory", tbl_cell_eligible)
            else:
                shortage_cnt += 1
                status_p = Paragraph("Shortage", tbl_cell_shortage)

            row_cells = [
                Paragraph(str(idx), tbl_cell_center),
                Paragraph(reg_no, tbl_cell_center),
                Paragraph(st_name.upper(), tbl_cell_left),
                Paragraph(str(st_total_conducted), tbl_cell_center),
                Paragraph(str(st_total_attended), tbl_cell_center),
                Paragraph(str(st_total_od), tbl_cell_center),
                Paragraph(f"<b>{overall_pct:.1f}%</b>", tbl_cell_center),
                status_p
            ]

            table_rows.append(row_cells)

        att_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        ts = [
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 2),
            ('RIGHTPADDING', (0,0), (-1,-1), 2),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
        ]
        for i in range(1, len(table_rows)):
            if i % 2 == 0:
                ts.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F8FAFC')))
        att_table.setStyle(TableStyle(ts))
        story.append(att_table)
        story.append(Spacer(1, 15))

        tot_students = len(students)
        summary_data = [
            [
                Paragraph("<b>Total Students</b>", tbl_hdr_style),
                Paragraph("<b>Eligible (>= 75%)</b>", tbl_hdr_style),
                Paragraph("<b>Shortage (< 75%)</b>", tbl_hdr_style),
                Paragraph("<b>Class Eligibility %</b>", tbl_hdr_style),
            ],
            [
                Paragraph(str(tot_students), tbl_cell_center),
                Paragraph(str(eligible_cnt), tbl_cell_eligible),
                Paragraph(str(shortage_cnt), tbl_cell_shortage),
                Paragraph(f"<b>{round(eligible_cnt / tot_students * 100, 2) if tot_students > 0 else 0:.2f}%</b>", tbl_cell_center),
            ]
        ]
        summ_table = Table(summary_data, colWidths=[135, 135, 135, 135])
        summ_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F5F5F5')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(summ_table)

        story.append(Spacer(1, 35))
        sig_data = [[
            Paragraph("<b>Class In-Charge</b>", val_norm),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='AttSigHOD', fontName='Helvetica-Bold', fontSize=8.5, alignment=1)),
            Paragraph("<b>Principal</b>", ParagraphStyle(name='AttSigPrin', fontName='Helvetica-Bold', fontSize=8.5, alignment=2))
        ]]
        sig_table = Table(sig_data, colWidths=[180, 180, 180])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        filename = generate_report_filename(
            "Subject_Wise_Attendance_Report",
            None,
            department,
            batch,
            section_obj,
            semester_id or semester_obj,
            subject_obj.subject_code if subject_obj else None
        )
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        response.write(pdf)
        return response
