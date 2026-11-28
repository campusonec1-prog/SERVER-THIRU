import io
import datetime
import re
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.permissions import RestrictDeleteToTechSupporterPermission
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction, models
from django.db.models import Count, Sum, Q
from django.utils import timezone

from .models import (
    UniversityExamSchedule, UniversityExamCandidate,
    ExamHallAllocation, ExamSeatAllocation, UniversityExamHall
)
from student.models import Student, OuterStudent, StudentStatus
from institution.models import Department, Batch, Program, Regulation, Semester, Section, Exam, ExamType
from subject.models import Subject
from common.caching import invalidate_option_cache
from .serializers import (
    UniversityExamScheduleSerializer, UniversityExamCandidateSerializer,
    ExamHallAllocationSerializer, ExamSeatAllocationSerializer,
    UniversityExamHallSerializer
)


# ─── New ViewSets ─────────────────────────────────────────────────────────────

class UniversityExamHallViewSet(viewsets.ModelViewSet):
    queryset = UniversityExamHall.objects.select_related(
        'hall__floor__block',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).all().order_by('hall__floor__block__block_code', 'hall__floor__floor_name', 'hall__hall_no')
    serializer_class = UniversityExamHallSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def get_queryset(self):
        qs = super().get_queryset()
        hall_id = self.request.query_params.get('hall_id')
        is_active = self.request.query_params.get('is_active')
        if hall_id:
            qs = qs.filter(hall_id=hall_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ('true', '1', 'yes'))
        return qs


# ─── PDF Parsing Utility ─────────────────────────────────────────────────────

