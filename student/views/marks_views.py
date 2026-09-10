import os
import io
import math
import urllib.request
import datetime
from io import BytesIO

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.db import transaction

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image as RLImage
from PIL import Image as PILImage

from ..models import Student, Marks, GradeSystem
from ..serializers import MarksSerializer
from ..permissions import MarksPermission

from institution.models import Department, Batch, Section, Semester, Regulation, CollegeHeader, ExamType, Exam
from subject.models import Subject
from timetable.models import ClassTimetable, ExamTimetable


class MarksViewSet(viewsets.ViewSet):
    permission_classes = [MarksPermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Marks records not found."
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
                "message": str(exc.detail)
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def list(self, request):
        queryset = Marks.objects.select_related('student', 'student__user', 'student__department', 'student__batch', 'student__section', 'subject', 'subject__semester', 'exam', 'exam__exam_type', 'created_by').all().order_by('id')
        
        user = request.user
        role_name = ""
        if user and user.is_authenticated and hasattr(user, 'role') and user.role:
            role_name = user.role.role_name.upper().replace(' ', '_')
            
        exam_id = request.query_params.get('exam_id')
        subject_id = request.query_params.get('subject_id')
        subject_category = request.query_params.get('subject_category')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')

        if role_name not in ['ADMIN', 'ADMINISTRATOR']:
            if not (exam_id or subject_id):
                queryset = queryset.filter(created_by=user)

        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if subject_category:
            queryset = queryset.filter(subject_category=subject_category)
        if batch_id:
            queryset = queryset.filter(student__batch_id=batch_id)
        if section_id:
            if str(section_id).isdigit():
                queryset = queryset.filter(student__section_id=section_id)
            else:
                queryset = queryset.filter(student__section__sections__iexact=section_id)

        raw_data = list(queryset.values(
            'id', 'student_id', 'exam_id', 'subject_id', 'subject_category', 'marks_obtained',
            'created_at', 'updated_at', 'created_by_id', 'updated_by_id',
            'student__roll_number', 'student__register_number', 'student__user__name',
            'student__department_id', 'student__department__department_name',
            'student__batch_id', 'student__batch__batch',
            'student__section_id', 'student__section__sections',
            'exam__exam_name', 'subject__subject_name', 'subject__subject_code', 'subject__semester_id',
            'created_by__name'
        ))

        data = []
        for m in raw_data:
            sec = m['student__section__sections']
            sec_str = ", ".join(sec) if isinstance(sec, list) else (str(sec) if sec else "")
            data.append({
                'id': m['id'],
                'student_id': m['student_id'],
                'exam_id': m['exam_id'],
                'subject_id': m['subject_id'],
                'subject_category': m['subject_category'],
                'marks_obtained': str(m['marks_obtained']) if m['marks_obtained'] is not None else None,
                'created_at': m['created_at'].isoformat() if m['created_at'] else None,
                'updated_at': m['updated_at'].isoformat() if m['updated_at'] else None,
                'created_by': m['created_by_id'],
                'updated_by': m['updated_by_id'],
                'student_roll': m['student__roll_number'],
                'student_register': m['student__register_number'],
                'student_name': m['student__user__name'] or "Unknown",
                'department_id': m['student__department_id'],
                'department_name': m['student__department__department_name'] or "",
                'batch_id': m['student__batch_id'],
                'batch_name': m['student__batch__batch'] or "",
                'section_id': m['student__section_id'],
                'section_name': sec_str,
                'exam_name': m['exam__exam_name'] or "",
                'subject_name': m['subject__subject_name'] or "",
                'subject_code': m['subject__subject_code'] or "",
                'semester_id': m['subject__semester_id'],
                'entered_by_name': m['created_by__name'] or "—",
            })

        return Response({
            "code": 200,
            "message": "Marks records listed successfully.",
            "data": data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        # pk represents student_id
        student_id = pk
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            raise Http404()
        
        queryset = Marks.objects.select_related('student', 'student__user', 'student__department', 'student__batch', 'student__section', 'subject', 'subject__semester', 'exam', 'exam__exam_type', 'created_by').filter(student_id=student_id).order_by('id')
        serializer = MarksSerializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": f"Marks records for student {student_id} retrieved successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def create(self, request):
        # We handle bulk insert/update in create endpoint
        return self._save_marks(request, is_create=True)

    def update(self, request, pk=None):
        # Update can also do bulk update/insert of entries
        return self._save_marks(request, is_create=False)

    def _save_marks(self, request, is_create):
        exam_id = request.data.get('exam_id')
        subject_id = request.data.get('subject_id')
        subject_category = request.data.get('subject_category', 'THEORY')
        marks_entries = request.data.get('marks_entries')

        if not exam_id or not subject_id or not isinstance(marks_entries, list):
            return Response({
                "code": 400,
                "message": "exam_id, subject_id and a list of marks_entries are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check for duplicate student_id in the payload
        seen_students = set()
        for entry in marks_entries:
            student_id = entry.get('student_id')
            if student_id in seen_students:
                return Response({
                    "code": 400,
                    "message": f"Duplicate student entry with ID {student_id} found in the payload."
                }, status=status.HTTP_400_BAD_REQUEST)
            seen_students.add(student_id)

        # Validate exam and subject exist
        try:
            exam = Exam.objects.get(pk=exam_id)
            subject = Subject.objects.get(pk=subject_id)
        except Exam.DoesNotExist:
            return Response({
                "code": 400,
                "message": f"Exam with ID {exam_id} does not exist."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Subject.DoesNotExist:
            return Response({
                "code": 400,
                "message": f"Subject with ID {subject_id} does not exist."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        saved_marks = []
        broadcast_payload_entries = []

        try:
            with transaction.atomic():
                for entry in marks_entries:
                    student_id = entry.get('student_id')
                    marks_obtained = str(entry.get('marks_obtained', '')).strip()

                    if not student_id or marks_obtained == '':
                        raise ValidationError("student_id and marks_obtained are required for each entry.")

                    try:
                        student = Student.objects.get(pk=student_id)
                    except Student.DoesNotExist:
                        raise ValidationError(f"Student with ID {student_id} does not exist.")

                    if is_create:
                        if Marks.objects.filter(student=student, exam=exam, subject=subject, subject_category=subject_category).exists():
                            raise ValidationError(f"Marks record already exists for student ID {student_id}, exam ID {exam_id}, subject ID {subject_id}, and category {subject_category}.")

                    # Create or update marks record
                    marks_instance, created = Marks.objects.get_or_create(
                        student=student,
                        exam=exam,
                        subject=subject,
                        subject_category=subject_category,
                        defaults={
                            'marks_obtained': marks_obtained,
                            'created_by': tracking_user,
                            'updated_by': tracking_user
                        }
                    )

                    if not created:
                        is_admin = getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)
                        if not is_admin:
                            try:
                                role = getattr(user, 'role', None)
                                if role:
                                    user_role = role.role_name.upper().replace(' ', '_')
                                    if user_role in ['ADMIN', 'ADMINISTRATOR']:
                                        is_admin = True
                            except AttributeError:
                                pass
                        
                        if marks_instance.created_by and marks_instance.created_by != tracking_user and not is_admin:
                            raise ValidationError(f"You do not have permission to edit the marks for student ID {student_id} since they were entered by {marks_instance.created_by.name or marks_instance.created_by.username}.")

                        marks_instance.marks_obtained = marks_obtained
                        marks_instance.updated_by = tracking_user
                        marks_instance.save()

                    saved_marks.append(marks_instance)
                    broadcast_payload_entries.append({
                        'student_id': student.id,
                        'roll_number': student.roll_number,
                        'student_name': student.user.name if hasattr(student, 'user') else "",
                        'marks_obtained': marks_obtained
                    })
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
                            'event': 'marks_created' if is_create else 'marks_updated',
                            'payload': {
                                'exam_id': exam.id,
                                'exam_name': exam.exam_name,
                                'subject_id': subject.id,
                                'subject_code': subject.subject_code,
                                'entries': broadcast_payload_entries
                            }
                        }
                    }
                )
        except Exception:
            pass

        serializer = MarksSerializer(saved_marks, many=True)
        return Response({
            "code": 201 if is_create else 200,
            "message": "Marks recorded successfully." if is_create else "Marks updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED if is_create else status.HTTP_200_OK)

    @action(detail=False, methods=['post', 'get'], url_path='marksheet-report/pdf')
    def marksheet_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else request.query_params
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        subject_id = req_data.get('subject_id')
        exam_type_id = req_data.get('exam_type_id')
        exam_ids_raw = req_data.get('exam_ids')
        exam_date_raw = req_data.get('exam_date')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        # Process exam_ids
        exam_ids = []
        if isinstance(exam_ids_raw, list):
            exam_ids = exam_ids_raw
        elif isinstance(exam_ids_raw, str) and exam_ids_raw.strip():
            exam_ids = [x.strip() for x in exam_ids_raw.split(',') if x.strip()]

        department = Department.objects.filter(id=department_id).first() if department_id else None
        batch = Batch.objects.filter(id=batch_id).first() if batch_id else None
        
        section_obj = None
        if section_id:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=section_id).first()
            else:
                section_obj = Section.objects.filter(sections__iexact=section_id).first()

        semester_obj = Semester.objects.filter(id=semester_id).first() if semester_id else None
        subject_obj = Subject.objects.filter(id=subject_id).first() if subject_id else None
        exam_type_obj = ExamType.objects.filter(id=exam_type_id).first() if exam_type_id else None

        college_header_obj = None
        if str(header_type).isdigit():
            college_header_obj = CollegeHeader.objects.filter(id=header_type).first()
        if not college_header_obj and header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type__iexact=str(header_type)).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        exam_date_str = ""
        sel_exams = []
        if exam_ids:
            sel_exams = list(Exam.objects.filter(id__in=exam_ids))
        elif exam_type_id:
            sel_exams = list(Exam.objects.filter(exam_type_id=exam_type_id))

        if sel_exams:
            dates_parts = []
            for ex in sel_exams:
                tt_qs = ExamTimetable.objects.filter(exam=ex)
                if subject_obj:
                    tt_qs = tt_qs.filter(subject=subject_obj)
                if department:
                    tt_qs = tt_qs.filter(department=department)
                if batch:
                    tt_qs = tt_qs.filter(batch=batch)
                if semester_id:
                    tt_qs = tt_qs.filter(semester_id=semester_id)
                if section_obj:
                    tt_qs = tt_qs.filter(section=section_obj)
                
                dates = list(tt_qs.values_list('exam_date', flat=True).distinct().order_by('exam_date'))
                
                if not dates and subject_obj:
                    tt_qs_sub = ExamTimetable.objects.filter(exam=ex, subject=subject_obj)
                    if department:
                        tt_qs_sub = tt_qs_sub.filter(department=department)
                    dates = list(tt_qs_sub.values_list('exam_date', flat=True).distinct().order_by('exam_date'))

                if not dates and department:
                    tt_qs_dept = ExamTimetable.objects.filter(exam=ex, department=department)
                    dates = list(tt_qs_dept.values_list('exam_date', flat=True).distinct().order_by('exam_date'))

                if not dates:
                    dates = list(ExamTimetable.objects.filter(exam=ex).values_list('exam_date', flat=True).distinct().order_by('exam_date'))

                if dates:
                    min_d = dates[0].strftime("%d/%m/%Y")
                    max_d = dates[-1].strftime("%d/%m/%Y")
                    range_str = min_d if min_d == max_d else f"{min_d} to {max_d}"
                    if len(sel_exams) > 1:
                        dates_parts.append(f"{ex.exam_name}: {range_str}")
                    else:
                        dates_parts.append(range_str)

            if dates_parts:
                exam_date_str = " | ".join(dates_parts)

        if not exam_date_str and exam_date_raw:
            try:
                if '-' in str(exam_date_raw):
                    parts = str(exam_date_raw).split('-')
                    if len(parts) == 3:
                        if len(parts[0]) == 4:
                            exam_date_str = f"{parts[2].zfill(2)}/{parts[1].zfill(2)}/{parts[0]}"
                        else:
                            exam_date_str = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
                elif '/' in str(exam_date_raw):
                    exam_date_str = str(exam_date_raw)
            except Exception:
                exam_date_str = str(exam_date_raw)
        if not exam_date_str:
            exam_date_str = datetime.date.today().strftime("%d/%m/%Y")

        exam_title_str = ""
        if exam_ids:
            sel_exams = Exam.objects.filter(id__in=exam_ids)
            if sel_exams.exists():
                exam_names = [e.exam_name for e in sel_exams]
                exam_title_str = " / ".join(exam_names).upper()

        if not exam_title_str and exam_type_id:
            ex_type_obj = ExamType.objects.filter(id=exam_type_id).first()
            if ex_type_obj:
                exam_title_str = ex_type_obj.exam_type_name.upper()

        if not exam_title_str:
            exam_title_str = "INTERNAL EXAM"

        sub_code_name = ""
        if subject_obj:
            sub_code_name = f"{subject_obj.subject_code} - {subject_obj.subject_name}"
        
        handler_name = "—"
        if subject_obj:
            ct_item = ClassTimetable.objects.filter(subject=subject_obj).exclude(faculty=None).first()
            if ct_item and ct_item.faculty:
                handler_name = ct_item.faculty.name or ct_item.faculty.username
            if handler_name == "—":
                m_item = Marks.objects.filter(subject=subject_obj).exclude(created_by=None).first()
                if m_item and m_item.created_by:
                    handler_name = m_item.created_by.name or m_item.created_by.username
            if handler_name == "—":
                handler_name = "Mrs MONISHA S"

        active_grades = list(GradeSystem.objects.filter(is_active=True))

        def evaluate_result(raw_val):
            if raw_val is None or str(raw_val).strip() == '':
                return '<font color="#64748B">-</font>'
            str_val = str(raw_val).strip().upper()
            try:
                num_val = float(str_val)
                pass_entries = [g for g in active_grades if g.is_pass and g.min_mark is not None]
                min_pass = 50.0
                if pass_entries:
                    min_pass = min(float(g.min_mark) for g in pass_entries)
                if num_val >= min_pass:
                    return '<font color="#15803D"><b>PASS</b></font>'
                else:
                    return '<font color="#B91C1C"><b>FAIL</b></font>'
            except ValueError:
                matching_grade = next((g for g in active_grades if g.grade.upper() == str_val), None)
                if matching_grade:
                    if matching_grade.is_pass:
                        return '<font color="#15803D"><b>PASS</b></font>'
                    else:
                        return '<font color="#B91C1C"><b>FAIL</b></font>'
                if str_val in ['U', 'UA', 'F', 'RA', 'AB', 'ABSENT']:
                    return '<font color="#B91C1C"><b>FAIL</b></font>'
                return '<font color="#15803D"><b>PASS</b></font>'

        sem_num = 1
        if semester_id and str(semester_id).isdigit():
            sem_num = int(semester_id)
        
        roman_map = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'VIII'}
        year_names = {1: 'First Year', 2: 'First Year', 3: 'Second Year', 4: 'Second Year', 5: 'Third Year', 6: 'Third Year', 7: 'Final Year', 8: 'Final Year'}
        
        sem_roman = roman_map.get(sem_num, str(sem_num))
        year_str = year_names.get(sem_num, 'First Year')
        sec_name = section_obj.sections if section_obj else (str(section_id) if section_id else 'A')
        
        students_qs = Student.objects.all().select_related('user')
        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)

        student_ids_raw = req_data.get('student_ids') or req_data.get('student_id')
        if student_ids_raw:
            if isinstance(student_ids_raw, list):
                students_qs = students_qs.filter(id__in=student_ids_raw)
            elif str(student_ids_raw).isdigit():
                students_qs = students_qs.filter(id=student_ids_raw)
            
        students = list(students_qs.order_by('roll_number', 'user__name'))

        marks_map = {}
        if students and subject_obj:
            m_qs = Marks.objects.filter(student__in=students, subject=subject_obj)
            if exam_ids:
                m_qs = m_qs.filter(exam_id__in=exam_ids)
            for m in m_qs:
                marks_map[m.student_id] = m.marks_obtained

        has_grades = False
        for val in marks_map.values():
            if val is not None and str(val).strip() != '':
                str_val = str(val).strip().upper()
                try:
                    float(str_val)
                except ValueError:
                    has_grades = True
                    break

        col_mark_hdr = "Grade" if has_grades else "Marks(100)"

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=30,
            rightMargin=30,
            topMargin=25,
            bottomMargin=25
        )

        styles = getSampleStyleSheet()

        header_title_style = ParagraphStyle(
            name='HeaderTitleMarksheet',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=13,
            alignment=1,
            textColor=colors.black
        )
        meta_lbl_style = ParagraphStyle(
            name='MetaLblBoldMs',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )
        meta_val_style = ParagraphStyle(
            name='MetaValNormMs',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )
        tbl_header_style = ParagraphStyle(
            name='TblHeaderMs',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=9,
            alignment=1,
            textColor=colors.black
        )
        tbl_cell_center = ParagraphStyle(
            name='TblCellCenterMs',
            fontName='Helvetica',
            fontSize=7.5,
            leading=9,
            alignment=1,
            textColor=colors.black
        )
        tbl_cell_left = ParagraphStyle(
            name='TblCellLeftMs',
            fontName='Helvetica',
            fontSize=7.5,
            leading=9,
            alignment=0,
            textColor=colors.black
        )

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        img_data = response.read()
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

        if not logo_flowable:
            fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
            try:
                if os.path.exists(fallback_logo_path):
                    pil_img = PILImage.open(fallback_logo_path)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=45, height=45)
            except Exception:
                pass

        story = []

        college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
        college_header_parts = []
        if college_name_str:
            college_header_parts.append(college_name_str)
        if exam_title_str:
            college_header_parts.append(exam_title_str)
        college_header_parts.append("EXAM MARK SHEET")
        header_title_text = "<br/>".join(college_header_parts)
        title_paragraph = Paragraph(header_title_text, header_title_style)

        if logo_flowable:
            header_table_data = [[logo_flowable, title_paragraph]]
            header_table = Table(header_table_data, colWidths=[65, 470])
        else:
            header_table_data = [[title_paragraph]]
            header_table = Table(header_table_data, colWidths=[535])

        header_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        dept_name_str = department.department_name.title() if department else "Computer Science and Engineering"
        batch_str = batch.batch if batch else ""
        regulation_str = ""
        if regulation_id:
            reg_obj = Regulation.objects.filter(id=regulation_id).first()
            if reg_obj:
                regulation_str = reg_obj.regulation_code

        meta_table_data = [
            [
                Paragraph("<b>Department:</b>", meta_lbl_style), Paragraph(dept_name_str, meta_val_style),
                Paragraph("<b>Batch:</b>", meta_lbl_style), Paragraph(str(batch_str), meta_val_style)
            ],
            [
                Paragraph("<b>Year / Sem / Sec:</b>", meta_lbl_style), Paragraph(f"{year_str} / Sem {sem_num} / Sec {sec_name}", meta_val_style),
                Paragraph("<b>Date of Exam:</b>", meta_lbl_style), Paragraph(exam_date_str, meta_val_style)
            ],
            [
                Paragraph("<b>Subject Handler:</b>", meta_lbl_style), Paragraph(handler_name, meta_val_style),
                Paragraph("<b>Regulation:</b>", meta_lbl_style), Paragraph(regulation_str, meta_val_style)
            ],
            [
                Paragraph("<b>Sub Code & Name:</b>", meta_lbl_style), Paragraph(sub_code_name, meta_val_style),
                Paragraph("", meta_lbl_style), Paragraph("", meta_val_style)
            ]
        ]
        meta_table = Table(meta_table_data, colWidths=[90, 177, 85, 183])
        meta_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,0), (2,-2), colors.HexColor('#F8FAFC')),
            ('SPAN', (1,3), (3,3)),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        col_widths = [22, 48, 100, 54, 38, 11, 22, 48, 100, 54, 38]
        
        total_students = len(students)
        half = math.ceil(total_students / 2) if total_students > 0 else 1

        left_students = students[0:half]
        right_students = students[half:]

        max_rows = max(len(left_students), len(right_students))

        table_rows = []
        header_row = [
            Paragraph("<b>S. No.</b>", tbl_header_style),
            Paragraph("<b>Roll No.</b>", tbl_header_style),
            Paragraph("<b>Student Name</b>", tbl_header_style),
            Paragraph(f"<b>{col_mark_hdr}</b>", tbl_header_style),
            Paragraph("<b>Result</b>", tbl_header_style),
            Paragraph("", tbl_cell_center),
            Paragraph("<b>S. No.</b>", tbl_header_style),
            Paragraph("<b>Roll No.</b>", tbl_header_style),
            Paragraph("<b>Student Name</b>", tbl_header_style),
            Paragraph(f"<b>{col_mark_hdr}</b>", tbl_header_style),
            Paragraph("<b>Result</b>", tbl_header_style)
        ]
        table_rows.append(header_row)

        for r_i in range(max_rows):
            global_left_idx = r_i + 1
            global_right_idx = half + r_i + 1

            if r_i < len(left_students):
                s_left = left_students[r_i]
                l_sno = str(global_left_idx)
                l_roll = s_left.roll_number or ""
                l_name = s_left.user.name.upper() if (s_left.user and s_left.user.name) else ""
                raw_l_mark = marks_map.get(s_left.id)
                l_mark = str(raw_l_mark) if raw_l_mark is not None else ""
                l_res = evaluate_result(raw_l_mark)
            else:
                l_sno, l_roll, l_name, l_mark, l_res = "", "", "", "", ""

            if r_i < len(right_students):
                s_right = right_students[r_i]
                r_sno = str(global_right_idx)
                r_roll = s_right.roll_number or ""
                r_name = s_right.user.name.upper() if (s_right.user and s_right.user.name) else ""
                raw_r_mark = marks_map.get(s_right.id)
                r_mark = str(raw_r_mark) if raw_r_mark is not None else ""
                r_res = evaluate_result(raw_r_mark)
            else:
                r_sno, r_roll, r_name, r_mark, r_res = "", "", "", "", ""

            row_cells = [
                Paragraph(l_sno, tbl_cell_center),
                Paragraph(l_roll, tbl_cell_center),
                Paragraph(l_name, tbl_cell_left),
                Paragraph(l_mark, tbl_cell_center),
                Paragraph(l_res, tbl_cell_center),
                Paragraph("", tbl_cell_center),
                Paragraph(r_sno, tbl_cell_center),
                Paragraph(r_roll, tbl_cell_center),
                Paragraph(r_name, tbl_cell_left),
                Paragraph(r_mark, tbl_cell_center),
                Paragraph(r_res, tbl_cell_center)
            ]
            table_rows.append(row_cells)

        marks_table = Table(table_rows, colWidths=col_widths)
        marks_table.setStyle(TableStyle([
            ('GRID', (0,0), (4,-1), 0.5, colors.black),
            ('BACKGROUND', (0,0), (4,0), colors.HexColor('#F5F5F5')),
            ('GRID', (6,0), (10,-1), 0.5, colors.black),
            ('BACKGROUND', (6,0), (10,0), colors.HexColor('#F5F5F5')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('LEFTPADDING', (0,0), (-1,-1), 2),
            ('RIGHTPADDING', (0,0), (-1,-1), 2),
        ]))
        story.append(marks_table)

        story.append(Spacer(1, 35))
        sig_data = [[
            Paragraph("<b>Faculty In-Charge</b>", meta_val_style),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='SigHODMs', fontName='Helvetica-Bold', fontSize=8.5, alignment=2))
        ]]
        sig_table = Table(sig_data, colWidths=[265, 270])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Marksheet_Report_{datetime.date.today().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        return response

    @action(detail=False, methods=['post', 'get'], url_path='consolidated-marksheet-report/pdf')
    def consolidated_marksheet_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else request.query_params
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        exam_type_id = req_data.get('exam_type_id')
        exam_ids_raw = req_data.get('exam_ids') or req_data.get('exam_id')
        exam_date_raw = req_data.get('exam_date')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        exam_ids = []
        if isinstance(exam_ids_raw, list):
            exam_ids = exam_ids_raw
        elif isinstance(exam_ids_raw, str) and exam_ids_raw.strip():
            exam_ids = [x.strip() for x in exam_ids_raw.split(',') if x.strip()]
        elif isinstance(exam_ids_raw, int):
            exam_ids = [exam_ids_raw]

        department = Department.objects.filter(id=department_id).first() if department_id else None
        batch = Batch.objects.filter(id=batch_id).first() if batch_id else None

        section_obj = None
        if section_id:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=section_id).first()
            else:
                section_obj = Section.objects.filter(sections__iexact=section_id).first()

        semester_obj = Semester.objects.filter(id=semester_id).first() if (semester_id and str(semester_id).isdigit()) else None
        exam_type_obj = ExamType.objects.filter(id=exam_type_id).first() if exam_type_id else None

        college_header_obj = None
        if str(header_type).isdigit():
            college_header_obj = CollegeHeader.objects.filter(id=header_type).first()
        if not college_header_obj and header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type__iexact=str(header_type)).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        exam_date_str = ""
        sel_exams_cnt = []
        if exam_ids:
            sel_exams_cnt = list(Exam.objects.filter(id__in=exam_ids))
        elif exam_type_id:
            sel_exams_cnt = list(Exam.objects.filter(exam_type_id=exam_type_id))

        if sel_exams_cnt:
            dates_parts = []
            for ex in sel_exams_cnt:
                tt_qs = ExamTimetable.objects.filter(exam=ex)
                if department:
                    tt_qs = tt_qs.filter(department=department)
                if batch:
                    tt_qs = tt_qs.filter(batch=batch)
                if semester_id:
                    tt_qs = tt_qs.filter(semester_id=semester_id)
                if section_obj:
                    tt_qs = tt_qs.filter(section=section_obj)
                
                dates = list(tt_qs.values_list('exam_date', flat=True).distinct().order_by('exam_date'))
                
                if not dates and department:
                    tt_qs_dept = ExamTimetable.objects.filter(exam=ex, department=department)
                    dates = list(tt_qs_dept.values_list('exam_date', flat=True).distinct().order_by('exam_date'))

                if not dates:
                    dates = list(ExamTimetable.objects.filter(exam=ex).values_list('exam_date', flat=True).distinct().order_by('exam_date'))

                if dates:
                    min_d = dates[0].strftime("%d/%m/%Y")
                    max_d = dates[-1].strftime("%d/%m/%Y")
                    range_str = min_d if min_d == max_d else f"{min_d} to {max_d}"
                    if len(sel_exams_cnt) > 1:
                        dates_parts.append(f"{ex.exam_name}: {range_str}")
                    else:
                        dates_parts.append(range_str)

            if dates_parts:
                exam_date_str = " | ".join(dates_parts)

        if not exam_date_str and exam_date_raw:
            try:
                if '-' in str(exam_date_raw):
                    parts = str(exam_date_raw).split('-')
                    if len(parts) == 3:
                        if len(parts[0]) == 4:
                            exam_date_str = f"{parts[2].zfill(2)}/{parts[1].zfill(2)}/{parts[0]}"
                        else:
                            exam_date_str = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
                elif '/' in str(exam_date_raw):
                    exam_date_str = str(exam_date_raw)
            except Exception:
                exam_date_str = str(exam_date_raw)
        if not exam_date_str:
            exam_date_str = datetime.date.today().strftime("%d/%m/%Y")

        exam_title_str = "CAT1 Exam"
        if exam_ids:
            sel_exams = Exam.objects.filter(id__in=exam_ids)
            if sel_exams.exists():
                exam_names = [e.exam_name for e in sel_exams]
                exam_title_str = " / ".join(exam_names)

        sem_num = 1
        if semester_id and str(semester_id).isdigit():
            sem_num = int(semester_id)
        elif semester_obj:
            try:
                sem_num = int(semester_obj.semester_name or semester_obj.id)
            except Exception:
                sem_num = 1

        roman_map = {1: 'I', 2: 'I', 3: 'II', 4: 'II', 5: 'III', 6: 'III', 7: 'IV', 8: 'IV'}
        year_roman = roman_map.get(sem_num, 'I')
        sec_name = section_obj.sections if section_obj else (str(section_id) if section_id else 'A')

        academic_year_str = "Academic Year 2026-2027"
        if batch and batch.batch:
            academic_year_str = f"Academic Year {batch.batch}"

        dept_name_str = f"Department of {department.department_name}" if department else ""

        subjects_qs = Subject.objects.all()
        if department:
            subjects_qs = subjects_qs.filter(department=department)
        if semester_obj:
            subjects_qs = subjects_qs.filter(semester=semester_obj)
        elif semester_id:
            subjects_qs = subjects_qs.filter(semester_id=semester_id)
        if regulation_id:
            subjects_qs = subjects_qs.filter(regulation_id=regulation_id)

        subjects = list(subjects_qs.order_by('subject_code'))

        students_qs = Student.objects.all().select_related('user')
        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)

        student_ids_raw = req_data.get('student_ids') or req_data.get('student_id')
        if student_ids_raw:
            if isinstance(student_ids_raw, list):
                students_qs = students_qs.filter(id__in=student_ids_raw)
            elif str(student_ids_raw).isdigit():
                students_qs = students_qs.filter(id=student_ids_raw)

        students = list(students_qs.order_by('roll_number', 'user__name'))

        marks_map = {}
        if students and subjects:
            m_qs = Marks.objects.filter(student__in=students, subject__in=subjects)
            if exam_ids:
                m_qs = m_qs.filter(exam_id__in=exam_ids)
            for m in m_qs:
                marks_map[(m.student_id, m.subject_id)] = m.marks_obtained

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=25,
            rightMargin=25,
            topMargin=20,
            bottomMargin=20
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            name='CollHeaderTitleCons',
            fontName='Helvetica-Bold',
            fontSize=11.5,
            leading=13.5,
            alignment=1,
            textColor=colors.black
        )
        heading_title_style = ParagraphStyle(
            name='ConsolidatedTitleCons',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=13,
            alignment=1,
            textColor=colors.black
        )
        heading_meta_style = ParagraphStyle(
            name='ConsolidatedMetaCons',
            fontName='Helvetica',
            fontSize=9,
            leading=11,
            alignment=1,
            textColor=colors.black
        )

        tbl_header_style = ParagraphStyle(
            name='TblHeaderStyleCons',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            leading=9,
            alignment=1,
            textColor=colors.black
        )
        tbl_cell_center = ParagraphStyle(
            name='TblCellCenterStyleCons',
            fontName='Helvetica',
            fontSize=7.5,
            leading=9,
            alignment=1,
            textColor=colors.black
        )
        tbl_cell_left = ParagraphStyle(
            name='TblCellLeftStyleCons',
            fontName='Helvetica',
            fontSize=7.5,
            leading=9,
            alignment=0,
            textColor=colors.black
        )

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        img_data = response.read()
                        pil_img = PILImage.open(BytesIO(img_data))
                        out_io = BytesIO()
                        pil_img.save(out_io, format='PNG')
                        out_io.seek(0)
                        logo_flowable = RLImage(out_io, width=50, height=50)
                elif os.path.exists(logo_url):
                    pil_img = PILImage.open(logo_url)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=50, height=50)
            except Exception:
                pass

        if not logo_flowable:
            fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
            try:
                if os.path.exists(fallback_logo_path):
                    pil_img = PILImage.open(fallback_logo_path)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=50, height=50)
            except Exception:
                pass

        story = []

        header_title_style = ParagraphStyle(
            name='ConsMarksheetHdrTitle',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            alignment=1,
            textColor=colors.black
        )

        college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
        college_header_parts = []
        if college_name_str:
            college_header_parts.append(college_name_str)
        if exam_title_str:
            college_header_parts.append(exam_title_str)
        college_header_parts.append("CONSOLIDATED MARKSHEET REPORT")
        header_title_text = "<br/>".join(college_header_parts)
        title_paragraph = Paragraph(f"<b>{header_title_text}</b>", header_title_style)

        if logo_flowable:
            header_table_data = [[logo_flowable, title_paragraph]]
            header_table = Table(header_table_data, colWidths=[65, 460])
        else:
            header_table_data = [[title_paragraph]]
            header_table = Table(header_table_data, colWidths=[525])

        header_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        regulation_str = ""
        if regulation_id:
            reg_obj = Regulation.objects.filter(id=regulation_id).first()
            if reg_obj:
                regulation_str = reg_obj.regulation_code

        lbl_bold = ParagraphStyle(
            name='CmsLblBold',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )

        val_norm = ParagraphStyle(
            name='CmsValNorm',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )

        batch_str = batch.batch if batch else "—"

        meta_data = [
            [
                Paragraph("<b>Department:</b>", lbl_bold), Paragraph(dept_name_str, val_norm),
                Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(batch_str, val_norm)
            ],
            [
                Paragraph("<b>Year/Sem/Sec:</b>", lbl_bold), Paragraph(f"{year_roman} / Semester {sem_num} / {sec_name}", val_norm),
                Paragraph("<b>Regulation:</b>", lbl_bold), Paragraph(regulation_str if regulation_str else "—", val_norm)
            ],
            [
                Paragraph("<b>Date of Exam:</b>", lbl_bold), Paragraph(exam_date_str, val_norm),
                Paragraph("", val_norm), Paragraph("", val_norm)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[80, 187, 80, 188])
        meta_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('SPAN', (1,2), (3,2)),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,0), (2,-2), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 15))

        sub_count = max(len(subjects), 1)
        sub_col_width = max(345 / sub_count, 32)

        table_header = [
            Paragraph("S.<br/>No.", tbl_header_style),
            Paragraph("Roll No.", tbl_header_style),
            Paragraph("Name", tbl_header_style)
        ]
        for sub in subjects:
            table_header.append(Paragraph(sub.subject_code, tbl_header_style))

        table_data = [table_header]
        col_widths = [25, 55, 120] + [sub_col_width] * len(subjects)

        subject_stats = {
            sub.id: {
                'total': len(students),
                'appeared': 0,
                'pass': 0,
                'fail': 0,
                'absent': 0
            }
            for sub in subjects
        }

        performance_counts = {
            'cleared_all': 0,
            'failed_1': 0,
            'failed_2': 0,
            'failed_3': 0,
            'failed_more_than_3': 0
        }

        conducted_subjects = set()
        for sub in subjects:
            for s in students:
                val = marks_map.get((s.id, sub.id))
                if val is not None and str(val).strip() != '' and str(val).strip() != '-':
                    conducted_subjects.add(sub.id)

        active_grades = list(GradeSystem.objects.filter(is_active=True))

        def evaluate_mark_pass_fail(val):
            if val is None:
                return True, False, "-"
            str_val = str(val).strip().upper()
            if str_val in ['-', '']:
                return True, False, "-"
            
            if str_val in ['AB', 'ABSENT']:
                return True, False, "AB"
            if str_val == 'UA':
                return True, False, "UA"

            try:
                num_val = float(str_val)
                disp = str(int(num_val)) if num_val.is_integer() else str(num_val)

                absent_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and float(g.min_mark) == 0 and float(g.max_mark) == 0 and not g.is_pass), None)
                if absent_entry and num_val == 0:
                    return True, False, "UA"

                matching_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark) == 0) and float(g.min_mark) <= num_val <= float(g.max_mark)), None)
                if matching_entry:
                    return False, matching_entry.is_pass, disp

                pass_entries = [g for g in active_grades if g.is_pass and g.min_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark or 0) == 0)]
                if pass_entries:
                    min_pass_mark = min(float(g.min_mark) for g in pass_entries)
                    return False, num_val >= min_pass_mark, disp

                return False, num_val >= 50.0, disp
            except ValueError:
                matching_grade = next((g for g in active_grades if g.grade.upper() == str_val), None)
                if matching_grade:
                    is_abs = (matching_grade.min_mark is not None and matching_grade.max_mark is not None and float(matching_grade.min_mark) == 0 and float(matching_grade.max_mark) == 0) or str_val == 'UA'
                    return is_abs, matching_grade.is_pass, str_val

                is_fail_code = str_val in ['U', 'UA', 'F', 'RA', 'AB', 'ABSENT']
                return (str_val in ['AB', 'ABSENT', 'UA']), (not is_fail_code), str_val

        for idx, student in enumerate(students, start=1):
            s_sno = str(idx)
            s_roll = student.roll_number or ""
            s_name = student.user.name if (student.user and student.user.name) else ""

            row = [
                Paragraph(s_sno, tbl_cell_center),
                Paragraph(s_roll, tbl_cell_center),
                Paragraph(s_name, tbl_cell_left)
            ]

            student_failed_conducted_count = 0
            student_conducted_count = 0

            for sub in subjects:
                raw_val = marks_map.get((student.id, sub.id))
                is_abs, is_pass, display_val = evaluate_mark_pass_fail(raw_val)

                if display_val == "-":
                    subject_stats[sub.id]['absent'] += 1
                elif is_abs:
                    subject_stats[sub.id]['absent'] += 1
                    if sub.id in conducted_subjects:
                        student_failed_conducted_count += 1
                        student_conducted_count += 1
                else:
                    subject_stats[sub.id]['appeared'] += 1
                    if sub.id in conducted_subjects:
                        student_conducted_count += 1

                    if is_pass:
                        subject_stats[sub.id]['pass'] += 1
                    else:
                        subject_stats[sub.id]['fail'] += 1
                        if sub.id in conducted_subjects:
                            student_failed_conducted_count += 1

                row.append(Paragraph(display_val, tbl_cell_center))

            table_data.append(row)

            if len(conducted_subjects) > 0 or len(subjects) > 0:
                if student_failed_conducted_count == 0:
                    performance_counts['cleared_all'] += 1
                elif student_failed_conducted_count == 1:
                    performance_counts['failed_1'] += 1
                elif student_failed_conducted_count == 2:
                    performance_counts['failed_2'] += 1
                elif student_failed_conducted_count == 3:
                    performance_counts['failed_3'] += 1
                else:
                    performance_counts['failed_more_than_3'] += 1

        marks_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        marks_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 2),
            ('RIGHTPADDING', (0,0), (-1,-1), 2),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#D9D9D9')),
        ]))
        story.append(marks_table)
        story.append(Spacer(1, 15))

        story.append(Paragraph("<b>Subject-wise Analysis</b>", ParagraphStyle(name='SecHead1Cons', fontName='Helvetica-Bold', fontSize=9.5, leading=12)))
        story.append(Spacer(1, 4))

        ana_header = [Paragraph("Subject Code", tbl_header_style)]
        for sub in subjects:
            ana_header.append(Paragraph(sub.subject_code, tbl_header_style))

        row_total = [Paragraph("Total No. of Students", tbl_cell_left)]
        row_appeared = [Paragraph("No. of Students Appeared", tbl_cell_left)]
        row_pass = [Paragraph("No. of Students Pass", tbl_cell_left)]
        row_fail = [Paragraph("No. of Students Fail", tbl_cell_left)]
        row_absent = [Paragraph("No. of Students Absent", tbl_cell_left)]
        row_pass_pct_total = [Paragraph("Percentage of Pass: (Based on Total)", tbl_cell_left)]
        row_pass_pct_app = [Paragraph("(Based on Appeared)", tbl_cell_left)]

        for sub in subjects:
            st = subject_stats[sub.id]
            tot = st['total']
            app = st['appeared']
            pas = st['pass']
            fal = st['fail']
            absn = st['absent']

            pct_tot_str = f"{round((pas / tot * 100), 2)}%" if tot > 0 else "0.0%"
            pct_app_str = f"{round((pas / app * 100), 2)}%" if app > 0 else "0.0%"

            row_total.append(Paragraph(str(tot), tbl_cell_center))
            row_appeared.append(Paragraph(str(app), tbl_cell_center))
            row_pass.append(Paragraph(str(pas), tbl_cell_center))
            row_fail.append(Paragraph(str(fal), tbl_cell_center))
            row_absent.append(Paragraph(str(absn), tbl_cell_center))
            row_pass_pct_total.append(Paragraph(pct_tot_str, tbl_cell_center))
            row_pass_pct_app.append(Paragraph(pct_app_str, tbl_cell_center))

        ana_table_data = [
            ana_header,
            row_total,
            row_appeared,
            row_pass,
            row_fail,
            row_absent,
            row_pass_pct_total,
            row_pass_pct_app
        ]

        ana_col_widths = [200] + [sub_col_width] * len(subjects)
        ana_table = Table(ana_table_data, colWidths=ana_col_widths)
        ana_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 2.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#D9D9D9')),
        ]))
        story.append(ana_table)
        story.append(Spacer(1, 15))

        story.append(Paragraph("<b>Overall Student Performance</b>", ParagraphStyle(name='SecHead2Cons', fontName='Helvetica-Bold', fontSize=9.5, leading=12)))
        story.append(Spacer(1, 4))

        perf_data = [
            [Paragraph("Performance Category", tbl_header_style), Paragraph("Number of Students", tbl_header_style)],
            [Paragraph("Cleared All Subjects", tbl_cell_left), Paragraph(str(performance_counts['cleared_all']), tbl_cell_center)],
            [Paragraph("Failed in One Subject", tbl_cell_left), Paragraph(str(performance_counts['failed_1']), tbl_cell_center)],
            [Paragraph("Failed in Two Subjects", tbl_cell_left), Paragraph(str(performance_counts['failed_2']), tbl_cell_center)],
            [Paragraph("Failed in Three Subjects", tbl_cell_left), Paragraph(str(performance_counts['failed_3']), tbl_cell_center)],
            [Paragraph("Failed in More Than Three Subjects", tbl_cell_left), Paragraph(str(performance_counts['failed_more_than_3']), tbl_cell_center)],
        ]
        perf_table = Table(perf_data, colWidths=[240, 140])
        perf_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 2.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2.5),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#D9D9D9')),
        ]))
        story.append(perf_table)
        story.append(Spacer(1, 15))

        total_students_cnt = len(students)
        overall_pct_val = f"{round((performance_counts['cleared_all'] / total_students_cnt * 100), 2)}%" if total_students_cnt > 0 else "0.0%"

        story.append(Paragraph("<b>Overall Pass Percentage</b>", ParagraphStyle(name='SecHead3Cons', fontName='Helvetica-Bold', fontSize=9.5, leading=12)))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"<b>{overall_pct_val}</b>", ParagraphStyle(name='OverallValCons', fontName='Helvetica', fontSize=9.5, leading=12, alignment=1)))
        story.append(Spacer(1, 35))

        sig_data = [[
            Paragraph("<b>Test Coordinator</b>", ParagraphStyle(name='SigLeftCons', fontName='Helvetica-Bold', fontSize=8.5, alignment=0)),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='SigCenterCons', fontName='Helvetica-Bold', fontSize=8.5, alignment=1)),
            Paragraph("<b>Principal</b>", ParagraphStyle(name='SigRightCons', fontName='Helvetica-Bold', fontSize=8.5, alignment=2))
        ]]
        sig_table = Table(sig_data, colWidths=[175, 175, 175])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Consolidated_Marksheet_{datetime.date.today().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        return response

    @action(detail=False, methods=['post', 'get'], url_path='progress-report/pdf')
    def progress_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else request.query_params
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        exam_type_id = req_data.get('exam_type_id')
        exam_ids_raw = req_data.get('exam_ids') or req_data.get('exam_id')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        exam_ids = []
        if isinstance(exam_ids_raw, list):
            exam_ids = exam_ids_raw
        elif isinstance(exam_ids_raw, str) and exam_ids_raw.strip():
            exam_ids = [x.strip() for x in exam_ids_raw.split(',') if x.strip()]
        elif isinstance(exam_ids_raw, int):
            exam_ids = [exam_ids_raw]

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

        exams = []
        if exam_ids:
            exams = list(Exam.objects.filter(id__in=exam_ids))
        elif exam_type_id:
            exams = list(Exam.objects.filter(exam_type_id=exam_type_id))
        else:
            exams = list(Exam.objects.all()[:3])

        subjects_qs = Subject.objects.all()
        if department:
            subjects_qs = subjects_qs.filter(department=department)
        if semester_obj:
            subjects_qs = subjects_qs.filter(semester=semester_obj)
        elif semester_id:
            subjects_qs = subjects_qs.filter(semester_id=semester_id)
        if regulation_id:
            subjects_qs = subjects_qs.filter(regulation_id=regulation_id)

        subjects = list(subjects_qs.order_by('subject_code'))

        students_qs = Student.objects.all().select_related('user')
        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)

        student_ids_raw = req_data.get('student_ids') or req_data.get('student_id')
        if student_ids_raw:
            if isinstance(student_ids_raw, list):
                students_qs = students_qs.filter(id__in=student_ids_raw)
            elif str(student_ids_raw).isdigit():
                students_qs = students_qs.filter(id=student_ids_raw)

        students = list(students_qs.order_by('roll_number', 'user__name'))

        marks_dict = {}
        if students and subjects and exams:
            m_qs = Marks.objects.filter(student__in=students, subject__in=subjects, exam__in=exams)
            for m in m_qs:
                marks_dict[(m.student_id, m.subject_id, m.exam_id)] = m.marks_obtained

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=30,
            rightMargin=30,
            topMargin=25,
            bottomMargin=25
        )

        styles = getSampleStyleSheet()

        prog_title_style = ParagraphStyle(
            name='ProgTitle',
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=14,
            alignment=1,
            textColor=colors.black
        )

        lbl_bold = ParagraphStyle(
            name='LblBold',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )

        val_norm = ParagraphStyle(
            name='ValNorm',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )

        tbl_hdr_style = ParagraphStyle(
            name='ProgTblHdr',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.black
        )

        tbl_cell_center = ParagraphStyle(
            name='ProgCellCenter',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.black
        )

        tbl_cell_left = ParagraphStyle(
            name='ProgCellLeft',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            alignment=0,
            textColor=colors.black
        )

        active_grades = list(GradeSystem.objects.filter(is_active=True))
        grade_pass_map = {g.grade.strip().upper(): g.is_pass for g in active_grades}

        def evaluate_result_category(val):
            if val is None:
                return "-", "#64748B"
            str_val = str(val).strip().upper()
            if str_val in ['-', '']:
                return "-", "#64748B"
            if str_val in ['AB', 'ABSENT', 'UA']:
                return "FAIL", "#B91C1C"
            if str_val in grade_pass_map:
                return ("PASS", "#15803D") if grade_pass_map[str_val] else ("FAIL", "#B91C1C")
            try:
                num = float(str_val)
                pass_entries = [g for g in active_grades if g.is_pass and g.min_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark or 0) == 0)]
                min_pass = min([float(g.min_mark) for g in pass_entries]) if pass_entries else 50.0
                return ("PASS", "#15803D") if num >= min_pass else ("FAIL", "#B91C1C")
            except ValueError:
                pass
            if str_val in ['F', 'RA', 'U', 'FAIL']:
                return "FAIL", "#B91C1C"
            return "PASS", "#15803D"

        story = []

        for s_idx, st in enumerate(students):
            if s_idx > 0:
                story.append(PageBreak())

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

            if not logo_flowable:
                fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
                try:
                    if os.path.exists(fallback_logo_path):
                        pil_img = PILImage.open(fallback_logo_path)
                        out_io = BytesIO()
                        pil_img.save(out_io, format='PNG')
                        out_io.seek(0)
                        logo_flowable = RLImage(out_io, width=45, height=45)
                except Exception:
                    pass

            exam_title_str = "CAT-1 / CAT-2 / MODEL"
            if exams:
                exam_title_str = " / ".join([e.exam_name.upper() for e in exams])

            header_title_style = ParagraphStyle(
                name='HdrTitleImage2',
                fontName='Helvetica-Bold',
                fontSize=11,
                leading=14,
                alignment=1,
                textColor=colors.black
            )

            college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
            college_header_parts = []
            if college_name_str:
                college_header_parts.append(college_name_str)
            if exam_title_str:
                college_header_parts.append(exam_title_str)
            college_header_parts.append("STUDENT PROGRESS REPORT")
            header_title_text = "<br/>".join(college_header_parts)
            title_paragraph = Paragraph(f"<b>{header_title_text}</b>", header_title_style)

            if logo_flowable:
                header_table_data = [[logo_flowable, title_paragraph]]
                header_table = Table(header_table_data, colWidths=[65, 470])
            else:
                header_table_data = [[title_paragraph]]
                header_table = Table(header_table_data, colWidths=[535])

            header_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(header_table)
            story.append(Spacer(1, 10))

            exam_date_str = ""
            if exams:
                dates_parts = []
                for ex in exams:
                    tt_qs = ExamTimetable.objects.filter(exam=ex)
                    if department:
                        tt_qs = tt_qs.filter(department=department)
                    if batch:
                        tt_qs = tt_qs.filter(batch=batch)
                    if semester_id:
                        tt_qs = tt_qs.filter(semester_id=semester_id)
                    if section_obj:
                        tt_qs = tt_qs.filter(section=section_obj)
                    
                    dates = list(tt_qs.values_list('exam_date', flat=True).distinct().order_by('exam_date'))
                    
                    if not dates and department:
                        tt_qs_dept = ExamTimetable.objects.filter(exam=ex, department=department)
                        dates = list(tt_qs_dept.values_list('exam_date', flat=True).distinct().order_by('exam_date'))
                    
                    if not dates:
                        dates = list(ExamTimetable.objects.filter(exam=ex).values_list('exam_date', flat=True).distinct().order_by('exam_date'))

                    if dates:
                        min_d = dates[0].strftime("%d/%m/%Y")
                        max_d = dates[-1].strftime("%d/%m/%Y")
                        range_str = min_d if min_d == max_d else f"{min_d} to {max_d}"
                        if len(exams) > 1:
                            dates_parts.append(f"{ex.exam_name}: {range_str}")
                        else:
                            dates_parts.append(range_str)

                if dates_parts:
                    exam_date_str = " | ".join(dates_parts)

            if not exam_date_str:
                exam_date_raw = req_data.get('exam_date')
                if exam_date_raw:
                    try:
                        if '-' in str(exam_date_raw):
                            parts = str(exam_date_raw).split('-')
                            if len(parts) == 3:
                                if len(parts[0]) == 4:
                                    exam_date_str = f"{parts[2].zfill(2)}/{parts[1].zfill(2)}/{parts[0]}"
                                else:
                                    exam_date_str = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{parts[2]}"
                        elif '/' in str(exam_date_raw):
                            exam_date_str = str(exam_date_raw)
                    except Exception:
                        exam_date_str = str(exam_date_raw)
            if not exam_date_str:
                exam_date_str = datetime.date.today().strftime("%d/%m/%Y")

            s_name = st.user.name.upper() if (st.user and st.user.name) else "—"
            r_no = st.register_number or "—"
            roll_no = st.roll_number or "—"
            dept_name = department.department_name if department else "—"
            sec_name = section_obj.sections if section_obj else "A"
            sem_val = semester_id or "—"
            batch_val = batch.batch if batch else "—"

            regulation_str = "—"
            if regulation_id:
                reg_obj = Regulation.objects.filter(id=regulation_id).first()
                if reg_obj:
                    regulation_str = reg_obj.regulation_code

            info_data = [
                [
                    Paragraph("<b>Student Name:</b>", lbl_bold), Paragraph(s_name, val_norm),
                    Paragraph("<b>Register No:</b>", lbl_bold), Paragraph(r_no, val_norm)
                ],
                [
                    Paragraph("<b>Roll No:</b>", lbl_bold), Paragraph(roll_no, val_norm),
                    Paragraph("<b>Department:</b>", lbl_bold), Paragraph(dept_name, val_norm)
                ],
                [
                    Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(str(batch_val), val_norm),
                    Paragraph("<b>Sem / Section:</b>", lbl_bold), Paragraph(f"Sem {sem_val} - Sec {sec_name}", val_norm)
                ],
                [
                    Paragraph("<b>Date of Exam:</b>", lbl_bold), Paragraph(exam_date_str, val_norm),
                    Paragraph("<b>Regulation:</b>", lbl_bold), Paragraph(regulation_str, val_norm)
                ]
            ]
            info_tbl = Table(info_data, colWidths=[80, 187, 80, 188])
            info_tbl.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
                ('SPAN', (1,3), (3,3)),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
                ('BACKGROUND', (2,0), (2,-2), colors.HexColor('#F8FAFC')),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
                ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(info_tbl)
            story.append(Spacer(1, 15))

            def clean_pdf_text(val, split_slash=False):
                if not val:
                    return ""
                val_str = str(val).strip()
                if '\n' in val_str:
                    lines = [clean_pdf_text(l, split_slash) for l in val_str.split('\n')]
                    return "<br/>".join([l for l in lines if l])
                
                if split_slash and '/' in val_str:
                    parts = [p.strip() for p in val_str.split('/')]
                    cleaned_parts = []
                    for p in parts:
                        cp = "".join(c for c in p if ord(c) < 256).strip()
                        if cp:
                            cleaned_parts.append(cp)
                    if len(cleaned_parts) > 1:
                        return "<br/>".join(cleaned_parts)
                    elif len(cleaned_parts) == 1:
                        return cleaned_parts[0]

                res = "".join(c for c in val_str if ord(c) < 256).strip()
                return res if res else val_str

            if len(exams) <= 1:
                col_widths = [35, 75, 235, 105, 85]
                table_rows = []
                ex_name = exams[0].exam_name if exams else "Marks"
                header_cells = [
                    Paragraph("S. No.", tbl_hdr_style),
                    Paragraph("Subject Code", tbl_hdr_style),
                    Paragraph("Subject Name", tbl_hdr_style),
                    Paragraph(clean_pdf_text(ex_name, split_slash=True), tbl_hdr_style),
                    Paragraph("Result<br/>Category", tbl_hdr_style)
                ]
                table_rows.append(header_cells)

                for sub_i, sub in enumerate(subjects):
                    cleaned_name = clean_pdf_text(sub.subject_name)
                    cleaned_code = clean_pdf_text(sub.subject_code)
                    m_val = marks_dict.get((st.id, sub.id, exams[0].id)) if exams else None
                    m_str = str(m_val) if (m_val is not None) else "-"
                    res_text, res_color = evaluate_result_category(m_val)

                    row_cells = [
                        Paragraph(str(sub_i + 1), tbl_cell_center),
                        Paragraph(cleaned_code or "—", tbl_cell_center),
                        Paragraph(cleaned_name or "—", tbl_cell_left),
                        Paragraph(m_str, tbl_cell_center),
                        Paragraph(f"<font color='{res_color}'><b>{res_text}</b></font>", tbl_cell_center) if res_text != "-" else Paragraph("-", tbl_cell_center)
                    ]
                    table_rows.append(row_cells)

                if len(subjects) == 0:
                    table_rows.append([Paragraph("No subjects found", tbl_cell_center)] * 5)

            elif len(exams) == 2:
                col_widths = [30, 65, 180, 65, 65, 65, 65]
                table_rows = []
                header_cells = [
                    Paragraph("S. No.", tbl_hdr_style),
                    Paragraph("Subject Code", tbl_hdr_style),
                    Paragraph("Subject Name", tbl_hdr_style),
                    Paragraph(clean_pdf_text(exams[0].exam_name, split_slash=True), tbl_hdr_style),
                    Paragraph("Result<br/>Category", tbl_hdr_style),
                    Paragraph(clean_pdf_text(exams[1].exam_name, split_slash=True), tbl_hdr_style),
                    Paragraph("Result<br/>Category", tbl_hdr_style)
                ]
                table_rows.append(header_cells)

                for sub_i, sub in enumerate(subjects):
                    cleaned_name = clean_pdf_text(sub.subject_name)
                    cleaned_code = clean_pdf_text(sub.subject_code)

                    m1_val = marks_dict.get((st.id, sub.id, exams[0].id))
                    m1_str = str(m1_val) if (m1_val is not None) else "-"
                    res1_text, res1_color = evaluate_result_category(m1_val)
                    res1_cell = Paragraph(f"<font color='{res1_color}'><b>{res1_text}</b></font>", tbl_cell_center) if res1_text != "-" else Paragraph("-", tbl_cell_center)

                    m2_val = marks_dict.get((st.id, sub.id, exams[1].id))
                    m2_str = str(m2_val) if (m2_val is not None) else "-"
                    res2_text, res2_color = evaluate_result_category(m2_val)
                    res2_cell = Paragraph(f"<font color='{res2_color}'><b>{res2_text}</b></font>", tbl_cell_center) if res2_text != "-" else Paragraph("-", tbl_cell_center)

                    row_cells = [
                        Paragraph(str(sub_i + 1), tbl_cell_center),
                        Paragraph(cleaned_code or "—", tbl_cell_center),
                        Paragraph(cleaned_name or "—", tbl_cell_left),
                        Paragraph(m1_str, tbl_cell_center),
                        res1_cell,
                        Paragraph(m2_str, tbl_cell_center),
                        res2_cell
                    ]
                    table_rows.append(row_cells)

                if len(subjects) == 0:
                    table_rows.append([Paragraph("No subjects found", tbl_cell_center)] * 7)

            else:
                num_exams = len(exams)
                exam_col_width = max(int(220 / num_exams), 60)
                subj_name_width = 535 - 35 - 75 - (exam_col_width * num_exams)
                col_widths = [35, 75, subj_name_width] + [exam_col_width] * num_exams

                table_rows = []
                header_cells = [
                    Paragraph("S. No.", tbl_hdr_style),
                    Paragraph("Subject Code", tbl_hdr_style),
                    Paragraph("Subject Name", tbl_hdr_style),
                ] + [Paragraph(clean_pdf_text(e.exam_name, split_slash=True), tbl_hdr_style) for e in exams]
                table_rows.append(header_cells)

                for sub_i, sub in enumerate(subjects):
                    cleaned_name = clean_pdf_text(sub.subject_name)
                    cleaned_code = clean_pdf_text(sub.subject_code)

                    row_cells = [
                        Paragraph(str(sub_i + 1), tbl_cell_center),
                        Paragraph(cleaned_code or "—", tbl_cell_center),
                        Paragraph(cleaned_name or "—", tbl_cell_left),
                    ]
                    for ex in exams:
                        m_val = marks_dict.get((st.id, sub.id, ex.id))
                        if m_val is not None and str(m_val).strip() not in ['', '-']:
                            m_str = str(m_val).strip()
                            res_text, res_color = evaluate_result_category(m_val)
                            cell_html = f"<b>{m_str}</b><br/><font size=7 color='{res_color}'><b>{res_text}</b></font>"
                            row_cells.append(Paragraph(cell_html, tbl_cell_center))
                        else:
                            row_cells.append(Paragraph("-", tbl_cell_center))

                    table_rows.append(row_cells)

                if len(subjects) == 0:
                    table_rows.append([Paragraph("No subjects found", tbl_cell_center)] * (3 + len(exams)))

            marks_table = Table(table_rows, colWidths=col_widths)
            marks_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 3.5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3.5),
                ('LEFTPADDING', (0,0), (-1,-1), 5),
                ('RIGHTPADDING', (0,0), (-1,-1), 5),
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
            ]))
            story.append(marks_table)
            story.append(Spacer(1, 35))

            sig_data = [[
                Paragraph("<b>Class In-Charge</b>", ParagraphStyle(name='Sig1', fontName='Helvetica-Bold', fontSize=8.5, alignment=0)),
                Paragraph("<b>HOD</b>", ParagraphStyle(name='Sig2', fontName='Helvetica-Bold', fontSize=8.5, alignment=1)),
                Paragraph("<b>Parent Signature</b>", ParagraphStyle(name='Sig3', fontName='Helvetica-Bold', fontSize=8.5, alignment=2))
            ]]
            sig_table = Table(sig_data, colWidths=[178, 178, 179])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(pdf, content_type='application/pdf')
        return response

    @action(detail=False, methods=['post', 'get'], url_path='internal-exam-result-analysis-report/pdf')
    def internal_exam_result_analysis_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else request.query_params
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        subject_id = req_data.get('subject_id')
        exam_type_id = req_data.get('exam_type_id')
        exam_ids_raw = req_data.get('exam_ids') or req_data.get('exam_id')
        exam_date_req = req_data.get('exam_date')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        exam_ids = []
        if isinstance(exam_ids_raw, list):
            exam_ids = exam_ids_raw
        elif isinstance(exam_ids_raw, str) and exam_ids_raw.strip():
            exam_ids = [x.strip() for x in exam_ids_raw.split(',') if x.strip()]
        elif isinstance(exam_ids_raw, int):
            exam_ids = [exam_ids_raw]

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

        if subject_id:
            sub_obj = Subject.objects.filter(id=subject_id).first()
            subjects = [sub_obj] if sub_obj else []
        else:
            subjects_qs = Subject.objects.all()
            if department:
                subjects_qs = subjects_qs.filter(department=department)
            if semester_obj:
                subjects_qs = subjects_qs.filter(semester=semester_obj)
            elif semester_id:
                subjects_qs = subjects_qs.filter(semester_id=semester_id)
            if regulation_id:
                subjects_qs = subjects_qs.filter(regulation_id=regulation_id)
            subjects = list(subjects_qs.order_by('subject_code'))

        if not subjects:
            return HttpResponse("No subjects found matching the selected criteria.", status=400)

        students_qs = Student.objects.all().select_related('user')
        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)

        students = list(students_qs.order_by('roll_number', 'user__name'))

        exams = []
        if exam_ids:
            exams = list(Exam.objects.filter(id__in=exam_ids))
        elif exam_type_id:
            exams = list(Exam.objects.filter(exam_type_id=exam_type_id))

        active_grades = list(GradeSystem.objects.filter(is_active=True))

        def evaluate_mark(val):
            if val is None:
                return True, False, 0.0, "AB"
            str_val = str(val).strip().upper()
            if str_val in ['-', '', 'AB', 'ABSENT', 'UA']:
                return True, False, 0.0, str_val or "AB"
            try:
                num_val = float(str_val)
                absent_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and float(g.min_mark) == 0 and float(g.max_mark) == 0 and not g.is_pass), None)
                if absent_entry and num_val == 0:
                    return True, False, 0.0, "UA"
                
                matching_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark) == 0) and float(g.min_mark) <= num_val <= float(g.max_mark)), None)
                if matching_entry:
                    return False, matching_entry.is_pass, num_val, str_val
                
                pass_entries = [g for g in active_grades if g.is_pass and g.min_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark or 0) == 0)]
                if pass_entries:
                    min_pass = min(float(g.min_mark) for g in pass_entries)
                    return False, (num_val >= min_pass), num_val, str_val
                
                return False, (num_val >= 50.0), num_val, str_val
            except ValueError:
                matching_grade = next((g for g in active_grades if g.grade.upper() == str_val), None)
                if matching_grade:
                    is_abs = (matching_grade.min_mark is not None and matching_grade.max_mark is not None and float(matching_grade.min_mark) == 0 and float(matching_grade.max_mark) == 0) or str_val == 'UA'
                    return is_abs, matching_grade.is_pass, 0.0, str_val
                is_fail_code = str_val in ['U', 'UA', 'F', 'RA', 'AB', 'ABSENT']
                return (str_val in ['AB', 'ABSENT', 'UA']), (not is_fail_code), 0.0, str_val

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=35,
            rightMargin=35,
            topMargin=30,
            bottomMargin=30
        )

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            name='InternalAnalysisHeaderTitle',
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=14,
            alignment=1,
            textColor=colors.black
        )
        report_title_style = ParagraphStyle(
            name='InternalAnalysisReportTitle',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=13,
            alignment=1,
            textColor=colors.black
        )
        meta_label_style = ParagraphStyle(
            name='InternalAnalysisMetaLabel',
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=12,
            alignment=0,
            textColor=colors.black
        )
        meta_val_style = ParagraphStyle(
            name='InternalAnalysisMetaVal',
            fontName='Helvetica',
            fontSize=9,
            leading=12,
            alignment=0,
            textColor=colors.black
        )
        tbl_hdr_style = ParagraphStyle(
            name='InternalAnalysisTblHdr',
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            alignment=1,
            textColor=colors.black
        )
        tbl_cell_center = ParagraphStyle(
            name='InternalAnalysisTblCellCenter',
            fontName='Helvetica',
            fontSize=8.5,
            leading=11,
            alignment=1,
            textColor=colors.black
        )

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        img_data = response.read()
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

        if not logo_flowable:
            fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
            try:
                if os.path.exists(fallback_logo_path):
                    pil_img = PILImage.open(fallback_logo_path)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=45, height=45)
            except Exception:
                pass

        story = []

        exam_date_str = ""
        if exam_date_req:
            try:
                d_obj = datetime.datetime.strptime(str(exam_date_req), '%Y-%m-%d')
                exam_date_str = d_obj.strftime('%d/%m/%Y')
            except ValueError:
                exam_date_str = str(exam_date_req)
        if not exam_date_str:
            exam_date_str = datetime.date.today().strftime('%d/%m/%Y')

        sem_num = 1
        if semester_id and str(semester_id).isdigit():
            sem_num = int(semester_id)
        elif semester_obj and hasattr(semester_obj, 'id') and isinstance(semester_obj.id, int):
            sem_num = semester_obj.id

        year_roman = 'I'
        if sem_num in [3, 4]:
            year_roman = 'II'
        elif sem_num in [5, 6]:
            year_roman = 'III'
        elif sem_num in [7, 8]:
            year_roman = 'IV'

        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'A')
        year_sem_sec_str = f"{year_roman} / Semester {sem_num} / {sec_name}"

        dept_name_str = department.department_name.title() if department else ""
        header_name = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
        header_address = college_header_obj.address if (college_header_obj and college_header_obj.address) else ""

        exam_title_str = ""
        if exams:
            exam_title_str = " / ".join([e.exam_name.upper() for e in exams])
        elif exam_type_id:
            ex_type_obj = ExamType.objects.filter(id=exam_type_id).first()
            if ex_type_obj:
                exam_title_str = ex_type_obj.exam_type_name.upper()

        if not exam_title_str:
            exam_title_str = "INTERNAL EXAM"

        header_title_style = ParagraphStyle(
            name='InternalHdrTitle',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            alignment=1,
            textColor=colors.black
        )

        for subj_index, target_subj in enumerate(subjects):
            if subj_index > 0:
                story.append(PageBreak())

            college_header_parts = []
            if header_name:
                college_header_parts.append(header_name)
            if exam_title_str:
                college_header_parts.append(exam_title_str)
            college_header_parts.append("EXAM RESULT ANALYSIS")
            header_title_text = "<br/>".join(college_header_parts)
            title_paragraph = Paragraph(f"<b>{header_title_text}</b>", header_title_style)

            if logo_flowable:
                header_table_data = [[logo_flowable, title_paragraph]]
                header_table = Table(header_table_data, colWidths=[65, 460])
            else:
                header_table_data = [[title_paragraph]]
                header_table = Table(header_table_data, colWidths=[525])

            header_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(header_table)
            story.append(Spacer(1, 14))

            faculty_handler_name = "N/A"
            tt = ClassTimetable.objects.filter(
                subject=target_subj,
                department=department if department else target_subj.department,
                semester=semester_obj if semester_obj else target_subj.semester
            )
            if section_obj:
                tt = tt.filter(section=section_obj)
            tt_item = tt.first()
            if tt_item and tt_item.faculty:
                faculty_handler_name = tt_item.faculty.name.upper()
            elif request.user and hasattr(request.user, 'role') and request.user.role and request.user.role.role_name.upper() == 'FACULTY':
                faculty_handler_name = request.user.name.upper()

            target_exam_date_str = ""
            tt_exam_qs = ExamTimetable.objects.filter(subject=target_subj)
            if exams:
                tt_exam_qs = tt_exam_qs.filter(exam__in=exams)
            if department:
                tt_exam_qs = tt_exam_qs.filter(department=department)
            if section_obj:
                tt_exam_qs = tt_exam_qs.filter(section=section_obj)

            tt_exam_item = tt_exam_qs.first()
            if not tt_exam_item and exams:
                tt_exam_item = ExamTimetable.objects.filter(exam__in=exams).first()

            if tt_exam_item and tt_exam_item.exam_date:
                target_exam_date_str = tt_exam_item.exam_date.strftime('%d/%m/%Y')
            elif exam_date_req:
                try:
                    d_obj = datetime.datetime.strptime(str(exam_date_req), '%Y-%m-%d')
                    target_exam_date_str = d_obj.strftime('%d/%m/%Y')
                except ValueError:
                    target_exam_date_str = str(exam_date_req)
            else:
                target_exam_date_str = datetime.date.today().strftime('%d/%m/%Y')

            lbl_bold = ParagraphStyle(
                name='InternalLblBold',
                fontName='Helvetica-Bold',
                fontSize=8.5,
                leading=11,
                textColor=colors.black
            )
            val_norm = ParagraphStyle(
                name='InternalValNorm',
                fontName='Helvetica',
                fontSize=8.5,
                leading=11,
                textColor=colors.black
            )

            sub_code_name_str = f"{target_subj.subject_code} - {target_subj.subject_name}"

            batch_str = batch.batch if batch else "—"
            regulation_str = ""
            if regulation_id:
                reg_obj = Regulation.objects.filter(id=regulation_id).first()
                if reg_obj:
                    regulation_str = reg_obj.regulation_code

            meta_data = [
                [
                    Paragraph("Department:", lbl_bold),
                    Paragraph(dept_name_str, val_norm),
                    Paragraph("Batch:", lbl_bold),
                    Paragraph(batch_str, val_norm)
                ],
                [
                    Paragraph("Year/ Sem/ Sec:", lbl_bold),
                    Paragraph(year_sem_sec_str, val_norm),
                    Paragraph("Regulation:", lbl_bold),
                    Paragraph(regulation_str if regulation_str else "—", val_norm)
                ],
                [
                    Paragraph("Subject Handler:", lbl_bold),
                    Paragraph(faculty_handler_name, val_norm),
                    Paragraph("Exam Date:", lbl_bold),
                    Paragraph(target_exam_date_str, val_norm)
                ],
                [
                    Paragraph("Sub Code & Name:", lbl_bold),
                    Paragraph(sub_code_name_str, val_norm),
                    Paragraph("", val_norm),
                    Paragraph("", val_norm)
                ]
            ]

            meta_table = Table(meta_data, colWidths=[105, 157, 105, 158])
            meta_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
                ('SPAN', (1,3), (3,3)),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
                ('BACKGROUND', (2,0), (2,-2), colors.HexColor('#F8FAFC')),
                ('TOPPADDING', (0,0), (-1,-1), 4.5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
                ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ]))
            story.append(meta_table)

            story.append(Spacer(1, 20))

            m_qs = Marks.objects.filter(student__in=students, subject=target_subj)
            if exams:
                m_qs = m_qs.filter(exam__in=exams)
            
            marks_dict = {m.student_id: m.marks_obtained for m in m_qs}

            is_univ_report = False
            if exam_type_id:
                ex_type_obj = ExamType.objects.filter(id=exam_type_id).first()
                if ex_type_obj and 'UNIV' in ex_type_obj.exam_type_name.upper():
                    is_univ_report = True
            if not is_univ_report and exams:
                for ex in exams:
                    if ex.exam_type and 'UNIV' in ex.exam_type.exam_type_name.upper():
                        is_univ_report = True
                        break

            active_grades_list = list(GradeSystem.objects.filter(is_active=True).order_by('-points', 'id'))
            db_grade_names = [g.grade.strip().upper() for g in active_grades_list]
            db_grade_set = set(db_grade_names)

            has_grade_marks = any(
                str(raw).strip().upper() in db_grade_set
                for raw in marks_dict.values() if raw is not None
            )
            use_grade_distribution = is_univ_report or has_grade_marks

            display_grades = []
            seen_grades = set()
            for g_name in db_grade_names:
                if g_name not in seen_grades:
                    seen_grades.add(g_name)
                    display_grades.append(g_name)

            grade_counts = {g: 0 for g in display_grades}

            total_students_cnt = len(students)
            appeared_cnt = 0
            absent_cnt = 0
            passed_cnt = 0
            failed_cnt = 0

            dist_91_100 = 0
            dist_81_90 = 0
            dist_71_80 = 0
            dist_61_70 = 0
            dist_50_60 = 0
            dist_less_50 = 0

            for st in students:
                raw_val = marks_dict.get(st.id)
                is_abs, is_pass, num_val, str_val = evaluate_mark(raw_val)

                if is_abs:
                    absent_cnt += 1
                    dist_less_50 += 1
                else:
                    appeared_cnt += 1
                    if is_pass:
                        passed_cnt += 1
                    else:
                        failed_cnt += 1

                    if use_grade_distribution:
                        matched_grade = None
                        if str_val in grade_counts:
                            matched_grade = str_val
                        else:
                            for g in active_grades_list:
                                if g.min_mark is not None and g.max_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark) == 0):
                                    if float(g.min_mark) <= num_val <= float(g.max_mark):
                                        matched_grade = g.grade.strip().upper()
                                        break
                            if not matched_grade:
                                if not is_pass:
                                    fail_entry = next((g for g in active_grades_list if not g.is_pass), None)
                                    matched_grade = fail_entry.grade.strip().upper() if fail_entry else None

                        if matched_grade and matched_grade in grade_counts:
                            grade_counts[matched_grade] += 1
                        elif str_val and str_val not in ['AB', 'ABSENT', 'UA']:
                            display_grades.append(str_val)
                            grade_counts[str_val] = 1
                    else:
                        if num_val >= 91 and num_val <= 100:
                            dist_91_100 += 1
                        elif num_val >= 81 and num_val <= 90:
                            dist_81_90 += 1
                        elif num_val >= 71 and num_val <= 80:
                            dist_71_80 += 1
                        elif num_val >= 61 and num_val <= 70:
                            dist_61_70 += 1
                        elif num_val >= 50 and num_val <= 60:
                            dist_50_60 += 1
                        else:
                            dist_less_50 += 1

            pass_pct_total = f"{round((passed_cnt / total_students_cnt * 100), 2):.2f}%" if total_students_cnt > 0 else "0.00%"
            pass_pct_app = f"{round((passed_cnt / appeared_cnt * 100), 2):.2f}%" if appeared_cnt > 0 else "0.00%"

            stats_colon_style = ParagraphStyle(
                name='InternalAnalysisMetaColon',
                fontName='Helvetica-Bold',
                fontSize=9,
                leading=12,
                alignment=1,
                textColor=colors.black
            )
            stats_val_bold_style = ParagraphStyle(
                name='InternalAnalysisMetaValBold',
                fontName='Helvetica-Bold',
                fontSize=9,
                leading=12,
                alignment=0,
                textColor=colors.black
            )

            stats_data = [
                [Paragraph("<b>Total Number of Students</b>", meta_label_style), Paragraph(":", stats_colon_style), Paragraph(f"<b>{total_students_cnt}</b>", stats_val_bold_style)],
                [Paragraph("<b>Number of Students Appeared</b>", meta_label_style), Paragraph(":", stats_colon_style), Paragraph(f"<b>{appeared_cnt}</b>", stats_val_bold_style)],
                [Paragraph("<b>Number of Students Absent</b>", meta_label_style), Paragraph(":", stats_colon_style), Paragraph(f"<b>{absent_cnt}</b>", stats_val_bold_style)],
                [Paragraph("<b>Number of Students Passed</b>", meta_label_style), Paragraph(":", stats_colon_style), Paragraph(f"<b>{passed_cnt}</b>", stats_val_bold_style)],
                [Paragraph("<b>Number of Students Failed</b>", meta_label_style), Paragraph(":", stats_colon_style), Paragraph(f"<b>{failed_cnt}</b>", stats_val_bold_style)],
                [Paragraph("<b>Pass % Based on Total Students</b>", meta_label_style), Paragraph(":", stats_colon_style), Paragraph(f"<b>{pass_pct_total}</b>", stats_val_bold_style)],
                [Paragraph("<b>Pass % Based on Appeared</b>", meta_label_style), Paragraph(":", stats_colon_style), Paragraph(f"<b>{pass_pct_app}</b>", stats_val_bold_style)],
            ]
            stats_table = Table(stats_data, colWidths=[350, 25, 150])
            stats_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
                ('TOPPADDING', (0,0), (-1,-1), 4.5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ]))
            story.append(stats_table)
            story.append(Spacer(1, 24))

            if use_grade_distribution:
                col_count = len(display_grades)
                desc_w = 120
                grade_w = (525 - desc_w) / max(1, col_count)
                dist_widths = [desc_w] + [grade_w] * col_count
                dist_data = [
                    [Paragraph("<b>Description</b>", tbl_hdr_style)] + [Paragraph(f"<b>{g}</b>", tbl_hdr_style) for g in display_grades],
                    [Paragraph("<b>No. of Students</b>", tbl_hdr_style)] + [Paragraph(str(grade_counts.get(g, 0)), tbl_cell_center) for g in display_grades]
                ]
                dist_table = Table(dist_data, colWidths=dist_widths)
            else:
                dist_data = [
                    [
                        Paragraph("Description", tbl_hdr_style),
                        Paragraph("91-100", tbl_hdr_style),
                        Paragraph("81-90", tbl_hdr_style),
                        Paragraph("71-80", tbl_hdr_style),
                        Paragraph("61-70", tbl_hdr_style),
                        Paragraph("50-60", tbl_hdr_style),
                        Paragraph("&lt;50", tbl_hdr_style)
                    ],
                    [
                        Paragraph("<b>No. of Students</b>", tbl_hdr_style),
                        Paragraph(str(dist_91_100), tbl_cell_center),
                        Paragraph(str(dist_81_90), tbl_cell_center),
                        Paragraph(str(dist_71_80), tbl_cell_center),
                        Paragraph(str(dist_61_70), tbl_cell_center),
                        Paragraph(str(dist_50_60), tbl_cell_center),
                        Paragraph(str(dist_less_50), tbl_cell_center)
                    ]
                ]
                dist_table = Table(dist_data, colWidths=[130, 60, 60, 60, 60, 60, 55])

            dist_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                ('LEFTPADDING', (0,0), (-1,-1), 4),
                ('RIGHTPADDING', (0,0), (-1,-1), 4),
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F2F2F2')),
            ]))
            story.append(dist_table)
            story.append(Spacer(1, 10))

            if not use_grade_distribution:
                story.append(Paragraph("<b>Minimum Pass Marks: 50 Marks</b>", ParagraphStyle(name='MinPassNote', fontName='Helvetica-Bold', fontSize=9, leading=12)))
            story.append(Spacer(1, 60))

            sig_data = [[
                Paragraph("<b>Faculty In-Charge</b>", ParagraphStyle(name='InternalSig1', fontName='Helvetica-Bold', fontSize=9.5, alignment=1)),
                Paragraph("<b>HOD</b>", ParagraphStyle(name='InternalSig2', fontName='Helvetica-Bold', fontSize=9.5, alignment=1))
            ]]
            sig_table = Table(sig_data, colWidths=[260, 265])
            sig_table.setStyle(TableStyle([
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ]))
            story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Internal_Exam_Result_Analysis_{datetime.date.today().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        return response

    @action(detail=False, methods=['post', 'get'])
    def consolidated_exam_result_analysis_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else request.query_params
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        exam_type_id = req_data.get('exam_type_id')
        exam_ids_raw = req_data.get('exam_ids') or req_data.get('exam_id')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        exam_ids = []
        if isinstance(exam_ids_raw, list):
            exam_ids = exam_ids_raw
        elif isinstance(exam_ids_raw, str) and exam_ids_raw.strip():
            exam_ids = [x.strip() for x in exam_ids_raw.split(',') if x.strip()]
        elif isinstance(exam_ids_raw, int):
            exam_ids = [exam_ids_raw]

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

        subjects_qs = Subject.objects.all()
        if department:
            subjects_qs = subjects_qs.filter(department=department)
        if semester_obj:
            subjects_qs = subjects_qs.filter(semester=semester_obj)
        elif semester_id:
            subjects_qs = subjects_qs.filter(semester_id=semester_id)
        if regulation_id and subjects_qs.filter(regulation_id=regulation_id).exists():
            subjects_qs = subjects_qs.filter(regulation_id=regulation_id)
        subjects = list(subjects_qs.order_by('subject_code'))

        if not subjects and department:
            subjects = list(Subject.objects.filter(department=department).order_by('subject_code'))

        if not subjects:
            return HttpResponse("No subjects found matching the selected criteria.", status=400)

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

        exams = []
        if exam_ids:
            exams = list(Exam.objects.filter(id__in=exam_ids))
        elif exam_type_id:
            exams = list(Exam.objects.filter(exam_type_id=exam_type_id))

        active_grades = list(GradeSystem.objects.filter(is_active=True))

        def evaluate_mark(val):
            if val is None:
                return True, False, 0.0, "AB"
            str_val = str(val).strip().upper()
            if str_val in ['-', '', 'AB', 'ABSENT', 'UA']:
                return True, False, 0.0, str_val or "AB"
            try:
                num_val = float(str_val)
                absent_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and float(g.min_mark) == 0 and float(g.max_mark) == 0 and not g.is_pass), None)
                if absent_entry and num_val == 0:
                    return True, False, 0.0, "UA"
                
                matching_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark) == 0) and float(g.min_mark) <= num_val <= float(g.max_mark)), None)
                if matching_entry:
                    return False, matching_entry.is_pass, num_val, str_val
                
                pass_entries = [g for g in active_grades if g.is_pass and g.min_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark or 0) == 0)]
                if pass_entries:
                    min_pass = min(float(g.min_mark) for g in pass_entries)
                    return False, (num_val >= min_pass), num_val, str_val
                
                return False, (num_val >= 50.0), num_val, str_val
            except ValueError:
                matching_grade = next((g for g in active_grades if g.grade.upper() == str_val), None)
                if matching_grade:
                    is_abs = (matching_grade.min_mark is not None and matching_grade.max_mark is not None and float(matching_grade.min_mark) == 0 and float(matching_grade.max_mark) == 0) or str_val == 'UA'
                    return is_abs, matching_grade.is_pass, 0.0, str_val
                is_fail_code = str_val in ['U', 'UA', 'F', 'RA', 'AB', 'ABSENT']
                return (str_val in ['AB', 'ABSENT', 'UA']), (not is_fail_code), 0.0, str_val

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=35,
            rightMargin=35,
            topMargin=30,
            bottomMargin=30
        )
        styles = getSampleStyleSheet()

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        img_data = response.read()
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

        if not logo_flowable:
            fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
            try:
                if os.path.exists(fallback_logo_path):
                    pil_img = PILImage.open(fallback_logo_path)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=45, height=45)
            except Exception:
                pass

        story = []

        sem_num = 1
        if semester_id and str(semester_id).isdigit():
            sem_num = int(semester_id)
        elif semester_obj and hasattr(semester_obj, 'id') and isinstance(semester_obj.id, int):
            sem_num = semester_obj.id

        year_roman = 'I'
        if sem_num in [3, 4]:
            year_roman = 'II'
        elif sem_num in [5, 6]:
            year_roman = 'III'
        elif sem_num in [7, 8]:
            year_roman = 'IV'

        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'A')
        year_sem_sec_str = f"{year_roman} / Semester {sem_num} / {sec_name}"

        exam_title_str = ""
        if exams:
            exam_title_str = " / ".join([e.exam_name.upper() for e in exams])
        elif exam_type_id:
            ex_type_obj = ExamType.objects.filter(id=exam_type_id).first()
            if ex_type_obj:
                exam_title_str = ex_type_obj.exam_type_name.upper()

        if not exam_title_str:
            exam_title_str = "EXAM"

        header_title_style = ParagraphStyle(
            name='ConsolidatedHdrTitle',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            alignment=1,
            textColor=colors.black
        )

        college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
        college_header_parts = []
        if college_name_str:
            college_header_parts.append(college_name_str)
        if exam_title_str:
            college_header_parts.append(exam_title_str)
        college_header_parts.append("CONSOLIDATED EXAM RESULT ANALYSIS")
        header_title_text = "<br/>".join(college_header_parts)
        title_paragraph = Paragraph(f"<b>{header_title_text}</b>", header_title_style)

        if logo_flowable:
            header_table_data = [[logo_flowable, title_paragraph]]
            header_table = Table(header_table_data, colWidths=[65, 460])
        else:
            header_table_data = [[title_paragraph]]
            header_table = Table(header_table_data, colWidths=[525])

        header_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        dept_name_str = department.department_name.title() if department else ""
        batch_str = batch.batch if batch else ""
        regulation_str = ""
        if regulation_id:
            reg_obj = Regulation.objects.filter(id=regulation_id).first()
            if reg_obj:
                regulation_str = reg_obj.regulation_code

        lbl_bold = ParagraphStyle(
            name='CeraLblBold',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )

        val_norm = ParagraphStyle(
            name='CeraValNorm',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            textColor=colors.black
        )

        meta_data = [
            [
                Paragraph("<b>Department:</b>", lbl_bold), Paragraph(dept_name_str, val_norm),
                Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(batch_str, val_norm)
            ],
            [
                Paragraph("<b>Year/Sem/Sec:</b>", lbl_bold), Paragraph(year_sem_sec_str, val_norm),
                Paragraph("<b>Regulation:</b>", lbl_bold), Paragraph(regulation_str, val_norm)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[80, 187, 80, 188])
        meta_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 15))

        tbl_hdr_style = ParagraphStyle(
            name='ConsolidatedTblHdr',
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.black
        )
        tbl_cell_center = ParagraphStyle(
            name='ConsolidatedTblCellCenter',
            fontName='Helvetica',
            fontSize=8,
            leading=10,
            alignment=1,
            textColor=colors.black
        )
        try:
            pdfmetrics.registerFont(TTFont('ArialUni', 'C:\\Windows\\Fonts\\ARIALUNI.TTF'))
            font_name_left = 'ArialUni'
        except Exception:
            font_name_left = 'Helvetica'

        tbl_cell_left = ParagraphStyle(
            name='ConsolidatedTblCellLeft',
            fontName=font_name_left,
            fontSize=8,
            leading=10,
            alignment=0,
            textColor=colors.black
        )

        m_qs_all = Marks.objects.filter(student__in=students, subject__in=subjects)
        if exams:
            m_qs_all = m_qs_all.filter(exam__in=exams)
        
        all_marks_list = list(m_qs_all)
        student_fail_counts = {st.id: 0 for st in students}

        raw_rows = []
        has_any_exam_date = False

        for subj in subjects:
            tt_exam_qs = ExamTimetable.objects.filter(subject=subj)
            if exams:
                tt_exam_qs = tt_exam_qs.filter(exam__in=exams)
            if department:
                tt_exam_qs = tt_exam_qs.filter(department=department)
            if section_obj:
                tt_exam_qs = tt_exam_qs.filter(section=section_obj)
            
            tt_exam_item = tt_exam_qs.first()
            if not tt_exam_item and exams:
                tt_exam_item = ExamTimetable.objects.filter(exam__in=exams).first()

            exam_date_str = ""
            if tt_exam_item and tt_exam_item.exam_date:
                exam_date_str = tt_exam_item.exam_date.strftime('%d/%m/%Y')
                has_any_exam_date = True
            
            ct_item = ClassTimetable.objects.filter(subject=subj).exclude(faculty=None).first()
            faculty_name = ""
            if ct_item and ct_item.faculty:
                faculty_name = ct_item.faculty.name or ct_item.faculty.username or ""
            if not faculty_name:
                m_item = [m for m in all_marks_list if m.subject_id == subj.id and m.created_by]
                if m_item and m_item[0].created_by:
                    faculty_name = m_item[0].created_by.name or m_item[0].created_by.username or ""
            if not faculty_name:
                faculty_name = "Mrs AMBIGA A"

            subj_marks = [m for m in all_marks_list if m.subject_id == subj.id]
            subj_marks_dict = {m.student_id: m.marks_obtained for m in subj_marks}

            total_students_cnt = len(students)
            appeared_cnt = 0
            passed_cnt = 0
            failed_cnt = 0

            for st in students:
                raw_val = subj_marks_dict.get(st.id)
                is_abs, is_pass, num_val, str_val = evaluate_mark(raw_val)

                if not is_abs:
                    appeared_cnt += 1
                    if is_pass:
                        passed_cnt += 1
                    else:
                        failed_cnt += 1
                        student_fail_counts[st.id] += 1
                else:
                    failed_cnt += 1
                    student_fail_counts[st.id] += 1

            pass_pct = f"{round((passed_cnt / appeared_cnt * 100), 2):.2f}%" if appeared_cnt > 0 else "0.00%"
            
            raw_rows.append({
                'exam_date': exam_date_str,
                'code': subj.subject_code,
                'name': subj.subject_name,
                'faculty': faculty_name,
                'total': str(total_students_cnt),
                'appear': str(appeared_cnt),
                'pass': str(passed_cnt),
                'fail': str(failed_cnt),
                'pct': pass_pct
            })

        table_data = []
        if has_any_exam_date:
            table_data.append([
                Paragraph("<b>Exam Date</b>", tbl_hdr_style),
                Paragraph("<b>Subject Code</b>", tbl_hdr_style),
                Paragraph("<b>Subject Name</b>", tbl_hdr_style),
                Paragraph("<b>Faculty Handling</b>", tbl_hdr_style),
                Paragraph("<b>Total Students</b>", tbl_hdr_style),
                Paragraph("<b>Total Appear</b>", tbl_hdr_style),
                Paragraph("<b>Pass</b>", tbl_hdr_style),
                Paragraph("<b>Fail</b>", tbl_hdr_style),
                Paragraph("<b>Pass %</b>", tbl_hdr_style)
            ])
            for r in raw_rows:
                table_data.append([
                    Paragraph(r['exam_date'], tbl_cell_center),
                    Paragraph(r['code'], tbl_cell_center),
                    Paragraph(r['name'], tbl_cell_left),
                    Paragraph(r['faculty'], tbl_cell_left),
                    Paragraph(r['total'], tbl_cell_center),
                    Paragraph(r['appear'], tbl_cell_center),
                    Paragraph(r['pass'], tbl_cell_center),
                    Paragraph(r['fail'], tbl_cell_center),
                    Paragraph(r['pct'], tbl_cell_center)
                ])
            col_widths = [55, 55, 125, 100, 40, 40, 35, 35, 50]
        else:
            table_data.append([
                Paragraph("<b>Subject Code</b>", tbl_hdr_style),
                Paragraph("<b>Subject Name</b>", tbl_hdr_style),
                Paragraph("<b>Faculty Handling</b>", tbl_hdr_style),
                Paragraph("<b>Total Students</b>", tbl_hdr_style),
                Paragraph("<b>Total Appear</b>", tbl_hdr_style),
                Paragraph("<b>Pass</b>", tbl_hdr_style),
                Paragraph("<b>Fail</b>", tbl_hdr_style),
                Paragraph("<b>Pass %</b>", tbl_hdr_style)
            ])
            for r in raw_rows:
                table_data.append([
                    Paragraph(r['code'], tbl_cell_center),
                    Paragraph(r['name'], tbl_cell_left),
                    Paragraph(r['faculty'], tbl_cell_left),
                    Paragraph(r['total'], tbl_cell_center),
                    Paragraph(r['appear'], tbl_cell_center),
                    Paragraph(r['pass'], tbl_cell_center),
                    Paragraph(r['fail'], tbl_cell_center),
                    Paragraph(r['pct'], tbl_cell_center)
                ])
            col_widths = [65, 160, 110, 40, 40, 35, 35, 50]

        main_table = Table(table_data, colWidths=col_widths)
        main_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
        ]))
        story.append(main_table)
        story.append(Spacer(1, 20))

        fail_0 = 0
        fail_1 = 0
        fail_2 = 0
        fail_3 = 0
        fail_more = 0

        for st_id, f_cnt in student_fail_counts.items():
            if f_cnt == 0:
                fail_0 += 1
            elif f_cnt == 1:
                fail_1 += 1
            elif f_cnt == 2:
                fail_2 += 1
            elif f_cnt == 3:
                fail_3 += 1
            else:
                fail_more += 1

        total_students_val = len(students)
        overall_pass_pct = f"{round((fail_0 / total_students_val * 100), 2):.2f}%" if total_students_val > 0 else "0.00%"

        is_university_exam = False
        if exam_type_id:
            ex_type_obj = ExamType.objects.filter(id=exam_type_id).first()
            if ex_type_obj and 'UNIV' in ex_type_obj.exam_type_name.upper():
                is_university_exam = True

        if not is_university_exam and exams:
            for ex in exams:
                if ex.exam_type and 'UNIV' in ex.exam_type.exam_type_name.upper():
                    is_university_exam = True
                    break

        story.append(Paragraph("<b>Overall Student Performance</b>", header_title_style))
        story.append(Spacer(1, 6))

        if is_university_exam:
            try:
                current_sem_val = int(sem_num)
            except (ValueError, TypeError):
                current_sem_val = 1

            if current_sem_val <= 1:
                cum_fail_0 = fail_0
                cum_fail_1 = fail_1
                cum_fail_2 = fail_2
                cum_fail_3 = fail_3
                cum_fail_more = fail_more
                cum_overall_pass_pct = overall_pass_pct
            else:
                from django.db.models import Q
                univ_marks_qs = Marks.objects.filter(
                    student__in=students,
                    exam__exam_type__exam_type_name__icontains='University'
                ).select_related('exam', 'subject')

                student_subject_cleared = {st.id: {} for st in students}
                for m in univ_marks_qs:
                    is_abs, is_pass, num_val, str_val = evaluate_mark(m.marks_obtained)
                    if m.student_id in student_subject_cleared:
                        current_status = student_subject_cleared[m.student_id].get(m.subject_id, False)
                        student_subject_cleared[m.student_id][m.subject_id] = current_status or is_pass

                student_cum_fail_counts = {}
                for st in students:
                    subj_status = student_subject_cleared.get(st.id, {})
                    standing_arrears = sum(1 for is_cleared in subj_status.values() if not is_cleared)
                    student_cum_fail_counts[st.id] = standing_arrears

                cum_fail_0 = sum(1 for f in student_cum_fail_counts.values() if f == 0)
                cum_fail_1 = sum(1 for f in student_cum_fail_counts.values() if f == 1)
                cum_fail_2 = sum(1 for f in student_cum_fail_counts.values() if f == 2)
                cum_fail_3 = sum(1 for f in student_cum_fail_counts.values() if f == 3)
                cum_fail_more = sum(1 for f in student_cum_fail_counts.values() if f > 3)
                cum_overall_pass_pct = f"{round((cum_fail_0 / total_students_val * 100), 2):.2f}%" if total_students_val > 0 else "0.00%"

            summary_hdr_style = ParagraphStyle(name='SumHdr', fontName='Helvetica-Bold', fontSize=8, alignment=1)
            summary_cell_center = ParagraphStyle(name='SumCellCenter', fontName='Helvetica', fontSize=8, alignment=1)

            summary_table_data = [
                [
                    Paragraph("<b>Description</b>", summary_hdr_style),
                    Paragraph("<b>Total No. of Students</b>", summary_hdr_style),
                    Paragraph("<b>All Cleared</b>", summary_hdr_style),
                    Paragraph("<b>One</b>", summary_hdr_style),
                    Paragraph("<b>Two</b>", summary_hdr_style),
                    Paragraph("<b>Three</b>", summary_hdr_style),
                    Paragraph("<b>>Three</b>", summary_hdr_style),
                    Paragraph("<b>% of Pass</b>", summary_hdr_style)
                ],
                [
                    Paragraph(f"Semester {sem_num}", summary_cell_center),
                    Paragraph(str(total_students_val), summary_cell_center),
                    Paragraph(str(fail_0), summary_cell_center),
                    Paragraph(str(fail_1), summary_cell_center),
                    Paragraph(str(fail_2), summary_cell_center),
                    Paragraph(str(fail_3), summary_cell_center),
                    Paragraph(str(fail_more), summary_cell_center),
                    Paragraph(overall_pass_pct, summary_cell_center)
                ],
                [
                    Paragraph("Cumulative", summary_cell_center),
                    Paragraph(str(total_students_val), summary_cell_center),
                    Paragraph(str(cum_fail_0), summary_cell_center),
                    Paragraph(str(cum_fail_1), summary_cell_center),
                    Paragraph(str(cum_fail_2), summary_cell_center),
                    Paragraph(str(cum_fail_3), summary_cell_center),
                    Paragraph(str(cum_fail_more), summary_cell_center),
                    Paragraph(cum_overall_pass_pct, summary_cell_center)
                ]
            ]

            summary_table = Table(summary_table_data, colWidths=[95, 75, 65, 50, 50, 50, 60, 90])
            summary_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                ('LEFTPADDING', (0,0), (-1,-1), 4),
                ('RIGHTPADDING', (0,0), (-1,-1), 4),
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 40))

        else:
            perf_hdr_style = ParagraphStyle(name='PerfHdrInt', fontName='Helvetica-Bold', fontSize=9, alignment=1)
            tbl_cell_left_perf = ParagraphStyle(name='PerfLeftInt', fontName='Helvetica', fontSize=8, alignment=0)

            perf_data = [
                [Paragraph("<b>Performance Category</b>", perf_hdr_style), Paragraph("<b>Number of Students</b>", perf_hdr_style)],
                [Paragraph("Cleared All Subjects", tbl_cell_left_perf), Paragraph(str(fail_0), tbl_cell_center)],
                [Paragraph("Failed in One Subject", tbl_cell_left_perf), Paragraph(str(fail_1), tbl_cell_center)],
                [Paragraph("Failed in Two Subjects", tbl_cell_left_perf), Paragraph(str(fail_2), tbl_cell_center)],
                [Paragraph("Failed in Three Subjects", tbl_cell_left_perf), Paragraph(str(fail_3), tbl_cell_center)],
                [Paragraph("Failed in More Than Three Subjects", tbl_cell_left_perf), Paragraph(str(fail_more), tbl_cell_center)],
            ]

            perf_table = Table(perf_data, colWidths=[250, 150])
            perf_table.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
                ('RIGHTPADDING', (0,0), (-1,-1), 6),
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E2E8F0')),
            ]))
            story.append(perf_table)
            story.append(Spacer(1, 40))

        sig_data = [[
            Paragraph("<b>Test Coordinator</b>", ParagraphStyle(name='Sig1', fontName='Helvetica', fontSize=9, alignment=1)),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='Sig2', fontName='Helvetica', fontSize=9, alignment=1)),
            Paragraph("<b>Vice Principal</b>", ParagraphStyle(name='Sig3', fontName='Helvetica', fontSize=9, alignment=1)),
            Paragraph("<b>Principal</b>", ParagraphStyle(name='Sig4', fontName='Helvetica', fontSize=9, alignment=1))
        ]]
        sig_table = Table(sig_data, colWidths=[130, 130, 130, 130])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Consolidated_Exam_Result_Analysis_{datetime.date.today().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        return response

    @action(detail=False, methods=['post', 'get'], url_path='student-performance-report/pdf')
    def student_performance_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else request.query_params
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        exam_type_id = req_data.get('exam_type_id')
        exam_ids_raw = req_data.get('exam_ids') or req_data.get('exam_id')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        exam_ids = []
        if isinstance(exam_ids_raw, list):
            exam_ids = exam_ids_raw
        elif isinstance(exam_ids_raw, str) and exam_ids_raw.strip():
            exam_ids = [x.strip() for x in exam_ids_raw.split(',') if x.strip()]
        elif isinstance(exam_ids_raw, int):
            exam_ids = [exam_ids_raw]

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

        exams = []
        if exam_ids:
            exams = list(Exam.objects.filter(id__in=exam_ids))
        elif exam_type_id:
            exams = list(Exam.objects.filter(exam_type_id=exam_type_id))

        active_grades = list(GradeSystem.objects.filter(is_active=True))

        def evaluate_mark_spr(val):
            if val is None:
                return True, False
            str_val = str(val).strip().upper()
            if str_val in ['-', '', 'AB', 'ABSENT', 'UA']:
                return True, False
            try:
                num_val = float(str_val)
                absent_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None
                                     and float(g.min_mark) == 0 and float(g.max_mark) == 0 and not g.is_pass), None)
                if absent_entry and num_val == 0:
                    return True, False
                matching_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None
                                       and not (float(g.min_mark) == 0 and float(g.max_mark) == 0)
                                       and float(g.min_mark) <= num_val <= float(g.max_mark)), None)
                if matching_entry:
                    return False, matching_entry.is_pass
                pass_entries = [g for g in active_grades if g.is_pass and g.min_mark is not None
                                and not (float(g.min_mark) == 0 and float(g.max_mark or 0) == 0)]
                if pass_entries:
                    min_pass = min(float(g.min_mark) for g in pass_entries)
                    return False, (num_val >= min_pass)
                return False, (num_val >= 50.0)
            except ValueError:
                matching_grade = next((g for g in active_grades if g.grade.upper() == str_val), None)
                if matching_grade:
                    is_abs = (matching_grade.min_mark is not None and matching_grade.max_mark is not None
                              and float(matching_grade.min_mark) == 0 and float(matching_grade.max_mark) == 0) or str_val == 'UA'
                    return is_abs, matching_grade.is_pass
                is_fail_code = str_val in ['U', 'UA', 'F', 'RA', 'AB', 'ABSENT']
                return (str_val in ['AB', 'ABSENT', 'UA']), (not is_fail_code)

        marks_qs = Marks.objects.filter(student__in=students)
        if exams:
            marks_qs = marks_qs.filter(exam__in=exams)
        elif exam_type_id:
            marks_qs = marks_qs.filter(exam__exam_type_id=exam_type_id)
        all_marks = list(marks_qs.order_by('id'))

        student_fail_counts = {}
        for st in students:
            st_subject_marks = {}
            for m in all_marks:
                if m.student_id == st.id:
                    st_subject_marks[m.subject_id] = m.marks_obtained

            fail_count = 0
            for mark_val in st_subject_marks.values():
                is_abs, is_pass = evaluate_mark_spr(mark_val)
                if not is_pass:
                    fail_count += 1
            student_fail_counts[st.id] = fail_count

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=35, rightMargin=35, topMargin=30, bottomMargin=30)

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req_obj = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req_obj, timeout=5) as resp:
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

        exam_title_str = ""
        if exams:
            exam_title_str = " / ".join([e.exam_name.upper() for e in exams])
        elif exam_type_id:
            ex_type_obj = ExamType.objects.filter(id=exam_type_id).first()
            if ex_type_obj:
                exam_title_str = ex_type_obj.exam_type_name.upper()
        if not exam_title_str:
            exam_title_str = "ALL EXAMS"

        hdr_style = ParagraphStyle(name='SPRHdrTitle', fontName='Helvetica-Bold', fontSize=11, leading=14, alignment=1, textColor=colors.black)
        college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""

        hdr_parts = []
        if college_name_str:
            hdr_parts.append(college_name_str)
        if exam_title_str:
            hdr_parts.append(exam_title_str)
            hdr_parts.append("STUDENT PERFORMANCE REPORT")

        hdr_paragraph = Paragraph("<br/>".join(f"<b>{p}</b>" for p in hdr_parts), hdr_style)

        if logo_flowable:
            header_table = Table([[logo_flowable, hdr_paragraph]], colWidths=[65, 460])
        else:
            header_table = Table([[hdr_paragraph]], colWidths=[525])
        header_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
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

        lbl_bold = ParagraphStyle(name='SPRLblBold', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.black)
        val_norm = ParagraphStyle(name='SPRValNorm', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.black)

        meta_data = [
            [
                Paragraph("<b>Department:</b>", lbl_bold), Paragraph(department.department_name.title() if department else "", val_norm),
                Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(batch_str, val_norm),
            ],
            [
                Paragraph("<b>Year/Sem/Section:</b>", lbl_bold), Paragraph(f"{year_roman} / Semester {sem_num} / {sec_name}", val_norm),
                Paragraph("<b>Regulation:</b>", lbl_bold), Paragraph(regulation_str, val_norm),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[90, 177, 80, 178])
        meta_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 12))

        try:
            pdfmetrics.registerFont(TTFont('ArialUni', 'C:\\Windows\\Fonts\\ARIALUNI.TTF'))
            name_font = 'ArialUni'
        except Exception:
            name_font = 'Helvetica'

        tbl_hdr_style = ParagraphStyle(name='SPRTblHdr', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.black)
        tbl_cell_center = ParagraphStyle(name='SPRTblCC', fontName='Helvetica', fontSize=8, leading=10, alignment=1, textColor=colors.black)
        tbl_cell_left = ParagraphStyle(name='SPRTblCL', fontName=name_font, fontSize=8, leading=10, alignment=0, textColor=colors.black)
        tbl_cell_fail = ParagraphStyle(name='SPRTblFail', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#1D4ED8'))

        table_data = [[
            Paragraph("<b>S.No</b>", tbl_hdr_style),
            Paragraph("<b>Register No</b>", tbl_hdr_style),
            Paragraph("<b>Student Name</b>", tbl_hdr_style),
            Paragraph("<b>Arrears</b>", tbl_hdr_style),
        ]]
        row_styles = []
        for idx, st in enumerate(students, start=1):
            st_name = (st.user.name if st.user and st.user.name else (st.user.username if st.user else "")) or ""
            reg_no = st.register_number or st.roll_number or (st.user.username if st.user else "") or ""
            fail_count = student_fail_counts.get(st.id, 0)
            arrears_para = Paragraph(str(fail_count), tbl_cell_fail if fail_count > 0 else tbl_cell_center)

            table_data.append([
                Paragraph(str(idx), tbl_cell_center),
                Paragraph(reg_no, tbl_cell_center),
                Paragraph(st_name, tbl_cell_left),
                arrears_para,
            ])
            if fail_count > 0:
                row_styles.append(('TEXTCOLOR', (3, idx), (3, idx), colors.HexColor('#1D4ED8')))

        col_widths = [35, 110, 310, 70]
        perf_table = Table(table_data, colWidths=col_widths, repeatRows=1)
        ts = [
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ]
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                ts.append(('BACKGROUND', (0, i), (-1, i), colors.HexColor('#F8FAFC')))
        ts.extend(row_styles)
        perf_table.setStyle(TableStyle(ts))
        story.append(perf_table)
        story.append(Spacer(1, 25))

        total_st = len(students)
        count_0    = sum(1 for v in student_fail_counts.values() if v == 0)
        count_1    = sum(1 for v in student_fail_counts.values() if v == 1)
        count_2    = sum(1 for v in student_fail_counts.values() if v == 2)
        count_3plus = sum(1 for v in student_fail_counts.values() if v >= 3)

        summ_hdr  = ParagraphStyle(name='SPRSummHdr',  fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.black)
        summ_cell = ParagraphStyle(name='SPRSummCell', fontName='Helvetica',      fontSize=8, leading=10, alignment=1, textColor=colors.black)
        summ_cell_left = ParagraphStyle(name='SPRSummCellL', fontName='Helvetica', fontSize=8, leading=10, alignment=0, textColor=colors.black)

        summ_bold_left = ParagraphStyle(name='SPRSummBL',   fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=0, textColor=colors.black)
        summ_blue = ParagraphStyle(name='SPRSummBlue', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.HexColor('#1D4ED8'))

        breakdown_data = [
            [
                Paragraph("<b>No. of Arrears</b>",        summ_hdr),
                Paragraph("<b>No. of Students</b>",       summ_hdr),
            ],
            [
                Paragraph("0  (No Arrears)",               summ_cell_left),
                Paragraph(str(count_0),                    summ_cell),
            ],
            [
                Paragraph("1",                             summ_cell_left),
                Paragraph(str(count_1),  summ_blue if count_1  > 0 else summ_cell),
            ],
            [
                Paragraph("2",                             summ_cell_left),
                Paragraph(str(count_2),  summ_blue if count_2  > 0 else summ_cell),
            ],
            [
                Paragraph("3 or More",                     summ_cell_left),
                Paragraph(str(count_3plus), summ_blue if count_3plus > 0 else summ_cell),
            ],
            [
                Paragraph("<b>Total Students</b>",         summ_bold_left),
                Paragraph(str(total_st),                   summ_hdr),
            ],
        ]

        breakdown_col_widths = [250, 150]
        breakdown_table = Table(breakdown_data, colWidths=breakdown_col_widths)
        breakdown_ts = [
            ('GRID',        (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN',      (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',       (1, 0), (1, -1),  'CENTER'),
            ('TOPPADDING',  (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING',(0,0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',(0, 0), (-1, -1), 8),
            ('BACKGROUND',  (0, 0), (-1,  0), colors.HexColor('#E2E8F0')),
            ('BACKGROUND',  (0, -1),(-1, -1), colors.HexColor('#F1F5F9')),
            ('BACKGROUND',  (0, 2), (-1,  2), colors.HexColor('#F8FAFC')),
            ('BACKGROUND',  (0, 4), (-1,  4), colors.HexColor('#F8FAFC')),
        ]
        breakdown_table.setStyle(TableStyle(breakdown_ts))
        story.append(breakdown_table)
        story.append(Spacer(1, 40))

        sig_style = ParagraphStyle(name='SPRSig', fontName='Helvetica', fontSize=9, alignment=1)
        sig_data = [[
            Paragraph("<b>Test Coordinator</b>", sig_style),
            Paragraph("<b>HOD</b>", sig_style),
            Paragraph("<b>Vice Principal</b>", sig_style),
            Paragraph("<b>Principal</b>", sig_style),
        ]]
        sig_table = Table(sig_data, colWidths=[130, 130, 130, 130])
        sig_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
        story.append(sig_table)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Student_Performance_Report_{datetime.date.today().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        return response

    @action(detail=False, methods=['post', 'get'], url_path='capa-report/pdf')
    def capa_report_pdf(self, request):
        req_data = request.data if request.method == 'POST' else request.query_params
        department_id = req_data.get('department_id')
        batch_id = req_data.get('batch_id')
        section_id = req_data.get('section_id')
        semester_id = req_data.get('semester_id')
        regulation_id = req_data.get('regulation_id')
        subject_id = req_data.get('subject_id')
        exam_type_id = req_data.get('exam_type_id')
        exam_ids_raw = req_data.get('exam_ids') or req_data.get('exam_id')
        header_type = req_data.get('header_type') or req_data.get('header_type_id') or 'Main'

        exam_ids = []
        if isinstance(exam_ids_raw, list):
            exam_ids = exam_ids_raw
        elif isinstance(exam_ids_raw, str) and exam_ids_raw.strip():
            exam_ids = [x.strip() for x in exam_ids_raw.split(',') if x.strip()]
        elif isinstance(exam_ids_raw, int):
            exam_ids = [exam_ids_raw]

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

        subject_obj = None
        if subject_id:
            subject_obj = Subject.objects.filter(id=subject_id).first()
        if not subject_obj and department:
            subject_obj = Subject.objects.filter(department=department).first()

        if not subject_obj:
            return HttpResponse("Please select a valid subject to generate CAPA Form.", status=400)

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

        exams = []
        if exam_ids:
            exams = list(Exam.objects.filter(id__in=exam_ids))
        elif exam_type_id:
            exams = list(Exam.objects.filter(exam_type_id=exam_type_id))

        active_grades = list(GradeSystem.objects.filter(is_active=True))

        def evaluate_mark(val):
            if val is None:
                return True, False, 0.0, "AB"
            str_val = str(val).strip().upper()
            if str_val in ['-', '', 'AB', 'ABSENT', 'UA']:
                return True, False, 0.0, str_val or "AB"
            try:
                num_val = float(str_val)
                absent_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and float(g.min_mark) == 0 and float(g.max_mark) == 0 and not g.is_pass), None)
                if absent_entry and num_val == 0:
                    return True, False, 0.0, "UA"
                
                matching_entry = next((g for g in active_grades if g.min_mark is not None and g.max_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark) == 0) and float(g.min_mark) <= num_val <= float(g.max_mark)), None)
                if matching_entry:
                    return False, matching_entry.is_pass, num_val, str_val
                
                pass_entries = [g for g in active_grades if g.is_pass and g.min_mark is not None and not (float(g.min_mark) == 0 and float(g.max_mark or 0) == 0)]
                if pass_entries:
                    min_pass = min(float(g.min_mark) for g in pass_entries)
                    return False, (num_val >= min_pass), num_val, str_val
                
                return False, (num_val >= 50.0), num_val, str_val
            except ValueError:
                matching_grade = next((g for g in active_grades if g.grade.upper() == str_val), None)
                if matching_grade:
                    is_abs = (matching_grade.min_mark is not None and matching_grade.max_mark is not None and float(matching_grade.min_mark) == 0 and float(matching_grade.max_mark) == 0) or str_val == 'UA'
                    return is_abs, matching_grade.is_pass, 0.0, str_val
                is_fail_code = str_val in ['U', 'UA', 'F', 'RA', 'AB', 'ABSENT']
                return (str_val in ['AB', 'ABSENT', 'UA']), (not is_fail_code), 0.0, str_val

        m_qs = Marks.objects.filter(subject=subject_obj, student__in=students)
        if exams:
            m_qs = m_qs.filter(exam__in=exams)
        
        marks_dict = {m.student_id: m.marks_obtained for m in m_qs}
        failed_rolls = []

        for st in students:
            raw_val = marks_dict.get(st.id)
            is_abs, is_pass, num_val, str_val = evaluate_mark(raw_val)
            if not is_pass or is_abs:
                roll_display = str(st.roll_number or st.register_number or st.user.name)
                failed_rolls.append(roll_display)

        failed_rolls_str = ", ".join(failed_rolls) if failed_rolls else "Nil"

        tt_qs = ExamTimetable.objects.filter(subject=subject_obj)
        if exams:
            tt_qs = tt_qs.filter(exam__in=exams)
        tt_item = tt_qs.first()
        exam_date_str = tt_item.exam_date.strftime('%d/%m/%Y') if (tt_item and tt_item.exam_date) else ""
        if not exam_date_str:
            exam_date_str = req_data.get('exam_date') or datetime.date.today().strftime('%d/%m/%Y')

        ct_item = ClassTimetable.objects.filter(subject=subject_obj).exclude(faculty=None).first()
        faculty_name = ""
        if ct_item and ct_item.faculty:
            faculty_name = ct_item.faculty.name or ct_item.faculty.username or ""
        if not faculty_name:
            m_item = Marks.objects.filter(subject=subject_obj).exclude(created_by=None).first()
            if m_item and m_item.created_by:
                faculty_name = m_item.created_by.name or m_item.created_by.username or ""
        if not faculty_name:
            faculty_name = "Mrs AMBIGA A"

        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=35,
            rightMargin=35,
            topMargin=30,
            bottomMargin=30
        )

        logo_url = college_header_obj.primary_logo if college_header_obj else None
        logo_flowable = None
        if logo_url:
            try:
                if isinstance(logo_url, str) and logo_url.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(logo_url, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        img_data = response.read()
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

        if not logo_flowable:
            fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
            try:
                if os.path.exists(fallback_logo_path):
                    pil_img = PILImage.open(fallback_logo_path)
                    out_io = BytesIO()
                    pil_img.save(out_io, format='PNG')
                    out_io.seek(0)
                    logo_flowable = RLImage(out_io, width=45, height=45)
            except Exception:
                pass

        story = []

        sem_num = 1
        if semester_id and str(semester_id).isdigit():
            sem_num = int(semester_id)
        elif semester_obj and hasattr(semester_obj, 'id') and isinstance(semester_obj.id, int):
            sem_num = semester_obj.id

        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'A')

        exam_title_str = ""
        if exams:
            exam_title_str = " / ".join([e.exam_name.upper() for e in exams])
        elif exam_type_id:
            ex_type_obj = ExamType.objects.filter(id=exam_type_id).first()
            if ex_type_obj:
                exam_title_str = ex_type_obj.exam_type_name.upper()

        if not exam_title_str:
            exam_title_str = "INTERNAL EXAM"

        header_title_style = ParagraphStyle(
            name='CapaHdrTitle',
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=14,
            alignment=1,
            textColor=colors.black
        )

        college_name_str = college_header_obj.college_name.upper() if (college_header_obj and college_header_obj.college_name) else ""
        college_header_parts = []
        if college_name_str:
            college_header_parts.append(college_name_str)
        if exam_title_str:
            college_header_parts.append(exam_title_str)
        college_header_parts.append("CORRECTIVE AND PREVENTIVE ACTION FORM")
        header_title_text = "<br/>".join(college_header_parts)
        title_paragraph = Paragraph(f"<b>{header_title_text}</b>", header_title_style)

        if logo_flowable:
            header_table_data = [[logo_flowable, title_paragraph]]
            header_table = Table(header_table_data, colWidths=[65, 460])
        else:
            header_table_data = [[title_paragraph]]
            header_table = Table(header_table_data, colWidths=[525])

        header_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        dept_name_str = department.department_name.title() if department else ""
        batch_str = batch.batch if batch else ""
        regulation_str = ""
        if regulation_id:
            reg_obj = Regulation.objects.filter(id=regulation_id).first()
            if reg_obj:
                regulation_str = reg_obj.regulation_code

        lbl_bold = ParagraphStyle(name='CapaLblBold', fontName='Helvetica-Bold', fontSize=8, leading=10, textColor=colors.black)
        val_norm = ParagraphStyle(name='CapaValNorm', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.black)

        subj_full_str = f"{subject_obj.subject_code} - {subject_obj.subject_name}" if subject_obj else "—"

        meta_data = [
            [
                Paragraph("<b>Department:</b>", lbl_bold), Paragraph(dept_name_str, val_norm),
                Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(str(batch_str), val_norm)
            ],
            [
                Paragraph("<b>Sem / Section:</b>", lbl_bold), Paragraph(f"Sem {sem_num} - Sec {sec_name}", val_norm),
                Paragraph("<b>Date of Exam:</b>", lbl_bold), Paragraph(exam_date_str, val_norm)
            ],
            [
                Paragraph("<b>Subject:</b>", lbl_bold), Paragraph(subj_full_str, val_norm),
                Paragraph("<b>Regulation:</b>", lbl_bold), Paragraph(regulation_str, val_norm)
            ],
            [
                Paragraph("<b>Faculty Handling:</b>", lbl_bold), Paragraph(faculty_name, val_norm),
                Paragraph("", lbl_bold), Paragraph("", val_norm)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[80, 187, 80, 188])
        meta_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,0), (2,-2), colors.HexColor('#F8FAFC')),
            ('SPAN', (1,3), (3,3)),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        issue_type_style = ParagraphStyle(name='IssueTypeStyle', fontName='Helvetica-Bold', fontSize=8.5, leading=11, alignment=1)
        issue_box_data = [
            [
                Paragraph("<b>Issue Type</b>", issue_type_style),
                Paragraph("<b>[X] Poor Performance</b>", issue_type_style),
                Paragraph("<b>[ &nbsp; ] Irregularity</b>", issue_type_style),
                Paragraph("<b>[ &nbsp; ] Others</b>", issue_type_style)
            ]
        ]
        issue_table = Table(issue_box_data, colWidths=[100, 150, 140, 135])
        issue_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,0), (0,0), colors.HexColor('#F8FAFC')),
        ]))
        story.append(issue_table)
        story.append(Spacer(1, 10))

        cell_hdr_style = ParagraphStyle(name='FormHdr', fontName='Helvetica-Bold', fontSize=8.5, leading=11)
        cell_text_style = ParagraphStyle(name='FormTxt', fontName='Helvetica', fontSize=8, leading=11)
        right_action_date_style = ParagraphStyle(name='FormActionDate', fontName='Helvetica-Bold', fontSize=8, leading=11, alignment=2)

        failed_roll_para = Paragraph(failed_rolls_str, cell_text_style)

        form_data = [
            [
                Paragraph("<b>Student's Details</b>", cell_hdr_style),
                failed_roll_para
            ],
            [
                Paragraph("<b>Corrective Measure</b>", cell_hdr_style),
                Paragraph("<br/><br/><br/>", cell_text_style)
            ],
            [
                Paragraph("<b>Root Causes</b>", cell_hdr_style),
                Paragraph("<br/><br/><br/>", cell_text_style)
            ],
            [
                Paragraph("<b>Corrective Action</b>", cell_hdr_style),
                Paragraph("<br/><br/><br/><br/><b>Date of Action: ______________________</b>", right_action_date_style)
            ],
            [
                Paragraph("<b>Effectiveness</b>", cell_hdr_style),
                Paragraph("<br/><br/><br/>", cell_text_style)
            ]
        ]

        form_table = Table(form_data, colWidths=[120, 405])
        form_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(form_table)
        story.append(Spacer(1, 12))

        story.append(Paragraph("<b>Effectiveness Verified By:</b>", ParagraphStyle(name='VerifiedTitle', fontName='Helvetica-Bold', fontSize=8.5, alignment=1)))
        story.append(Spacer(1, 4))

        ver_hdr_style = ParagraphStyle(name='VerHdr', fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1)
        ver_txt_style = ParagraphStyle(name='VerTxt', fontName='Helvetica', fontSize=8, leading=10, alignment=1)
        ver_data = [
            [
                Paragraph("<b>Responsible Member</b>", ver_hdr_style),
                Paragraph("<b>Closed on</b>", ver_hdr_style),
                Paragraph("<b>Details Required to Close</b>", ver_hdr_style),
                Paragraph("<b>Report by Member: Signature with Date</b>", ver_hdr_style)
            ],
            [
                Paragraph(f"<br/>{faculty_name}<br/>", ver_txt_style),
                Paragraph("<br/><br/>", ver_txt_style),
                Paragraph("<br/><br/>", ver_txt_style),
                Paragraph("<br/><br/>", ver_txt_style)
            ]
        ]
        ver_table = Table(ver_data, colWidths=[130, 95, 150, 150])
        ver_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
        ]))
        story.append(ver_table)
        story.append(Spacer(1, 35))

        story.append(Paragraph("<b>HOD</b>", ParagraphStyle(name='HodSig', fontName='Helvetica-Bold', fontSize=9, alignment=1)))

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="CAPA_Form_{datetime.date.today().strftime("%Y%m%d")}.pdf"'
        response.write(pdf)
        return response
