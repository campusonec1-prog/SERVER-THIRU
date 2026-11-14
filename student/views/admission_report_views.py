import re
import datetime
from io import BytesIO
from decimal import Decimal

from django.http import HttpResponse
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated

from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether
)
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas

from common.report_utils import (
    build_standard_college_header, format_unicode_text, register_unicode_fonts
)
from institution.models import AcademicYear, Department, Batch, Quota, CollegeHeader
from student.models import Student, StudentAdmissionSlip
from dynamic_forms.models import Application


class NumberedCanvas(canvas.Canvas):
    """Adds professional 'Page X of Y' pagination and official bottom timestamp."""

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
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 7.5)
        self.setFillColor(colors.HexColor('#64748B'))

        # Thin footer line
        self.setStrokeColor(colors.HexColor('#CBD5E1'))
        self.setLineWidth(0.5)
        self.line(20, 22, 575, 22)

        # Footer Left: Document authenticity notice
        self.drawString(20, 12, "Official Institutional Document — Confidential — For College Administrative Use Only")

        # Footer Right: Page X of Y
        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(575, 12, page_str)
        self.restoreState()


def _parse_date(val):
    if not val or str(val).strip().lower() in ['', 'null', 'undefined', 'all']:
        return None
    val_str = str(val).strip()
    # Try YYYY-MM-DD
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.datetime.strptime(val_str, fmt).date()
        except ValueError:
            pass
    return None


def _resolve_student_recommender(st):
    """
    Returns normalized dictionary describing the recommender for a student:
    - id: unique key ('user_X', 'other_XYZ', or 'direct')
    - user_id: integer or None
    - name: formatted label with role or type
    - clean_name: bare recommender name
    - is_direct: boolean True if no recommendation
    - is_user: boolean True if staff/faculty user
    """
    slip = getattr(st, 'admission_slip', None)
    if not slip:
        return {
            'id': 'direct',
            'user_id': None,
            'name': 'Direct / No Recommendation',
            'clean_name': 'Direct / None',
            'is_direct': True,
            'is_user': False,
        }

    if slip.recommendation:
        u = slip.recommendation
        u_name = u.name or u.get_full_name() or u.username or f"User #{u.id}"
        role_obj = getattr(u, 'role', None)
        role_name = getattr(role_obj, 'role_name', '') if role_obj else ''
        role_suffix = f" ({role_name})" if role_name else ""
        return {
            'id': f"user_{u.id}",
            'user_id': u.id,
            'name': f"{u_name}{role_suffix}".strip(),
            'clean_name': u_name,
            'is_direct': False,
            'is_user': True,
        }

    certs = slip.certificates_surrendered if isinstance(slip.certificates_surrendered, dict) else {}
    other_rec = str(certs.get('other_recommendation') or '').strip()
    if other_rec:
        return {
            'id': f"other_{other_rec.lower()}",
            'user_id': None,
            'name': f"{other_rec} (Other)",
            'clean_name': other_rec,
            'is_direct': False,
            'is_user': False,
        }

    return {
        'id': 'direct',
        'user_id': None,
        'name': 'Direct / No Recommendation',
        'clean_name': 'Direct / None',
        'is_direct': True,
        'is_user': False,
    }


def _get_all_faculties_and_others():
    """
    Returns (all_faculties_list, all_others_list) to show ALL faculties along with others.
    """
    from users.models import User
    try:
        users_qs = User.objects.exclude(status='LEFT').exclude(role__role_name__iexact='STUDENT').select_related('role')
        faculties = list(users_qs.values('id', 'name', 'role__role_name').order_by('name'))
    except Exception:
        try:
            faculties = list(User.objects.all().select_related('role').values('id', 'name', 'role__role_name').order_by('name'))
        except Exception:
            faculties = []

    other_recs = set()
    try:
        for slip_certs in StudentAdmissionSlip.objects.exclude(certificates_surrendered={}).values_list('certificates_surrendered', flat=True):
            if isinstance(slip_certs, dict):
                o = (slip_certs.get('other_recommendation') or '').strip()
                if o:
                    other_recs.add(o)
    except Exception:
        pass

    return faculties, sorted(other_recs)


