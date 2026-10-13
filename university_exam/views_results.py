import io
import re
import datetime
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.db.models import Q

from student.models import Student, Marks
from subject.models import Subject
from institution.models import Exam, ExamType, Department


def clean_cell_text(val):
    if val is None:
        return ''
    return str(val).strip()


def parse_anna_university_result_pdf(file_bytes):
    """
    Parse Anna University Regular / Revaluation Semester Result PDF.
    Supports multi-page PDFs where headers might appear on page 1 and omit on continuation pages.
    Extracts:
      - College, Branch, Semester, Degree Examination title
      - Subject codes list
      - Register Numbers and corresponding Grades for each subject
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required. Run: pip install pdfplumber")

    metadata = {
        'college_code': '',
        'college_name': '',
        'branch_code': '',
        'branch_name': '',
        'semester': '',
        'degree_exam': '',
        'total_pages': 0,
    }

    # Tracking across pages
    active_college = ''
    active_branch = ''
    active_branch_code = ''
    active_semester = ''
    active_degree_exam = ''
    active_subject_codes = []  # List of subject code strings

    student_records_map = {}  # reg_no -> {'register_number': reg, 'page': page_num, 'branch': ..., 'semester': ..., 'grades': {}}

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        metadata['total_pages'] = len(pdf.pages)

        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ''

            # ── 1. Metadata Extraction ─────────────────────────────────────────
            # College line: College : 1114 - K.L.N. COLLEGE OF ENGINEERING
            col_match = re.search(r'College\s*:\s*(.*?)(?:\n|$)', raw_text, re.IGNORECASE)
            if col_match:
                c_text = col_match.group(1).strip()
                if '-' in c_text:
                    parts = c_text.split('-', 1)
                    metadata['college_code'] = parts[0].strip()
                    metadata['college_name'] = parts[1].strip()
                    active_college = c_text
                else:
                    metadata['college_name'] = c_text
                    active_college = c_text

            # Branch line: Branch : 148 - B.E. Computer Science and Engineering
            br_match = re.search(r'Branch\s*:\s*(.*?)(?:\n|$)', raw_text, re.IGNORECASE)
            if br_match:
                b_text = br_match.group(1).strip()
                if '-' in b_text:
                    parts = b_text.split('-', 1)
                    metadata['branch_code'] = parts[0].strip()
                    metadata['branch_name'] = parts[1].strip()
                    active_branch_code = parts[0].strip()
                    active_branch = parts[1].strip()
                else:
                    metadata['branch_name'] = b_text
                    active_branch = b_text

            # Semester No: Semester No. : 07
            sem_match = re.search(r'Semester\s*(?:No\.?|Number)?\s*:\s*([0-9IVXLCDMivxlcdm]+)', raw_text, re.IGNORECASE)
            if sem_match:
                metadata['semester'] = sem_match.group(1).strip()
                active_semester = metadata['semester']

            # Exam Header: B.E. / B.Tech. DEGREE EXAMINATIONS - NOV. / DEC. 2024
            deg_match = re.search(r'(?:B\.E\.|B\.Tech|M\.E\.|M\.Tech|DEGREE EXAMINATIONS)[^\n\r]+', raw_text, re.IGNORECASE)
            if deg_match:
                metadata['degree_exam'] = deg_match.group(0).strip()
                active_degree_exam = metadata['degree_exam']

            # ── 2. Table Extraction ────────────────────────────────────────────
            # Try default extraction first; fallback to explicit strategies if needed
            tables = page.extract_tables()
            if not tables:
                tables = page.extract_tables({
                    "vertical_strategy": "text",
                    "horizontal_strategy": "text",
                    "snap_tolerance": 5
                })

            page_subject_columns = {}  # col_idx -> subject_code

            for table in tables:
                for row_idx, row in enumerate(table):
                    if not row or len(row) < 2:
                        continue

                    # Filter and clean row cells
                    cleaned_row = [clean_cell_text(c) for c in row]

                    # Check if this row is a Subject Code header row
                    # Indicators: first cell is 'Reg. No.' or contains 'Reg' or 'Register',
                    # and subsequent cells have subject-like patterns (e.g. CS25C01, GE3151)
                    first_cell = cleaned_row[0].lower()
                    looks_like_reg_header = any(k in first_cell for k in ['reg', 'roll', 'student', 'sl', 'no']) or (first_cell == '')

                    subject_matches_in_row = {}
                    for col_i in range(1, len(cleaned_row)):
                        cell_str = re.sub(r'\s+', '', cleaned_row[col_i]).upper()
                        # Subject code pattern: 5-10 chars, starting with 2-4 letters followed by numbers/letters
                        # e.g. CS25C01, GE3151, MA8151, CS8075, CY3151, etc.
                        if re.match(r'^[A-Z]{2,4}[0-9]{2,5}[A-Z0-9]*$', cell_str):
                            subject_matches_in_row[col_i] = cell_str

                    if looks_like_reg_header and len(subject_matches_in_row) >= 1:
                        # Found subject header row!
                        page_subject_columns = subject_matches_in_row
                        # Update active subject codes
                        for sub_code in subject_matches_in_row.values():
                            if sub_code not in active_subject_codes:
                                active_subject_codes.append(sub_code)
                        continue

                    # Check if this row is a Sub-header row like: [Sub-header] | Grade | Grade | Grade...
                    # or row with all 'Grade' / 'Credits' / 'Marks'
                    grade_words_count = sum(1 for c in cleaned_row[1:] if c.lower() in ['grade', 'sub-header', 'subheader', 'credits', 'mark', 'marks'])
                    if grade_words_count >= max(1, len(cleaned_row) // 3):
                        continue

                    # Check if this row is a student data row
                    # Register numbers are typically 10 to 14 numeric digits (e.g., 111421104001, 513223103301)
                    reg_no = None
                    # Search cell 0, or if cell 0 is serial number, check cell 1
                    for check_idx in [0, 1]:
                        if check_idx < len(cleaned_row):
                            m = re.search(r'\b(\d{10,14})\b', cleaned_row[check_idx])
                            if m:
                                reg_no = m.group(1)
                                break

                    if reg_no:
                        # Use either current page's detected columns or active columns
                        cols_to_use = page_subject_columns
                        if not cols_to_use and active_subject_codes:
                            # If continuation page has no header row, map remaining cells sequentially to active_subject_codes
                            data_start = 1 if re.search(r'\b\d{10,14}\b', cleaned_row[0]) else 2
                            cols_to_use = {}
                            for idx, sub_code in enumerate(active_subject_codes):
                                target_idx = data_start + idx
                                if target_idx < len(cleaned_row):
                                    cols_to_use[target_idx] = sub_code

                        # Extract grades
                        extracted_grades = {}
                        for col_idx, sub_code in cols_to_use.items():
                            if col_idx < len(cleaned_row):
                                val = cleaned_row[col_idx].strip().upper()
                                # Common valid grades or status codes in Anna University:
                                # O, A+, A, B+, B, C, U, UA, RA, SA, W, WH, AB, NA, PASS, FAIL
                                # Ignore dashes or blank cells
                                if val and val not in ['-', '--', 'NIL', 'NULL']:
                                    extracted_grades[sub_code] = val

                        if reg_no not in student_records_map:
                            student_records_map[reg_no] = {
                                'register_number': reg_no,
                                'page': page_num,
                                'branch_code': active_branch_code,
                                'branch_name': active_branch,
                                'semester': active_semester,
                                'grades': {}
                            }
                        student_records_map[reg_no]['grades'].update(extracted_grades)

            # ── 3. Fallback: Text-based line parser if table extraction found 0 rows for this page ──
            if not any(rec['page'] == page_num for rec in student_records_map.values()):
                lines = raw_text.splitlines()
                # Find lines containing 10-14 digit register numbers
                for line in lines:
                    reg_m = re.search(r'\b(\d{10,14})\b', line)
                    if reg_m:
                        reg_no = reg_m.group(1)
                        # Split remaining tokens after register number
                        after_reg = line[reg_m.end():].strip()
                        tokens = [t.upper() for t in re.split(r'\s+', after_reg) if t]
                        extracted_grades = {}
                        if active_subject_codes:
                            for idx, token in enumerate(tokens):
                                if idx < len(active_subject_codes):
                                    if token not in ['-', '--']:
                                        extracted_grades[active_subject_codes[idx]] = token

                        if reg_no not in student_records_map:
                            student_records_map[reg_no] = {
                                'register_number': reg_no,
                                'page': page_num,
                                'branch_code': active_branch_code,
                                'branch_name': active_branch,
                                'semester': active_semester,
                                'grades': {}
                            }
                        student_records_map[reg_no]['grades'].update(extracted_grades)

    return {
        'metadata': metadata,
        'subject_codes': active_subject_codes,
        'records': list(student_records_map.values())
    }


class UniversityResultPublishViewSet(viewsets.ViewSet):
    """
    ViewSet for Anna University Result and Revaluation Result processing.
    - preview_results: Parses uploaded PDF, matches students & subjects against DB, flags unmatched items.
    - publish_results: Commits grades into the marks table with student_id, exam_id, and grade string.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @action(detail=False, methods=['post'], url_path='preview')
    def preview_results(self, request):
        """
        Preview Anna University Results from uploaded PDF file.
        Returns extracted metadata, list of subjects (matched & unmatched),
        and list of student records (matched with student_id & unmatched register numbers).
        """
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No PDF file provided. Please upload a result PDF.'}, status=status.HTTP_400_BAD_REQUEST)

        if not file_obj.name.lower().endswith('.pdf'):
            return Response({'error': 'Only PDF files are supported.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            file_bytes = file_obj.read()
            parsed_data = parse_anna_university_result_pdf(file_bytes)
        except ImportError as e:
            return Response({'error': str(e)}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            return Response({'error': f'Failed to parse PDF: {str(e)}'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        records = parsed_data.get('records', [])
        pdf_subject_codes = parsed_data.get('subject_codes', [])

        if not records:
            return Response({
                'error': 'No student result rows could be detected in the uploaded PDF. Please verify that this is an Anna University Semester / Revaluation Result PDF.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── 1. Query Database for Matching Students ────────────────────────
        all_reg_numbers = [r['register_number'] for r in records]
        students_qs = Student.objects.filter(
            register_number__in=all_reg_numbers
        ).select_related('department', 'batch', 'section')

        student_by_reg = {}
        for s in students_qs:
            if s.register_number:
                student_by_reg[s.register_number.strip().upper()] = s

        # ── 2. Query Database for Matching Subjects ────────────────────────
        # If no subject codes found in table header, collect unique keys from records
        if not pdf_subject_codes:
            unique_subs = set()
            for r in records:
                unique_subs.update(r.get('grades', {}).keys())
            pdf_subject_codes = sorted(list(unique_subs))

        # Query subjects matching these codes
        subjects_qs = Subject.objects.filter(
            is_active=True,
            subject_code__in=pdf_subject_codes
        ).select_related('department', 'semester')

        subject_by_code = {}
        for sub in subjects_qs:
            code_key = sub.subject_code.strip().upper()
            if code_key not in subject_by_code:
                subject_by_code[code_key] = sub

        # Build Subjects Analysis
        subject_analysis = []
        for code in pdf_subject_codes:
            code_upper = code.upper()
            matched_sub = subject_by_code.get(code_upper)
            subject_analysis.append({
                'subject_code': code,
                'matched': bool(matched_sub),
                'subject_id': matched_sub.id if matched_sub else None,
                'subject_name': matched_sub.subject_name if matched_sub else '',
                'subject_category': 'LAB' if (matched_sub and matched_sub.is_lab) else 'THEORY',
                'credits': matched_sub.credits if matched_sub else 0,
            })

        unmatched_subject_codes = [s['subject_code'] for s in subject_analysis if not s['matched']]

        # ── 3. Build Student Rows Analysis ─────────────────────────────────
        student_analysis = []
        unmatched_reg_numbers = []

        for r in records:
            reg_clean = r['register_number'].strip().upper()
            matched_student = student_by_reg.get(reg_clean)

            if matched_student:
                student_analysis.append({
                    'register_number': r['register_number'],
                    'matched': True,
                    'student_id': matched_student.id,
                    'student_name': matched_student.student_name or '',
                    'roll_number': matched_student.roll_number or '',
                    'department_id': matched_student.department_id,
                    'department_code': matched_student.department.department_code if matched_student.department else '',
                    'department_name': matched_student.department.department_name if matched_student.department else '',
                    'batch_name': str(matched_student.batch) if matched_student.batch else '',
                    'section_name': str(matched_student.section) if matched_student.section else '',
                    'grades': r.get('grades', {}),
                    'page': r.get('page', 1),
                })
            else:
                unmatched_reg_numbers.append(r['register_number'])
                student_analysis.append({
                    'register_number': r['register_number'],
                    'matched': False,
                    'student_id': None,
                    'student_name': 'Unknown / Not in DB',
                    'roll_number': '',
                    'department_id': None,
                    'department_code': '',
                    'department_name': '',
                    'batch_name': '',
                    'section_name': '',
                    'grades': r.get('grades', {}),
                    'page': r.get('page', 1),
                })

        # Calculate statistics
        total_students = len(records)
        matched_students_count = len(student_analysis) - len(unmatched_reg_numbers)
        unmatched_students_count = len(unmatched_reg_numbers)

        return Response({
            'metadata': parsed_data.get('metadata', {}),
            'summary': {
                'total_students_in_pdf': total_students,
                'matched_students_count': matched_students_count,
                'unmatched_students_count': unmatched_students_count,
                'total_subjects_in_pdf': len(pdf_subject_codes),
                'matched_subjects_count': len(pdf_subject_codes) - len(unmatched_subject_codes),
                'unmatched_subjects_count': len(unmatched_subject_codes),
            },
            'subjects': subject_analysis,
            'unmatched_subject_codes': unmatched_subject_codes,
            'unmatched_register_numbers': unmatched_reg_numbers,
            'students': student_analysis,
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='publish')
    def publish_results(self, request):
        """
        Publish extracted results to the marks table.
        Payload:
        {
          "exam_id": 1,
          "results": [
            {
              "student_id": 101,
              "register_number": "111421104001",
              "grades": { "CS25C01": "A+", "CS25C02": "A" }
            }
          ],
          "subject_mappings": { "CS25C01": 501, ... }, # optional manual/override mapping
          "mode": "REGULAR" or "REVALUATION"
        }
        """
        exam_id = request.data.get('exam_id')
        if not exam_id:
            return Response({'error': 'Exam is required. Please select an exam.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            exam = Exam.objects.get(id=exam_id, is_active=True)
        except Exam.DoesNotExist:
            return Response({'error': f'Exam with ID {exam_id} not found or inactive.'}, status=status.HTTP_404_NOT_FOUND)

        results = request.data.get('results', [])
        if not results or not isinstance(results, list):
            return Response({'error': 'No student result rows provided to publish.'}, status=status.HTTP_400_BAD_REQUEST)

        subject_mappings = request.data.get('subject_mappings') or {}
        mode = request.data.get('mode', 'REGULAR').upper()

        # Cache Subjects for quick lookup
        # First gather all subject codes from the results
        all_codes = set()
        for r in results:
            all_codes.update(r.get('grades', {}).keys())

        # Collect subject IDs already specified in subject_mappings
        subject_cache = {}
        for code, sub_id in subject_mappings.items():
            if sub_id:
                try:
                    subject_cache[code.upper()] = Subject.objects.get(id=sub_id)
                except Subject.DoesNotExist:
                    pass

        # Lookup remaining codes in DB
        unmapped_codes = [c for c in all_codes if c.upper() not in subject_cache]
        if unmapped_codes:
            db_subs = Subject.objects.filter(is_active=True, subject_code__in=unmapped_codes)
            for s in db_subs:
                code_key = s.subject_code.strip().upper()
                if code_key not in subject_cache:
                    subject_cache[code_key] = s

        # Gather Students
        student_ids = [r['student_id'] for r in results if r.get('student_id')]
        student_db_map = {s.id: s for s in Student.objects.filter(id__in=student_ids)}

        created_count = 0
        updated_count = 0
        skipped_count = 0
        errors = []

        current_user = request.user if request.user.is_authenticated else None

        with transaction.atomic():
            for row in results:
                student_id = row.get('student_id')
                reg_no = row.get('register_number', '')
                student = student_db_map.get(student_id)

                if not student:
                    skipped_count += 1
                    continue

                grades = row.get('grades', {})
                for sub_code, grade_val in grades.items():
                    if not grade_val or grade_val in ['-', '--', 'NIL']:
                        continue

                    grade_str = str(grade_val).strip().upper()
                    subject = subject_cache.get(sub_code.upper())

                    if not subject:
                        errors.append(f"Subject '{sub_code}' could not be resolved to a DB Subject for student {reg_no}.")
                        continue

                    category = 'LAB' if subject.is_lab else 'THEORY'

                    # update_or_create in marks table
                    # unique_together = ('student', 'exam', 'subject', 'subject_category')
                    mark_obj, created = Marks.objects.update_or_create(
                        student=student,
                        exam=exam,
                        subject=subject,
                        subject_category=category,
                        defaults={
                            'marks_obtained': grade_str,
                            'updated_by': current_user,
                        }
                    )

                    if created:
                        if current_user:
                            mark_obj.created_by = current_user
                            mark_obj.save(update_fields=['created_by'])
                        created_count += 1
                    else:
                        updated_count += 1

        total_processed = created_count + updated_count
        verb = "updated" if mode == 'REVALUATION' else "published"
        message = f"Successfully {verb} {total_processed} grade records ({created_count} new, {updated_count} updated) for exam '{exam.exam_name}'."

        return Response({
            'message': message,
            'exam_id': exam.id,
            'exam_name': exam.exam_name,
            'mode': mode,
            'total_grades_processed': total_processed,
            'created_count': created_count,
            'updated_count': updated_count,
            'skipped_students': skipped_count,
            'errors': errors[:10]  # Return top 10 errors if any
        }, status=status.HTTP_200_OK)
