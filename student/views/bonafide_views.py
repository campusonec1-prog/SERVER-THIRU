import io
import re
import datetime
import zoneinfo
from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT, TA_JUSTIFY

from common.report_utils import (
    build_standard_college_header, format_unicode_text, register_unicode_fonts
)
from institution.models import AcademicYear, Department, Batch, CollegeHeader
from student.models import Student, BonafideCertificate
from student.views.admission_report_views import _format_dept_with_program


def _get_ist_now():
    """Returns the current datetime in Indian Standard Time (Asia/Kolkata)."""
    try:
        ist = zoneinfo.ZoneInfo("Asia/Kolkata")
        return datetime.datetime.now(ist)
    except Exception:
        # Fallback to UTC + 5:30 offset
        tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        return datetime.datetime.now(tz)


def _calculate_year_of_study(batch_name, ay_name):
    """
    Calculates year of study (e.g. 'First Year', 'Second Year', 'Third Year', 'Final Year')
    based on batch start year and academic year start year.
    """
    if not batch_name or not ay_name:
        return "First Year"
    b_years = [int(y) for y in re.findall(r'\b\d{4}\b', str(batch_name))]
    ay_years = [int(y) for y in re.findall(r'\b\d{4}\b', str(ay_name))]

    if len(b_years) >= 1 and len(ay_years) >= 1:
        diff = ay_years[0] - b_years[0] + 1
        year_names = {
            1: "First Year",
            2: "Second Year",
            3: "Third Year",
            4: "Final Year",
        }
        if diff in year_names:
            return year_names[diff]
        elif diff > 4:
            return "Final Year"
        elif diff < 1:
            return "First Year"
    return "First Year"


def _resolve_student_details(st, active_ay):
    """
    Extracts and standardizes student details for bonafide generation.
    """
    # 1. Candidate Name
    cand_name = ''
    if st.student_name:
        cand_name = st.student_name.strip()

    app_form = {}
    if hasattr(st, 'application') and st.application and st.application.form_data:
        app_form = st.application.form_data

    personal = app_form.get('personal_information', {}) if isinstance(app_form, dict) else {}
    parent_info = app_form.get('parent_information', {}) if isinstance(app_form, dict) else {}

    if not cand_name:
        cand_name = (
            personal.get('applicant_name') or
            (st.name if hasattr(st, 'name') and st.name else '') or
            'Student'
        ).strip()

    # 2. Gender & Salutation & Relation
    raw_gender = str(personal.get('gender') or getattr(st, 'gender', 'Male')).strip()
    is_female = raw_gender.lower().startswith('f')
    gender = 'Female' if is_female else 'Male'
    salutation = 'Ms.' if is_female else 'Mr.'
    relation = 'D/O' if is_female else 'S/O'

    # 3. Parent / Father Name
    raw_parent = (
        parent_info.get('father_name') or
        parent_info.get('parent_name') or
        parent_info.get('guardian_name') or
        ''
    ).strip()

    # Clean leading titles like "Mr." or "Mrs." to prevent "Mr. Mr. Suresh"
    clean_parent = re.sub(r'^(mr\.|mrs\.|ms\.|dr\.)\s*', '', raw_parent, flags=re.IGNORECASE).strip()

    # 4. Department & Program
    dept_formatted = _format_dept_with_program(st.department) if st.department else '—'

    # 5. Academic Year & Year of Study
    ay_str = active_ay.academic_year if active_ay else '2026-2027'
    batch_str = st.batch.batch if st.batch else ''
    year_of_study = _calculate_year_of_study(batch_str, ay_str)

    today_ist = _get_ist_now().strftime('%d/%m/%Y')

    return {
        'id': st.id,
        'student_id': st.id,
        'roll_number': st.roll_number or '—',
        'register_number': st.register_number or '—',
        'student_name': cand_name.upper(),
        'gender': gender,
        'salutation': salutation,
        'relation': relation,
        'parent_name': clean_parent.upper(),
        'department_name': dept_formatted.upper(),
        'batch': batch_str,
        'year_of_study': year_of_study,
        'academic_year': ay_str,
        'default_purpose': 'Current Enrollment and Eligibility',
        'issue_date': today_ist,
    }