def _compute_recommendation_breakdown(students, all_faculties=None, other_names=None):
    """
    Groups students by recommender and returns candidate count and percentage for each.
    Includes ALL faculties and ALL other recommenders so management sees complete faculty statistics.
    """
    rec_groups = {}

    # 1. Initialize ALL faculty members
    if all_faculties:
        for f in all_faculties:
            uid = f.get('id')
            uname = (f.get('name') or '').strip()
            if not uname:
                continue
            rname = f.get('role__role_name') or ''
            role_suffix = f" ({rname})" if rname else ""
            k = f"user_{uid}"
            rec_groups[k] = {
                'id': k,
                'user_id': uid,
                'name': f"{uname}{role_suffix}".strip(),
                'clean_name': uname,
                'role': rname or 'Faculty',
                'is_direct': False,
                'is_user': True,
                'count': 0,
            }

    # 2. Initialize ALL other custom recommenders
    if other_names:
        for o in other_names:
            o_clean = str(o).strip()
            if not o_clean:
                continue
            k = f"other_{o_clean.lower()}"
            rec_groups[k] = {
                'id': k,
                'user_id': None,
                'name': f"{o_clean} (Other)",
                'clean_name': o_clean,
                'role': 'External / Other',
                'is_direct': False,
                'is_user': False,
                'count': 0,
            }

    # 3. Initialize Direct / No Recommendation
    rec_groups['direct'] = {
        'id': 'direct',
        'user_id': None,
        'name': 'Direct / No Recommendation',
        'clean_name': 'Direct / None',
        'role': 'Direct Admission',
        'is_direct': True,
        'is_user': False,
        'count': 0,
    }

    # 4. Count from students matching current criteria
    for st in students:
        rec_info = _resolve_student_recommender(st)
        k = rec_info['id']
        if k not in rec_groups:
            rec_groups[k] = {
                'id': k,
                'user_id': rec_info['user_id'],
                'name': rec_info['name'],
                'clean_name': rec_info['clean_name'],
                'role': 'Staff / Faculty' if rec_info['is_user'] else ('Direct Admission' if rec_info['is_direct'] else 'External / Other'),
                'is_direct': rec_info['is_direct'],
                'is_user': rec_info['is_user'],
                'count': 0,
            }
        rec_groups[k]['count'] += 1

    total = len(students)
    breakdown = []
    for g in rec_groups.values():
        cnt = g['count']
        pct = round((cnt / total * 100), 1) if total > 0 else 0
        breakdown.append({
            **g,
            'percentage': pct,
            'summary_text': f"{g['clean_name']} recommended {cnt} candidate{'s' if cnt != 1 else ''}" if not g['is_direct'] else f"Direct / No Recommendation: {cnt} candidate{'s' if cnt != 1 else ''}"
        })

    # Sort order:
    # 1. Non-direct items with count > 0 (highest candidates recommended first)
    # 2. Direct with count > 0
    # 3. All other faculties (count == 0) alphabetically by name
    # 4. Other recommenders (count == 0)
    # 5. Direct (if count == 0)
    def _sort_key(item):
        if item['count'] > 0:
            if not item['is_direct']:
                return (0, -item['count'], item['clean_name'].lower())
            else:
                return (1, -item['count'], item['clean_name'].lower())
        else:
            if item['is_user']:
                return (2, 0, item['clean_name'].lower())
            elif not item['is_direct']:
                return (3, 0, item['clean_name'].lower())
            else:
                return (4, 0, item['clean_name'].lower())

    breakdown.sort(key=_sort_key)
    return breakdown


