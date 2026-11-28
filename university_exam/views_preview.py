import io
import re
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction

from student.models import Student, StudentStatus, OuterStudent
from subject.models import Subject
from institution.models import Department, Program, Batch, Regulation, Semester, Section
from .models import UniversityExamSchedule
from .views import format_short_exam_code, ensure_university_exam_code
from common.caching import invalidate_option_cache
from common.signals import _send_realtime_broadcast


def _bust_preview_caches(model_names):
    """
    Invalidate in-memory LocMemCache/Redis option caches and versions
    for created/updated models so other pages immediately reflect updated records.
    """
    for m in model_names:
        try:
            invalidate_option_cache(m)
            invalidate_option_cache(m.lower())
            invalidate_option_cache(f"{m.lower()}s")
        except Exception:
            pass


def clean_str(val):
    if val is None:
        return ''
    return str(val).strip()


def get_institutional_college_code():
    """
    Fetch the institutional college code configured in CollegeHeader (e.g. '5132').
    Defaults to '5132' if not configured.
    """
    from institution.models import CollegeHeader
    try:
        header = CollegeHeader.objects.first()
        if header and header.college_code:
            return str(header.college_code).strip()
    except Exception:
        pass
    return '5132'


def format_exam_title(raw):
    """
    Standardize exam string into standard format e.g. 'NOV/DEC-26' or 'APR/MAY-26'.
    Unified with Attendance Import to prevent duplicate exam creation.
    """
    return format_short_exam_code(raw)


def clean_subject_title(t):
    """
    Format glued CamelCase or concatenated PDF titles into readable titles.
    E.g.: 'FluidMechanics' -> 'Fluid Mechanics'
          'ConstructionMaterialsandTechnology' -> 'Construction Materials and Technology'
          'StructuralAnalysisI' -> 'Structural Analysis I'
    """
    if not t:
        return ''
    # Fix glued words like MaterialsandTechnology -> Materials and Technology
    t = re.sub(r'([a-zA-Z])(and|of)([A-Z])', r'\1 \2 \3', t)
    # Insert space between lower and Upper case (CamelCase)
    t = re.sub(r'([a-z])([A-Z])', r'\1 \2', t)
    t = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', t)
    # Fix Roman numerals
    t = re.sub(r'([a-zA-Z])(I{1,3}|IV|V|VI{1,3})\b', r'\1 \2', t)
    # Fix commas without space
    t = re.sub(r',([A-Za-z])', r', \1', t)
    return re.sub(r'\s+', ' ', t).strip()


def derive_short_name(name):
    """Derive clean short name / acronym for a department name."""
    if not name:
        return 'DEPT'
    nl = name.lower()
    if 'computer science' in nl:
        return 'CSE'
    if 'civil' in nl:
        return 'CIVIL'
    if 'mechanical' in nl:
        return 'MECH'
    if 'information tech' in nl:
        return 'IT'
    if 'artificial intelligence' in nl or 'data science' in nl:
        return 'AI&DS'
    if 'agricultural' in nl:
        return 'AGRI'
    if 'electrical' in nl and 'electronic' in nl:
        return 'EEE'
    if 'electronic' in nl and 'communication' in nl:
        return 'ECE'
    if 'biomedical' in nl:
        return 'BME'
    if 'chemical' in nl:
        return 'CHEM'
    if 'business' in nl:
        return 'MBA'
    if 'computer application' in nl:
        return 'MCA'
    # Extract capital initials
    words = re.findall(r'[A-Za-z]+', name)
    ignored = {'and', 'of', 'in', '&', 'the', 'for', 'to'}
    initials = [w[0].upper() for w in words if w.lower() not in ignored]
    if len(initials) >= 2:
        return ''.join(initials)
    return name[:5].upper()


def parse_subject_triplet(col0, col1, col2):
    """
    Parse a column triplet (Sem No, Subject Code, Subject Title).
    Handles both single-row cells and multi-line cells produced by pdfplumber.
    Matches traditional codes (CE3301, GE3451, OCH353, NM1153) and new codes (CS25C01, UC25A01, EE25C11).
    """
    subjects = []
    col0_str = clean_str(col0)
    col1_str = clean_str(col1)
    col2_str = clean_str(col2)

    found_codes = re.findall(r'\b([A-Z]{2,4}\d[A-Z0-9]{3,7})\b', col1_str)
    if not found_codes:
        return subjects

    found_sems = re.findall(r'\b0?([1-8])\b', col0_str)

    col2_lines = [l.strip() for l in col2_str.splitlines() if l.strip()]
    col2_tokens = [tok.strip() for tok in col2_str.split() if tok.strip()]

    if len(col2_lines) == len(found_codes):
        title_candidates = col2_lines
    elif len(col2_tokens) == len(found_codes):
        title_candidates = col2_tokens
    elif len(col2_lines) > len(found_codes):
        title_candidates = col2_lines[:len(found_codes)]
    elif len(col2_tokens) > len(found_codes):
        title_candidates = col2_tokens[:len(found_codes)]
    else:
        title_candidates = col2_lines if col2_lines else col2_tokens

    for i, code in enumerate(found_codes):
        sem_val = int(found_sems[i]) if i < len(found_sems) else 1
        raw_t = title_candidates[i] if i < len(title_candidates) else ''
        t_cleaned = clean_subject_title(raw_t)
        subjects.append({
            'semester': sem_val,
            'subject_code': code,
            'subject_title': t_cleaned
        })

    return subjects


def extract_subjects_from_page_text(raw_text):
    """
    Ultra-fast regex-based subject extractor from page text (<1ms execution time).
    Avoids expensive vector geometry extraction on pdfplumber.extract_tables() (200ms+).
    """
    subjects = []
    if not raw_text:
        return subjects

    for line in raw_text.splitlines():
        line_clean = line.strip()
        if not line_clean:
            continue
        low = line_clean.lower()
        if 'sem no' in low and 'subject' in low:
            continue
        if any(h in low for h in ['register number', 'date of birth', 'anna university', 'degree & branch', 'regulations', 'signature of candidate', 'signature of principal', 'name of the candidate', 'college name']):
            continue

        codes = list(re.finditer(r'\b([A-Z]{2,4}\d[A-Z0-9]{3,7})\b', line_clean))
        if not codes:
            continue

        for idx, cm in enumerate(codes):
            code = cm.group(1)
            pre_text = line_clean[:cm.start()].strip()
            if idx > 0:
                pre_text = line_clean[codes[idx - 1].end():cm.start()].strip()

            sem_m = re.findall(r'\b(?:0?([1-8])|S([1-8]))\b', pre_text)
            sem = 1
            if sem_m:
                last_m = sem_m[-1]
                sem_str = last_m[0] or last_m[1]
                if sem_str and sem_str.isdigit():
                    sem = int(sem_str)

            next_start = codes[idx + 1].start() if idx + 1 < len(codes) else len(line_clean)
            title_part = line_clean[cm.end():next_start].strip(' \t-:|')

            title_part = re.sub(r'\s+\d{2}[-/.]\d{2}[-/.]\d{2,4}.*$', '', title_part)
            title_part = re.sub(r'\s+(?:FN|AN|FORENOON|AFTERNOON)\b.*$', '', title_part, flags=re.IGNORECASE)
            title_part = re.sub(r'\s+(?:0?[1-8]|S[1-8])\s*$', '', title_part)
            title_part = re.sub(r'\s+\d{1,3}\s*$', '', title_part)
            title = clean_subject_title(title_part)

            if code:
                subjects.append({
                    'semester': sem,
                    'subject_code': code,
                    'subject_title': title or code
                })
    return subjects