def parse_flexible_date(date_str):
    if not date_str:
        return None
    d_clean = date_str.strip()
    d_clean = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', d_clean)
    d_clean = d_clean.replace('/', '-').replace('.', '-')
    formats = [
        '%d-%m-%Y', '%d-%m-%y',
        '%Y-%m-%d',
        '%d-%b-%Y', '%d-%b-%y',
        '%d-%B-%Y', '%d-%B-%y',
        '%d %b %Y', '%d %b %y',
        '%d %B %Y', '%d %B %y',
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(d_clean, fmt).date()
        except Exception:
            pass
    return None


def format_short_exam_code(raw):
    """
    Standardize exam string into standard format e.g. 'NOV/DEC-26' or 'APR/MAY-26'.
    Extracts month pair (e.g. Nov. / Dec. -> NOV/DEC, Apr. / May. -> APR/MAY)
    and 2-digit year (e.g. 2026 -> 26).
    """
    if not raw:
        return ''
    t = str(raw).strip()

    # 1. Extract 2-digit year
    four_yr = re.search(r'20(\d{2})', t)
    two_yr = re.search(r'\b(\d{2})\b', t)
    yr = four_yr.group(1) if four_yr else (two_yr.group(1) if two_yr else '')

    # 2. Extract Session Months
    t_low = t.lower()
    months_str = ''
    if 'nov' in t_low and 'dec' in t_low:
        months_str = 'NOV/DEC'
    elif 'apr' in t_low and 'may' in t_low:
        months_str = 'APR/MAY'
    elif 'jan' in t_low and 'feb' in t_low:
        months_str = 'JAN/FEB'
    elif 'may' in t_low and 'jun' in t_low:
        months_str = 'MAY/JUN'
    else:
        m = re.search(r'([A-Za-z]{3,4})\.?\s*\/\s*([A-Za-z]{3,4})', t)
        if m:
            months_str = f"{m.group(1).upper()}/{m.group(2).upper()}"
        else:
            m_s = re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b', t, re.IGNORECASE)
            if m_s:
                months_str = m_s.group(1).upper()

    if months_str and yr:
        return f"{months_str}-{yr}"
    elif months_str:
        return f"{months_str}-{datetime.datetime.now().strftime('%y')}"
    elif yr:
        return f"UNIV-EXAM-{yr}"
    return t.upper()


def ensure_university_exam_code(raw_name):
    """
    Ensure ExamType ('University Exam') and Exam ('NOV/DEC-26') exist in 'exams' table.
    Auto-deduplicates: if previous long names (e.g. 'Nov. / Dec. Examination - 2026', 
    'Nov. / Dec. 2026', or 'Nov./Dec.Examination,2026') exist in database, unifies them 
    under the canonical code ('NOV/DEC-26') to strictly prevent duplicate exam records.
    """
    if not raw_name:
        return None

    exam_code = format_short_exam_code(raw_name)
    if not exam_code:
        return None

    from institution.models import ExamType, Exam
    from common.caching import invalidate_option_cache

    def _bust_exam_cache():
        for k in ('Exam', 'exams', 'ExamType', 'exam_types'):
            try:
                invalidate_option_cache(k)
            except Exception:
                pass

    try:
        # 1. Resolve or create 'University Exam' ExamType
        univ_type = ExamType.objects.filter(exam_type_name__iexact='University Exam').first()
        if not univ_type:
            univ_type = ExamType.objects.filter(exam_type_name__icontains='University').first()
        if not univ_type:
            univ_type = ExamType.objects.create(exam_type_name='University Exam', is_active=True)
            _bust_exam_cache()

        # 2. Check for exact match by canonical code
        exam_obj = Exam.objects.filter(exam_name__iexact=exam_code).first()

        # 3. Find all existing exams in database that match this session (fuzzy/normalized)
        # e.g., 'Nov. / Dec. Examination - 2026', 'Nov. / Dec. Examination,2026', 'Nov. / Dec. 2026'
        all_exams = list(Exam.objects.all())
        matching_exams = []
        for ex in all_exams:
            if ex.exam_name:
                ex_code = format_short_exam_code(ex.exam_name)
                if ex_code == exam_code:
                    matching_exams.append(ex)

        is_new = False
        if exam_obj:
            # Canonical record already exists. If any leftover duplicate long-named exams exist,
            # soft-deactivate them so they do not duplicate in UI dropdowns
            for extra_ex in matching_exams:
                if extra_ex.id != exam_obj.id and extra_ex.is_active:
                    try:
                        extra_ex.is_active = False
                        extra_ex.save()
                    except Exception:
                        pass
        elif matching_exams:
            # An existing exam has a legacy long name (e.g. 'Nov. / Dec. Examination - 2026').
            # Rename it in-place to the canonical code ('NOV/DEC-26') to avoid duplicate rows!
            exam_obj = matching_exams[0]
            exam_obj.exam_name = exam_code
            exam_obj.exam_type = univ_type
            exam_obj.is_active = True
            exam_obj.save()
            _bust_exam_cache()

            # If there are additional duplicate records, deactivate them
            for extra_ex in matching_exams[1:]:
                if extra_ex.id != exam_obj.id and extra_ex.is_active:
                    try:
                        extra_ex.is_active = False
                        extra_ex.save()
                    except Exception:
                        pass
        else:
            # No existing exam matches this session, create a clean canonical exam
            exam_obj = Exam.objects.create(
                exam_name=exam_code,
                exam_type=univ_type,
                is_active=True
            )
            is_new = True
            _bust_exam_cache()

        # Ensure active & proper type
        if not exam_obj.is_active or exam_obj.exam_type_id != univ_type.id:
            exam_obj.is_active = True
            exam_obj.exam_type = univ_type
            exam_obj.save()
            _bust_exam_cache()

        return {
            'id': exam_obj.id,
            'exam_name': exam_obj.exam_name,
            'exam_type_id': univ_type.id,
            'exam_type_name': univ_type.exam_type_name,
            'is_new': is_new,
        }
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("ensure_university_exam_code error: %s", e)
        return {'id': None, 'exam_name': exam_code, 'is_new': False}


def is_header_table(table):
    """Detect if table is the top Anna University metadata header box."""
    if not table:
        return False
    joined = ' '.join(str(cell or '') for row in table for cell in row).lower()
    return any(h in joined for h in ['date of examination', 'branch code', 'subject code', 'session', 'college code'])


def extract_metadata_from_header_table(table):
    meta = {}
    if not table:
        return meta
    for row in table:
        cells = [str(c or '').strip() for c in row if str(c or '').strip()]
        for idx, cell in enumerate(cells):
            cell_low = cell.lower()
            if 'date of exam' in cell_low:
                val = re.sub(r'^.*?date\s*of\s*exam(?:ination)?\s*[:\-]?\s*', '', cell, flags=re.IGNORECASE).strip()
                if not val and idx + 1 < len(cells):
                    val = cells[idx + 1]
                d = parse_flexible_date(val)
                if d: meta['exam_date'] = d

            if 'session' in cell_low:
                val = re.sub(r'^.*?session\s*[:\-]?\s*', '', cell, flags=re.IGNORECASE).strip()
                if not val and idx + 1 < len(cells):
                    val = cells[idx + 1]
                s_u = val.upper()
                if 'FORENOON' in s_u or s_u.startswith('FN'):
                    meta['session'] = 'FN'
                elif 'AFTERNOON' in s_u or s_u.startswith('AN'):
                    meta['session'] = 'AN'

            if 'branch' in cell_low:
                val = re.sub(r'^.*?(?:branch|degree|programme)\s*(?:code\s*(?:&|and|/)?\s*name|code|name)?\s*[:\-]?\s*', '', cell, flags=re.IGNORECASE).strip()
                if not val and idx + 1 < len(cells):
                    val = cells[idx + 1]
                val = re.split(r'\s+(?:Session|Date\s*of)\b', val, flags=re.IGNORECASE)[0].strip()
                m = re.match(r'^([0-9]{3,4})\s*[-:\s]\s*(.*)$', val)
                if m:
                    meta['branch_code'] = m.group(1).strip()
                    meta['branch_name'] = m.group(2).strip()
                elif val.isdigit() and len(val) in [3, 4]:
                    meta['branch_code'] = val
                elif val:
                    meta['branch_name'] = val

            if 'subject' in cell_low:
                val = re.sub(r'^.*?(?:subject|sub|course)\s*(?:code\s*(?:&|and|/)?\s*name|code|name)?\s*[:\-]?\s*', '', cell, flags=re.IGNORECASE).strip()
                if not val and idx + 1 < len(cells):
                    val = cells[idx + 1]
                val = re.split(r'\s+(?:Session|Date\s*of|Branch)\b', val, flags=re.IGNORECASE)[0].strip()
                if '-' in val:
                    parts = val.split('-', 1)
                    meta['subject_code'] = parts[0].strip()
                    meta['subject_name'] = parts[1].strip()
                elif val:
                    meta['subject_code'] = val

            if 'college' in cell_low or 'centre' in cell_low:
                val = re.sub(r'^.*?(?:college|centre)\s*(?:code\s*(?:&|and|/)?\s*name|code|name)?\s*[:\-]?\s*', '', cell, flags=re.IGNORECASE).strip()
                if not val and idx + 1 < len(cells):
                    val = cells[idx + 1]
                val = re.split(r'\s+(?:Date\s*of|Session|Branch)\b', val, flags=re.IGNORECASE)[0].strip()
                m = re.match(r'^([0-9]{4})\s*[-:\s]\s*(.*)$', val)
                if m:
                    meta['college_code'] = m.group(1).strip()
                    meta['college_name'] = m.group(2).strip()
                elif val:
                    meta['college_name'] = val
    return meta


def extract_metadata_from_text(raw_text):
    """
    Extract Anna University exam attendance header metadata from text:
    College, Branch, Subject, Exam Date, Session, and Question Paper Code.
    Processes line-by-line across header lines to guarantee sub-millisecond execution.
    """
    meta = {
        'college_code': '', 'college_name': '',
        'branch_code': '', 'branch_name': '',
        'subject_code': '', 'subject_name': '',
        'exam_date': None, 'session': '',
        'qp_code': '',
        'exam_name': '',
    }
    if not raw_text:
        return meta

    for line in raw_text.splitlines()[:60]:
        line_clean = line.strip()
        if not line_clean:
            continue

        # 1. College
        if not meta['college_code'] or not meta['college_name']:
            m = re.search(r'(?:College|Centre|Center)\s*(?:Code\s*(?:&|and|/)?\s*Name|Code|Name)?\s*[:\-]\s*([^\r\n]+)', line_clean, re.IGNORECASE)
            if m:
                val = re.split(r'\s+(?:Date\s*of|Branch|Subject|Exam|Session|Q\.?P\.?)\b', m.group(1).strip(), flags=re.IGNORECASE)[0].strip()
                code_m = re.match(r'^([0-9]{4})\s*[-:\s]\s*(.*)$', val)
                if code_m:
                    meta['college_code'] = code_m.group(1).strip()
                    meta['college_name'] = code_m.group(2).strip()
                elif val.isdigit() and len(val) == 4:
                    meta['college_code'] = val
                else:
                    meta['college_name'] = val

        # 2. Branch
        if not meta['branch_code'] or not meta['branch_name']:
            m = re.search(r'(?:Branch|Degree\s*(?:&|and|/)?\s*Branch|Programme)\s*(?:Code\s*(?:&|and|/)?\s*Name|Code|Name)?\s*[:\-]\s*([^\r\n]+)', line_clean, re.IGNORECASE)
            if m:
                val = re.split(r'\s+(?:Date\s*of|College|Subject|Exam|Semester|Session|Q\.?P\.?)\b', m.group(1).strip(), flags=re.IGNORECASE)[0].strip()
                code_m = re.match(r'^([0-9]{3,4})\s*[-:\s]\s*(.*)$', val)
                if code_m:
                    meta['branch_code'] = code_m.group(1).strip()
                    meta['branch_name'] = code_m.group(2).strip()
                elif val.isdigit() and len(val) in [3, 4]:
                    meta['branch_code'] = val
                else:
                    meta['branch_name'] = val

        # 3. Subject
        if not meta['subject_code']:
            m = re.search(r'(?:Subject|Sub\.?|Course)\s*(?:Code\s*(?:&|and|/)?\s*Name|Code|Name)?\s*[:\-]\s*([^\r\n]+)', line_clean, re.IGNORECASE)
            if m:
                val = re.split(r'\s+(?:Date\s*of|Branch|College|Exam|Session|Q\.?P\.?)\b', m.group(1).strip(), flags=re.IGNORECASE)[0].strip()
                if '-' in val:
                    parts = val.split('-', 1)
                    meta['subject_code'] = parts[0].strip()
                    meta['subject_name'] = parts[1].strip()
                else:
                    meta['subject_code'] = val

        # 4. Exam Date
        if not meta['exam_date']:
            m = re.search(r'(?:Date\s*of\s*Exam(?:ination)?|Exam\s*Date|\bDate)\s*[:\-]\s*([0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{2,4}|[0-9]{1,2}[-/\s][a-zA-Z]{3,9}[-/\s][0-9]{2,4})', line_clean, re.IGNORECASE)
            if m:
                meta['exam_date'] = parse_flexible_date(m.group(1).strip())

        # 5. Session
        if not meta['session']:
            m = re.search(r'\bSession\s*[:\-]\s*([A-Za-z]+)', line_clean, re.IGNORECASE)
            if m:
                s_val = m.group(1).strip().upper()
                if 'FORENOON' in s_val or s_val.startswith('FN'):
                    meta['session'] = 'FN'
                elif 'AFTERNOON' in s_val or s_val.startswith('AN'):
                    meta['session'] = 'AN'
                else:
                    meta['session'] = s_val[:2]

        # 6. QP Code
        if not meta['qp_code']:
            m = re.search(r'(?:Q\.?P\.?\s*Code|Question\s*Paper\s*Code)\s*[:\-]\s*([0-9A-Za-z]+)', line_clean, re.IGNORECASE)
            if m:
                meta['qp_code'] = m.group(1).strip()

        # 7. Exam Name
        if not meta['exam_name']:
            m = re.search(r'(?:Application\s+for\s+|ANNA\s+UNIVERSITY\s+(?:THEORY\s+)?EXAMINATION[S]?\s*[-–:]?\s*)([^\r\n]+)', line_clean, re.IGNORECASE)
            if m:
                t = m.group(1).strip()
                t = re.sub(r'\s+Examination\s*$', '', t, flags=re.IGNORECASE).strip()
                meta['exam_name'] = t
            else:
                m2 = re.search(r'([A-Za-z\.\s\/]+(?:Examination|Exam)\s*,?\s*\d{4})', line_clean, re.IGNORECASE)
                if m2:
                    meta['exam_name'] = m2.group(1).strip()

    # Fallback to search for standard Anna University subject code (e.g. CS3351, ME3151) if not found in headers
    if not meta['subject_code']:
        sub_code_m = re.search(r'\b([A-Z]{2,4}\s*\d{3,5})\b', raw_text)
        if sub_code_m:
            meta['subject_code'] = sub_code_m.group(1).replace(' ', '')

    return meta


def extract_candidates_from_table(table):
    """
    Extract (register_number, student_name) tuples from table cells.
    Handles:
    - Register numbers with spaces or hyphens.
    - Reg no and student name in the same cell.
    - Two-column rosters on a single page.
    - Name in adjacent column or preceding/subsequent columns.
    """
    found = []
    if not table:
        return found

    for row in table:
        if not row or len(row) < 2:
            continue
        cleaned = [str(c or '').strip() for c in row]
        joined = ' '.join(cleaned).lower()
        if any(h in joined for h in ['reg. no', 'register number', 'reg no', 'name of the candidate', 'candidate name', 'sl.no', 'ans. book']):
            continue

        i = 0
        while i < len(cleaned):
            cell = cleaned[i]
            reg_match = re.search(r'\b(?:\d{4}\s+\d{2}\s+\d{3}\s+\d{3}|\d{11,12}|\d{10})\b', cell)
            if reg_match:
                reg_no = re.sub(r'\s+', '', reg_match.group(0))
                name = ''
                # 1. Check if name is in the same cell
                remainder = cell[reg_match.end():].strip(' \t\n\r-:|')
                if not remainder:
                    remainder = cell[:reg_match.start()].strip(' \t\n\r-:|')
                if remainder and re.search(r'[A-Za-z]{2,}', remainder) and not remainder.isdigit():
                    name = remainder.split('\n')[0].strip()

                # 2. Check all other cells in this row (subsequent first, then preceding)
                if not name:
                    cell_order = list(range(i + 1, len(cleaned))) + list(range(i - 1, -1, -1))
                    for nxt in cell_order:
                        cand = cleaned[nxt]
                        if not cand:
                            continue
                        c_clean = str(cand).strip()
                        if c_clean in ['-', '—', 'AB', 'A', 'P', 'OD', 'WH', 'ABSENT', 'PRESENT']:
                            continue
                        digits_only = re.sub(r'[\s\-]+', '', c_clean)
                        if digits_only.isdigit():
                            continue
                        if re.search(r'[A-Za-z]{2,}', c_clean):
                            low_c = c_clean.lower()
                            if any(h in low_c for h in ['reg', 'sl.no', 'ans', 'book', 'signature', 'college', 'centre', 'branch', 'subject', 'anna univ']):
                                continue
                            first_line = c_clean.split('\n')[0].strip()
                            first_line = re.sub(r'^\d+[\.\s\-]+', '', first_line).strip()
                            if re.search(r'[A-Za-z]{2,}', first_line):
                                name = first_line
                                break

                found.append((reg_no, name))
            i += 1
    return found


def extract_candidates_from_text(raw_text):
    """
    Extract (register_number, student_name) tuples directly from text lines.
    Serves as fallback or supplement if PDF borders cannot be detected as tables.
    """
    found = []
    if not raw_text:
        return found

    for line in raw_text.splitlines():
        line_str = line.strip()
        if not line_str:
            continue
        low = line_str.lower()
        if any(h in low for h in ['register number', 'name of the candidate', 'centre code', 'subject code', 'anna university']):
            continue

        reg_matches = list(re.finditer(r'\b(?:\d{4}\s+\d{2}\s+\d{3}\s+\d{3}|\d{11,12}|\d{10})\b', line_str))
        for idx, m in enumerate(reg_matches):
            reg_no = re.sub(r'\s+', '', m.group(0))
            start_pos = m.end()
            end_pos = reg_matches[idx + 1].start() if idx + 1 < len(reg_matches) else len(line_str)
            seg = line_str[start_pos:end_pos].strip(' \t\n\r-:|')

            # Clean trailing numbers (booklet no, next sl.no, attendance status), without stripping initials
            seg = re.sub(r'\s+\d{1,4}\s*$', '', seg)
            seg = re.sub(r'\s+(?:AB|OD|WH|ABSENT|PRESENT)\b\s*$', '', seg, flags=re.IGNORECASE).strip()
            seg = seg.strip(' \t-:|')

            name = seg if re.search(r'[A-Za-z]{2,}', seg) else ''
            found.append((reg_no, name))
    return found


def parse_anna_university_pdf(file_bytes):
    """
    Parse Anna University attendance sheet PDF.
    Returns list of dicts with extracted row data.
    Multi-strategy parser prioritizing PyMuPDF (fitz) for native C++ performance (<0.1s),
    with pdfplumber and pypdf fallbacks.
    """
    import io
    import re

    rows = []
    seen_candidates = set()  # (reg_no, subject_code)

    # Global tracking across pages
    active_college_code = ''
    active_college_name = ''
    active_branch_code = ''
    active_branch_name = ''
    active_subject_code = ''
    active_subject_name = ''
    active_exam_date = None
    active_session = ''
    active_qp_code = ''
    active_exam_name = ''

    # Multi-engine PDF page extraction
    pdf_pages_data = []  # list of (page_num, raw_text, tables)

    # Strategy 1: PyMuPDF (fitz) - ultra-fast native C++ engine (<0.05s)
    try:
        import fitz
        with fitz.open(stream=file_bytes, filetype='pdf') as f_doc:
            for page_num, f_page in enumerate(f_doc, start=1):
                raw_text = f_page.get_text() or ''
                tables = []
                try:
                    found_tabs = f_page.find_tables()
                    if found_tabs and getattr(found_tabs, 'tables', None):
                        for t in found_tabs:
                            tables.append(t.extract())
                except Exception:
                    pass
                pdf_pages_data.append((page_num, raw_text, tables))
    except Exception:
        # Strategy 2: pdfplumber fallback (standard line-based tables only, never vertical_strategy: text)
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    raw_text = page.extract_text() or ''
                    tables = []
                    try:
                        tables = page.extract_tables() or []
                    except Exception:
                        pass
                    pdf_pages_data.append((page_num, raw_text, tables))
        except Exception:
            # Strategy 3: pypdf fallback
            try:
                import pypdf
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                for page_num, page in enumerate(reader.pages, start=1):
                    raw_text = page.extract_text() or ''
                    pdf_pages_data.append((page_num, raw_text, []))
            except Exception as e:
                raise Exception(f"Unable to read or parse PDF file: {str(e)}")

    for page_num, raw_text, tables in pdf_pages_data:
        # 1. Update metadata if present on this page
        # Check header tables first
        for t in tables:
            if is_header_table(t):
                h_meta = extract_metadata_from_header_table(t)
                if h_meta.get('college_code'): active_college_code = h_meta['college_code']
                if h_meta.get('college_name'): active_college_name = h_meta['college_name']
                if h_meta.get('branch_code'): active_branch_code = h_meta['branch_code']
                if h_meta.get('branch_name'): active_branch_name = h_meta['branch_name']
                if h_meta.get('subject_code'): active_subject_code = h_meta['subject_code']
                if h_meta.get('subject_name'): active_subject_name = h_meta['subject_name']
                if h_meta.get('exam_date'): active_exam_date = h_meta['exam_date']
                if h_meta.get('session'): active_session = h_meta['session']

        # Also check raw_text line-by-line
        page_meta = extract_metadata_from_text(raw_text)
        if page_meta.get('college_code'): active_college_code = page_meta['college_code']
        if page_meta.get('college_name'): active_college_name = page_meta['college_name']
        if page_meta.get('branch_code'): active_branch_code = page_meta['branch_code']
        if page_meta.get('branch_name'): active_branch_name = page_meta['branch_name']
        if page_meta.get('subject_code'): active_subject_code = page_meta['subject_code']
        if page_meta.get('subject_name'): active_subject_name = page_meta['subject_name']
        if page_meta.get('exam_date'): active_exam_date = page_meta['exam_date']
        if page_meta.get('session'): active_session = page_meta['session']
        if page_meta.get('qp_code'): active_qp_code = page_meta['qp_code']
        if page_meta.get('exam_name'):
            active_exam_name = page_meta['exam_name']

        # 2. Extract candidates from non-header tables
        candidates = []
        for table in tables:
            if not is_header_table(table):
                candidates.extend(extract_candidates_from_table(table))

        # 3. If no candidates found from tables, fallback to raw text stream
        if not candidates and raw_text:
            candidates = extract_candidates_from_text(raw_text)

        # 4. Process candidates for this page
        sess = active_session[:2] if active_session else 'FN'
        for reg_no, s_name in candidates:
            # Automatic branch and college deduction from 12-digit AU reg_no if missing
            b_code = active_branch_code
            if not b_code and len(reg_no) >= 9 and reg_no[:4].isdigit():
                b_code = reg_no[6:9]

            c_code = active_college_code
            if not c_code and len(reg_no) >= 4 and reg_no[:4].isdigit():
                c_code = reg_no[:4]

            dedup_key = (reg_no, active_subject_code, str(active_exam_date), sess)
            if dedup_key in seen_candidates:
                continue
            seen_candidates.add(dedup_key)

            rows.append({
                'college_code': c_code,
                'college_name': active_college_name,
                'branch_code': b_code,
                'branch_name': active_branch_name,
                'register_no': reg_no,
                'student_name': s_name,
                'subject_code': active_subject_code,
                'subject_name': active_subject_name,
                'exam_date': active_exam_date,
                'session': sess,
                'qp_code': active_qp_code,
                'exam_name': active_exam_name,
                'source_page': page_num,
            })

    return rows


# ─── ViewSets ────────────────────────────────────────────────────────────────

class ExamAttendanceImportViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @action(detail=False, methods=['post'], url_path='preview', parser_classes=[MultiPartParser, FormParser])
    def preview_pdf(self, request):
        """
        Parse an uploaded PDF and return preview analysis:
        - Departments Found vs Not Found
        - Subjects Found vs Not Found
        - Students Found vs Not Found
        - Distinct Exam Schedule Slots
        Does NOT store anything into the database.
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if not file_obj.name.lower().endswith('.pdf'):
            return Response({'error': 'Only PDF files are accepted'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            file_bytes = file_obj.read()
            parsed_rows = parse_anna_university_pdf(file_bytes)
        except ImportError as e:
            return Response({'error': str(e)}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            return Response({'error': f'Failed to parse PDF: {str(e)}'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        if not parsed_rows:
            return Response({'error': 'No student data found in the PDF. Please verify the format.'}, status=status.HTTP_400_BAD_REQUEST)

        from institution.models import Department, Batch
        from subject.models import Subject
        from student.models import Student

        # 1. Departments Analysis (Found vs Not Found)
        all_departments = list(Department.objects.filter(is_active=True).values('id', 'department_code', 'department_name', 'short_name'))
        dept_code_map = {d['department_code'].lower(): d for d in all_departments if d['department_code']}
        all_batches = list(Batch.objects.all().values('id', 'department_id', 'batch', 'is_active'))
        active_batch_set = set((b['department_id'], str(b['batch']).strip().lower()) for b in all_batches if b.get('is_active'))
        
        raw_branches = {}
        for row in parsed_rows:
            b_code = (row.get('branch_code') or 'UNKNOWN').strip()
            b_name = (row.get('branch_name') or '').strip()
            key = b_code
            if key not in raw_branches:
                raw_branches[key] = {
                    'branch_code': b_code,
                    'branch_name': b_name,
                    'student_count': 0
                }
            raw_branches[key]['student_count'] += 1

        departments_analysis = []
        for b_code, b_info in raw_branches.items():
            matched_dept = dept_code_map.get(b_code.lower())
            if not matched_dept and b_info['branch_name']:
                # Try finding by name substring
                for d in all_departments:
                    if b_info['branch_name'].lower() in d['department_name'].lower() or d['department_name'].lower() in b_info['branch_name'].lower():
                        matched_dept = d
                        break

            is_found = matched_dept is not None
            departments_analysis.append({
                'branch_code': b_code,
                'branch_name': b_info['branch_name'],
                'is_found': is_found,
                'mapped_department_id': matched_dept['id'] if matched_dept else (all_departments[0]['id'] if all_departments else None),
                'matched_department_code': matched_dept['department_code'] if matched_dept else None,
                'matched_department_name': matched_dept['department_name'] if matched_dept else None,
                'matched_department_short_name': matched_dept.get('short_name') or (matched_dept['department_code'] if matched_dept else None),
                'student_count': b_info['student_count']
            })

        # 2. Subjects Analysis (Found vs Not Found)
        all_subjects_qs = Subject.objects.filter(is_active=True).select_related(
            'department', 'regulation', 'semester'
        )
        all_subjects = []
        for s in all_subjects_qs:
            reg_code = s.regulation.regulation_code if s.regulation else ''
            if not reg_code and s.regulation and s.regulation.effective_from_year:
                reg_code = f"R{s.regulation.effective_from_year}"

            sem_str = ""
            if s.semester:
                sem_name = getattr(s.semester, 'semester_name', '') or ''
                sem_num = getattr(s.semester, 'semester_number', None)
                if sem_name:
                    sem_str = str(sem_name)
                elif sem_num:
                    sem_str = f"Sem {sem_num}"

            dept_short = s.department.short_name if (s.department and s.department.short_name) else (s.department.department_code if s.department else '')

            all_subjects.append({
                'id': s.id,
                'subject_code': s.subject_code or '',
                'subject_name': s.subject_name or '',
                'department_id': s.department_id,
                'department_code': s.department.department_code if s.department else '',
                'department_name': s.department.department_name if s.department else '',
                'department_short_name': dept_short,
                'short_name': dept_short,
                'regulation_id': s.regulation_id,
                'regulation_code': reg_code,
                'semester_id': s.semester_id,
                'semester_name': sem_str,
            })

        subj_code_map = {}
        for s in all_subjects:
            code_lower = s['subject_code'].lower() if s['subject_code'] else ''
            if code_lower not in subj_code_map:
                subj_code_map[code_lower] = []
            subj_code_map[code_lower].append(s)
        
        raw_subjects = {}
        for row in parsed_rows:
            s_code = (row.get('subject_code') or 'UNKNOWN').strip()
            s_name = (row.get('subject_name') or '').strip()
            b_code = (row.get('branch_code') or '').strip()
            b_name = (row.get('branch_name') or '').strip()
            key = f"{b_code}__{s_code}" if b_code else s_code
            if key not in raw_subjects:
                raw_subjects[key] = {
                    'key': key,
                    'subject_code': s_code,
                    'subject_name': s_name,
                    'branch_code': b_code,
                    'branch_name': b_name,
                    'student_count': 0
                }
            raw_subjects[key]['student_count'] += 1

        subjects_analysis = []
        for key, s_info in raw_subjects.items():
            s_code = s_info['subject_code']
            b_code = s_info['branch_code']
            b_name = s_info['branch_name']

            # Find matched department for this branch
            matched_dept = dept_code_map.get(b_code.lower())
            if not matched_dept and b_name:
                for d in all_departments:
                    if b_name.lower() in d['department_name'].lower() or d['department_name'].lower() in b_name.lower():
                        matched_dept = d
                        break

            matched_dept_id = matched_dept['id'] if matched_dept else None

            # Look for matching subject in this department first
            matched_subj = None
            cand_subjs = subj_code_map.get(s_code.lower(), [])
            if matched_dept_id:
                for s in cand_subjs:
                    if s['department_id'] == matched_dept_id:
                        matched_subj = s
                        break

            # Fallback to any department matching subject_code
            if not matched_subj and cand_subjs:
                matched_subj = cand_subjs[0]

            # Fallback to subject_name matching in the department
            if not matched_subj and s_info['subject_name'] and matched_dept_id:
                for s in all_subjects:
                    if s['department_id'] == matched_dept_id and (
                        s_info['subject_name'].lower() in s['subject_name'].lower() or
                        s['subject_name'].lower() in s_info['subject_name'].lower()
                    ):
                        matched_subj = s
                        break

            # Fallback to subject_name matching anywhere
            if not matched_subj and s_info['subject_name']:
                for s in all_subjects:
                    if (
                        s_info['subject_name'].lower() in s['subject_name'].lower() or
                        s['subject_name'].lower() in s_info['subject_name'].lower()
                    ):
                        matched_subj = s
                        break

            is_found = matched_subj is not None
            dept_subjects = [s for s in all_subjects if s['department_id'] == matched_dept_id] if matched_dept_id else []
            default_subj = dept_subjects[0] if dept_subjects else (all_subjects[0] if all_subjects else None)

            subjects_analysis.append({
                'key': key,
                'subject_code': s_code,
                'subject_name': s_info['subject_name'],
                'branch_code': b_code,
                'branch_name': b_name,
                'mapped_department_id': matched_dept_id,
                'is_found': is_found,
                'mapped_subject_id': matched_subj['id'] if matched_subj else (default_subj['id'] if default_subj else None),
                'matched_subject_code': matched_subj['subject_code'] if matched_subj else None,
                'matched_subject_name': matched_subj['subject_name'] if matched_subj else None,
                'matched_regulation_code': matched_subj['regulation_code'] if matched_subj else None,
                'student_count': s_info['student_count']
            })

        # 0. Ensure University Exam is Created / Found in exams table
        raw_exam_title = ''
        for r in parsed_rows:
            if r.get('exam_name'):
                raw_exam_title = r['exam_name']
                break
        if not raw_exam_title and parsed_rows:
            raw_exam_title = parsed_rows[0].get('exam_name') or ''

        exam_info = ensure_university_exam_code(raw_exam_title) if raw_exam_title else None

        # 3. Students Analysis (Found vs Not Found in students or outer_student)
        reg_numbers = list({r['register_no'] for r in parsed_rows if r.get('register_no')})
        existing_students = Student.objects.filter(register_number__in=reg_numbers).select_related(
            'department', 'batch', 'application', 'application__candidate'
        )
        student_map = {}
        for s in existing_students:
            s_name = getattr(s, 'student_name', '') or ''
            if not s_name and s.application and s.application.form_data:
                s_name = s.application.form_data.get('personal_info', {}).get('full_name', '')
            if not s_name and s.application and getattr(s.application, 'candidate', None):
                s_name = getattr(s.application.candidate, 'name', '')
            student_map[s.register_number] = {
                'id': s.id,
                'name': s_name,
                'department_id': s.department_id,
                'department_code': s.department.department_code if s.department else '',
                'department_name': s.department.department_name if s.department else '',
                'batch_name': s.batch.batch if s.batch else '',
                'college_type': 'INTER',
            }

        existing_outer = OuterStudent.objects.filter(register_number__in=reg_numbers).select_related(
            'department', 'batch'
        )
        for o in existing_outer:
            if o.register_number not in student_map:
                student_map[o.register_number] = {
                    'id': o.id,
                    'name': o.student_name,
                    'department_id': o.department_id,
                    'department_code': o.department.department_code if o.department else '',
                    'department_name': o.department.department_name if o.department else '',
                    'batch_name': o.batch.batch if o.batch else '',
                    'college_type': 'OUTER',
                }

        students_analysis = []
        found_student_count = 0
        not_found_student_count = 0

        for idx, row in enumerate(parsed_rows, start=1):
            r_no = (row.get('register_no') or '').strip()
            db_s = student_map.get(r_no)
            is_found = db_s is not None

            if is_found:
                found_student_count += 1
            else:
                not_found_student_count += 1

            b_code = (row.get('branch_code') or '').strip()
            b_name = (row.get('branch_name') or '').strip()
            matched_dept_for_row = dept_code_map.get(b_code.lower())
            if not matched_dept_for_row and b_name:
                for d in all_departments:
                    if b_name.lower() in d['department_name'].lower() or d['department_name'].lower() in b_name.lower():
                        matched_dept_for_row = d
                        break

            extracted_name = (row.get('student_name') or '').strip()
            final_name = extracted_name or (db_s['name'] if db_s else '')

            # Extract batch digit and calculate batch
            batch_digit = ''
            calculated_batch = ''
            clean_reg = r_no.replace(' ', '')
            from .views_preview import get_institutional_college_code
            inst_code = get_institutional_college_code()
            is_own_college = clean_reg.startswith(inst_code) if (clean_reg and len(clean_reg) >= 4) else True

            if db_s:
                calc_college_type = db_s['college_type']
            else:
                calc_college_type = 'INTER' if is_own_college else 'OUTER'

            if len(clean_reg) >= 6 and clean_reg[4:6].isdigit():
                batch_digit = clean_reg[4:6]
                yr = int(batch_digit)
                calculated_batch = f"{2000 + yr}-{2000 + yr + 4}"

            row_session = (row.get('session') or 'FN').upper()
            row_date_str = row.get('exam_date').strftime('%Y-%m-%d') if row.get('exam_date') else ''

            final_batch_name = db_s.get('batch_name') if (db_s and db_s.get('batch_name')) else calculated_batch
            dept_id_for_batch = db_s['department_id'] if db_s else (matched_dept_for_row['id'] if matched_dept_for_row else None)
            is_batch_active = False
            if dept_id_for_batch and final_batch_name:
                is_batch_active = (dept_id_for_batch, str(final_batch_name).strip().lower()) in active_batch_set

            students_analysis.append({
                'key': f"{idx}_{r_no}",
                'register_no': r_no,
                'student_name': final_name,
                'raw_name_in_pdf': extracted_name,
                'branch_code': b_code,
                'branch_name': b_name,
                'subject_code': row.get('subject_code') or '',
                'subject_name': row.get('subject_name') or '',
                'exam_date': row_date_str,
                'session': row_session,
                'source_page': row.get('source_page', 1),
                'is_found': is_found,
                'college_type': calc_college_type,
                'is_own_college': is_own_college,
                'student_id': db_s['id'] if db_s else None,
                'db_student_name': db_s['name'] if db_s else '',
                'db_department_code': db_s['department_code'] if db_s else '',
                'mapped_department_id': dept_id_for_batch,
                'batch_digit': batch_digit,
                'calculated_batch': final_batch_name,
                'is_batch_active': is_batch_active,
                'batch_status': 'ACTIVE' if is_batch_active else 'INACTIVE',
                'selected': True,
            })

        # 4. Detected Schedule Slots in the PDF (separated strictly by session and date)
        slots_map = {}
        for row in parsed_rows:
            s_date = row.get('exam_date').strftime('%Y-%m-%d') if row.get('exam_date') else ''
            s_session = (row.get('session') or 'FN').upper()
            b_code = row.get('branch_code') or ''
            s_code = row.get('subject_code') or ''
            slot_key = f"{b_code}__{s_code}__{s_date}__{s_session}"
            if slot_key not in slots_map:
                slots_map[slot_key] = {
                    'slot_key': slot_key,
                    'branch_code': b_code,
                    'branch_name': row.get('branch_name') or '',
                    'subject_code': s_code,
                    'subject_name': row.get('subject_name') or '',
                    'exam_date': s_date,
                    'session': s_session,
                    'student_count': 0
                }
            slots_map[slot_key]['student_count'] += 1

        detected_schedules = list(slots_map.values())

        first_row = parsed_rows[0]
        header_date = first_row.get('exam_date').strftime('%Y-%m-%d') if first_row.get('exam_date') else ''
        header_session = (first_row.get('session') or 'FN').upper()
        header_qp_code = first_row.get('qp_code') or ''

        fn_candidates_count = sum(1 for s in students_analysis if s['session'] == 'FN')
        an_candidates_count = sum(1 for s in students_analysis if s['session'] == 'AN')

        return Response({
            'summary': {
                'exam': exam_info,
                'exam_name': exam_info['exam_name'] if exam_info else (format_short_exam_code(raw_exam_title) or 'UNIVERSITY EXAM'),
                'total_candidates': len(students_analysis),
                'students_found': found_student_count,
                'students_not_found': not_found_student_count,
                'fn_candidates_count': fn_candidates_count,
                'an_candidates_count': an_candidates_count,
                'total_departments': len(departments_analysis),
                'departments_found': sum(1 for d in departments_analysis if d['is_found']),
                'departments_not_found': sum(1 for d in departments_analysis if not d['is_found']),
                'total_subjects': len(subjects_analysis),
                'subjects_found': sum(1 for s in subjects_analysis if s['is_found']),
                'subjects_not_found': sum(1 for s in subjects_analysis if not s['is_found']),
                'source_file': file_obj.name,
                'default_exam_date': header_date,
                'default_session': header_session,
                'default_qp_code': header_qp_code,
            },
            'departments_analysis': departments_analysis,
            'subjects_analysis': subjects_analysis,
            'students_analysis': students_analysis,
            'detected_schedules': detected_schedules,
            'available_departments': all_departments,
            'available_subjects': all_subjects,
            'available_batches': all_batches,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-dept')
    def quick_add_dept(self, request):
        """Quick add missing department from preview (1-click, no manual form needed)."""
        from institution.models import Department, Program
        b_code = (request.data.get('department_code') or '').strip()
        b_name = (request.data.get('department_name') or '').strip()
        short_name = (request.data.get('short_name') or '').strip()

        if not short_name and b_name:
            nl = b_name.lower()
            if 'computer science' in nl: short_name = 'CSE'
            elif 'civil' in nl: short_name = 'CIVIL'
            elif 'mechanical' in nl: short_name = 'MECH'
            elif 'information tech' in nl: short_name = 'IT'
            elif 'artificial' in nl: short_name = 'AI&DS'
            elif 'agricultural' in nl: short_name = 'AGRI'
            elif 'electrical' in nl and 'electronic' in nl: short_name = 'EEE'
            elif 'electronic' in nl and 'communication' in nl: short_name = 'ECE'
            else:
                words = re.findall(r'[A-Za-z]+', b_name)
                inits = [w[0].upper() for w in words if w.lower() not in {'and', 'of', 'in', '&', 'the', 'for'}]
                short_name = ''.join(inits) if len(inits) >= 2 else b_name[:5].upper()
        if not short_name:
            short_name = b_code

        if not b_code:
            return Response({'error': 'Department code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        program = Program.objects.first()
        if not program:
            program = Program.objects.create(program_name='Under Graduate Engineering', program_level='UG', duration=4)

        dept, created = Department.objects.get_or_create(
            department_code=b_code,
            defaults={
                'department_name': b_name or b_code,
                'short_name': short_name,
                'program': program,
                'is_active': False,
            }
        )
        for m in ('Department', 'department', 'departments'):
            try:
                invalidate_option_cache(m)
            except Exception:
                pass
        try:
            from common.signals import _send_realtime_broadcast
            _send_realtime_broadcast({'model': 'Department', 'action': 'create', 'event': 'department_created'})
        except Exception:
            pass

        return Response({
            'id': dept.id,
            'department_code': dept.department_code,
            'department_name': dept.department_name,
            'short_name': dept.short_name,
            'created': created
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-subject')
    def quick_add_subject(self, request):
        """Quick add missing subject from preview (1-click, no manual form needed)."""
        from institution.models import Department, Regulation, Semester
        from subject.models import Subject

        s_code = (request.data.get('subject_code') or '').strip()
        s_name = (request.data.get('subject_name') or '').strip()
        dept_id = request.data.get('department_id')
        credits = float(request.data.get('credits') or 3)

        if not s_code:
            return Response({'error': 'Subject code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        dept = Department.objects.filter(id=dept_id).first() if dept_id else Department.objects.first()
        reg = Regulation.objects.first()
        if not reg:
            reg = Regulation.objects.create(regulation_code='2021', effective_from_year=2021)
        sem = Semester.objects.first()
        if not sem:
            sem = Semester.objects.create(semester_no=1, semester_name='Semester 1')

        subj, created = Subject.objects.get_or_create(
            subject_code=s_code,
            department=dept,
            defaults={
                'subject_name': s_name or s_code,
                'regulation': reg,
                'semester': sem,
                'credits': credits,
                'is_theory': True,
                'is_active': False,
            }
        )
        for m in ('Subject', 'subject', 'subjects'):
            try:
                invalidate_option_cache(m)
            except Exception:
                pass
        try:
            from common.signals import _send_realtime_broadcast
            _send_realtime_broadcast({'model': 'Subject', 'action': 'create', 'event': 'subject_created'})
        except Exception:
            pass

        return Response({
            'id': subj.id,
            'subject_code': subj.subject_code,
            'subject_name': subj.subject_name,
            'department_id': subj.department_id,
            'regulation_id': subj.regulation_id,
            'regulation_code': subj.regulation.regulation_code if subj.regulation else '2021',
            'created': created
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-student')
    def quick_add_student(self, request):
        """Quick add missing student directly to students or outer_student table."""
        from institution.models import Department, Batch, Section, Quota
        from student.models import Student, StudentStatus, OuterStudent

        reg_no = (request.data.get('register_number') or request.data.get('register_no') or '').strip()
        roll_no = (request.data.get('roll_number') or '').strip() or None
        s_name = (request.data.get('student_name') or '').strip() or reg_no
        dept_id = request.data.get('department_id')
        branch_code = (request.data.get('branch_code') or request.data.get('department_code') or '').strip()
        branch_name = (request.data.get('branch_name') or request.data.get('department_name') or '').strip()
        batch_id = request.data.get('batch_id')
        batch_name = request.data.get('batch_name') or request.data.get('calculated_batch')
        section_id = request.data.get('section_id')
        quota_id = request.data.get('quota_id')
        status_id = request.data.get('status_id')
        college_type = (request.data.get('college_type') or 'INTER').upper()

        if not reg_no:
            return Response({'error': 'Register number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        dept = None
        if dept_id and str(dept_id).isdigit():
            dept = Department.objects.filter(id=int(dept_id)).first()
        if not dept and branch_code:
            dept = Department.objects.filter(department_code__iexact=branch_code).first()
        if not dept and branch_name:
            dept = Department.objects.filter(department_name__icontains=branch_name).first()
        if not dept:
            dept = Department.objects.first()

        batch = None
        if batch_id and str(batch_id).isdigit():
            found_b = Batch.objects.filter(id=int(batch_id)).first()
            if found_b:
                if dept and found_b.department_id != dept.id:
                    batch, _ = Batch.objects.get_or_create(department=dept, batch=found_b.batch, defaults={'is_active': False})
                else:
                    batch = found_b
        if not batch and batch_name and dept:
            batch, _ = Batch.objects.get_or_create(department=dept, batch=batch_name, defaults={'is_active': False})
        if not batch and dept and reg_no:
            clean_reg = reg_no.replace(' ', '')
            if len(clean_reg) >= 6 and clean_reg[4:6].isdigit():
                yr = int(clean_reg[4:6])
                est_batch_name = f"{2000 + yr}-{2000 + yr + 4}"
                batch, _ = Batch.objects.get_or_create(department=dept, batch=est_batch_name, defaults={'is_active': False})
        if not batch and dept:
            batch = Batch.objects.filter(department=dept).first()
        if not batch and dept:
            batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR', defaults={'is_active': False})

        if college_type == 'OUTER':
            outer_stud, created = OuterStudent.objects.get_or_create(
                register_number=reg_no,
                defaults={
                    'student_name': s_name,
                    'department': dept,
                    'program': dept.program if dept else None,
                    'batch': batch,
                }
            )
            if not created and s_name and not outer_stud.student_name:
                outer_stud.student_name = s_name
                outer_stud.save()
            return Response({
                'id': outer_stud.id,
                'register_number': outer_stud.register_number,
                'student_name': outer_stud.student_name,
                'college_type': 'OUTER',
                'table': 'outer_student',
                'department_code': dept.department_code if dept else '',
                'created': created
            }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

        section = None
        if dept:
            if section_id and str(section_id).isdigit():
                section = Section.objects.filter(id=int(section_id), department=dept).first()
            if not section:
                section = Section.objects.filter(department=dept, sections__iexact='A').first()
            if not section:
                section = Section.objects.filter(department=dept, sections__iexact='Section: A').first()
            if not section:
                section = Section.objects.filter(department=dept, sections__icontains='A').first()
            if not section:
                section, _ = Section.objects.get_or_create(department=dept, sections='A')

        quota = Quota.objects.filter(id=quota_id).first() if quota_id else None

        student_status_obj = None
        if status_id:
            student_status_obj = StudentStatus.objects.filter(id=status_id).first()
        if not student_status_obj:
            student_status_obj = StudentStatus.objects.filter(status_name__iexact='ACTIVE').first()
        if not student_status_obj:
            student_status_obj, _ = StudentStatus.objects.get_or_create(status_name='ACTIVE')

        student, created = Student.objects.get_or_create(
            register_number=reg_no,
            defaults={
                'student_name': s_name,
                'roll_number': roll_no,
                'department': dept,
                'batch': batch,
                'section': section,
                'quota': quota,
                'status': student_status_obj,
            }
        )
        if not created and s_name and not student.student_name:
            student.student_name = s_name
            student.save(update_fields=['student_name'])

        for m in ('Student', 'student', 'students', 'Batch', 'batch', 'batches'):
            try:
                invalidate_option_cache(m)
            except Exception:
                pass
        try:
            from common.signals import _send_realtime_broadcast
            _send_realtime_broadcast({'model': 'Student', 'action': 'create', 'event': 'student_created'})
        except Exception:
            pass

        return Response({
            'id': student.id,
            'register_number': student.register_number,
            'student_name': student.student_name or student.name,
            'college_type': 'INTER',
            'table': 'students',
            'department_code': dept.department_code if dept else '',
            'created': created
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-all-students')
    def quick_add_all_students(self, request):
        """Bulk add missing students with chosen college_type ('INTER' or 'OUTER')."""
        from institution.models import Department, Batch, Section
        from student.models import Student, StudentStatus, OuterStudent

        students_data = request.data.get('students', [])
        default_college_type = request.data.get('college_type', 'INTER')

        if not students_data:
            return Response({'error': 'No student data provided'}, status=status.HTTP_400_BAD_REQUEST)

        added_inter = 0
        added_outer = 0
        added_students = []

        with transaction.atomic():
            status_obj = StudentStatus.objects.filter(status_name__iexact='ACTIVE').first()
            if not status_obj:
                status_obj = StudentStatus.objects.first() or StudentStatus.objects.create(status_name='ACTIVE')

            for s_info in students_data:
                reg_no = (s_info.get('register_no') or s_info.get('register_number') or '').strip()
                if not reg_no:
                    continue

                c_type = (s_info.get('college_type') or default_college_type or 'INTER').upper()
                s_name = (s_info.get('student_name') or reg_no).strip()
                dept_id = s_info.get('department_id') or s_info.get('mapped_department_id')
                b_code = (s_info.get('branch_code') or '').strip()

                dept = None
                if dept_id and str(dept_id).isdigit():
                    dept = Department.objects.filter(id=int(dept_id)).first()
                if not dept and b_code:
                    dept = Department.objects.filter(department_code__iexact=b_code).first()
                if not dept:
                    dept = Department.objects.first()

                # Batch
                batch = None
                calc_b = s_info.get('calculated_batch') or s_info.get('batch_name')
                if calc_b and dept:
                    batch, _ = Batch.objects.get_or_create(department=dept, batch=calc_b, defaults={'is_active': False})
                if not batch and dept and len(reg_no) >= 6 and reg_no[4:6].isdigit():
                    yr = int(reg_no[4:6])
                    est_batch = f"{2000 + yr}-{2000 + yr + 4}"
                    batch, _ = Batch.objects.get_or_create(department=dept, batch=est_batch, defaults={'is_active': False})
                if not batch and dept:
                    batch = Batch.objects.filter(department=dept).first()
                if not batch and dept:
                    batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR', defaults={'is_active': False})

                if c_type == 'OUTER':
                    outer_stud, created = OuterStudent.objects.get_or_create(
                        register_number=reg_no,
                        defaults={
                            'student_name': s_name,
                            'department': dept,
                            'program': dept.program if dept else None,
                            'batch': batch,
                        }
                    )
                    if not created and s_name and not outer_stud.student_name:
                        outer_stud.student_name = s_name
                        outer_stud.save()
                    added_outer += 1
                    added_students.append({
                        'register_no': reg_no,
                        'student_id': outer_stud.id,
                        'college_type': 'OUTER',
                    })
                else:
                    sec_obj = None
                    if dept:
                        sec_obj = Section.objects.filter(department=dept, sections__iexact='A').first()
                        if not sec_obj:
                            sec_obj = Section.objects.filter(department=dept, sections__iexact='Section: A').first()
                        if not sec_obj:
                            sec_obj = Section.objects.filter(department=dept, sections__icontains='A').first()
                        if not sec_obj:
                            sec_obj, _ = Section.objects.get_or_create(department=dept, sections='A')

                    stud, created = Student.objects.get_or_create(
                        register_number=reg_no,
                        defaults={
                            'student_name': s_name,
                            'department': dept,
                            'batch': batch,
                            'section': sec_obj,
                            'status': status_obj,
                        }
                    )
                    if not created and s_name and not stud.student_name:
                        stud.student_name = s_name
                        stud.save()
                    added_inter += 1
                    added_students.append({
                        'register_no': reg_no,
                        'student_id': stud.id,
                        'college_type': 'INTER',
                    })

        for m in ('Student', 'student', 'students', 'Batch', 'batch', 'batches'):
            try:
                invalidate_option_cache(m)
            except Exception:
                pass
        try:
            from common.signals import _send_realtime_broadcast
            _send_realtime_broadcast({
                'model': 'Student',
                'action': 'bulk_create',
                'event': 'student_created',
                'count': len(added_students)
            })
        except Exception:
            pass

        return Response({
            'message': f'Successfully added {len(added_students)} students ({added_inter} Internal, {added_outer} Outer).',
            'added_count': len(added_students),
            'added_inter': added_inter,
            'added_outer': added_outer,
            'added_students': added_students,
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='confirm-save')
    def confirm_save(self, request):
        """
        Save the verified preview data, schedule, and attendance roster.
        Only runs when the user explicitly clicks the confirm button.
        """
        data = request.data
        department_mappings = data.get('department_mappings', {}) # { branch_code: dept_id }
        subject_mappings = data.get('subject_mappings', {}) # { subject_code or branch_code__subject_code: subj_id }
        default_dept_id = data.get('department_id')
        default_subj_id = data.get('subject_id')
        exam_date_str = data.get('exam_date')
        session = (data.get('session') or 'FN').upper()
        qp_code = data.get('qp_code') or ''
        source_file = data.get('source_file') or 'attendance_upload.pdf'
        create_missing_students = data.get('create_missing_students', True)
        records = data.get('records', [])

        if not records:
            return Response({'error': 'No student records provided to save.'}, status=status.HTTP_400_BAD_REQUEST)

        from institution.models import Department, Batch, Program
        from subject.models import Subject
        from student.models import Student, StudentStatus, OuterStudent

        # Pre-cache mapped departments and subjects safely (handling string/invalid IDs)
        dept_cache = {}
        for b_code, d_id in department_mappings.items():
            if d_id and str(d_id).isdigit():
                dept_obj = Department.objects.filter(id=int(d_id)).first()
                if dept_obj:
                    dept_cache[b_code] = dept_obj
            elif d_id and isinstance(d_id, str) and d_id.strip() not in ['undefined', 'null', '']:
                dept_obj = Department.objects.filter(department_code__iexact=d_id.strip()).first()
                if dept_obj:
                    dept_cache[b_code] = dept_obj

        subj_cache = {}
        for s_key, s_id in subject_mappings.items():
            if s_id and str(s_id).isdigit():
                subj_obj = Subject.objects.filter(id=int(s_id)).first()
                if subj_obj:
                    subj_cache[s_key] = subj_obj
            elif s_id and isinstance(s_id, str) and s_id.strip() not in ['undefined', 'null', '']:
                subj_obj = Subject.objects.filter(subject_code__iexact=s_id.strip()).first()
                if subj_obj:
                    subj_cache[s_key] = subj_obj

        # Fallbacks
        fallback_dept = None
        if default_dept_id and str(default_dept_id).isdigit():
            fallback_dept = Department.objects.filter(id=int(default_dept_id)).first()
        if not fallback_dept:
            fallback_dept = Department.objects.first()

        fallback_subj = None
        if default_subj_id and str(default_subj_id).isdigit():
            fallback_subj = Subject.objects.filter(id=int(default_subj_id)).first()
        if not fallback_subj:
            fallback_subj = Subject.objects.first()

        saved_attendance_count = 0
        new_students_created = 0
        schedules_created = 0

        # Pre-fetch existing students and outer students in bulk (O(1) queries instead of O(N))
        all_reg_nos = list({str(r.get('register_no', '')).strip() for r in records if r.get('register_no')})
        existing_students = {s.register_number: s for s in Student.objects.filter(register_number__in=all_reg_nos).select_related('department', 'batch', 'status')}
        existing_outer = {s.register_number: s for s in OuterStudent.objects.filter(register_number__in=all_reg_nos).select_related('department', 'batch')}

        new_attendance_records = []
        seen_schedule_student_pairs = set()

        audit_user = request.user if request.user and request.user.is_authenticated else None

        with transaction.atomic():
            schedule_cache = {}

            # 1. Resolve or create all exam schedules
            for row in records:
                if not row.get('selected', True):
                    continue

                reg_no = (row.get('register_no') or '').strip()
                if not reg_no:
                    continue

                row_b_code = row.get('branch_code') or ''
                row_s_code = row.get('subject_code') or ''
                row_s_key = f"{row_b_code}__{row_s_code}"
                row_date_str = row.get('exam_date') or exam_date_str
                row_session = (row.get('session') or session).upper()

                dept = dept_cache.get(row_b_code) or fallback_dept
                subj = subj_cache.get(row_s_key) or subj_cache.get(row_s_code) or fallback_subj

                if not dept or not subj:
                    continue

                try:
                    row_date = datetime.datetime.strptime(row_date_str, '%Y-%m-%d').date()
                except Exception:
                    row_date = datetime.date.today()

                sched_key = f"{dept.id}_{subj.id}_{row_date}_{row_session}"
                if sched_key not in schedule_cache:
                    sched_obj, created = UniversityExamSchedule.objects.get_or_create(
                        department=dept,
                        exam_date=row_date,
                        session=row_session,
                        subject=subj,
                        defaults={
                            'qp_code': qp_code,
                            'exam_type': 'UNIVERSITY',
                            'status': 'DRAFT',
                            'created_by': audit_user,
                            'updated_by': audit_user,
                        }
                    )
                    if not created and audit_user and not sched_obj.updated_by:
                        sched_obj.updated_by = audit_user
                        sched_obj.save(update_fields=['updated_by', 'updated_at'])
                    if created:
                        schedules_created += 1
                    schedule_cache[sched_key] = sched_obj

            # Pre-fetch existing candidate pairs for all active schedules to prevent duplicates
            if schedule_cache:
                existing_att_pairs = set(
                    UniversityExamCandidate.objects.filter(
                        exam_schedule__in=schedule_cache.values()
                    ).values_list('exam_schedule_id', 'student_id')
                )
            else:
                existing_att_pairs = set()

            # 2. Process Candidates and build candidate list in memory
            for row in records:
                if not row.get('selected', True):
                    continue

                reg_no = (row.get('register_no') or '').strip()
                if not reg_no:
                    continue

                row_b_code = row.get('branch_code') or ''
                row_s_code = row.get('subject_code') or ''
                row_s_key = f"{row_b_code}__{row_s_code}"
                row_date_str = row.get('exam_date') or exam_date_str
                row_session = (row.get('session') or session).upper()

                dept = dept_cache.get(row_b_code) or fallback_dept
                subj = subj_cache.get(row_s_key) or subj_cache.get(row_s_code) or fallback_subj
                if not dept or not subj:
                    continue

                try:
                    row_date = datetime.datetime.strptime(row_date_str, '%Y-%m-%d').date()
                except Exception:
                    row_date = datetime.date.today()

                sched_key = f"{dept.id}_{subj.id}_{row_date}_{row_session}"
                schedule = schedule_cache.get(sched_key)
                if not schedule:
                    continue

                # Fast in-memory lookup
                student = existing_students.get(reg_no)

                # Outer student proxy
                if not student:
                    outer_student = existing_outer.get(reg_no)
                    if outer_student:
                        status_obj, _ = StudentStatus.objects.get_or_create(status_name='INACTIVE', defaults={'is_active': False})
                        student, _ = Student.objects.get_or_create(
                            register_number=reg_no,
                            defaults={
                                'student_name': outer_student.student_name or reg_no,
                                'department': outer_student.department or dept,
                                'batch': outer_student.batch,
                                'status': status_obj
                            }
                        )
                        existing_students[reg_no] = student

                # Auto-create missing student if needed
                if not student and create_missing_students:
                    batch = None
                    clean_reg = reg_no.replace(' ', '')
                    year_cand = None
                    if len(clean_reg) >= 10 and clean_reg[4:6].isdigit():
                        year_cand = int(clean_reg[4:6])
                    elif len(clean_reg) >= 8 and clean_reg[:2].isdigit():
                        year_cand = int(clean_reg[:2])

                    if year_cand and 15 <= year_cand <= 35:
                        est_batch_name = f"{2000 + year_cand}-{2000 + year_cand + 4}"
                        batch, _ = Batch.objects.get_or_create(department=dept, batch=est_batch_name, defaults={'is_active': False})

                    if not batch:
                        batch = Batch.objects.filter(department=dept).first()
                    if not batch:
                        batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR', defaults={'is_active': False})

                    s_name = row.get('student_name') or reg_no
                    student_status_obj, _ = StudentStatus.objects.get_or_create(status_name='ACTIVE')

                    student = Student.objects.create(
                        register_number=reg_no,
                        student_name=s_name,
                        department=dept,
                        batch=batch,
                        status=student_status_obj
                    )
                    existing_students[reg_no] = student
                    new_students_created += 1

                if student:
                    pair = (schedule.id, student.id)
                    if pair not in existing_att_pairs and pair not in seen_schedule_student_pairs:
                        seen_schedule_student_pairs.add(pair)
                        new_attendance_records.append(
                            UniversityExamCandidate(
                                exam_schedule=schedule,
                                student=student,
                                department=dept,
                                created_by=audit_user,
                                updated_by=audit_user,
                            )
                        )

            # 3. High-speed Bulk Insertion (500 records/batch in a single SQL operation)
            if new_attendance_records:
                UniversityExamCandidate.objects.bulk_create(
                    new_attendance_records,
                    batch_size=500,
                    ignore_conflicts=True
                )
                saved_attendance_count = len(new_attendance_records)

        # 4. Broadcast Real-time WebSocket Event
        try:
            from common.signals import _send_realtime_broadcast
            _send_realtime_broadcast({
                'model': 'UniversityExamCandidate',
                'action': 'bulk_import',
                'event': 'CANDIDATES_IMPORTED',
                'schedules_count': len(schedule_cache),
                'candidates_count': saved_attendance_count,
                'new_students': new_students_created,
                'exam_date': str(exam_date_str) if exam_date_str else '',
                'session': session,
            })
        except Exception:
            pass

        return Response({
            'message': f'Successfully created/updated {len(schedule_cache)} exam schedules and saved {saved_attendance_count} candidate records.',
            'schedules_count': len(schedule_cache),
            'candidates_count': saved_attendance_count,
            'new_students_created': new_students_created,
        }, status=status.HTTP_201_CREATED)


class UniversityExamScheduleViewSet(viewsets.ModelViewSet):
    queryset = UniversityExamSchedule.objects.select_related(
        'department', 'subject', 'subject__semester', 'subject__regulation',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).annotate(
        student_count=Count('candidates')
    ).all().order_by('-exam_date', '-session')
    serializer_class = UniversityExamScheduleSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def get_queryset(self):
        qs = super().get_queryset()
        exam_date = self.request.query_params.get('exam_date')
        session = self.request.query_params.get('session')
        department_id = self.request.query_params.get('department_id')
        exam_status = self.request.query_params.get('status')
        if exam_date:
            qs = qs.filter(exam_date=exam_date)
        if session:
            qs = qs.filter(session=session)
        if department_id:
            qs = qs.filter(department_id=department_id)
        if exam_status:
            qs = qs.filter(status=exam_status)
        return qs

    @action(detail=False, methods=['post'], url_path='generate-seating')
    def generate_seating(self, request):
        """
        Auto-generate seating allocation for all schedules on a given date+session.
        Body: { "exam_date": "YYYY-MM-DD", "session": "FN"|"AN" }
        """
        exam_date = request.data.get('exam_date')
        session = request.data.get('session')
        audit_user = request.user if request.user and request.user.is_authenticated else None

        if not exam_date or not session:
            return Response({'error': 'exam_date and session are required'}, status=status.HTTP_400_BAD_REQUEST)

        schedules = UniversityExamSchedule.objects.filter(
            exam_date=exam_date, session=session, status__in=['DRAFT', 'PUBLISHED']
        ).select_related('department', 'subject')

        if not schedules.exists():
            return Response({'error': 'No exam schedules found for this date/session'}, status=status.HTTP_404_NOT_FOUND)

        # Gather all students across all schedules
        all_attendances = []
        for schedule in schedules:
            candidates = UniversityExamCandidate.objects.filter(
                exam_schedule=schedule
            ).select_related('student', 'department', 'exam_schedule__subject', 'exam_schedule__subject__semester')
            for cand in candidates:
                all_attendances.append(cand)

        if not all_attendances:
            return Response({'error': 'No candidate records found for these schedules'}, status=status.HTTP_404_NOT_FOUND)

        total_students = len(all_attendances)

        # Retrieve user-selected rooms for allocation
        hall_ids = request.data.get('hall_ids') or request.data.get('room_ids') or request.data.get('rooms')
        if not hall_ids:
            return Response({
                'error': 'Please select the exam rooms/halls for seating allocation. Automatic room allocation without selection is disabled.'
            }, status=status.HTTP_400_BAD_REQUEST)

        hall_id_ints = [int(h) for h in hall_ids if str(h).isdigit()]
        if not hall_id_ints:
            return Response({'error': 'Invalid room selection provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # Query active UniversityExamHall objects matching user selection
        # Match primarily by UniversityExamHall primary key `id` (as selected in frontend)
        by_id_map = {h.id: h for h in UniversityExamHall.objects.filter(id__in=hall_id_ints, is_active=True).select_related('hall__floor__block')}

        # If any IDs were not found by primary key, check fallback infrastructure hall_id
        missing_ids = [hid for hid in hall_id_ints if hid not in by_id_map]
        by_hall_fk_map = {}
        if missing_ids:
            by_hall_fk_map = {h.hall_id: h for h in UniversityExamHall.objects.filter(hall_id__in=missing_ids, is_active=True).select_related('hall__floor__block') if h.hall_id}

        # Preserve the exact user selection order without key collision
        available_halls = []
        for hid in hall_id_ints:
            h = by_id_map.get(hid) or by_hall_fk_map.get(hid)
            if h and h not in available_halls:
                available_halls.append(h)

        if not available_halls:
            return Response({
                'error': 'None of the selected rooms were found or active. Please select valid exam halls.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Calculate total capacity of selected rooms
        total_selected_capacity = sum(h.max_capacity for h in available_halls)
        if total_selected_capacity < total_students:
            shortfall = total_students - total_selected_capacity
            return Response({
                'error': f'Selected rooms cannot accommodate all candidates. Total candidates: {total_students}, but selected {len(available_halls)} room(s) have a combined capacity of {total_selected_capacity} seats ({shortfall} more seats needed). Please select additional room(s).'
            }, status=status.HTTP_400_BAD_REQUEST)

        strategies = request.data.get('strategy', ['SUBJECT_MIX'])
        if isinstance(strategies, str):
            strategies = [strategies]

        # Plan capacities across the user-selected rooms:
        # Use strictly sufficient rooms needed to seat all candidates based on actual room capacities
        sufficient_halls = []
        accumulated_cap = 0
        for hall in available_halls:
            sufficient_halls.append(hall)
            accumulated_cap += (hall.max_capacity or 28)
            if accumulated_cap >= total_students:
                break

        active_halls = sufficient_halls
        num_selected = len(active_halls)

        if total_students <= 28 or num_selected == 1:
            hall_capacities = [total_students]
        else:
            base = total_students // num_selected
            rem = total_students % num_selected
            hall_capacities = [base + (1 if i < rem else 0) for i in range(num_selected)]

        if len(active_halls) < len(hall_capacities):
            shortfall = len(hall_capacities) - len(active_halls)
            return Response({
                'error': f'Selected rooms cannot accommodate all candidates. Need {len(hall_capacities)} rooms, but only {len(active_halls)} selected. Please select {shortfall} more room(s).'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ─── Anti-Adjacent Subject Code Checkerboard Seating Engine ──────────
        # Guarantee: Students with the same subject code DO NOT sit in front, back, left, or right.
        from collections import defaultdict

        def get_seat_coords(seat_no):
            if 1 <= seat_no <= 25:
                return ((seat_no - 1) % 5, (seat_no - 1) // 5)
            elif seat_no == 26:
                return (-1, 0)
            elif seat_no == 27:
                return (-1, 2)
            elif seat_no == 28:
                return (-1, 4)
            return (5, seat_no - 29)

        def build_neighbors(seats):
            s2c = {s: get_seat_coords(s) for s in seats}
            c2s = {c: s for s, c in s2c.items()}
            nbrs = {}
            for s, (r, c) in s2c.items():
                adj = []
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    if (r + dr, c + dc) in c2s:
                        adj.append(c2s[(r + dr, c + dc)])
                nbrs[s] = adj
            return nbrs

        def get_cand_subject_code(cand):
            if not cand or not cand.exam_schedule:
                return ''
            subj = cand.exam_schedule.subject
            return (subj.subject_code if subj and subj.subject_code else str(cand.exam_schedule.subject_id)).strip().upper()

        def optimize_seat_map(seat_map, nbrs):
            def count_conflicts(s_map):
                c = 0
                for s, cand in s_map.items():
                    if not cand:
                        continue
                    sc = get_cand_subject_code(cand)
                    for n in nbrs.get(s, []):
                        if n in s_map and s_map[n] and get_cand_subject_code(s_map[n]) == sc:
                            c += 1
                return c // 2

            cur_conflicts = count_conflicts(seat_map)
            if cur_conflicts == 0:
                return seat_map

            seats_list = list(seat_map.keys())
            improved = True
            iterations = 0
            while improved and iterations < 200:
                improved = False
                iterations += 1
                for i in range(len(seats_list)):
                    s1 = seats_list[i]
                    for j in range(i + 1, len(seats_list)):
                        s2 = seats_list[j]
                        if get_cand_subject_code(seat_map[s1]) == get_cand_subject_code(seat_map[s2]):
                            continue
                        seat_map[s1], seat_map[s2] = seat_map[s2], seat_map[s1]
                        new_c = count_conflicts(seat_map)
                        if new_c < cur_conflicts:
                            cur_conflicts = new_c
                            improved = True
                            if cur_conflicts == 0:
                                return seat_map
                        else:
                            seat_map[s1], seat_map[s2] = seat_map[s2], seat_map[s1]
                if cur_conflicts == 0:
                    break
            return seat_map

        is_subject_mix = 'SUBJECT_MIX' in strategies and 'DEPARTMENT_MIX' not in strategies
        is_sequential = 'SEQUENTIAL' in strategies

        if not is_subject_mix and not is_sequential:
            # ─── Department Pairwise Swap with Subject Code Avoidance (Old Pattern) ─
            # Pairs two departments per hall (e.g. Dept A on odds, Dept B on evens).
            # If two departments share the same subject code, passes that department and
            # pairs with another department having a different subject code.
            dept_groups = defaultdict(list)
            for cand in all_attendances:
                dept_groups[cand.department_id].append(cand)

            for d_id in dept_groups:
                dept_groups[d_id].sort(key=lambda c: (
                    -(c.exam_schedule.subject.semester.semester_number if c.exam_schedule.subject and c.exam_schedule.subject.semester else 0),
                    c.student.register_number if c.student else ''
                ))

            num_halls = len(hall_capacities)
            hall_seat_maps = []

            for h_idx in range(num_halls):
                cap = hall_capacities[h_idx]
                if cap <= 25:
                    available_seats = list(range(1, cap + 1))
                elif cap == 26:
                    available_seats = list(range(1, 26)) + [26]
                elif cap == 27:
                    available_seats = list(range(1, 26)) + [26, 27]
                else:
                    available_seats = list(range(1, 26)) + [26, 27, 28]

                nbrs = build_neighbors(available_seats)
                set0 = [s for s in available_seats if sum(get_seat_coords(s)) % 2 == 0]
                set1 = [s for s in available_seats if sum(get_seat_coords(s)) % 2 == 1]
                needed0 = len(set0)
                needed1 = len(set1)

                active_depts = sorted([d for d in dept_groups if len(dept_groups[d]) > 0], key=lambda d: len(dept_groups[d]), reverse=True)
                if not active_depts:
                    break

                dept_a = active_depts[0]
                subj_a = get_cand_subject_code(dept_groups[dept_a][0])

                # Pair with department B having a different subject code (pass same subject code)
                dept_b = next((d for d in active_depts[1:] if get_cand_subject_code(dept_groups[d][0]) != subj_a), None)
                if not dept_b and len(active_depts) > 1:
                    dept_b = active_depts[1]

                take_a = min(len(dept_groups[dept_a]), needed0)
                pool0 = [dept_groups[dept_a].pop(0) for _ in range(take_a)]

                pool1 = []
                if dept_b:
                    take_b = min(len(dept_groups[dept_b]), needed1)
                    pool1 = [dept_groups[dept_b].pop(0) for _ in range(take_b)]

                # Fill remaining in pool0 if dept_a was exhausted
                while len(pool0) < needed0:
                    rem_depts = sorted([d for d in dept_groups if len(dept_groups[d]) > 0], key=lambda d: len(dept_groups[d]), reverse=True)
                    if not rem_depts:
                        break
                    p1_subj = get_cand_subject_code(pool1[0]) if pool1 else None
                    compat = [d for d in rem_depts if not p1_subj or get_cand_subject_code(dept_groups[d][0]) != p1_subj]
                    target_d = compat[0] if compat else rem_depts[0]
                    pool0.append(dept_groups[target_d].pop(0))

                # Fill remaining in pool1 if dept_b was exhausted
                while len(pool1) < needed1:
                    rem_depts = sorted([d for d in dept_groups if len(dept_groups[d]) > 0], key=lambda d: len(dept_groups[d]), reverse=True)
                    if not rem_depts:
                        break
                    p0_subj = get_cand_subject_code(pool0[0]) if pool0 else None
                    compat = [d for d in rem_depts if not p0_subj or get_cand_subject_code(dept_groups[d][0]) != p0_subj]
                    target_d = compat[0] if compat else rem_depts[0]
                    pool1.append(dept_groups[target_d].pop(0))

                seat_map = {}
                for s_no, cand in zip(set0, pool0):
                    seat_map[s_no] = cand
                for s_no, cand in zip(set1, pool1):
                    seat_map[s_no] = cand

                seat_map = optimize_seat_map(seat_map, nbrs)
                hall_seat_maps.append((available_seats, seat_map))

        else:
            # ─── Pure Subject-Balanced Strategy ─────────────────────────────
            subject_queues = defaultdict(list)
            for cand in all_attendances:
                sc = get_cand_subject_code(cand)
                subject_queues[sc].append(cand)

            for sc in subject_queues:
                subject_queues[sc].sort(key=lambda c: (
                    -(c.exam_schedule.subject.semester.semester_number if c.exam_schedule.subject and c.exam_schedule.subject.semester else 0),
                    c.department.department_code if c.department else '',
                    c.student.register_number if c.student else ''
                ))

            num_halls = len(hall_capacities)
            hall_students_map = [[] for _ in range(num_halls)]
            sorted_subject_keys = sorted(subject_queues.keys(), key=lambda k: len(subject_queues[k]), reverse=True)

            for sc in sorted_subject_keys:
                q = subject_queues[sc]
                while q:
                    eligible_halls = [h for h in range(num_halls) if len(hall_students_map[h]) < hall_capacities[h]]
                    if not eligible_halls:
                        break
                    best_h = min(eligible_halls, key=lambda h: len(hall_students_map[h]))
                    hall_students_map[best_h].append(q.pop(0))

            hall_seat_maps = []
            for h_idx in range(num_halls):
                hall_students = hall_students_map[h_idx]
                if not hall_students:
                    continue

                K = len(hall_students)
                if K <= 25:
                    available_seats = list(range(1, K + 1))
                elif K == 26:
                    available_seats = list(range(1, 26)) + [26]
                elif K == 27:
                    available_seats = list(range(1, 26)) + [26, 27]
                else:
                    available_seats = list(range(1, 26)) + [26, 27, 28]

                nbrs = build_neighbors(available_seats)
                set0 = [s for s in available_seats if sum(get_seat_coords(s)) % 2 == 0]
                set1 = [s for s in available_seats if sum(get_seat_coords(s)) % 2 == 1]

                h_subjs = defaultdict(list)
                for cand in hall_students:
                    h_subjs[get_cand_subject_code(cand)].append(cand)

                sorted_h_subjs = sorted(h_subjs.keys(), key=lambda k: len(h_subjs[k]), reverse=True)
                pool0 = []
                pool1 = []
                needed0 = len(set0)
                needed1 = len(set1)

                for sc in sorted_h_subjs:
                    q_s = h_subjs[sc]
                    if len(pool0) + len(q_s) <= needed0:
                        pool0.extend(q_s)
                    elif len(pool1) + len(q_s) <= needed1:
                        pool1.extend(q_s)
                    else:
                        take_0 = max(0, needed0 - len(pool0))
                        pool0.extend(q_s[:take_0])
                        pool1.extend(q_s[take_0:])

                seat_map = {}
                for s_no, cand in zip(set0, pool0):
                    seat_map[s_no] = cand
                for s_no, cand in zip(set1, pool1):
                    seat_map[s_no] = cand

                seat_map = optimize_seat_map(seat_map, nbrs)
                hall_seat_maps.append((available_seats, seat_map))

        # Clear old allocations for this date+session
        ExamSeatAllocation.objects.filter(exam_schedule__in=schedules).delete()
        ExamHallAllocation.objects.filter(exam_schedule__in=schedules).delete()

        with transaction.atomic():
            hall_order = 1
            allocations_created = 0
            all_seat_allocations = []
            all_hall_allocations = []

            for h_idx, (available_seats, seat_map) in enumerate(hall_seat_maps):
                if h_idx >= len(active_halls) or not seat_map:
                    continue

                hall = active_halls[h_idx]
                hall_students = list(seat_map.values())
                K = len(hall_students)

                # Create one ExamHallAllocation per schedule that has students in this hall
                schedule_in_hall = {}
                for att in hall_students:
                    if att.exam_schedule_id not in schedule_in_hall:
                        ha = ExamHallAllocation.objects.create(
                            exam_schedule=att.exam_schedule,
                            exam_hall=hall,
                            allocation_order=hall_order,
                            planned_capacity=max(20, min(28, K)),
                            allocated_students=0,
                            status='ALLOCATED',
                            created_by=audit_user,
                            updated_by=audit_user,
                        )
                        schedule_in_hall[att.exam_schedule_id] = ha
                        all_hall_allocations.append(ha)

                # Collect seat allocation records for batch insertion
                for seat_offset, chosen_att in sorted(seat_map.items()):
                    if seat_offset <= 25:
                        row_num = ((seat_offset - 1) % 5) + 1
                        col_num = ((seat_offset - 1) // 5) + 1
                    elif seat_offset == 26:
                        row_num = 0
                        col_num = 1
                    elif seat_offset == 27:
                        row_num = 0
                        col_num = 3
                    elif seat_offset == 28:
                        row_num = 0
                        col_num = 5
                    else:
                        row_num = ((seat_offset - 1) % 5) + 1
                        col_num = ((seat_offset - 1) // 5) + 1

                    ha = schedule_in_hall[chosen_att.exam_schedule_id]
                    all_seat_allocations.append(
                        ExamSeatAllocation(
                            exam_schedule=chosen_att.exam_schedule,
                            hall_allocation=ha,
                            student=chosen_att.student,
                            seat_number=seat_offset,
                            row_number=row_num,
                            column_number=col_num,
                            department=chosen_att.department,
                            subject=chosen_att.exam_schedule.subject,
                            allocation_status='ALLOCATED',
                            created_by=audit_user,
                            updated_by=audit_user,
                        )
                    )
                    ha.allocated_students += 1
                    allocations_created += 1

                hall_order += 1

            if all_seat_allocations:
                ExamSeatAllocation.objects.bulk_create(all_seat_allocations, batch_size=500)

            if all_hall_allocations:
                ExamHallAllocation.objects.bulk_update(all_hall_allocations, ['allocated_students'], batch_size=500)

        return Response({
            'message': f'Seating generated successfully. {allocations_created} seats allocated across {len(hall_capacities)} selected room(s).',
            'seats_allocated': allocations_created,
            'allocated_rooms_count': len(hall_capacities),
        })


class UniversityExamCandidateViewSet(viewsets.ModelViewSet):
    queryset = UniversityExamCandidate.objects.select_related(
        'exam_schedule', 'student', 'department',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).all().order_by('exam_schedule', 'student__register_number')
    serializer_class = UniversityExamCandidateSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def get_queryset(self):
        qs = super().get_queryset()
        schedule_id = self.request.query_params.get('schedule_id')
        department_id = self.request.query_params.get('department_id')
        if schedule_id:
            qs = qs.filter(exam_schedule_id=schedule_id)
        if department_id:
            qs = qs.filter(department_id=department_id)
        return qs


# Backward compatibility alias
UniversityExamAttendanceViewSet = UniversityExamCandidateViewSet


class ExamHallAllocationViewSet(viewsets.ModelViewSet):
    queryset = ExamHallAllocation.objects.select_related(
        'exam_schedule', 'exam_hall__hall__floor__block',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).all().order_by('exam_schedule__exam_date', 'allocation_order')
    serializer_class = ExamHallAllocationSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def get_queryset(self):
        qs = super().get_queryset()
        schedule_id = self.request.query_params.get('schedule_id')
        exam_date = self.request.query_params.get('exam_date')
        session = self.request.query_params.get('session')
        if schedule_id:
            qs = qs.filter(exam_schedule_id=schedule_id)
        if exam_date:
            qs = qs.filter(exam_schedule__exam_date=exam_date)
        if session:
            qs = qs.filter(exam_schedule__session=session)
        return qs

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        qs = ExamHallAllocation.objects.values(
            'exam_schedule__exam_date', 'exam_schedule__session'
        ).annotate(
            total_students=Sum('allocated_students'),
            total_halls=Count('exam_hall', distinct=True),
            total_departments=Count('exam_schedule__department', distinct=True)
        ).order_by('-exam_schedule__exam_date', '-exam_schedule__session')

        results = list(qs)
        for item in results:
            latest = ExamHallAllocation.objects.filter(
                exam_schedule__exam_date=item['exam_schedule__exam_date'],
                exam_schedule__session=item['exam_schedule__session']
            ).select_related('created_by', 'created_by__role', 'updated_by', 'updated_by__role').order_by('-id').first()
            if latest:
                item['created_at'] = latest.created_at
                item['updated_at'] = latest.updated_at
                if latest.created_by:
                    item['created_by_name'] = latest.created_by.name or latest.created_by.username
                    item['created_by_username'] = latest.created_by.username
                    item['created_by_role'] = latest.created_by.role.role_name if latest.created_by.role else None
                if latest.updated_by:
                    item['updated_by_name'] = latest.updated_by.name or latest.updated_by.username
                    item['updated_by_username'] = latest.updated_by.username
                    item['updated_by_role'] = latest.updated_by.role.role_name if latest.updated_by.role else None
        return Response(results)


class ExamSeatAllocationViewSet(viewsets.ModelViewSet):
    queryset = ExamSeatAllocation.objects.select_related(
        'exam_schedule', 'hall_allocation__exam_hall__hall__floor__block',
        'student', 'department', 'subject', 'subject__regulation', 'subject__semester',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).all().order_by('hall_allocation', 'seat_number')
    serializer_class = ExamSeatAllocationSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    def get_queryset(self):
        qs = super().get_queryset()
        schedule_id = self.request.query_params.get('schedule_id')
        hall_allocation_id = self.request.query_params.get('hall_allocation_id')
        department_id = self.request.query_params.get('department_id')
        exam_date = self.request.query_params.get('exam_date')
        session = self.request.query_params.get('session')
        if schedule_id:
            qs = qs.filter(exam_schedule_id=schedule_id)
        if hall_allocation_id:
            qs = qs.filter(hall_allocation_id=hall_allocation_id)
        if department_id:
            qs = qs.filter(department_id=department_id)
        if exam_date:
            qs = qs.filter(exam_schedule__exam_date=exam_date)
        if session:
            qs = qs.filter(exam_schedule__session=session)
        return qs

    @action(detail=False, methods=['get'], url_path='by-hall/(?P<hall_id>[^/.]+)')
    def by_hall(self, request, hall_id=None):
        """Get all seat allocations for a hall on a given date+session for print view."""
        exam_date = request.query_params.get('exam_date')
        session = request.query_params.get('session')
        qs = self.get_queryset().filter(hall_allocation__exam_hall__hall_id=hall_id)
        if exam_date:
            qs = qs.filter(exam_schedule__exam_date=exam_date)
        if session:
            qs = qs.filter(exam_schedule__session=session)
        qs = qs.order_by('seat_number')
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['patch'], url_path='edit')
    def edit_seat(self, request, pk=None):
        seat = self.get_object()
        allocation_status = request.data.get('allocation_status')
        answer_book_no = request.data.get('answer_book_no')
        
        # Update seat status
        if allocation_status:
            seat.allocation_status = allocation_status
            seat.save()

        return Response({'status': 'success'})