def _generate_bonafide_pdf(data):
    """
    Builds the ReportLab PDF matching the uploaded template:
    - Optional letterhead top margin / college header
    - Date on the top-right
    - Centered boxed title: BONAFIDE CERTIFICATE
    - Paragraph 1: "This is to certify that Mr./Ms. <NAME> S/O / D/O Mr. <PARENT> is studying <YEAR> in the department of <DEPT> in our college during the academic year <AY>."
    - Paragraph 2: "This certificate is issued only for <PURPOSE> Purpose only."
    - Empty lower section for seal & principal signature
    """
    register_unicode_fonts()

    buffer = io.BytesIO()

    include_header = data.get('include_header', False)
    header_obj = None
    if include_header:
        header_obj = CollegeHeader.objects.filter(is_active=True).first()

    # Top margin: If pre-printed letterhead, leave 160pt top space; else 36pt
    top_margin = 36 if include_header else 150
    bottom_margin = 54
    left_margin = 54
    right_margin = 54

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left_margin,
        rightMargin=right_margin,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
    )

    story = []

    # Optional College Header
    if include_header and header_obj:
        hdr_elements = build_standard_college_header(header_obj, A4[0] - left_margin - right_margin)
        for el in hdr_elements:
            story.append(el)
        story.append(Spacer(1, 25))

    # Date Block (Top-right aligned, e.g. "04/11/2026") - Times New Roman
    date_style = ParagraphStyle(
        'BonafideDate',
        fontName='Times-Bold',
        fontSize=13.5,
        leading=18,
        alignment=TA_RIGHT,
        textColor=colors.black,
    )
    issue_date_str = data.get('issue_date') or _get_ist_now().strftime('%d/%m/%Y')
    story.append(Paragraph(f"<b>{issue_date_str}</b>", date_style))

    # Spacing between Date and Boxed Title
    story.append(Spacer(1, 42))

    # Boxed Title: "BONAFIDE CERTIFICATE" inside a black border - Times New Roman
    title_inner_style = ParagraphStyle(
        'BonafideTitleInner',
        fontName='Times-Bold',
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        textColor=colors.black,
    )
    title_p = Paragraph("<b>BONAFIDE CERTIFICATE</b>", title_inner_style)

    # Wrap inside a single-cell table with a solid border
    title_table = Table([[title_p]], colWidths=[260])
    title_table.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 1.5, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 18),
        ('RIGHTPADDING', (0, 0), (-1, -1), 18),
    ]))
    title_table.hAlign = 'CENTER'
    story.append(title_table)

    # Spacing between Title and Body Paragraph
    story.append(Spacer(1, 50))

    # Body Paragraph Style - Times New Roman, bigger font size & leading
    body_style = ParagraphStyle(
        'BonafideBody',
        fontName='Times-Roman',
        fontSize=15.5,
        leading=32,
        alignment=TA_JUSTIFY,
        textColor=colors.black,
    )

    salutation = data.get('salutation', 'Mr.')
    student_name = format_unicode_text(data.get('student_name', 'STUDENT'))
    relation = data.get('relation', 'S/O')
    parent_name = format_unicode_text(data.get('parent_name', ''))
    year_of_study = data.get('year_of_study', 'First Year')
    department_name = format_unicode_text(data.get('department_name', 'ENGINEERING'))
    academic_year = data.get('academic_year', '2026-2027')

    parent_part = f"{relation} Mr. {parent_name}" if parent_name else ""

    body_text = (
        f"This is to certify that <b>{salutation} {student_name}</b>"
        + (f" &nbsp;{parent_part}&nbsp; " if parent_part else " ")
        + f"is studying <b>{year_of_study}</b> in the department of <b>{department_name}</b>"
        f" in our college during the academic year {academic_year}."
    )
    story.append(Paragraph(body_text, body_style))

    # Spacing between Paragraph 1 and Paragraph 2
    story.append(Spacer(1, 30))

    # Purpose Paragraph
    raw_purpose = data.get('purpose', 'Current Enrollment and Eligibility').strip()
    # Remove redundant trailing 'purpose' or 'only' if user wrote it
    clean_purpose = re.sub(r'\s+purpose(\s+only)?$', '', raw_purpose, flags=re.IGNORECASE).strip()
    if not clean_purpose:
        clean_purpose = 'Current Enrollment and Eligibility'

    purpose_formatted = format_unicode_text(clean_purpose)
    purpose_text = (
        f"This certificate is issued only for <b>{purpose_formatted}</b> Purpose only."
    )
    story.append(Paragraph(purpose_text, body_style))

    # Build the document
    doc.build(story)
    buffer.seek(0)
    return buffer