def _filter_admissions_queryset(request):
    req_data = getattr(request, 'data', None) or {}
    req_params = getattr(request, 'query_params', None) or getattr(request, 'GET', {})

    ay_param = (
        req_data.get('academic_year') or req_params.get('academic_year') or
        req_data.get('academic_year_id') or req_params.get('academic_year_id')
    )
    date_mode = req_data.get('date_mode') or req_params.get('date_mode') or 'single'
    date_param = req_data.get('date') or req_params.get('date')
    from_date_param = req_data.get('from_date') or req_params.get('from_date')
    to_date_param = req_data.get('to_date') or req_params.get('to_date')
    dept_param = req_data.get('department') or req_params.get('department')
    quota_param = req_data.get('quota') or req_params.get('quota')
    batch_param = req_data.get('batch') or req_params.get('batch')
    header_type = req_data.get('report_header') or req_params.get('report_header')
    rec_param = (
        req_data.get('recommendation') or req_params.get('recommendation') or
        req_data.get('recommendation_id') or req_params.get('recommendation_id')
    )

    # Base Queryset with eager joins (only active students)
    qs = Student.objects.select_related(
        'department', 'department__program', 'batch', 'section', 'quota',
        'admission_slip', 'admission_slip__recommendation', 'admission_slip__recommendation__role',
        'application', 'application__candidate', 'application__status', 'application__academic_year'
    ).filter(status__is_active=True)

    # 1. Resolve Academic Year
    acad_year_obj = None
    ay_label = "All Academic Years"
    if ay_param and str(ay_param).strip().lower() not in ['', 'all', 'all_years', 'undefined', 'null']:
        if str(ay_param).isdigit():
            acad_year_obj = AcademicYear.objects.filter(id=int(ay_param)).first()
        if not acad_year_obj:
            acad_year_obj = AcademicYear.objects.filter(academic_year__iexact=str(ay_param).strip()).first()

    if acad_year_obj:
        ay_label = acad_year_obj.academic_year
        # Extract start and end year (e.g. 2026 from 2026-2027)
        years = [int(y) for y in re.findall(r'\b\d{4}\b', str(ay_label))]
        if len(years) >= 2:
            ay_start, ay_end = years[0], years[1]
        elif len(years) == 1:
            ay_start, ay_end = years[0], years[0] + 1
        else:
            ay_start, ay_end = 2026, 2027

        # Academic year window: June 1 of start year to May 31 of end year
        ay_date_min = datetime.date(ay_start, 6, 1)
        ay_date_max = datetime.date(ay_end, 5, 31)

        # Match application's academic_year OR created_at in AY window OR batch starting with AY start year
        qs = qs.filter(
            Q(application__academic_year=acad_year_obj) |
            Q(created_at__date__gte=ay_date_min, created_at__date__lte=ay_date_max) |
            Q(batch__batch__startswith=str(ay_start))
        )

    # 2. Date Filtering
    parsed_single_date = _parse_date(date_param)
    parsed_from_date = _parse_date(from_date_param)
    parsed_to_date = _parse_date(to_date_param)

    effective_mode = str(date_mode or '').strip().lower()
    if effective_mode in ['all', 'academic_year', 'year', 'all_year', 'all_academic_year']:
        effective_mode = 'all'
        # Full academic year intake - no single day or date range sub-filter
    elif effective_mode == 'range' or (parsed_from_date and parsed_to_date):
        effective_mode = 'range'
        if parsed_from_date:
            qs = qs.filter(created_at__date__gte=parsed_from_date)
        if parsed_to_date:
            qs = qs.filter(created_at__date__lte=parsed_to_date)
    elif effective_mode == 'single' or (parsed_single_date and not parsed_from_date):
        effective_mode = 'single'
        if parsed_single_date:
            qs = qs.filter(created_at__date=parsed_single_date)
    else:
        effective_mode = 'all'

    # 3. Department Filter
    dept_obj = None
    if dept_param and str(dept_param).strip().lower() not in ['', 'all', 'all_departments', 'undefined', 'null']:
        if str(dept_param).isdigit():
            dept_obj = Department.objects.filter(id=int(dept_param)).first()
        if not dept_obj:
            dept_obj = Department.objects.filter(department_code__iexact=str(dept_param).strip()).first()
        if not dept_obj:
            dept_obj = Department.objects.filter(department_name__iexact=str(dept_param).strip()).first()
        if dept_obj:
            qs = qs.filter(department=dept_obj)

    # 4. Quota Filter
    quota_obj = None
    if quota_param and str(quota_param).strip().lower() not in ['', 'all', 'all_quotas', 'undefined', 'null']:
        if str(quota_param).isdigit():
            quota_obj = Quota.objects.filter(id=int(quota_param)).first()
        if not quota_obj:
            quota_obj = Quota.objects.filter(quota_name__iexact=str(quota_param).strip()).first()
        if quota_obj:
            qs = qs.filter(quota=quota_obj)

    # 5. Batch Filter (Optional direct specification)
    if batch_param and str(batch_param).strip().lower() not in ['', 'all', 'undefined', 'null']:
        if str(batch_param).isdigit():
            qs = qs.filter(batch_id=int(batch_param))
        else:
            qs = qs.filter(batch__batch__iexact=str(batch_param).strip())

    # 6. Recommendation Filter
    rec_val = str(rec_param).strip() if rec_param is not None else ""
    rec_filter_label = "All Recommendations"
    in_memory_rec_filter = None

    if rec_val and rec_val.lower() not in ['', 'all', 'all_recommenders', 'undefined', 'null']:
        if rec_val.lower() in ['none', 'direct', 'direct_admission']:
            rec_filter_label = "Direct / No Recommendation"
            qs = qs.filter(Q(admission_slip__isnull=True) | Q(admission_slip__recommendation__isnull=True))
            in_memory_rec_filter = lambda st: _resolve_student_recommender(st)['is_direct']
        elif rec_val.isdigit() or (rec_val.startswith('user_') and rec_val[5:].isdigit()):
            uid = int(rec_val[5:]) if rec_val.startswith('user_') else int(rec_val)
            qs = qs.filter(admission_slip__recommendation_id=uid)
            from users.models import User
            usr = User.objects.filter(id=uid).first()
            if usr:
                rec_filter_label = usr.name or usr.get_full_name() or f"User #{uid}"
            else:
                rec_filter_label = f"User #{uid}"
        elif rec_val.startswith('other_'):
            other_clean = rec_val[6:].strip()
            rec_filter_label = f"{other_clean} (Other)"
            in_memory_rec_filter = lambda st: (
                _resolve_student_recommender(st)['id'] == rec_val.lower() or
                _resolve_student_recommender(st)['clean_name'].lower() == other_clean.lower()
            )
        else:
            rec_filter_label = rec_val
            # Match either user name or other custom recommender
            in_memory_rec_filter = lambda st: (
                _resolve_student_recommender(st)['clean_name'].lower() == rec_val.lower() or
                _resolve_student_recommender(st)['name'].lower() == rec_val.lower() or
                _resolve_student_recommender(st)['id'] == rec_val.lower()
            )

    # Sort in clean admission chronological order (earliest to latest)
    qs = qs.order_by('created_at', 'department__department_name', 'application__application_no')

    meta = {
        'academic_year': ay_label,
        'date_mode': effective_mode,
        'selected_date': str(parsed_single_date) if parsed_single_date else None,
        'from_date': str(parsed_from_date) if parsed_from_date else None,
        'to_date': str(parsed_to_date) if parsed_to_date else None,
        'department_name': dept_obj.department_name if dept_obj else "All Departments",
        'quota_name': quota_obj.quota_name if quota_obj else "All Quotas",
        'recommendation_name': rec_filter_label,
        'recommendation_filter': rec_val,
        'header_type': header_type
    }

    return qs, meta, in_memory_rec_filter


