import io
import datetime
import re
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from users.permissions import RestrictDeleteToTechSupporterPermission
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from .models import (
    ExamAttendanceImport, UniversityExamSchedule,
    UniversityExamAttendance, ExamHallAllocation, ExamSeatAllocation,
    UniversityExamHall, ExamHallDate
)
from student.models import Student
from institution.models import Department
from subject.models import Subject
from .serializers import (
    ExamAttendanceImportSerializer, UniversityExamScheduleSerializer,
    UniversityExamAttendanceSerializer, ExamHallAllocationSerializer,
    ExamSeatAllocationSerializer, UniversityExamHallSerializer, ExamHallDateSerializer
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

    def get_queryset(self):
        qs = super().get_queryset()
        hall_id = self.request.query_params.get('hall_id')
        is_active = self.request.query_params.get('is_active')
        if hall_id:
            qs = qs.filter(hall_id=hall_id)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() in ('true', '1', 'yes'))
        return qs


class ExamHallDateViewSet(viewsets.ModelViewSet):
    queryset = ExamHallDate.objects.select_related(
        'exam_hall__hall__floor__block',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).all().order_by('-exam_date', 'session', 'exam_hall__hall__hall_no')
    serializer_class = ExamHallDateSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        exam_date = self.request.query_params.get('exam_date')
        session = self.request.query_params.get('session')
        exam_hall_id = self.request.query_params.get('exam_hall_id')
        is_available = self.request.query_params.get('is_available')

        if exam_date:
            qs = qs.filter(exam_date=exam_date)
        if session:
            qs = qs.filter(session=session)
        if exam_hall_id:
            qs = qs.filter(exam_hall_id=exam_hall_id)
        if is_available is not None:
            qs = qs.filter(is_available=is_available.lower() in ('true', '1', 'yes'))
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
    - Name in adjacent column.
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

                # 2. Check subsequent cells for name
                if not name:
                    for nxt in range(i + 1, min(i + 3, len(cleaned))):
                        cand = cleaned[nxt]
                        if not cand or cand in ['-', 'AB', 'A', 'P']:
                            continue
                        c_clean = cand.strip()
                        if c_clean.isdigit() or len(c_clean.replace(' ', '')) >= 10:
                            continue
                        if re.search(r'[A-Za-z]{2,}', c_clean):
                            name = c_clean.split('\n')[0].strip()
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

            # Clean trailing numbers (booklet no, next sl.no, attendance status)
            seg = re.sub(r'\s+\d{1,4}\s*$', '', seg)
            seg = re.sub(r'\s+(?:\d{4,9}|AB|OD|WH|ABSENT|PRESENT|[AP])\s*$', '', seg, flags=re.IGNORECASE).strip()
            seg = re.sub(r'\s+(?:\d{4,9}|AB|OD|WH|ABSENT|PRESENT|[AP])\s*$', '', seg, flags=re.IGNORECASE).strip()
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

        # 2. Extract candidates from tables
        candidates = []
        for table in tables:
            candidates.extend(extract_candidates_from_table(table))

        # 3. If no candidates found from tables, fallback to raw text stream
        if not candidates and raw_text:
            candidates = extract_candidates_from_text(raw_text)

        # 4. Process candidates for this page
        for reg_no, s_name in candidates:
            # Automatic branch and college deduction from 12-digit AU reg_no if missing
            b_code = active_branch_code
            if not b_code and len(reg_no) >= 9 and reg_no[:4].isdigit():
                b_code = reg_no[6:9]

            c_code = active_college_code
            if not c_code and len(reg_no) >= 4 and reg_no[:4].isdigit():
                c_code = reg_no[:4]

            dedup_key = (reg_no, active_subject_code)
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
                'session': active_session[:2] if active_session else 'FN',
                'qp_code': active_qp_code,
                'source_page': page_num,
            })

    return rows


# ─── ViewSets ────────────────────────────────────────────────────────────────