class BonafideStudentSearchView(APIView):
    """
    Searches for students by roll number or register number (or name).
    Returns formatted student details for the Bonafide Certificate Generator.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
        if not query:
            return Response({'success': True, 'count': 0, 'results': []})

        active_ay = AcademicYear.objects.filter(is_active=True).first()

        # Search matching roll_number, register_number, or student_name
        students_qs = Student.objects.select_related(
            'department', 'department__program', 'batch', 'application'
        ).filter(
            Q(roll_number__iexact=query) |
            Q(register_number__iexact=query) |
            Q(roll_number__icontains=query) |
            Q(register_number__icontains=query) |
            Q(student_name__icontains=query)
        )[:15]

        results = []
        for st in students_qs:
            results.append(_resolve_student_details(st, active_ay))

        return Response({
            'success': True,
            'count': len(results),
            'results': results,
            'active_academic_year': active_ay.academic_year if active_ay else '2026-2027',
        })


class BonafideGenerateView(APIView):
    """
    Generates a new Bonafide Certificate, records it in the database,
    and returns the generated PDF file.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({'error': 'Student ID is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.select_related(
                'department', 'department__program', 'batch', 'application'
            ).get(id=student_id)
        except Student.DoesNotExist:
            return Response({'error': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)

        active_ay = AcademicYear.objects.filter(is_active=True).first()
        defaults = _resolve_student_details(student, active_ay)

        student_name = (request.data.get('student_name') or defaults['student_name']).strip().upper()
        gender = request.data.get('gender') or defaults['gender']
        salutation = request.data.get('salutation') or defaults['salutation']
        parent_name = (request.data.get('parent_name') or defaults['parent_name']).strip().upper()
        relation = request.data.get('relation') or defaults['relation']
        department_name = (request.data.get('department_name') or defaults['department_name']).strip().upper()
        year_of_study = request.data.get('year_of_study') or defaults['year_of_study']
        academic_year = request.data.get('academic_year') or defaults['academic_year']
        purpose = (request.data.get('purpose') or defaults['default_purpose']).strip()
        include_header = bool(request.data.get('include_header', False))

        # Parse issue date
        issue_date_input = request.data.get('issue_date')
        parsed_issue_date = timezone.now().date()
        if issue_date_input:
            try:
                if '/' in str(issue_date_input):
                    parts = str(issue_date_input).strip().split('/')
                    if len(parts) == 3:
                        # DD/MM/YYYY
                        parsed_issue_date = datetime.date(int(parts[2]), int(parts[1]), int(parts[0]))
                else:
                    parsed_issue_date = datetime.date.fromisoformat(str(issue_date_input).strip())
            except Exception:
                parsed_issue_date = timezone.now().date()

        # Generate unique Certificate Number: BON/YYYY/XXXX
        current_year = parsed_issue_date.year
        year_prefix = f"BON/{current_year}/"
        current_count = BonafideCertificate.objects.filter(certificate_number__startswith=year_prefix).count()
        cert_number = f"{year_prefix}{current_count + 1:04d}"

        # Ensure uniqueness in case of race condition
        while BonafideCertificate.objects.filter(certificate_number=cert_number).exists():
            current_count += 1
            cert_number = f"{year_prefix}{current_count + 1:04d}"

        # Create record in database
        bonafide_record = BonafideCertificate.objects.create(
            certificate_number=cert_number,
            student=student,
            student_name=student_name,
            roll_number=student.roll_number,
            register_number=student.register_number,
            gender=gender,
            salutation=salutation,
            parent_name=parent_name,
            relation=relation,
            department_name=department_name,
            year_of_study=year_of_study,
            academic_year=academic_year,
            purpose=purpose,
            issue_date=parsed_issue_date,
            include_header=include_header,
            created_by=request.user,
            updated_by=request.user,
        )

        # Prepare PDF payload
        pdf_payload = {
            'certificate_number': cert_number,
            'issue_date': parsed_issue_date.strftime('%d/%m/%Y'),
            'student_name': student_name,
            'salutation': salutation,
            'relation': relation,
            'parent_name': parent_name,
            'year_of_study': year_of_study,
            'department_name': department_name,
            'academic_year': academic_year,
            'purpose': purpose,
            'include_header': include_header,
        }

        pdf_buffer = _generate_bonafide_pdf(pdf_payload)

        clean_roll = (student.roll_number or student.register_number or f"ST{student.id}").replace('/', '_')
        filename = f"Bonafide_{clean_roll}_{cert_number.replace('/', '_')}.pdf"

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition, X-Certificate-Number, X-Certificate-Id'
        response['X-Certificate-Number'] = cert_number
        response['X-Certificate-Id'] = str(bonafide_record.id)
        return response


class BonafideHistoryListView(APIView):
    """
    Returns list of issued bonafide certificates, sorted newest first.
    Supports search query on certificate_number, student_name, roll_number, or register_number.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        query = (request.query_params.get('q') or request.query_params.get('search') or '').strip()
        qs = BonafideCertificate.objects.select_related('student', 'created_by')

        if query:
            qs = qs.filter(
                Q(certificate_number__icontains=query) |
                Q(student_name__icontains=query) |
                Q(roll_number__icontains=query) |
                Q(register_number__icontains=query) |
                Q(purpose__icontains=query)
            )

        limit = int(request.query_params.get('limit', 50))
        records = qs[:limit]

        data = []
        for r in records:
            created_by_str = r.created_by.name if r.created_by and hasattr(r.created_by, 'name') and r.created_by.name else (r.created_by.username if r.created_by else 'Staff')
            data.append({
                'id': r.id,
                'certificate_number': r.certificate_number,
                'student_id': r.student_id,
                'student_name': r.student_name,
                'roll_number': r.roll_number or '—',
                'register_number': r.register_number or '—',
                'gender': r.gender,
                'salutation': r.salutation,
                'parent_name': r.parent_name or '—',
                'relation': r.relation,
                'department_name': r.department_name,
                'year_of_study': r.year_of_study,
                'academic_year': r.academic_year,
                'purpose': r.purpose,
                'issue_date': r.issue_date.strftime('%d/%m/%Y') if r.issue_date else '—',
                'created_at': r.created_at.strftime('%d/%m/%Y %I:%M %p') if r.created_at else '—',
                'created_by': created_by_str,
                'include_header': r.include_header,
            })

        return Response({
            'success': True,
            'count': len(data),
            'records': data,
        })


class BonafideDownloadExistingView(APIView):
    """
    Re-downloads an existing issued Bonafide Certificate PDF without creating duplicate records.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, cert_id):
        try:
            r = BonafideCertificate.objects.select_related('student').get(id=cert_id)
        except BonafideCertificate.DoesNotExist:
            return Response({'error': 'Certificate record not found.'}, status=status.HTTP_404_NOT_FOUND)

        pdf_payload = {
            'certificate_number': r.certificate_number,
            'issue_date': r.issue_date.strftime('%d/%m/%Y') if r.issue_date else _get_ist_now().strftime('%d/%m/%Y'),
            'student_name': r.student_name,
            'salutation': r.salutation,
            'relation': r.relation,
            'parent_name': r.parent_name or '',
            'year_of_study': r.year_of_study,
            'department_name': r.department_name,
            'academic_year': r.academic_year,
            'purpose': r.purpose,
            'include_header': r.include_header,
        }

        pdf_buffer = _generate_bonafide_pdf(pdf_payload)

        clean_roll = (r.roll_number or r.register_number or f"ST{r.student_id}").replace('/', '_')
        filename = f"Bonafide_{clean_roll}_{r.certificate_number.replace('/', '_')}.pdf"

        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition, X-Certificate-Number, X-Certificate-Id'
        response['X-Certificate-Number'] = r.certificate_number
        response['X-Certificate-Id'] = str(r.id)
        return response