class AdmissionReportDataView(APIView):
    """
    Returns admission statistics and student records matching academic year and date / date-range filters.
    Supports GET & POST.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return self._process(request)

    def post(self, request, *args, **kwargs):
        return self._process(request)

    def _process(self, request):
        qs, meta, in_memory_rec_filter = _filter_admissions_queryset(request)
        students = list(qs)
        if in_memory_rec_filter:
            students = [st for st in students if in_memory_rec_filter(st)]

        records = []
        dept_counts = {}
        quota_counts = {}
        date_counts = {}

        for st in students:
            app = st.application
            cand = app.candidate if app else None
            slip = getattr(st, 'admission_slip', None)

            # Candidate name lookup (app candidate name or slip or student_name)
            candidate_name = (
                (cand.name if cand else None) or
                (app.form_data.get('personal_information', {}).get('applicant_name') if app and isinstance(app.form_data, dict) else None) or
                st.student_name or
                '—'
            )

            # Mobile lookup
            mobile = (
                (cand.phone_number if cand else None) or
                (app.form_data.get('personal_information', {}).get('student_mobile') if app and isinstance(app.form_data, dict) else None) or
                (app.form_data.get('parent_information', {}).get('parent_mobile') if app and isinstance(app.form_data, dict) else None) or
                '—'
            )

            # Community lookup
            community = (
                (slip.community if slip else None) or
                (app.form_data.get('personal_information', {}).get('community') if app and isinstance(app.form_data, dict) else None) or
                '—'
            )

            # Quota lookup
            quota_name = st.quota.quota_name if st.quota else '—'

            # Department lookup
            dept_name = st.department.department_name if st.department else '—'

            # Recommendation lookup
            rec_info = _resolve_student_recommender(st)

            # Date formatting (local date)
            dt = st.created_at
            if dt:
                date_str = dt.strftime('%d/%m/%Y')
                time_str = dt.strftime('%I:%M %p')
                iso_date = dt.strftime('%Y-%m-%d')
            else:
                date_str, time_str, iso_date = '—', '—', '—'

            status_name = app.status.status_name if app and app.status else 'Admitted'

            records.append({
                'id': st.id,
                'application_no': app.application_no if app else (st.roll_number or f'ADM{st.id}'),
                'student_name': candidate_name,
                'roll_number': st.roll_number or '—',
                'register_number': st.register_number or '—',
                'department_id': st.department_id,
                'department_name': dept_name,
                'batch': st.batch.batch if st.batch else '—',
                'quota': quota_name,
                'academic_year': (
                    st.application.academic_year.academic_year if st.application and st.application.academic_year else (
                        meta.get('academic_year_name') if meta.get('academic_year_name') != 'All Academic Years' else '2026-2027'
                    )
                ),
                'community': community,
                'mobile': mobile,
                'recommendation_id': rec_info.get('user_id'),
                'recommendation_name': rec_info.get('clean_name'),
                'recommendation_display': rec_info.get('name'),
                'is_direct_admission': rec_info.get('is_direct', False),
                'is_user_recommender': rec_info.get('is_user', False),
                'admission_date': date_str,
                'admission_time': time_str,
                'created_at': st.created_at.isoformat() if st.created_at else None,
                'status': status_name,
            })

            # Aggregations
            dept_counts[dept_name] = dept_counts.get(dept_name, 0) + 1
            quota_counts[quota_name] = quota_counts.get(quota_name, 0) + 1
            if iso_date != '—':
                date_counts[iso_date] = date_counts.get(iso_date, 0) + 1

        all_faculties, all_others = _get_all_faculties_and_others()
        rec_breakdown = _compute_recommendation_breakdown(students, all_faculties=all_faculties, other_names=all_others)

        return Response({
            'success': True,
            'data': {
                'admissions': records,
                'stats': {
                    'total_admissions': len(records),
                    'by_department': dept_counts,
                    'by_quota': quota_counts,
                    'by_date': date_counts,
                    'recommendation_breakdown': rec_breakdown,
                    'recommended_count': sum(x['count'] for x in rec_breakdown if not x['is_direct'] and x['count'] > 0),
                    'direct_count': sum(x['count'] for x in rec_breakdown if x['is_direct']),
                },
                'available_recommenders': {
                    'users': [
                        {
                            'id': f"user_{u['id']}",
                            'user_id': u['id'],
                            'name': u['name'],
                            'role': u.get('role__role_name') or ''
                        }
                        for u in all_faculties if u.get('name')
                    ],
                    'others': [
                        {
                            'id': f"other_{o}",
                            'name': o
                        }
                        for o in all_others
                    ]
                },
                'filter_meta': meta
            }
        })


class AdmissionReportPDFView(APIView):
    """
    Generates and downloads the official Institutional Admission Report PDF in Portrait A4.
    Supports GET & POST.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return self._generate_pdf(request)

    def post(self, request, *args, **kwargs):
        return self._generate_pdf(request)

    def _generate_pdf(self, request):
        register_unicode_fonts()
        qs, meta, in_memory_rec_filter = _filter_admissions_queryset(request)
        students = list(qs)
        if in_memory_rec_filter:
            students = [st for st in students if in_memory_rec_filter(st)]

        if not students:
            return Response(
                {"error": "For the selected criteria the report can't be generated"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 1. Resolve College Header
        header_type = meta.get('header_type')
        college_header_obj = None
        if header_type:
            if str(header_type).isdigit():
                college_header_obj = CollegeHeader.objects.filter(id=int(header_type)).first()
            if not college_header_obj:
                college_header_obj = CollegeHeader.objects.filter(header_type=header_type).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        # 2. PDF Document Setup (Portrait A4)
        buffer = BytesIO()
        page_size = A4
        doc = SimpleDocTemplate(
            buffer,
            pagesize=page_size,
            leftMargin=20,
            rightMargin=20,
            topMargin=20,
            bottomMargin=28
        )
        page_w = page_size[0] - 40  # 555.27 pt
        story = []

        # 3. Official College Header Table
        header_table = build_standard_college_header(college_header_obj, page_w=page_w, logo_size=58)
        if header_table:
            story.append(header_table)
            story.append(Spacer(1, 8))

        # 4. Report Title Banner
        date_mode = meta.get('date_mode')
        selected_date = meta.get('selected_date')
        from_date = meta.get('from_date')
        to_date = meta.get('to_date')

        if date_mode == 'single' and selected_date:
            try:
                disp_d = datetime.datetime.strptime(selected_date, '%Y-%m-%d').strftime('%d/%m/%Y')
            except Exception:
                disp_d = selected_date
            title_main = "DAILY ADMISSION REPORT"
            title_sub = f"ADMISSIONS RECORDED ON: {disp_d}"
        elif date_mode == 'range' and (from_date or to_date):
            d_from_str = datetime.datetime.strptime(from_date, '%Y-%m-%d').strftime('%d/%m/%Y') if from_date else 'Start'
            d_to_str = datetime.datetime.strptime(to_date, '%Y-%m-%d').strftime('%d/%m/%Y') if to_date else 'End'
            title_main = "ADMISSION REPORT (DATE RANGE)"
            title_sub = f"PERIOD: {d_from_str} TO {d_to_str}"
        else:
            title_main = "ANNUAL ADMISSION REPORT"
            title_sub = f"ACADEMIC YEAR: {meta.get('academic_year')}"

        title_style = ParagraphStyle(
            name='AdmRepTitle',
            fontName='Helvetica-Bold',
            fontSize=11.5,
            leading=14,
            alignment=1,
            textColor=colors.HexColor('#0B2C5D')
        )
        subtitle_style = ParagraphStyle(
            name='AdmRepSub',
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=11,
            alignment=1,
            textColor=colors.HexColor('#475569')
        )

        title_data = [
            [Paragraph(title_main, title_style)],
            [Paragraph(title_sub, subtitle_style)]
        ]
        title_table = Table(title_data, colWidths=[page_w])
        title_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 1),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 0),
        ]))
        story.append(title_table)
        story.append(Spacer(1, 6))

        # 5. Metadata Filter Strip
        meta_label_style = ParagraphStyle(
            name='MetaLabel',
            fontName='Helvetica-Bold',
            fontSize=7,
            leading=8.5,
            textColor=colors.HexColor('#475569')
        )
        meta_val_style = ParagraphStyle(
            name='MetaVal',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor('#0F172A')
        )

        row1 = [
            Paragraph("ACADEMIC YEAR:", meta_label_style),
            Paragraph(meta.get('academic_year') or '—', meta_val_style),
            Paragraph("DEPARTMENT:", meta_label_style),
            Paragraph(meta.get('department_name') or 'All Departments', meta_val_style),
        ]
        row2 = [
            Paragraph("FILTER SCOPE:", meta_label_style),
            Paragraph(
                f"Date: {selected_date}" if date_mode == 'single' and selected_date else
                (f"Range: {from_date} to {to_date}" if date_mode == 'range' else "Full Academic Year"),
                meta_val_style
            ),
            Paragraph("QUOTA:", meta_label_style),
            Paragraph(meta.get('quota_name') or 'All Quotas', meta_val_style),
        ]
        row3 = [
            Paragraph("RECOMMENDATION:", meta_label_style),
            Paragraph(meta.get('recommendation_name') or 'All Recommendations', meta_val_style),
            Paragraph("TOTAL ADMITTED:", meta_label_style),
            Paragraph(f"<b>{len(students)}</b> Candidates", meta_val_style),
        ]
        row4 = [
            Paragraph("GENERATED ON:", meta_label_style),
            Paragraph(timezone.now().strftime('%d/%m/%Y %I:%M %p'), meta_val_style),
            Paragraph("DOCUMENT SCOPE:", meta_label_style),
            Paragraph(f"Official Admission Roster with Candidate Recommendation Summary", meta_val_style),
        ]

        meta_box = Table([row1, row2, row3, row4], colWidths=[95, 180, 95, 185.27])
        meta_box.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
            ('LINELEFT', (0, 0), (0, -1), 3.0, colors.HexColor('#0B2C5D')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        story.append(meta_box)
        story.append(Spacer(1, 8))

        # 6. Data Roster Table with Recommendation Column
        th_style = ParagraphStyle(
            name='ThAdm',
            fontName='Helvetica-Bold',
            fontSize=7,
            leading=8.5,
            alignment=1,
            textColor=colors.white
        )
        td_style = ParagraphStyle(
            name='TdAdm',
            fontName='Helvetica',
            fontSize=6.8,
            leading=8.5,
            textColor=colors.HexColor('#0F172A')
        )
        td_bold = ParagraphStyle(
            name='TdAdmBold',
            fontName='Helvetica-Bold',
            fontSize=6.8,
            leading=8.5,
            textColor=colors.HexColor('#0B2C5D')
        )
        td_rec_highlight = ParagraphStyle(
            name='TdAdmRec',
            fontName='Helvetica-Bold',
            fontSize=6.8,
            leading=8.5,
            textColor=colors.HexColor('#1E3A8A')
        )
        td_center = ParagraphStyle(
            name='TdAdmCenter',
            fontName='Helvetica',
            fontSize=6.8,
            leading=8.5,
            alignment=1,
            textColor=colors.HexColor('#0F172A')
        )

        col_widths = [24, 62, 112, 105, 45, 105, 50, 52]  # Total: 555 pt
        table_rows = [
            [
                Paragraph("S.No", th_style),
                Paragraph("App No", th_style),
                Paragraph("Candidate Name", th_style),
                Paragraph("Department", th_style),
                Paragraph("Quota", th_style),
                Paragraph("Recommendation", th_style),
                Paragraph("Date", th_style),
                Paragraph("Status", th_style),
            ]
        ]

        if not students:
            empty_style = ParagraphStyle(
                name='AdmEmpty',
                fontName='Helvetica-Bold',
                fontSize=8.5,
                leading=11,
                alignment=1,
                textColor=colors.HexColor('#DC2626')
            )
            empty_row = [Paragraph(f"No admissions recorded matching the selected criteria.", empty_style)] + [''] * 7
            table_rows.append(empty_row)
        else:
            for idx, st in enumerate(students, start=1):
                app = st.application
                cand = app.candidate if app else None

                cand_name = (
                    (cand.name if cand else None) or
                    (app.form_data.get('personal_information', {}).get('applicant_name') if app and isinstance(app.form_data, dict) else None) or
                    st.student_name or
                    '—'
                )

                dept_title = st.department.department_name if st.department else '—'
                quota_title = st.quota.quota_name if st.quota else '—'
                app_no = app.application_no if app else (st.roll_number or f'ADM{st.id}')

                rec_info = _resolve_student_recommender(st)
                rec_display = rec_info['name']
                rec_cell_style = td_rec_highlight if not rec_info['is_direct'] else td_style

                dt = st.created_at
                date_str = dt.strftime('%d/%m/%Y') if dt else '—'
                st_name = app.status.status_name if app and app.status else 'Admitted'

                table_rows.append([
                    Paragraph(str(idx), td_center),
                    Paragraph(app_no, td_bold),
                    Paragraph(cand_name, td_style),
                    Paragraph(dept_title, td_style),
                    Paragraph(quota_title, td_center),
                    Paragraph(rec_display, rec_cell_style),
                    Paragraph(date_str, td_center),
                    Paragraph(st_name, td_center),
                ])

        t_data = Table(table_rows, colWidths=col_widths, repeatRows=1)
        t_style = [
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0B2C5D')),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#CBD5E1')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]

        if not students:
            t_style.append(('SPAN', (0, 1), (-1, 1)))
            t_style.append(('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#FEF2F2')))
            t_style.append(('TOPPADDING', (0, 1), (-1, 1), 12))
            t_style.append(('BOTTOMPADDING', (0, 1), (-1, 1), 12))
        else:
            for r_idx in range(1, len(table_rows)):
                if r_idx % 2 == 0:
                    t_style.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#F8FAFC')))

        t_data.setStyle(TableStyle(t_style))
        story.append(t_data)
        story.append(Spacer(1, 10))

        # 7. Summary Breakdown Box at Bottom (Recommendation Candidate Count Breakdown)
        if students:
            all_faculties, all_others = _get_all_faculties_and_others()
            rec_breakdown = _compute_recommendation_breakdown(students, all_faculties=all_faculties, other_names=all_others)

            rec_heading_style = ParagraphStyle(
                name='RecSummHead',
                fontName='Helvetica-Bold',
                fontSize=8.5,
                leading=11,
                textColor=colors.HexColor('#0B2C5D')
            )
            story.append(Paragraph("RECOMMENDATION SUMMARY & CANDIDATE COUNT BREAKDOWN", rec_heading_style))
            story.append(Spacer(1, 4))

            rec_th_style = ParagraphStyle(
                name='RecSummTh',
                fontName='Helvetica-Bold',
                fontSize=7,
                leading=8.5,
                alignment=1,
                textColor=colors.white
            )
            rec_td_style = ParagraphStyle(
                name='RecSummTd',
                fontName='Helvetica',
                fontSize=7,
                leading=8.5,
                textColor=colors.HexColor('#0F172A')
            )
            rec_td_bold = ParagraphStyle(
                name='RecSummTdBold',
                fontName='Helvetica-Bold',
                fontSize=7.2,
                leading=8.8,
                textColor=colors.HexColor('#0B2C5D')
            )
            rec_td_center = ParagraphStyle(
                name='RecSummTdCenter',
                fontName='Helvetica-Bold',
                fontSize=7.2,
                leading=8.8,
                alignment=1,
                textColor=colors.HexColor('#0F172A')
            )

            rec_tbl_widths = [260, 150, 145.27]  # Total: 555.27 pt
            rec_tbl_rows = [
                [
                    Paragraph("RECOMMENDER / ADMISSION SOURCE", rec_th_style),
                    Paragraph("AFFILIATION / CATEGORY", rec_th_style),
                    Paragraph("CANDIDATES RECOMMENDED", rec_th_style),
                ]
            ]

            total_recomms = len(students)
            for r_item in rec_breakdown:
                affil = "Staff / Faculty" if r_item['is_user'] else ("External / Other" if not r_item['is_direct'] else "Direct Admission")
                count_str = f"<b>{r_item['count']} candidate{'s' if r_item['count'] != 1 else ''}</b>"

                rec_tbl_rows.append([
                    Paragraph(f"<b>{r_item['clean_name']}</b>", rec_td_bold),
                    Paragraph(affil, rec_td_style),
                    Paragraph(count_str, rec_td_center),
                ])

            # Grand Total Summary Row
            rec_tbl_rows.append([
                Paragraph("<b>TOTAL ADMISSIONS RECORDED</b>", rec_th_style),
                Paragraph("All Sources", rec_th_style),
                Paragraph(f"<b>{total_recomms} Candidates</b>", rec_th_style),
            ])

            rec_summary_table = Table(rec_tbl_rows, colWidths=rec_tbl_widths)
            rec_summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                ('GRID', (0, 0), (-1, -1), 0.35, colors.HexColor('#CBD5E1')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#0B2C5D')),
            ]))

            for row_i in range(1, len(rec_tbl_rows) - 1):
                if row_i % 2 == 0:
                    rec_summary_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, row_i), (-1, row_i), colors.HexColor('#F8FAFC'))
                    ]))

            story.append(KeepTogether([rec_summary_table]))
            story.append(Spacer(1, 8))

            # Department & Quota Breakdown Strip
            dept_counts = {}
            quota_counts = {}
            for st in students:
                d_n = st.department.department_name if st.department else 'Other'
                q_n = st.quota.quota_name if st.quota else 'Unassigned'
                dept_counts[d_n] = dept_counts.get(d_n, 0) + 1
                quota_counts[q_n] = quota_counts.get(q_n, 0) + 1

            summary_title_style = ParagraphStyle(
                name='SummTitle',
                fontName='Helvetica-Bold',
                fontSize=7,
                leading=8.5,
                textColor=colors.HexColor('#0B2C5D')
            )
            summary_item_style = ParagraphStyle(
                name='SummItem',
                fontName='Helvetica',
                fontSize=6.8,
                leading=8.2,
                textColor=colors.HexColor('#334155')
            )

            dept_summary_txt = " | ".join([f"<b>{k}</b>: {v}" for k, v in sorted(dept_counts.items())[:6]])
            quota_summary_txt = " | ".join([f"<b>{k}</b>: {v}" for k, v in sorted(quota_counts.items())])

            summary_table_data = [
                [
                    Paragraph("DEPARTMENT BREAKDOWN", summary_title_style),
                    Paragraph(dept_summary_txt, summary_item_style)
                ],
                [
                    Paragraph("QUOTA BREAKDOWN", summary_title_style),
                    Paragraph(quota_summary_txt, summary_item_style)
                ]
            ]
            summary_table = Table(summary_table_data, colWidths=[120, 435.27])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
                ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E2E8F0')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            story.append(KeepTogether(summary_table))

        # 8. Build Document
        doc.build(story, canvasmaker=NumberedCanvas)
        buffer.seek(0)

        filename_clean = f"Admission_Report_{date_mode}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename_clean}"'
        response['Access-Control-Expose-Headers'] = 'Content-Disposition'
        return response