def parse_anna_univ_reg_preview_pdf(file_bytes):
    """
    Parse Anna University 'REGISTRATION PREVIEW' PDF.
    Extracts student candidate details and their registered subjects table.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required to parse Registration Preview PDFs. Run: pip install pdfplumber")

    students = []
    seen_reg_nos = set()

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ''

            reg_match = re.search(r'Register\s*(?:Number|No\.?)\s*[:]?\s*([0-9]{10,14})', raw_text, re.IGNORECASE)
            name_match = re.search(r'Name\s*(?:of\s*the\s*Candidate)?\s*[:]?\s*([A-Za-z\s\.]+?)(?:\n|Date\s*of|Date|$)', raw_text, re.IGNORECASE)
            dob_match = re.search(r'Date\s*of\s*Birth\s*[:]?\s*([0-9\-\/]+)', raw_text, re.IGNORECASE)
            deg_branch_match = re.search(r'Degree\s*&\s*Branch\s*[:]?\s*(.+?)(?:\s+Regulations?|\n|$)', raw_text, re.IGNORECASE)
            reg_year_match = re.search(r'Regulations?\s*[:]?\s*(\d{4})', raw_text, re.IGNORECASE)
            college_match = re.search(r'College\s*(?:Name\s*&\s*Code)?\s*[:]?\s*([^\n\r]+)', raw_text, re.IGNORECASE)
            exam_title_match = re.search(r'Application\s*for\s*([^\n\r]+)', raw_text, re.IGNORECASE)

            if not reg_match:
                alt_reg = re.search(r'\b(5132\d{8}|\d{12})\b', raw_text)
                if alt_reg:
                    reg_match = alt_reg

            if not reg_match:
                continue

            reg_no = clean_str(reg_match.group(1))
            cand_name = clean_str(name_match.group(1)) if name_match else ''
            dob = clean_str(dob_match.group(1)) if dob_match else ''
            deg_branch = clean_str(deg_branch_match.group(1)) if deg_branch_match else ''
            regulations = clean_str(reg_year_match.group(1)) if reg_year_match else '2021'
            college = clean_str(college_match.group(1)) if college_match else ''

            # Extract clean Exam Name (e.g. 'Nov. / Dec. Examination, 2026')
            exam_title = ''
            if exam_title_match:
                exam_title = format_exam_title(exam_title_match.group(1))
            if not exam_title:
                alt_et = re.search(r'([A-Za-z\.\s\/]+(?:Examination|Exam)\s*,?\s*\d{4}[A-Za-z]*)', raw_text, re.IGNORECASE)
                if alt_et:
                    exam_title = format_exam_title(alt_et.group(1))

            degree = 'B.E.'
            branch = deg_branch
            if deg_branch:
                deg_prefix = re.match(r'^(B\.E\.|B\.Tech\.?|M\.E\.|M\.Tech\.?|MBA|MCA)\s*(.*)$', deg_branch, re.IGNORECASE)
                if deg_prefix:
                    degree = deg_prefix.group(1).upper()
                    branch = clean_subject_title(deg_prefix.group(2).strip())
                elif ' - ' in deg_branch:
                    parts = deg_branch.split(' - ', 1)
                    degree = parts[0].strip()
                    branch = clean_subject_title(parts[1].strip())

            batch_code = ''
            calculated_batch = ''
            if len(reg_no) >= 6:
                batch_code = reg_no[4:6]
                if batch_code.isdigit():
                    yr = int(batch_code)
                    start_yr = 2000 + yr
                    duration = 4
                    if any(pg in degree.upper() for pg in ['M.E.', 'M.TECH', 'MBA', 'MCA']):
                        duration = 2
                    end_yr = start_yr + duration
                    calculated_batch = f"{start_yr}-{end_yr}"

            branch_au_code = ''
            if len(reg_no) >= 9:
                branch_au_code = reg_no[6:9]

            # 1. Fast regex text-based extraction (<1ms per page)
            extracted_subjects = extract_subjects_from_page_text(raw_text)

            # 2. Fallback to vector table extraction only if text extraction yielded no subjects
            if not extracted_subjects:
                tables = page.extract_tables() or []
                for tbl in tables:
                    for row in tbl:
                        if not row or len(row) < 2:
                            continue
                        cleaned_row = [clean_str(c) for c in row]

                        joined_low = ' '.join(cleaned_row).lower()
                        if 'sem no' in joined_low and 'subject code' in joined_low:
                            continue

                        # Scan all cells for subject code occurrences (handles single & multi-column tables)
                        for col_idx, cell in enumerate(cleaned_row):
                            codes = re.findall(r'\b([A-Z]{2,4}\d[A-Z0-9]{3,7})\b', cell)
                            if codes:
                                sem_cell = cleaned_row[col_idx - 1] if col_idx > 0 else ''
                                title_cell = cleaned_row[col_idx + 1] if col_idx + 1 < len(cleaned_row) else ''
                                row_subjects = parse_subject_triplet(sem_cell, cell, title_cell)
                                extracted_subjects.extend(row_subjects)

            if not extracted_subjects:
                subj_pattern = re.compile(r'^\s*0?([1-8])\s+([A-Z]{2,4}\d[A-Z0-9]{3,7})\s+(.+?)\s*$', re.MULTILINE)
                for sm in subj_pattern.finditer(raw_text):
                    code = sm.group(2).strip()
                    title = clean_subject_title(sm.group(3).strip())
                    extracted_subjects.append({
                        'semester': int(sm.group(1)),
                        'subject_code': code,
                        'subject_title': title
                    })

            unique_subjects = []
            seen_subjs = set()
            for s in extracted_subjects:
                if s['subject_code'] not in seen_subjs:
                    seen_subjs.add(s['subject_code'])
                    unique_subjects.append(s)

            student_record = {
                'page': page_num,
                'register_no': reg_no,
                'student_name': cand_name,
                'dob': dob,
                'degree': degree,
                'branch': branch,
                'branch_au_code': branch_au_code,
                'degree_branch': deg_branch,
                'regulations': regulations,
                'college': college,
                'exam_title': exam_title,
                'batch_digit': batch_code,
                'calculated_batch': calculated_batch,
                'subjects': unique_subjects
            }

            if reg_no in seen_reg_nos:
                for existing in students:
                    if existing['register_no'] == reg_no:
                        existing_codes = {s['subject_code'] for s in existing['subjects']}
                        for s in unique_subjects:
                            if s['subject_code'] not in existing_codes:
                                existing['subjects'].append(s)
                        break
            else:
                seen_reg_nos.add(reg_no)
                students.append(student_record)

    return students


def ensure_university_exam_created(exam_name_str):
    """
    Ensure ExamType ('University Exam') and Exam ('NOV/DEC-26') exist in database.
    Directly routes to unified ensure_university_exam_code to prevent duplicate exams.
    """
    return ensure_university_exam_code(exam_name_str)


class UniversityRegistrationPreviewViewSet(viewsets.ViewSet):
    """
    Handles Preview, Matching, Verification and Quick-add for Anna University
    Registration Preview PDFs. Supports Inter College (internal) and Outer College (outer_student).
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @action(detail=False, methods=['post'], url_path='preview')
    def preview_pdf(self, request):
        files = request.FILES.getlist('files')
        if not files:
            files = request.FILES.getlist('file')
        if not files:
            f = request.FILES.get('file')
            if f:
                files = [f]

        if not files:
            return Response({'error': 'No file uploaded. Please upload one or more Anna University Registration Preview PDFs.'},
                            status=status.HTTP_400_BAD_REQUEST)

        invalid_files = [f.name for f in files if not f.name.lower().endswith('.pdf')]
        if invalid_files:
            return Response({'error': f"Only PDF files are accepted. Invalid: {', '.join(invalid_files)}"},
                            status=status.HTTP_400_BAD_REQUEST)

        college_type = request.data.get('college_type', 'INTER')

        raw_candidates = []
        file_names = []
        parsed_file_stats = []
        parse_errors = []
        seen_reg_map = {}  # reg_no -> index in raw_candidates

        for file_obj in files:
            file_names.append(file_obj.name)
            try:
                file_bytes = file_obj.read()
                file_candidates = parse_anna_univ_reg_preview_pdf(file_bytes)
                count = 0
                for cand in file_candidates:
                    cand['source_file'] = file_obj.name
                    reg = cand.get('register_no')
                    if reg and reg in seen_reg_map:
                        # Candidate appears in multiple sheets (e.g. arrears or multiple semesters)
                        existing_cand = raw_candidates[seen_reg_map[reg]]
                        if not isinstance(existing_cand.get('source_files'), list):
                            existing_cand['source_files'] = [existing_cand.get('source_file')]
                        if file_obj.name not in existing_cand['source_files']:
                            existing_cand['source_files'].append(file_obj.name)

                        existing_codes = {s['subject_code'].lower() for s in existing_cand.get('subjects', [])}
                        for new_s in cand.get('subjects', []):
                            if new_s['subject_code'].lower() not in existing_codes:
                                existing_cand['subjects'].append(new_s)
                                existing_codes.add(new_s['subject_code'].lower())
                    else:
                        cand['source_files'] = [file_obj.name]
                        if reg:
                            seen_reg_map[reg] = len(raw_candidates)
                        raw_candidates.append(cand)
                    count += 1
                parsed_file_stats.append({'name': file_obj.name, 'candidates': count})
            except ImportError as e:
                return Response({'error': str(e)}, status=status.HTTP_501_NOT_IMPLEMENTED)
            except Exception as e:
                parse_errors.append(f"{file_obj.name}: {str(e)}")

        if not raw_candidates:
            err_msg = 'No candidate registration data found in the uploaded PDF(s).'
            if parse_errors:
                err_msg += f" (Errors: {'; '.join(parse_errors)})"
            return Response({'error': err_msg}, status=status.HTTP_400_BAD_REQUEST)

        # 0. Automatically record/sync the University Exam in the database (exams & exam_type tables)
        detected_exam_title = ''
        for cand in raw_candidates:
            if cand.get('exam_title'):
                detected_exam_title = cand['exam_title']
                break

        db_exam_info = None
        if detected_exam_title:
            db_exam_info = ensure_university_exam_created(detected_exam_title)

        # Preload DB master lookups
        all_departments = list(Department.objects.filter(is_active=True).values('id', 'department_code', 'department_name', 'short_name', 'program_id'))
        all_programs = list(Program.objects.all().values('id', 'program_name', 'program_level', 'duration'))
        all_batches = list(Batch.objects.all().values('id', 'department_id', 'batch', 'is_active'))
        active_batch_set = set((b['department_id'], str(b['batch']).strip().lower()) for b in all_batches if b.get('is_active'))
        all_regulations = list(Regulation.objects.filter(is_active=True).values('id', 'regulation_code', 'effective_from_year'))
        all_sections = list(Section.objects.all().values('id', 'department_id', 'sections'))

        def match_department(branch_name, au_code, degree='B.E.'):
            b_low = branch_name.lower() if branch_name else ''

            # 1. Exact match by AU branch code (e.g. '104' for B.E. CSE, '225' for AGRI, '114' for MECH)
            if au_code:
                for d in all_departments:
                    d_c = str(d.get('department_code') or '').strip().lower()
                    if d_c and d_c == str(au_code).strip().lower():
                        return d

            # 2. Strict match by department name + program level (do NOT match UG B.E. candidate to PG M.E. 405 department!)
            cand_is_ug = any(p in degree.upper() for p in ['B.E.', 'B.TECH'])

            for d in all_departments:
                d_name = (d.get('department_name') or '').lower()
                d_prog_id = d.get('program_id')
                prog_obj = next((p for p in all_programs if p['id'] == d_prog_id), None)
                prog_level = (prog_obj['program_level'] if prog_obj else 'UG').upper()

                # Program level must match (UG vs PG)
                is_ug_dept = (prog_level == 'UG')
                if cand_is_ug != is_ug_dept:
                    continue

                # Check if codes conflict (e.g. candidate AU code is 104 but department code is 405)
                if au_code and d.get('department_code'):
                    d_c = str(d['department_code']).strip().lower()
                    if d_c and d_c != str(au_code).strip().lower():
                        continue

                if b_low in d_name or d_name in b_low:
                    return d

            return None

        # 1. Analyze Students - check both internal students and outer students
        reg_numbers = [c['register_no'] for c in raw_candidates if c.get('register_no')]

        existing_inter = Student.objects.filter(register_number__in=reg_numbers).select_related('department', 'batch')
        inter_map = {s.register_number: s for s in existing_inter}

        existing_outer = OuterStudent.objects.filter(register_number__in=reg_numbers).select_related('department', 'batch', 'program', 'regulation')
        outer_map = {s.register_number: s for s in existing_outer}

        students_analysis = []
        missing_students = []

        inst_college_code = get_institutional_college_code()

        for cand in raw_candidates:
            r_no = cand['register_no']
            s_name = cand['student_name']
            calc_batch = cand['calculated_batch']
            matched_dept = match_department(cand['branch'], cand.get('branch_au_code'), cand.get('degree', 'B.E.'))

            matched_batch = None
            is_batch_active = False
            if matched_dept and calc_batch:
                d_id = matched_dept['id']
                b_clean = calc_batch.strip().lower()
                is_batch_active = (d_id, b_clean) in active_batch_set
                for b in all_batches:
                    if b['department_id'] == d_id and str(b['batch']).strip().lower() == b_clean:
                        matched_batch = b
                        if b.get('is_active'):
                            is_batch_active = True
                        break

            matched_prog = None
            if matched_dept and matched_dept.get('program_id'):
                matched_prog = next((p for p in all_programs if p['id'] == matched_dept['program_id']), None)
            if not matched_prog and all_programs:
                # Try matching by degree
                deg_low = cand['degree'].lower()
                for p in all_programs:
                    if deg_low in p['program_name'].lower() or p['program_name'].lower() in deg_low:
                        matched_prog = p
                        break
            if not matched_prog and all_programs:
                matched_prog = all_programs[0]

            db_inter = inter_map.get(r_no)
            db_outer = outer_map.get(r_no)
            is_found = (db_inter is not None) or (db_outer is not None)

            # Auto-detect college type based on matching first 4 digits with institutional college code (5132)
            clean_reg = (r_no or '').replace(' ', '')
            is_own_college = clean_reg.startswith(inst_college_code) if (clean_reg and len(clean_reg) >= 4) else True

            if db_inter:
                found_college_type = 'INTER'
            elif db_outer:
                found_college_type = 'OUTER'
            else:
                found_college_type = 'INTER' if is_own_college else 'OUTER'

            db_student = db_inter or db_outer

            # Gather available batches specifically for the matched department
            dept_batches = [b for b in all_batches if matched_dept and b['department_id'] == matched_dept['id']]

            student_item = {
                'register_no': r_no,
                'student_name': s_name,
                'degree': cand['degree'],
                'branch': cand['branch'],
                'dob': cand['dob'],
                'regulations': cand['regulations'],
                'batch_digit': cand['batch_digit'],
                'calculated_batch': calc_batch,
                'is_found': is_found,
                'is_department_found': matched_dept is not None,
                'college_type': found_college_type,
                'is_own_college': is_own_college,
                'institutional_college_code': inst_college_code,
                'reg_college_code': clean_reg[:4] if len(clean_reg) >= 4 else '',
                'db_student_id': db_student.id if is_found else None,
                'db_student_name': db_student.student_name if is_found else '',
                'db_department_name': db_student.department.department_name if is_found and db_student.department else '',
                'db_batch_name': db_student.batch.batch if is_found and db_student.batch else '',
                'suggested_department_id': matched_dept['id'] if matched_dept else None,
                'suggested_department_name': matched_dept['department_name'] if matched_dept else cand['branch'],
                'suggested_department_code': matched_dept['department_code'] if matched_dept else cand.get('branch_au_code', ''),
                'suggested_short_name': matched_dept.get('short_name') if matched_dept else derive_short_name(cand['branch']),
                'suggested_program_id': matched_prog['id'] if matched_prog else None,
                'suggested_program_name': matched_prog['program_name'] if matched_prog else 'Under Graduate',
                'suggested_batch_id': matched_batch['id'] if matched_batch else None,
                'suggested_batch_name': calc_batch,
                'is_batch_active': is_batch_active,
                'batch_status': 'ACTIVE' if is_batch_active else ('INACTIVE' if matched_batch else 'NOT_FOUND'),
                'department_batches': dept_batches,
                'subjects_count': len(cand['subjects']),
                'subjects': cand['subjects'],
                'source_file': cand.get('source_file') or (file_names[0] if file_names else ''),
                'source_files': cand.get('source_files') or ([file_names[0]] if file_names else []),
            }

            students_analysis.append(student_item)
            if not is_found:
                missing_students.append(student_item)

        # 2. Analyze Subjects
        unique_subjects_dict = {}
        for cand in raw_candidates:
            matched_dept = match_department(cand['branch'], cand.get('branch_au_code'), cand.get('degree', 'B.E.'))
            dept_id = matched_dept['id'] if matched_dept else None
            reg_code = cand['regulations'] or '2025'
            src_f = cand.get('source_file') or (file_names[0] if file_names else '')

            for s in cand['subjects']:
                code = s['subject_code']
                key = f"{dept_id}__{code}"
                if key not in unique_subjects_dict:
                    unique_subjects_dict[key] = {
                        'subject_code': code,
                        'subject_title': s['subject_title'],
                        'semester': s['semester'],
                        'department_id': dept_id,
                        'department_name': matched_dept['department_name'] if matched_dept else cand['branch'],
                        'regulation_code': reg_code,
                        'student_count': 0,
                        'source_files': set(),
                    }
                unique_subjects_dict[key]['student_count'] += 1
                if src_f:
                    unique_subjects_dict[key]['source_files'].add(src_f)

        all_subject_codes = [s['subject_code'] for s in unique_subjects_dict.values()]
        existing_subjects = Subject.objects.filter(
            subject_code__in=all_subject_codes,
            is_active=True
        ).select_related('department', 'regulation')

        db_subject_map = {}
        for sub in existing_subjects:
            c = (sub.subject_code or '').lower()
            if c not in db_subject_map:
                db_subject_map[c] = []
            db_subject_map[c].append(sub)

        subjects_analysis = []
        missing_subjects = []

        for key, s_item in unique_subjects_dict.items():
            code_low = s_item['subject_code'].lower()
            candidates_in_db = db_subject_map.get(code_low, [])

            matched_sub = None
            if s_item['department_id']:
                for c_sub in candidates_in_db:
                    if c_sub.department_id == s_item['department_id']:
                        matched_sub = c_sub
                        break
            if not matched_sub and candidates_in_db:
                matched_sub = candidates_in_db[0]

            is_found = matched_sub is not None

            title_low = (s_item['subject_title'] or '').lower()
            is_lab = any(w in title_low for w in ['lab', 'laboratory', 'practical', 'project', 'seminar', 'workshop']) or code_low.endswith('8') or code_low.endswith('9')
            is_theory = not is_lab

            subj_item = {
                'key': key,
                'subject_code': s_item['subject_code'],
                'subject_title': s_item['subject_title'],
                'semester': s_item['semester'],
                'department_id': s_item['department_id'],
                'department_name': s_item['department_name'],
                'regulation_code': s_item['regulation_code'] or '2025',
                'student_count': s_item['student_count'],
                'is_found': is_found,
                'db_subject_id': matched_sub.id if is_found else None,
                'db_subject_name': matched_sub.subject_name if is_found else '',
                'db_subject_code': matched_sub.subject_code if is_found else '',
                'credits': 0.0,
                'is_theory': is_theory,
                'is_lab': is_lab,
                'source_files': sorted(list(s_item.get('source_files', []))),
            }
            subjects_analysis.append(subj_item)
            if not is_found:
                missing_subjects.append(subj_item)

        # 3. Analyze Departments from sheet
        detected_departments = {}
        for cand in raw_candidates:
            b_name = cand['branch'] or 'Engineering'
            au_code = cand.get('branch_au_code', '')
            deg_val = cand.get('degree', 'B.E.')
            m_dept = match_department(b_name, au_code, deg_val)
            key = f"{b_name}__{au_code}"
            if key not in detected_departments:
                deg_clean = deg_val.replace('.', '').strip().lower()
                sugg_prog = None
                for p in all_programs:
                    p_clean = p['program_name'].replace('.', '').strip().lower()
                    if deg_clean == p_clean or deg_clean in p_clean or p_clean in deg_clean:
                        sugg_prog = p
                        break
                if not sugg_prog and all_programs:
                    sugg_prog = all_programs[0]

                detected_departments[key] = {
                    'branch_name': b_name,
                    'branch_au_code': au_code,
                    'department_name': b_name,
                    'department_code': au_code,
                    'degree': deg_val,
                    'is_found': m_dept is not None,
                    'matched_department_id': m_dept['id'] if m_dept else None,
                    'matched_department_name': m_dept['department_name'] if m_dept else '',
                    'matched_department_code': m_dept['department_code'] if m_dept else '',
                    'suggested_program_id': sugg_prog['id'] if sugg_prog else None,
                    'suggested_program_name': sugg_prog['program_name'] if sugg_prog else '',
                    'suggested_short_name': derive_short_name(b_name),
                }

        departments_analysis = list(detected_departments.values())
        missing_departments = [d for d in departments_analysis if not d['is_found']]

        summary = {
            'file_name': file_names[0] if len(file_names) == 1 else f"{len(file_names)} PDFs Combined",
            'total_files': len(files),
            'file_names': file_names,
            'file_stats': parsed_file_stats,
            'college': '',
            'college_code': inst_college_code,
            'institutional_college_code': inst_college_code,
            'exam_title': detected_exam_title or (raw_candidates[0]['exam_title'] if raw_candidates else ''),
            'exam_info': db_exam_info,
            'college_type': college_type,
            'total_candidates': len(students_analysis),
            'students_found': len(students_analysis) - len(missing_students),
            'students_not_found': len(missing_students),
            'inter_candidates_count': sum(1 for c in students_analysis if c.get('college_type') == 'INTER'),
            'outer_candidates_count': sum(1 for c in students_analysis if c.get('college_type') == 'OUTER'),
            'total_subjects': len(subjects_analysis),
            'subjects_found': len(subjects_analysis) - len(missing_subjects),
            'subjects_not_found': len(missing_subjects),
            'total_departments': len(departments_analysis),
            'departments_found': len(departments_analysis) - len(missing_departments),
            'departments_not_found': len(missing_departments),
            'missing_departments': missing_departments,
        }

        return Response({
            'summary': summary,
            'students': students_analysis,
            'missing_students': missing_students,
            'subjects': subjects_analysis,
            'missing_subjects': missing_subjects,
            'departments': departments_analysis,
            'missing_departments': missing_departments,
            'available_departments': all_departments,
            'available_programs': all_programs,
            'available_batches': all_batches,
            'available_regulations': all_regulations,
            'available_sections': all_sections,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-student')
    def quick_add_student(self, request):
        """
        Add a single student. If Program, Department, or Batch does not exist,
        creates them automatically in their respective tables.
        Stores into 'outer_student' table if college_type == 'OUTER', else 'students' table.
        """
        reg_no = clean_str(request.data.get('register_number') or request.data.get('register_no'))
        s_name = clean_str(request.data.get('student_name'))
        dept_id = request.data.get('department_id')
        dept_name = clean_str(request.data.get('department_name'))
        dept_code = clean_str(request.data.get('department_code'))
        prog_id = request.data.get('program_id')
        prog_name = clean_str(request.data.get('program_name'))
        batch_name = clean_str(request.data.get('batch_name') or request.data.get('batch'))
        batch_id = request.data.get('batch_id')
        section_name = clean_str(request.data.get('section_name') or request.data.get('section') or 'Section: A')
        section_id = request.data.get('section_id')
        reg_code = clean_str(request.data.get('regulation_code', '2021') or '2021')
        college_type = clean_str(request.data.get('college_type') or '').upper()

        if not reg_no:
            return Response({'error': 'Register number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Auto-match college code if college_type not explicitly given
        if not college_type or college_type not in ('INTER', 'OUTER'):
            inst_code = get_institutional_college_code()
            clean_reg = reg_no.replace(' ', '')
            college_type = 'INTER' if (clean_reg and len(clean_reg) >= 4 and clean_reg.startswith(inst_code)) else 'OUTER'

        with transaction.atomic():
            # 1. Resolve / Create Program if missing
            program = None
            if prog_id and str(prog_id).isdigit():
                program = Program.objects.filter(id=int(prog_id)).first()
            if not program and prog_name:
                program, _ = Program.objects.get_or_create(
                    program_name=prog_name,
                    defaults={'program_level': 'UG', 'duration': 4}
                )
            if not program:
                program = Program.objects.first()
                if not program:
                    program = Program.objects.create(program_name='Under Graduate', program_level='UG', duration=4)

            # 2. Resolve / Create Department if missing
            dept = None
            if dept_id and str(dept_id).isdigit():
                dept = Department.objects.filter(id=int(dept_id)).first()
            if not dept and dept_code:
                dept = Department.objects.filter(department_code__iexact=dept_code).first()
            if not dept and dept_name:
                dept = Department.objects.filter(department_name__iexact=dept_name).first()
            if not dept and dept_name:
                dept, _ = Department.objects.get_or_create(
                    department_name=dept_name,
                    defaults={
                        'department_code': dept_code or dept_name[:10].upper(),
                        'short_name': dept_code or dept_name[:10].upper(),
                        'program': program,
                        'is_active': False
                    }
                )
            if not dept:
                dept = Department.objects.first()

            # 3. Resolve / Create Batch if missing (Auto-created batches default to inactive)
            batch = None
            if batch_id and str(batch_id).isdigit():
                batch = Batch.objects.filter(id=int(batch_id)).first()
            if not batch and batch_name and dept:
                batch, _ = Batch.objects.get_or_create(department=dept, batch=batch_name, defaults={'is_active': False})
            if not batch and dept and len(reg_no) >= 6:
                digit = reg_no[4:6]
                if digit.isdigit():
                    yr = int(digit)
                    est_batch = f"{2000 + yr}-{2000 + yr + 4}"
                    batch, _ = Batch.objects.get_or_create(department=dept, batch=est_batch, defaults={'is_active': False})
            if not batch and dept:
                batch = Batch.objects.filter(department=dept).first()
                if not batch:
                    batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR', defaults={'is_active': False})

            # 4. Resolve / Create Regulation if missing
            regulation = None
            if reg_code:
                regulation, _ = Regulation.objects.get_or_create(
                    regulation_code=reg_code,
                    defaults={'effective_from_year': int(reg_code) if reg_code.isdigit() else 2021}
                )

            # 5. Store in outer_student or student table
            if college_type == 'OUTER':
                outer_stud, created = OuterStudent.objects.get_or_create(
                    register_number=reg_no,
                    defaults={
                        'student_name': s_name or reg_no,
                        'program': program,
                        'department': dept,
                        'batch': batch,
                        'regulation': regulation,
                    }
                )
                if not created:
                    updated = False
                    if s_name and not outer_stud.student_name:
                        outer_stud.student_name = s_name; updated = True
                    if dept and not outer_stud.department:
                        outer_stud.department = dept; updated = True
                    if batch and not outer_stud.batch:
                        outer_stud.batch = batch; updated = True
                    if program and not outer_stud.program:
                        outer_stud.program = program; updated = True
                    if regulation and not outer_stud.regulation:
                        outer_stud.regulation = regulation; updated = True
                    if updated:
                        outer_stud.save()

                _bust_preview_caches(['Student', 'OuterStudent', 'Batch', 'Department', 'Program', 'Regulation'])
                _send_realtime_broadcast({
                    'model': 'Student',
                    'action': 'create',
                    'event': 'student_created',
                    'id': outer_stud.id,
                    'register_number': outer_stud.register_number,
                    'is_outer': True
                })

                return Response({
                    'success': True,
                    'college_type': 'OUTER',
                    'table': 'outer_student',
                    'id': outer_stud.id,
                    'register_number': outer_stud.register_number,
                    'student_name': outer_stud.student_name,
                    'department_id': dept.id if dept else None,
                    'department_name': dept.department_name if dept else '',
                    'program_name': program.program_name if program else '',
                    'batch_id': batch.id if batch else None,
                    'batch_name': batch.batch if batch else '',
                    'created': created
                }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

            else:
                status_obj = StudentStatus.objects.filter(status_name__iexact='inactive').first()
                if not status_obj:
                    status_obj = StudentStatus.objects.create(status_name='INACTIVE', is_active=False)

                # Resolve Section for Inter College Student (Default to Section A for this department)
                sec_obj = None
                if dept:
                    target_sec_name = section_name or 'A'
                    clean_sec = target_sec_name.replace('Section:', '').replace('Section', '').strip() or 'A'
                    if section_id and str(section_id).isdigit():
                        sec_obj = Section.objects.filter(id=int(section_id), department=dept).first()
                    # Always prioritize matching Section 'A' for this department
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__iexact='A').first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__iexact='Section: A').first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__iexact=target_sec_name).first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__icontains='A').first()
                    if not sec_obj:
                        sec_obj, _ = Section.objects.get_or_create(department=dept, sections='A')

                audit_user = request.user if request.user and request.user.is_authenticated else None
                student, created = Student.objects.get_or_create(
                    register_number=reg_no,
                    defaults={
                        'student_name': s_name or reg_no,
                        'department': dept,
                        'batch': batch,
                        'section': sec_obj,
                        'status': status_obj,
                        'created_by': audit_user,
                        'updated_by': audit_user,
                    }
                )
                if not created and audit_user and not student.updated_by:
                    student.updated_by = audit_user
                    student.save(update_fields=['updated_by', 'updated_at'])
                if not created:
                    updated = False
                    if s_name and not student.student_name:
                        student.student_name = s_name; updated = True
                    if dept and not student.department:
                        student.department = dept; updated = True
                    if batch and not student.batch:
                        student.batch = batch; updated = True
                    if sec_obj and not student.section:
                        student.section = sec_obj; updated = True
                    if updated:
                        student.save()

                _bust_preview_caches(['Student', 'Batch', 'Department', 'Program', 'Section'])
                _send_realtime_broadcast({
                    'model': 'Student',
                    'action': 'create',
                    'event': 'student_created',
                    'id': student.id,
                    'register_number': student.register_number,
                    'is_outer': False
                })

                return Response({
                    'success': True,
                    'college_type': 'INTER',
                    'student_type': 'Inter College',
                    'id': student.id,
                    'register_number': student.register_number,
                    'student_name': student.student_name,
                    'department_id': dept.id if dept else None,
                    'department_name': dept.department_name if dept else '',
                    'section_name': student.section.sections if student.section else '',
                    'batch_id': batch.id if batch else None,
                    'batch_name': batch.batch if batch else '',
                    'created': created
                }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-all-students')
    def quick_add_all_students(self, request):
        """Add all missing students in bulk, auto-creating Program, Department, Batch if not present."""
        students_data = request.data.get('students', [])
        college_type = clean_str(request.data.get('college_type', 'INTER')).upper()

        if not students_data:
            return Response({'error': 'No students provided to add.'}, status=status.HTTP_400_BAD_REQUEST)

        status_obj = StudentStatus.objects.filter(status_name__iexact='inactive').first()
        if not status_obj:
            status_obj = StudentStatus.objects.create(status_name='INACTIVE', is_active=False)
        
        # 1. Preload master records into memory dictionaries to eliminate 17,000+ repeated SQL queries
        all_depts = list(Department.objects.all())
        dept_by_id = {d.id: d for d in all_depts}
        dept_by_code = {d.department_code.strip().lower(): d for d in all_depts if d.department_code}
        dept_by_name = {d.department_name.strip().lower(): d for d in all_depts if d.department_name}
        default_dept = all_depts[0] if all_depts else None

        all_progs = list(Program.objects.all())
        prog_by_id = {p.id: p for p in all_progs}
        prog_by_name = {p.program_name.strip().lower(): p for p in all_progs if p.program_name}
        default_prog = all_progs[0] if all_progs else None

        all_batches = list(Batch.objects.all())
        batch_cache = {(b.department_id, b.batch.strip().lower()): b for b in all_batches}

        all_regs = list(Regulation.objects.all())
        reg_cache = {r.regulation_code.strip().lower(): r for r in all_regs if r.regulation_code}

        all_sections = list(Section.objects.all())
        section_cache = {}
        for sec in all_sections:
            section_cache.setdefault(sec.department_id, []).append(sec)

        reg_nos = [clean_str(item.get('register_no') or item.get('register_number')) for item in students_data if item.get('register_no') or item.get('register_number')]
        existing_inter_map = {s.register_number: s for s in Student.objects.filter(register_number__in=reg_nos)}
        existing_outer_map = {s.register_number: s for s in OuterStudent.objects.filter(register_number__in=reg_nos)}

        created_count = 0
        added_list = []
        to_create_inter = []
        to_create_outer = []
        to_update_inter = []

        with transaction.atomic():
            for item in students_data:
                reg_no = clean_str(item.get('register_no') or item.get('register_number'))
                s_name = clean_str(item.get('student_name'))
                dept_id = item.get('suggested_department_id') or item.get('department_id')
                dept_name = clean_str(item.get('suggested_department_name') or item.get('branch'))
                dept_code = clean_str(item.get('suggested_department_code') or item.get('branch_au_code'))
                prog_id = item.get('suggested_program_id') or item.get('program_id')
                prog_name = clean_str(item.get('suggested_program_name') or item.get('degree') or 'Under Graduate')
                batch_str = clean_str(item.get('calculated_batch') or item.get('batch_name'))
                reg_code = clean_str(item.get('regulations') or item.get('regulation_code') or '2021')

                if not reg_no:
                    continue

                # Program resolution in memory
                program = None
                if prog_id and str(prog_id).isdigit():
                    program = prog_by_id.get(int(prog_id))
                if not program and prog_name:
                    program = prog_by_name.get(prog_name.lower())
                    if not program:
                        program, _ = Program.objects.get_or_create(program_name=prog_name, defaults={'program_level': 'UG', 'duration': 4})
                        prog_by_id[program.id] = program
                        prog_by_name[prog_name.lower()] = program
                if not program:
                    program = default_prog

                # Department resolution in memory
                dept = None
                if dept_id and str(dept_id).isdigit():
                    dept = dept_by_id.get(int(dept_id))
                if not dept and dept_code:
                    dept = dept_by_code.get(dept_code.lower())
                if not dept and dept_name:
                    dept = dept_by_name.get(dept_name.lower())
                if not dept and dept_name:
                    dept, _ = Department.objects.get_or_create(
                        department_name=dept_name,
                        defaults={
                            'department_code': dept_code or dept_name[:10].upper(),
                            'short_name': dept_code or dept_name[:10].upper(),
                            'program': program,
                            'is_active': False
                        }
                    )
                    dept_by_id[dept.id] = dept
                    if dept.department_code:
                        dept_by_code[dept.department_code.lower()] = dept
                    dept_by_name[dept.department_name.lower()] = dept
                if not dept:
                    dept = default_dept

                # Batch resolution in memory
                batch = None
                if not batch_str and len(reg_no) >= 6 and reg_no[4:6].isdigit():
                    yr = int(reg_no[4:6])
                    batch_str = f"{2000 + yr}-{2000 + yr + 4}"

                if batch_str and dept:
                    b_key = (dept.id, batch_str.lower())
                    batch = batch_cache.get(b_key)
                    if not batch:
                        batch, _ = Batch.objects.get_or_create(department=dept, batch=batch_str, defaults={'is_active': False})
                        batch_cache[b_key] = batch
                elif dept:
                    for (d_id, b_name), b_obj in batch_cache.items():
                        if d_id == dept.id:
                            batch = b_obj
                            break
                    if not batch:
                        batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR', defaults={'is_active': False})
                        batch_cache[(dept.id, 'regular')] = batch

                # Regulation resolution in memory
                regulation = None
                if reg_code:
                    reg_key = reg_code.lower()
                    regulation = reg_cache.get(reg_key)
                    if not regulation:
                        regulation, _ = Regulation.objects.get_or_create(
                            regulation_code=reg_code,
                            defaults={'effective_from_year': int(reg_code) if reg_code.isdigit() else 2021}
                        )
                        reg_cache[reg_key] = regulation

                item_college_type = clean_str(item.get('college_type') or '').upper()
                if not item_college_type or item_college_type not in ('INTER', 'OUTER'):
                    inst_code = get_institutional_college_code()
                    clean_r = reg_no.replace(' ', '')
                    if clean_r and len(clean_r) >= 4 and not clean_r.startswith(inst_code):
                        item_college_type = 'OUTER'
                    else:
                        item_college_type = college_type or 'INTER'

                if item_college_type == 'OUTER':
                    outer_stud = existing_outer_map.get(reg_no)
                    if outer_stud:
                        added_list.append({
                            'id': outer_stud.id,
                            'register_number': outer_stud.register_number,
                            'student_name': outer_stud.student_name,
                            'college_type': 'OUTER',
                            'table': 'outer_student',
                            'created': False
                        })
                    else:
                        outer_stud = OuterStudent(
                            register_number=reg_no,
                            student_name=s_name or reg_no,
                            program=program,
                            department=dept,
                            batch=batch,
                            regulation=regulation,
                        )
                        existing_outer_map[reg_no] = outer_stud
                        to_create_outer.append(outer_stud)
                        created_count += 1
                else:
                    # Section resolution in memory
                    sec_name = clean_str(item.get('section_name') or item.get('section') or 'Section: A')
                    sec_id = item.get('section_id')
                    sec_obj = None

                    if dept:
                        dept_secs = section_cache.get(dept.id, [])
                        if sec_id and str(sec_id).isdigit():
                            sec_obj = next((s for s in dept_secs if s.id == int(sec_id)), None)

                        if not sec_obj:
                            clean_sec = sec_name.replace('Section:', '').replace('Section', '').strip() or 'A'
                            # Default strictly to Section A for this department
                            sec_obj = next((s for s in dept_secs if s.sections.strip().lower() == 'a'), None)
                            if not sec_obj:
                                sec_obj = next((s for s in dept_secs if s.sections.strip().lower() == 'section: a'), None)
                            if not sec_obj:
                                for s in dept_secs:
                                    s_low = s.sections.lower()
                                    if s_low == sec_name.lower() or s_low == clean_sec.lower():
                                        sec_obj = s
                                        break
                            if not sec_obj:
                                for s in dept_secs:
                                    if 'a' in s.sections.lower():
                                        sec_obj = s
                                        break
                            if not sec_obj and dept_secs:
                                sec_obj = dept_secs[0]

                            if not sec_obj:
                                sec_obj, _ = Section.objects.get_or_create(department=dept, sections='A')
                                section_cache.setdefault(dept.id, []).append(sec_obj)

                    student = existing_inter_map.get(reg_no)
                    if student:
                        if sec_obj and not student.section_id:
                            student.section = sec_obj
                            to_update_inter.append(student)
                        added_list.append({
                            'id': student.id,
                            'register_number': student.register_number,
                            'student_name': student.student_name,
                            'college_type': 'INTER',
                            'student_type': 'Inter College',
                            'section_name': student.section.sections if student.section else '',
                            'created': False
                        })
                    else:
                        student = Student(
                            register_number=reg_no,
                            student_name=s_name or reg_no,
                            department=dept,
                            batch=batch,
                            section=sec_obj,
                            status=status_obj
                        )
                        existing_inter_map[reg_no] = student
                        to_create_inter.append(student)
                        created_count += 1

            if to_create_inter:
                Student.objects.bulk_create(to_create_inter, batch_size=500)
                for s in to_create_inter:
                    added_list.append({
                        'id': s.id,
                        'register_number': s.register_number,
                        'student_name': s.student_name,
                        'college_type': 'INTER',
                        'student_type': 'Inter College',
                        'section_name': s.section.sections if s.section else '',
                        'created': True
                    })

            if to_create_outer:
                OuterStudent.objects.bulk_create(to_create_outer, batch_size=500)
                for s in to_create_outer:
                    added_list.append({
                        'id': s.id,
                        'register_number': s.register_number,
                        'student_name': s.student_name,
                        'college_type': 'OUTER',
                        'table': 'outer_student',
                        'created': True
                    })

            if to_update_inter:
                Student.objects.bulk_update(to_update_inter, ['section'], batch_size=500)

        inter_count = sum(1 for s in added_list if s.get('college_type') == 'INTER')
        outer_count = sum(1 for s in added_list if s.get('college_type') == 'OUTER')

        _bust_preview_caches(['Student', 'OuterStudent', 'Batch', 'Department', 'Program', 'Regulation', 'Section'])
        _send_realtime_broadcast({
            'model': 'Student',
            'action': 'bulk_create',
            'event': 'student_created',
            'count': created_count,
            'inter_count': inter_count,
            'outer_count': outer_count
        })
        _send_realtime_broadcast({'model': 'Batch', 'action': 'create', 'event': 'batch_created'})

        return Response({
            'success': True,
            'message': f"Successfully processed {len(added_list)} students ({inter_count} Inter College, {outer_count} Outer College).",
            'created_count': created_count,
            'inter_count': inter_count,
            'outer_count': outer_count,
            'students': added_list
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-subject')
    def quick_add_subject(self, request):
        """Add a single missing subject."""
        s_code = clean_str(request.data.get('subject_code'))
        s_name = clean_str(request.data.get('subject_name') or request.data.get('subject_title'))
        dept_id = request.data.get('department_id')
        sem_num = int(request.data.get('semester', 1) or 1)
        reg_code = clean_str(request.data.get('regulation_code') or '2025')
        try:
            credits = float(request.data.get('credits', 0.0) or 0.0)
        except (ValueError, TypeError):
            credits = 0.0
        is_lab = bool(request.data.get('is_lab', False))
        is_theory = bool(request.data.get('is_theory', not is_lab))

        if not s_code:
            return Response({'error': 'Subject code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        dept = Department.objects.filter(id=dept_id).first() if dept_id else Department.objects.first()
        if not dept:
            return Response({'error': 'Department is required.'}, status=status.HTTP_400_BAD_REQUEST)

        reg, _ = Regulation.objects.get_or_create(
            regulation_code=reg_code,
            defaults={'effective_from_year': int(reg_code) if reg_code.isdigit() else 2025}
        )

        sem, _ = Semester.objects.get_or_create(
            department=dept,
            semester_number=sem_num,
            defaults={'semester_name': f"Semester {sem_num}"}
        )

        audit_user = request.user if request.user and request.user.is_authenticated else None
        subj, created = Subject.objects.get_or_create(
            subject_code=s_code,
            department=dept,
            regulation=reg,
            semester=sem,
            defaults={
                'subject_name': s_name or s_code,
                'credits': credits,
                'is_theory': is_theory,
                'is_lab': is_lab,
                'is_active': False,
                'created_by': audit_user,
                'updated_by': audit_user,
            }
        )
        if not created and audit_user and not subj.updated_by:
            subj.updated_by = audit_user
            subj.save(update_fields=['updated_by', 'updated_at'])
        if not created:
            updated = False
            if s_name and subj.subject_name != s_name:
                subj.subject_name = s_name; updated = True
            if credits != subj.credits:
                subj.credits = credits; updated = True
            if is_theory != subj.is_theory:
                subj.is_theory = is_theory; updated = True
            if is_lab != subj.is_lab:
                subj.is_lab = is_lab; updated = True
            if updated:
                subj.save()

        _bust_preview_caches(['Subject', 'Semester', 'Regulation', 'Department'])
        _send_realtime_broadcast({
            'model': 'Subject',
            'action': 'create',
            'event': 'subject_created',
            'id': subj.id,
            'subject_code': subj.subject_code
        })

        return Response({
            'success': True,
            'id': subj.id,
            'subject_code': subj.subject_code,
            'subject_name': subj.subject_name,
            'department_id': dept.id,
            'semester': sem_num,
            'regulation_code': reg_code,
            'credits': subj.credits,
            'is_theory': subj.is_theory,
            'is_lab': subj.is_lab,
            'created': created
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-all-subjects')
    def quick_add_all_subjects(self, request):
        """Add all missing subjects in bulk."""
        subjects_data = request.data.get('subjects', [])
        if not subjects_data:
            return Response({'error': 'No subjects provided.'}, status=status.HTTP_400_BAD_REQUEST)

        # 1. Preload masters into memory dictionaries to avoid repeated SQL queries on 400+ subjects
        all_depts = {d.id: d for d in Department.objects.all()}
        default_dept = Department.objects.first()

        all_regs = {r.regulation_code.strip().lower(): r for r in Regulation.objects.all() if r.regulation_code}
        all_sems = {(s.department_id, s.semester_number): s for s in Semester.objects.all()}

        s_codes = [clean_str(item.get('subject_code')) for item in subjects_data if item.get('subject_code')]
        existing_subjects = {(s.department_id, s.subject_code.strip().lower()): s for s in Subject.objects.filter(subject_code__in=s_codes)}

        created_count = 0
        added_list = []
        to_create_subjects = []
        to_update_subjects = []

        with transaction.atomic():
            for item in subjects_data:
                s_code = clean_str(item.get('subject_code'))
                s_name = clean_str(item.get('subject_title') or item.get('subject_name'))
                dept_id = item.get('department_id')
                sem_num = int(item.get('semester', 1) or 1)
                reg_code = clean_str(item.get('regulation_code') or '2025')
                try:
                    credits = float(item.get('credits', 0.0) or 0.0)
                except (ValueError, TypeError):
                    credits = 0.0
                is_lab = bool(item.get('is_lab', False))
                is_theory = bool(item.get('is_theory', not is_lab))

                if not s_code:
                    continue

                dept = all_depts.get(dept_id) if dept_id else default_dept
                if not dept:
                    continue

                # Regulation in memory
                reg_key = reg_code.lower()
                reg = all_regs.get(reg_key)
                if not reg:
                    reg, _ = Regulation.objects.get_or_create(
                        regulation_code=reg_code,
                        defaults={'effective_from_year': int(reg_code) if reg_code.isdigit() else 2025}
                    )
                    all_regs[reg_key] = reg

                # Semester in memory
                sem_key = (dept.id, sem_num)
                sem = all_sems.get(sem_key)
                if not sem:
                    sem, _ = Semester.objects.get_or_create(
                        department=dept,
                        semester_number=sem_num,
                        defaults={'semester_name': f"Semester {sem_num}"}
                    )
                    all_sems[sem_key] = sem

                # Subject in memory
                subj_key = (dept.id, s_code.lower())
                subj = existing_subjects.get(subj_key)
                if subj:
                    created = False
                    updated = False
                    if s_name and subj.subject_name != s_name:
                        subj.subject_name = s_name; updated = True
                    if credits != subj.credits:
                        subj.credits = credits; updated = True
                    if is_theory != subj.is_theory:
                        subj.is_theory = is_theory; updated = True
                    if is_lab != subj.is_lab:
                        subj.is_lab = is_lab; updated = True
                    if updated:
                        to_update_subjects.append(subj)
                    added_list.append({
                        'id': subj.id,
                        'subject_code': subj.subject_code,
                        'subject_name': subj.subject_name,
                        'credits': subj.credits,
                        'regulation_code': reg_code,
                        'created': False
                    })
                else:
                    subj = Subject(
                        subject_code=s_code,
                        department=dept,
                        regulation=reg,
                        semester=sem,
                        subject_name=s_name or s_code,
                        credits=credits,
                        is_theory=is_theory,
                        is_lab=is_lab,
                        is_active=False,
                    )
                    existing_subjects[subj_key] = subj
                    to_create_subjects.append(subj)
                    created_count += 1

            if to_create_subjects:
                Subject.objects.bulk_create(to_create_subjects, batch_size=500)
                for subj in to_create_subjects:
                    added_list.append({
                        'id': subj.id,
                        'subject_code': subj.subject_code,
                        'subject_name': subj.subject_name,
                        'credits': subj.credits,
                        'regulation_code': subj.regulation.regulation_code if subj.regulation else '2025',
                        'created': True
                    })

            if to_update_subjects:
                Subject.objects.bulk_update(to_update_subjects, ['subject_name', 'credits', 'is_theory', 'is_lab'], batch_size=500)

        _bust_preview_caches(['Subject', 'Semester', 'Regulation', 'Department'])
        _send_realtime_broadcast({
            'model': 'Subject',
            'action': 'bulk_create',
            'event': 'subject_created',
            'count': created_count
        })

        return Response({
            'success': True,
            'message': f"Successfully processed {len(added_list)} subjects ({created_count} newly added).",
            'created_count': created_count,
            'subjects': added_list
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='quick-add-department')
    def quick_add_department(self, request):
        """
        Add a new Department into the `departments` table.
        Prompted fields:
        - Department Name (e.g. 'Computer Science and Engineering')
        - Department Code (e.g. '104')
        - Short Name (e.g. 'CSE')
        - Associated Program (e.g. 'B.E' / 'B.E (UG)')
        """
        dept_name = clean_str(request.data.get('department_name'))
        dept_code = clean_str(request.data.get('department_code'))
        short_name = clean_str(request.data.get('short_name'))
        prog_id = request.data.get('program_id')
        prog_name = clean_str(request.data.get('program_name'))
        degree = clean_str(request.data.get('degree'))

        if not dept_name:
            return Response({'error': 'Department Name is required.'}, status=status.HTTP_400_BAD_REQUEST)
        if not dept_code:
            return Response({'error': 'Department Code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve Program
        program = None
        if prog_id and str(prog_id).isdigit():
            program = Program.objects.filter(id=int(prog_id)).first()
        if not program and prog_name:
            program = Program.objects.filter(program_name__iexact=prog_name).first()
        if not program and degree:
            deg_clean = degree.replace('.', '').strip().lower()
            for p in Program.objects.all():
                p_clean = p.program_name.replace('.', '').strip().lower()
                if deg_clean == p_clean or deg_clean in p_clean or p_clean in deg_clean:
                    program = p
                    break
        if not program:
            program = Program.objects.first()
            if not program:
                program = Program.objects.create(program_name='Under Graduate', program_level='UG', duration=4)

        if not short_name:
            short_name = derive_short_name(dept_name)

        audit_user = request.user if request.user and request.user.is_authenticated else None

        with transaction.atomic():
            dept = Department.objects.filter(department_code__iexact=dept_code).first()
            created = False
            if dept:
                dept.department_name = dept_name
                dept.short_name = short_name
                if program:
                    dept.program = program
                dept.is_active = False
                dept.is_display = True
                if audit_user:
                    dept.updated_by = audit_user
                dept.save()
            else:
                dept = Department.objects.create(
                    department_name=dept_name,
                    department_code=dept_code,
                    short_name=short_name,
                    program=program,
                    is_active=False,
                    is_display=True,
                    created_by=audit_user,
                    updated_by=audit_user,
                )
                created = True

        _bust_preview_caches(['Department', 'Program'])
        _send_realtime_broadcast({
            'model': 'Department',
            'action': 'create',
            'event': 'department_created',
            'id': dept.id,
            'department_code': dept.department_code,
            'department_name': dept.department_name
        })

        return Response({
            'success': True,
            'department': {
                'id': dept.id,
                'department_code': dept.department_code,
                'department_name': dept.department_name,
                'short_name': dept.short_name,
                'program_id': dept.program_id,
                'program_name': dept.program.program_name if dept.program else ''
            },
            'created': created,
            'message': f"Department '{dept.department_name}' ({dept.department_code}) successfully {'created' if created else 'updated'}."
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='confirm-save')
    def confirm_save(self, request):
        """
        Confirm verified candidates and broadcast real-time sync notification.
        """
        candidates = request.data.get('candidates', [])
        source_file = request.data.get('source_file', 'Registration_Preview.pdf')

        if not candidates:
            return Response({'error': 'No candidates to save.'}, status=status.HTTP_400_BAD_REQUEST)

        exam_title = request.data.get('exam_title') or (candidates[0].get('exam_title') if candidates else '')
        if exam_title:
            ensure_university_exam_created(exam_title)

        saved_records = len(candidates)

        # Broadcast Real-time WebSocket Event
        try:
            from common.signals import _send_realtime_broadcast
            _send_realtime_broadcast({
                'model': 'UniversityExam',
                'action': 'registration_confirmed',
                'event': 'REGISTRATION_IMPORTED',
                'saved_count': saved_records,
                'candidates_count': len(candidates),
                'exam_title': exam_title,
            })
        except Exception:
            pass

        return Response({
            'success': True,
            'message': f"Successfully verified and saved registration entries for {len(candidates)} candidates.",
            'saved_count': saved_records
        }, status=status.HTTP_200_OK)