class ExamAttendanceImportViewSet(viewsets.ModelViewSet):
    queryset = ExamAttendanceImport.objects.all().order_by('-id')
    serializer_class = ExamAttendanceImportSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('import_status')
        exam_date = self.request.query_params.get('exam_date')
        if status_filter:
            qs = qs.filter(import_status=status_filter)
        if exam_date:
            qs = qs.filter(exam_date=exam_date)
        return qs

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

        # 3. Students Analysis (Found vs Not Found)
        reg_numbers = list({r['register_no'] for r in parsed_rows if r.get('register_no')})
        existing_students = Student.objects.filter(register_number__in=reg_numbers).select_related(
            'department', 'application', 'application__candidate'
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

            students_analysis.append({
                'key': f"{idx}_{r_no}",
                'register_no': r_no,
                'student_name': row.get('student_name') or '',
                'branch_code': b_code,
                'branch_name': b_name,
                'subject_code': row.get('subject_code') or '',
                'subject_name': row.get('subject_name') or '',
                'exam_date': row.get('exam_date').strftime('%Y-%m-%d') if row.get('exam_date') else '',
                'session': row.get('session') or 'FN',
                'source_page': row.get('source_page', 1),
                'is_found': is_found,
                'student_id': db_s['id'] if db_s else None,
                'db_student_name': db_s['name'] if db_s else '',
                'db_department_code': db_s['department_code'] if db_s else '',
                'mapped_department_id': db_s['department_id'] if db_s else (matched_dept_for_row['id'] if matched_dept_for_row else None),
                'selected': True,
            })

        # 4. Detected Schedule Slots in the PDF
        slots_map = {}
        for row in parsed_rows:
            s_date = row.get('exam_date').strftime('%Y-%m-%d') if row.get('exam_date') else ''
            s_session = row.get('session') or 'FN'
            b_code = row.get('branch_code') or ''
            s_code = row.get('subject_code') or ''
            slot_key = f"{b_code}__{s_code}__{s_date}__{s_session}"
            if slot_key not in slots_map:
                slots_map[slot_key] = {
                    'slot_key': slot_key,
                    'branch_code': b_code,
                    'subject_code': s_code,
                    'exam_date': s_date,
                    'session': s_session,
                    'student_count': 0
                }
            slots_map[slot_key]['student_count'] += 1

        detected_schedules = list(slots_map.values())

        first_row = parsed_rows[0]
        header_date = first_row.get('exam_date').strftime('%Y-%m-%d') if first_row.get('exam_date') else ''
        header_session = first_row.get('session') or 'FN'
        header_qp_code = first_row.get('qp_code') or ''

        return Response({
            'summary': {
                'total_candidates': len(students_analysis),
                'students_found': found_student_count,
                'students_not_found': not_found_student_count,
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
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-dept')
    def quick_add_dept(self, request):
        """Quick add missing department from preview slide-over."""
        from institution.models import Department, Program
        b_code = (request.data.get('department_code') or '').strip()
        b_name = (request.data.get('department_name') or '').strip()
        short_name = (request.data.get('short_name') or '').strip() or b_code

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
            }
        )
        return Response({
            'id': dept.id,
            'department_code': dept.department_code,
            'department_name': dept.department_name,
            'created': created
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-subject')
    def quick_add_subject(self, request):
        """Quick add missing subject from preview slide-over."""
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
            regulation=reg,
            department=dept,
            semester=sem,
            defaults={
                'subject_name': s_name or s_code,
                'credits': credits,
                'is_theory': True,
            }
        )
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
        """Quick add missing student directly to students table."""
        from institution.models import Department, Batch, Section, Quota
        from student.models import Student, StudentStatus

        reg_no = (request.data.get('register_number') or request.data.get('register_no') or '').strip()
        roll_no = (request.data.get('roll_number') or '').strip() or None
        s_name = (request.data.get('student_name') or '').strip() or reg_no
        dept_id = request.data.get('department_id')
        branch_code = (request.data.get('branch_code') or request.data.get('department_code') or '').strip()
        branch_name = (request.data.get('branch_name') or request.data.get('department_name') or '').strip()
        batch_id = request.data.get('batch_id')
        section_id = request.data.get('section_id')
        quota_id = request.data.get('quota_id')
        status_id = request.data.get('status_id')

        if not reg_no:
            return Response({'error': 'Register number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        dept = None
        if dept_id:
            dept = Department.objects.filter(id=dept_id).first()
        if not dept and branch_code:
            dept = Department.objects.filter(department_code__iexact=branch_code).first()
        if not dept and branch_name:
            dept = Department.objects.filter(department_name__icontains=branch_name).first()
        if not dept:
            dept = Department.objects.first()
        batch = None
        if batch_id:
            if str(batch_id).isdigit():
                found_b = Batch.objects.filter(id=int(batch_id)).first()
                if found_b:
                    if dept and found_b.department_id != dept.id:
                        batch, _ = Batch.objects.get_or_create(department=dept, batch=found_b.batch)
                    else:
                        batch = found_b
            else:
                batch_str = str(batch_id).strip()
                if dept and batch_str:
                    batch, _ = Batch.objects.get_or_create(department=dept, batch=batch_str)

        if not batch and dept and reg_no:
            clean_reg = reg_no.replace(' ', '')
            year_cand = None
            if len(clean_reg) >= 10 and clean_reg[4:6].isdigit():
                year_cand = int(clean_reg[4:6])
            elif len(clean_reg) >= 8 and clean_reg[:2].isdigit():
                year_cand = int(clean_reg[:2])

            if year_cand and 15 <= year_cand <= 35:
                est_batch_name = f"{2000 + year_cand}-{2000 + year_cand + 4}"
                batch, _ = Batch.objects.get_or_create(department=dept, batch=est_batch_name)

        if not batch and dept:
            batch = Batch.objects.filter(department=dept).first()
        if not batch and dept:
            batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR')

        section = Section.objects.filter(id=section_id).first() if section_id else None
        quota = Quota.objects.filter(id=quota_id).first() if quota_id else None
        
        student_status_obj = None
        if status_id:
            student_status_obj = StudentStatus.objects.filter(id=status_id).first()
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

        return Response({
            'id': student.id,
            'register_number': student.register_number,
            'student_name': student.student_name or student.name,
            'department_code': dept.department_code if dept else '',
            'created': created
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

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
        from student.models import Student, StudentStatus

        # Pre-cache mapped departments and subjects
        dept_cache = {}
        for b_code, d_id in department_mappings.items():
            if d_id:
                dept_obj = Department.objects.filter(id=d_id).first()
                if dept_obj:
                    dept_cache[b_code] = dept_obj

        subj_cache = {}
        for s_key, s_id in subject_mappings.items():
            if s_id:
                subj_obj = Subject.objects.filter(id=s_id).first()
                if subj_obj:
                    subj_cache[s_key] = subj_obj

        # Fallbacks
        fallback_dept = Department.objects.filter(id=default_dept_id).first() if default_dept_id else Department.objects.first()
        fallback_subj = Subject.objects.filter(id=default_subj_id).first() if default_subj_id else Subject.objects.first()

        saved_attendance_count = 0
        new_students_created = 0
        schedules_created = 0

        with transaction.atomic():
            schedule_cache = {}

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

                # Get or create schedule for this specific slot
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
                        }
                    )
                    if created:
                        schedules_created += 1
                    schedule_cache[sched_key] = sched_obj

                schedule = schedule_cache[sched_key]

                # Resolve or Create Student
                student_id = row.get('student_id')
                student = None
                if student_id:
                    student = Student.objects.filter(id=student_id).first()
                if not student:
                    student = Student.objects.filter(register_number=reg_no).first()

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
                        batch, _ = Batch.objects.get_or_create(department=dept, batch=est_batch_name)

                    if not batch:
                        batch = Batch.objects.filter(department=dept).first()
                    if not batch:
                        batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR')

                    s_name = row.get('student_name') or reg_no
                    student_status_obj, _ = StudentStatus.objects.get_or_create(status_name='ACTIVE')

                    student = Student.objects.create(
                        register_number=reg_no,
                        student_name=s_name,
                        department=dept,
                        batch=batch,
                        status=student_status_obj
                    )
                    new_students_created += 1

                if student:
                    att_obj, created = UniversityExamAttendance.objects.get_or_create(
                        exam_schedule=schedule,
                        student=student,
                        defaults={
                            'department': dept,
                            'qp_code': qp_code,
                        }
                    )
                    if created:
                        saved_attendance_count += 1

                    # Log to ExamAttendanceImport for history
                    ExamAttendanceImport.objects.create(
                        department=dept,
                        student=student,
                        subject=subj,
                        exam_date=row_date,
                        session=row_session,
                        source_file=source_file,
                        source_page=row.get('source_page', 1),
                        import_status='IMPORTED',
                    )

        return Response({
            'message': f'Successfully created/updated {len(schedule_cache)} exam schedules and saved {saved_attendance_count} attendance records.',
            'schedules_count': len(schedule_cache),
            'attendance_count': saved_attendance_count,
            'new_students_created': new_students_created,
        }, status=status.HTTP_201_CREATED)



    @action(detail=False, methods=['delete'], url_path='clear-pending')
    def clear_pending(self, request):
        """Delete all PENDING and ERROR records from the staging table."""
        count, _ = ExamAttendanceImport.objects.filter(import_status__in=['PENDING', 'ERROR']).delete()
        return Response({'message': f'Successfully cleared {count} unprocessed records'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='process')
    def process_imports(self, request):
        """Match staged import rows with master data and create normalized records."""
        pending = ExamAttendanceImport.objects.filter(import_status='PENDING')
        processed, errors = 0, 0
        new_students = 0
        existing_students = 0

        for record in pending:
            try:
                if not record.student or not record.subject or not record.department:
                    record.import_status = 'ERROR'
                    record.error_message = "Missing student, subject, or department references."
                    record.save()
                    errors += 1
                    continue

                schedule, _ = UniversityExamSchedule.objects.get_or_create(
                    department=record.student.department,
                    exam_date=record.exam_date,
                    session=record.session,
                    subject=record.subject,
                    defaults={
                        'qp_code': record.qp_code,
                        'exam_type': 'UNIVERSITY',
                        'status': 'DRAFT',
                    }
                )

                UniversityExamAttendance.objects.get_or_create(
                    exam_schedule=schedule,
                    student=record.student,
                    defaults={
                        'department': record.student.department,
                        'answer_book_no': record.answer_book_no,
                        'qp_code': record.qp_code,
                    }
                )

                record.import_status = 'IMPORTED'
                record.error_message = None
                record.save()
                processed += 1

            except Exception as e:
                record.import_status = 'ERROR'
                record.error_message = str(e)
                record.save()
                errors += 1

        return Response({
            'message': f'Processing complete: {processed} imported, {errors} errors',
            'processed': processed,
            'errors': errors,
            'new_students': new_students,
            'existing_students': existing_students
        })


class UniversityExamScheduleViewSet(viewsets.ModelViewSet):
    queryset = UniversityExamSchedule.objects.select_related(
        'department', 'subject',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).annotate(
        student_count=Count('attendances')
    ).all().order_by('-exam_date', 'session')
    serializer_class = UniversityExamScheduleSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]

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
            attendances = UniversityExamAttendance.objects.filter(
                exam_schedule=schedule
            ).select_related('student', 'department', 'exam_schedule__subject')
            for att in attendances:
                all_attendances.append(att)

        if not all_attendances:
            return Response({'error': 'No attendance records found for these schedules'}, status=status.HTTP_404_NOT_FOUND)

        # Get available halls for this date+session
        available_hall_ids = ExamHallDate.objects.filter(
            exam_date=exam_date, session=session, is_available=True
        ).values_list('exam_hall_id', flat=True)

        available_halls = list(UniversityExamHall.objects.filter(
            id__in=available_hall_ids, is_active=True
        ).select_related('hall__floor__block').order_by('hall__floor__block__block_code', 'hall__floor__floor_name', 'hall__hall_no'))

        if not available_halls:
            # Fall back: use all active halls if no ExamHallDate records exist
            available_halls = list(UniversityExamHall.objects.filter(
                is_active=True
            ).select_related('hall__floor__block').order_by('hall__floor__block__block_code', 'hall__floor__floor_name', 'hall__hall_no'))

        if not available_halls:
            return Response({'error': 'No active halls found for University Exams. Please go to "Hall Setup" from the sidebar and click "Sync Infra Halls" to pull your infrastructure halls into the exam module.'}, status=status.HTTP_400_BAD_REQUEST)

        # Calculate total available capacity
        total_capacity = 0
        for hall in available_halls:
            total_capacity += min(hall.max_capacity, hall.rows_count * hall.columns_count)

        total_students = len(all_attendances)
        if total_capacity < total_students:
            avg_capacity = total_capacity / len(available_halls) if available_halls else 25
            shortfall = total_students - total_capacity
            expected_extra_halls = (shortfall // avg_capacity) + 1
            return Response({
                'error': f'Halls not available for all students. \nSummary: Total students: {total_students}. \nAllocated: 0. \nNot allocated: {total_students}. \nExpected {int(expected_extra_halls)} more hall(s).'
            }, status=status.HTTP_400_BAD_REQUEST)

        strategies = request.data.get('strategy', ['DEPARTMENT_MIX'])
        if isinstance(strategies, str):
            strategies = [strategies]
        all_attendances = sorted(all_attendances, key=lambda x: x.student.register_number)

        mixed_students = []
        if 'SUBJECT_MIX' in strategies:
            from collections import defaultdict
            subj_groups = defaultdict(list)
            for att in all_attendances:
                subj_groups[att.exam_schedule.subject_id].append(att)
            subj_queues = sorted(list(subj_groups.values()), key=len, reverse=True)
            while any(subj_queues):
                for q in subj_queues:
                    if q: mixed_students.append(q.pop(0))
        elif 'DEPT_SUBJECT_MIX' in strategies:
            from collections import defaultdict
            ds_groups = defaultdict(list)
            for att in all_attendances:
                ds_groups[(att.department_id, att.exam_schedule.subject_id)].append(att)
            ds_queues = sorted(list(ds_groups.values()), key=len, reverse=True)
            while any(ds_queues):
                for q in ds_queues:
                    if q: mixed_students.append(q.pop(0))
        elif 'DEPARTMENT_MIX' in strategies:
            from collections import defaultdict
            dept_groups = defaultdict(list)
            for att in all_attendances:
                dept_groups[att.department_id].append(att)
            # Sort queues by size descending: [CSE(242), IT(116), AI&DS(87), ECE(57), ...]
            dept_queues = sorted(list(dept_groups.values()), key=len, reverse=True)
            
            # Round-robin: take 1 from each department in order, then repeat
            # This perfectly spaces out departments and gracefully handles when smaller ones run out
            while any(dept_queues):
                for q in dept_queues:
                    if q:
                        mixed_students.append(q.pop(0))
        elif 'REVERSE_SEQUENTIAL' in strategies:
            mixed_students = list(reversed(all_attendances))
        elif 'RANDOM' in strategies:
            import random
            mixed_students = all_attendances.copy()
            random.shuffle(mixed_students)
        else:
            mixed_students = all_attendances

        # Clear old allocations for this date+session
        ExamSeatAllocation.objects.filter(exam_schedule__in=schedules).delete()
        ExamHallAllocation.objects.filter(exam_schedule__in=schedules).delete()

        with transaction.atomic():
            student_idx = 0
            hall_order = 1
            allocations_created = 0

            for hall in available_halls:
                if student_idx >= len(mixed_students):
                    break

                capacity = min(hall.max_capacity, hall.rows_count * hall.columns_count, len(mixed_students) - student_idx)
                if capacity < hall.min_capacity and student_idx + capacity < len(mixed_students):
                    capacity = hall.max_capacity

                # Group students for this hall by their schedule
                hall_students = mixed_students[student_idx:student_idx + capacity]

                # Create one ExamHallAllocation per schedule that has students in this hall
                schedule_in_hall = {}
                for att in hall_students:
                    if att.exam_schedule_id not in schedule_in_hall:
                        ha = ExamHallAllocation.objects.create(
                            exam_schedule=att.exam_schedule,
                            exam_hall=hall,
                            allocation_order=hall_order,
                            planned_capacity=hall.max_capacity,
                            allocated_students=0,
                            status='ALLOCATED',
                        )
                        schedule_in_hall[att.exam_schedule_id] = ha

                # Generate seat layout sequence based on strategy
                total_seats = hall.rows_count * hall.columns_count
                available_seats = list(range(1, total_seats + 1))
                
                if 'ZIGZAG' in strategies:
                    seat_sequence = []
                    for r in range(hall.rows_count):
                        row_seats = list(range(r * hall.columns_count + 1, (r + 1) * hall.columns_count + 1))
                        if r % 2 == 1:
                            row_seats.reverse()
                        seat_sequence.extend(row_seats)
                elif 'W_SHAPE' in strategies:
                    # Column-major seat numbering:
                    # Seat 1,2,3,4,5 go DOWN column 1
                    # Seat 6,7,8,9,10 go DOWN column 2, etc.
                    # With pairwise A,B,A,B this creates a perfect checkerboard
                    seat_sequence = list(range(1, total_seats + 1))
                else:
                    seat_sequence = available_seats

                # Create seat allocations
                is_column_major = 'W_SHAPE' in strategies
                for idx, att in enumerate(hall_students):
                    seat_offset = seat_sequence[idx] if idx < len(seat_sequence) else available_seats[idx % len(available_seats)]
                    if is_column_major:
                        # Column-major: seat 1→r1c1, seat 2→r2c1, seat 5→r5c1, seat 6→r1c2
                        row_num = ((seat_offset - 1) % hall.rows_count) + 1
                        col_num = ((seat_offset - 1) // hall.rows_count) + 1
                    else:
                        # Row-major: seat 1→r1c1, seat 2→r1c2, seat 5→r1c5, seat 6→r2c1
                        row_num = ((seat_offset - 1) // hall.columns_count) + 1
                        col_num = ((seat_offset - 1) % hall.columns_count) + 1
                    ha = schedule_in_hall[att.exam_schedule_id]
                    ExamSeatAllocation.objects.create(
                        exam_schedule=att.exam_schedule,
                        hall_allocation=ha,
                        student=att.student,
                        seat_number=seat_offset,
                        row_number=row_num,
                        column_number=col_num,
                        department=att.department,
                        subject=att.exam_schedule.subject,
                        allocation_status='ALLOCATED',
                    )
                    allocations_created += 1

                # Update allocated_students count on each hall allocation
                for ha in schedule_in_hall.values():
                    ha.allocated_students = ExamSeatAllocation.objects.filter(hall_allocation=ha).count()
                    ha.save()

                student_idx += capacity
                hall_order += 1

        return Response({
            'message': f'Seating generated successfully. {allocations_created} seats allocated.',
            'seats_allocated': allocations_created,
        })


class UniversityExamAttendanceViewSet(viewsets.ModelViewSet):
    queryset = UniversityExamAttendance.objects.select_related(
        'exam_schedule', 'student', 'department'
    ).all().order_by('exam_schedule', 'student__register_number')
    serializer_class = UniversityExamAttendanceSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        schedule_id = self.request.query_params.get('schedule_id')
        department_id = self.request.query_params.get('department_id')
        attendance_status = self.request.query_params.get('attendance_status')
        if schedule_id:
            qs = qs.filter(exam_schedule_id=schedule_id)
        if department_id:
            qs = qs.filter(department_id=department_id)
        if attendance_status:
            qs = qs.filter(attendance_status=attendance_status)
        return qs


class ExamHallAllocationViewSet(viewsets.ModelViewSet):
    queryset = ExamHallAllocation.objects.select_related(
        'exam_schedule', 'exam_hall__hall__floor__block'
    ).all().order_by('exam_schedule__exam_date', 'allocation_order')
    serializer_class = ExamHallAllocationSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

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
            total_halls=Count('exam_hall', distinct=True)
        ).order_by('-exam_schedule__exam_date', 'exam_schedule__session')
        return Response(list(qs))


class ExamSeatAllocationViewSet(viewsets.ModelViewSet):
    queryset = ExamSeatAllocation.objects.select_related(
        'exam_schedule', 'hall_allocation__exam_hall__hall__floor__block',
        'student', 'department', 'subject'
    ).all().order_by('hall_allocation', 'seat_number')
    serializer_class = ExamSeatAllocationSerializer
    permission_classes = [IsAuthenticated, RestrictDeleteToTechSupporterPermission]
    pagination_class = None

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

        # Update attendance record
        try:
            from .models import UniversityExamAttendance
            attendance = UniversityExamAttendance.objects.get(
                exam_schedule=seat.exam_schedule,
                student=seat.student
            )
            if answer_book_no is not None:
                attendance.answer_book_no = answer_book_no
            if allocation_status in ['PRESENT', 'ABSENT']:
                attendance.attendance_status = allocation_status
            attendance.save()
        except Exception as e:
            pass # Ignore if attendance record not found

        return Response({'status': 'success'})
