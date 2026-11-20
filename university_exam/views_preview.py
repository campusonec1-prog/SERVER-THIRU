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
from .models import ExamAttendanceImport, UniversityExamSchedule


def clean_str(val):
    if val is None:
        return ''
    return str(val).strip()


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
            exam_title = clean_str(exam_title_match.group(1)) if exam_title_match else ''

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

            extracted_subjects = []
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


class UniversityRegistrationPreviewViewSet(viewsets.ViewSet):
    """
    Handles Preview, Matching, Verification and Quick-add for Anna University
    Registration Preview PDFs. Supports Inter College (internal) and Outer College (outer_student).
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @action(detail=False, methods=['post'], url_path='preview')
    def preview_pdf(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file uploaded. Please upload an Anna University Registration Preview PDF.'},
                            status=status.HTTP_400_BAD_REQUEST)

        if not file_obj.name.lower().endswith('.pdf'):
            return Response({'error': 'Only PDF files are accepted.'}, status=status.HTTP_400_BAD_REQUEST)

        college_type = request.data.get('college_type', 'INTER')

        try:
            file_bytes = file_obj.read()
            raw_candidates = parse_anna_univ_reg_preview_pdf(file_bytes)
        except ImportError as e:
            return Response({'error': str(e)}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            return Response({'error': f'Failed to parse PDF: {str(e)}'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        if not raw_candidates:
            return Response({
                'error': 'No candidate registration data found in the PDF. Please verify this is an Anna University Registration Preview document.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Preload DB master lookups
        all_departments = list(Department.objects.filter(is_active=True).values('id', 'department_code', 'department_name', 'short_name', 'program_id'))
        all_programs = list(Program.objects.all().values('id', 'program_name', 'program_level', 'duration'))
        all_batches = list(Batch.objects.filter(is_active=True).values('id', 'department_id', 'batch'))
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

        for cand in raw_candidates:
            r_no = cand['register_no']
            s_name = cand['student_name']
            calc_batch = cand['calculated_batch']
            matched_dept = match_department(cand['branch'], cand.get('branch_au_code'), cand.get('degree', 'B.E.'))

            matched_batch = None
            if matched_dept and calc_batch:
                for b in all_batches:
                    if b['department_id'] == matched_dept['id'] and b['batch'].lower() == calc_batch.lower():
                        matched_batch = b
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
            found_college_type = 'INTER' if db_inter else ('OUTER' if db_outer else 'INTER')
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
                'department_batches': dept_batches,
                'subjects_count': len(cand['subjects']),
                'subjects': cand['subjects'],
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
                    }
                unique_subjects_dict[key]['student_count'] += 1

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
            'file_name': file_obj.name,
            'college': '',
            'exam_title': raw_candidates[0]['exam_title'] if raw_candidates else '',
            'college_type': college_type,
            'total_candidates': len(students_analysis),
            'students_found': len(students_analysis) - len(missing_students),
            'students_not_found': len(missing_students),
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
        college_type = clean_str(request.data.get('college_type', 'INTER')).upper()

        if not reg_no:
            return Response({'error': 'Register number is required.'}, status=status.HTTP_400_BAD_REQUEST)

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
                        'is_active': True
                    }
                )
            if not dept:
                dept = Department.objects.first()

            # 3. Resolve / Create Batch if missing
            batch = None
            if batch_id and str(batch_id).isdigit():
                batch = Batch.objects.filter(id=int(batch_id)).first()
            if not batch and batch_name and dept:
                batch, _ = Batch.objects.get_or_create(department=dept, batch=batch_name)
            if not batch and dept and len(reg_no) >= 6:
                digit = reg_no[4:6]
                if digit.isdigit():
                    yr = int(digit)
                    est_batch = f"{2000 + yr}-{2000 + yr + 4}"
                    batch, _ = Batch.objects.get_or_create(department=dept, batch=est_batch)
            if not batch and dept:
                batch = Batch.objects.filter(department=dept).first()
                if not batch:
                    batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR')

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
                status_obj, _ = StudentStatus.objects.get_or_create(status_name='ACTIVE')

                # Resolve Section for Inter College Student (Default to Section A for this department)
                sec_obj = None
                if dept:
                    target_sec_name = section_name or 'Section: A'
                    clean_sec = target_sec_name.replace('Section:', '').replace('Section', '').strip() or 'A'
                    if section_id and str(section_id).isdigit():
                        sec_obj = Section.objects.filter(id=int(section_id), department=dept).first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__iexact=target_sec_name).first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__iexact=f"Section: {clean_sec}").first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__iexact=clean_sec).first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__icontains=clean_sec).first()
                    if not sec_obj:
                        sec_obj = Section.objects.filter(department=dept, sections__icontains='A').first()
                    if not sec_obj:
                        sec_obj, _ = Section.objects.get_or_create(department=dept, sections='Section: A')

                student, created = Student.objects.get_or_create(
                    register_number=reg_no,
                    defaults={
                        'student_name': s_name or reg_no,
                        'department': dept,
                        'batch': batch,
                        'section': sec_obj,
                        'status': status_obj,
                    }
                )
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

        status_obj, _ = StudentStatus.objects.get_or_create(status_name='ACTIVE')
        created_count = 0
        added_list = []

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

                # Program
                program = None
                if prog_id and str(prog_id).isdigit():
                    program = Program.objects.filter(id=int(prog_id)).first()
                if not program and prog_name:
                    program, _ = Program.objects.get_or_create(program_name=prog_name, defaults={'program_level': 'UG', 'duration': 4})
                if not program:
                    program = Program.objects.first()

                # Department
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
                            'is_active': True
                        }
                    )
                if not dept:
                    dept = Department.objects.first()

                # Batch
                batch = None
                if not batch_str and len(reg_no) >= 6 and reg_no[4:6].isdigit():
                    yr = int(reg_no[4:6])
                    batch_str = f"{2000 + yr}-{2000 + yr + 4}"

                if batch_str and dept:
                    batch, _ = Batch.objects.get_or_create(department=dept, batch=batch_str)
                elif dept:
                    batch = Batch.objects.filter(department=dept).first()
                    if not batch:
                        batch, _ = Batch.objects.get_or_create(department=dept, batch='REGULAR')

                # Regulation
                regulation = None
                if reg_code:
                    regulation, _ = Regulation.objects.get_or_create(
                        regulation_code=reg_code,
                        defaults={'effective_from_year': int(reg_code) if reg_code.isdigit() else 2021}
                    )

                item_college_type = clean_str(item.get('college_type') or college_type or 'INTER').upper()

                if item_college_type == 'OUTER':
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
                    if created:
                        created_count += 1
                    added_list.append({
                        'id': outer_stud.id,
                        'register_number': outer_stud.register_number,
                        'student_name': outer_stud.student_name,
                        'college_type': 'OUTER',
                        'table': 'outer_student',
                        'created': created
                    })
                else:
                    sec_name = clean_str(item.get('section_name') or item.get('section') or 'Section: A')
                    sec_id = item.get('section_id')
                    sec_obj = None
                    if dept:
                        clean_sec = sec_name.replace('Section:', '').replace('Section', '').strip() or 'A'
                        if sec_id and str(sec_id).isdigit():
                            sec_obj = Section.objects.filter(id=int(sec_id), department=dept).first()
                        if not sec_obj:
                            sec_obj = Section.objects.filter(department=dept, sections__iexact=sec_name).first()
                        if not sec_obj:
                            sec_obj = Section.objects.filter(department=dept, sections__iexact=f"Section: {clean_sec}").first()
                        if not sec_obj:
                            sec_obj = Section.objects.filter(department=dept, sections__iexact=clean_sec).first()
                        if not sec_obj:
                            sec_obj = Section.objects.filter(department=dept, sections__icontains=clean_sec).first()
                        if not sec_obj:
                            sec_obj = Section.objects.filter(department=dept, sections__icontains='A').first()
                        if not sec_obj:
                            sec_obj, _ = Section.objects.get_or_create(department=dept, sections='Section: A')

                    student, created = Student.objects.get_or_create(
                        register_number=reg_no,
                        defaults={
                            'student_name': s_name or reg_no,
                            'department': dept,
                            'batch': batch,
                            'section': sec_obj,
                            'status': status_obj
                        }
                    )
                    if not created and sec_obj and not student.section:
                        student.section = sec_obj
                        student.save(update_fields=['section'])

                    if created:
                        created_count += 1
                    added_list.append({
                        'id': student.id,
                        'register_number': student.register_number,
                        'student_name': student.student_name,
                        'college_type': 'INTER',
                        'student_type': 'Inter College',
                        'section_name': student.section.sections if student.section else '',
                        'created': created
                    })

        inter_count = sum(1 for s in added_list if s.get('college_type') == 'INTER')
        outer_count = sum(1 for s in added_list if s.get('college_type') == 'OUTER')
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
                'is_active': True,
            }
        )
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

        created_count = 0
        added_list = []

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

                dept = Department.objects.filter(id=dept_id).first() if dept_id else Department.objects.first()
                if not dept:
                    continue

                reg, _ = Regulation.objects.get_or_create(
                    regulation_code=reg_code,
                    defaults={'effective_from_year': int(reg_code) if reg_code.isdigit() else 2025}
                )

                sem, _ = Semester.objects.get_or_create(
                    department=dept,
                    semester_number=sem_num,
                    defaults={'semester_name': f"Semester {sem_num}"}
                )

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
                        'is_active': True,
                    }
                )
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

                if created:
                    created_count += 1
                added_list.append({
                    'id': subj.id,
                    'subject_code': subj.subject_code,
                    'subject_name': subj.subject_name,
                    'credits': subj.credits,
                    'regulation_code': reg_code,
                    'created': created
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

        with transaction.atomic():
            dept = Department.objects.filter(department_code__iexact=dept_code).first()
            created = False
            if dept:
                dept.department_name = dept_name
                dept.short_name = short_name
                if program:
                    dept.program = program
                dept.is_active = True
                dept.is_display = True
                dept.save()
            else:
                dept = Department.objects.create(
                    department_name=dept_name,
                    department_code=dept_code,
                    short_name=short_name,
                    program=program,
                    is_active=True,
                    is_display=True
                )
                created = True

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
        Save the verified candidates and their registered subjects into ExamAttendanceImport.
        """
        candidates = request.data.get('candidates', [])
        source_file = request.data.get('source_file', 'Registration_Preview.pdf')

        if not candidates:
            return Response({'error': 'No candidates to save.'}, status=status.HTTP_400_BAD_REQUEST)

        saved_records = 0
        with transaction.atomic():
            for cand in candidates:
                reg_no = clean_str(cand.get('register_no'))
                student = Student.objects.filter(register_number=reg_no).first()
                outer_student = OuterStudent.objects.filter(register_number=reg_no).first() if not student else None
                dept = (student.department if student else (outer_student.department if outer_student else None)) or Department.objects.filter(id=cand.get('suggested_department_id')).first()

                cand_subjects = cand.get('subjects', [])
                if cand_subjects:
                    for sub in cand_subjects:
                        sub_code = sub.get('subject_code')
                        subject_obj = Subject.objects.filter(subject_code__iexact=sub_code).first() if sub_code else None

                        ExamAttendanceImport.objects.create(
                            department=dept,
                            student=student,
                            subject=subject_obj,
                            source_file=source_file,
                            source_page=cand.get('page', 1),
                            import_status='MATCHED' if ((student or outer_student) and subject_obj) else 'PENDING',
                            error_message='Outer Candidate' if outer_student and not student else ('' if ((student or outer_student) and subject_obj) else 'Missing student or subject master')
                        )
                        saved_records += 1
                else:
                    # For sheets where subjects are 0 or candidate-level roster registration
                    ExamAttendanceImport.objects.create(
                        department=dept,
                        student=student,
                        subject=None,
                        source_file=source_file,
                        source_page=cand.get('page', 1),
                        import_status='MATCHED' if (student or outer_student) else 'PENDING',
                        error_message='Outer Candidate' if outer_student and not student else ('' if student else 'Missing student master')
                    )
                    saved_records += 1

        return Response({
            'success': True,
            'message': f"Successfully saved {saved_records} registration entries from {len(candidates)} candidates.",
            'saved_count': saved_records
        }, status=status.HTTP_200_OK)
