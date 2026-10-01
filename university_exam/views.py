import io
import datetime
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
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
    queryset = UniversityExamHall.objects.select_related('hall__floor__block').all().order_by('hall__floor__block__block_code', 'hall__floor__floor_order', 'hall__hall_no')
    serializer_class = UniversityExamHallSerializer
    permission_classes = [IsAuthenticated]
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
    queryset = ExamHallDate.objects.select_related('exam_hall__hall__floor__block').all().order_by('-exam_date', 'session', 'exam_hall__hall__hall_no')
    serializer_class = ExamHallDateSerializer
    permission_classes = [IsAuthenticated]
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

def parse_anna_university_pdf(file_bytes):
    """
    Parse Anna University attendance sheet PDF.
    Returns list of dicts with extracted row data.
    Requires pdfplumber installed.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber is required. Run: pip install pdfplumber")

    rows = []
    
    # Track headers across pages (subsequent pages might not repeat the header)
    college_code, college_name, branch_code, branch_name = '', '', '', ''
    subject_code, subject_name = '', ''
    exam_date_str, session, exam_date = '', '', None

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = page.extract_text() or ''
            
            import re
            
            # Accurate Multiline Regex extractors for Anna University PDF headers
            col_match = re.search(r'College\s*(?:Code/Name|Code|Name|/)?\s*:\s*(.*?)(?:\s+Date of Examination\s*:\s*(.*?))?$', raw_text, re.IGNORECASE | re.MULTILINE)
            if col_match:
                c_info = col_match.group(1).strip()
                if '-' in c_info:
                    college_code, college_name = [x.strip() for x in c_info.split('-', 1)]
                else:
                    college_code = c_info
                
                if col_match.group(2):
                    exam_date_str = col_match.group(2).strip()

            br_match = re.search(r'Branch\s*(?:Code/Name|Code|Name|/)?\s*:\s*(.*?)(?:\s+Session\s*:\s*(.*?))?$', raw_text, re.IGNORECASE | re.MULTILINE)
            if br_match:
                b_info = br_match.group(1).strip()
                if '-' in b_info:
                    branch_code, branch_name = [x.strip() for x in b_info.split('-', 1)]
                else:
                    branch_code = b_info
                
                if br_match.group(2):
                    session = br_match.group(2).strip().upper()

            sub_match = re.search(r'(?:Subject|Sub\.?)\s*(?:Code/Name|Code|Name|/)?\s*:\s*(.*?)$', raw_text, re.IGNORECASE | re.MULTILINE)
            if sub_match:
                s_info = sub_match.group(1).strip()
                if '-' in s_info:
                    subject_code, subject_name = [x.strip() for x in s_info.split('-', 1)]
                else:
                    subject_code = s_info

            # Parse exam_date only if it was newly found on this page
            if exam_date_str and not exam_date:
                for fmt in ('%d-%b-%Y', '%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                    try:
                        exam_date = datetime.datetime.strptime(exam_date_str, fmt).date()
                        break
                    except Exception:
                        pass

            # Extract table rows
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    # Skip header rows
                    if any(h in str(row[0] or '').lower() for h in ['s.no', 's no', 'sl', 'no.']):
                        continue
                    # Try to detect register number column (usually index 1)
                    register_no = None
                    student_name = None
                    for i, cell in enumerate(row):
                        cell_str = str(cell or '').strip()
                        # Register numbers are typically 12 purely numeric characters. 
                        # We extract the first word and ensure it is alphanumeric and long enough.
                        first_word = cell_str.split()[0] if cell_str else ''
                        if first_word.isalnum() and len(first_word) >= 10 and first_word[:4].isdigit():
                            register_no = first_word[:50]
                            if i + 1 < len(row):
                                name_cand = str(row[i + 1] or '').split('\n')[0].strip()
                                if name_cand and name_cand != '-':
                                    student_name = name_cand[:250]
                            break

                    if register_no and student_name:
                        rows.append({
                            'college_code': college_code,
                            'college_name': college_name,
                            'branch_code': branch_code,
                            'branch_name': branch_name,
                            'register_no': register_no,
                            'student_name': student_name,
                            'subject_code': subject_code,
                            'subject_name': subject_name,
                            'exam_date': exam_date,
                            'session': session[:2] if session else '',
                            'source_page': page_num,
                        })
    return rows


# ─── ViewSets ────────────────────────────────────────────────────────────────

class ExamAttendanceImportViewSet(viewsets.ModelViewSet):
    queryset = ExamAttendanceImport.objects.all().order_by('id')
    serializer_class = ExamAttendanceImportSerializer
    permission_classes = [IsAuthenticated]
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

    @action(detail=False, methods=['post'], url_path='upload', parser_classes=[MultiPartParser, FormParser])
    def upload_pdf(self, request):
        """Upload a PDF and parse it into the staging table."""
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if not file_obj.name.lower().endswith('.pdf'):
            return Response({'error': 'Only PDF files are accepted'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            file_bytes = file_obj.read()
            # DEBUG: Save file to disk so we can inspect its text format
            import os
            debug_path = os.path.join(r'C:\Users\Raiyan\.gemini\antigravity-ide\brain\fd1b47ff-4417-4243-a1ac-b507d8331566\scratch', 'latest_upload.pdf')
            os.makedirs(os.path.dirname(debug_path), exist_ok=True)
            with open(debug_path, 'wb') as f:
                f.write(file_bytes)

            parsed_rows = parse_anna_university_pdf(file_bytes)
        except ImportError as e:
            return Response({'error': str(e)}, status=status.HTTP_501_NOT_IMPLEMENTED)
        except Exception as e:
            return Response({'error': f'Failed to parse PDF: {str(e)}'}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        if not parsed_rows:
            return Response({'error': 'No student data found in the PDF'}, status=status.HTTP_400_BAD_REQUEST)

        from institution.models import Department, Batch, Program
        from subject.models import Subject
        from student.models import Student, StudentStatus
        from dynamic_forms.models import Application, ApplicationUser, ApplicationStatus
        import random
        import string

        created_records = []
        for row in parsed_rows:
            try:
                dept = Department.objects.filter(department_code=row.get('branch_code')).first()
                if not dept and row.get('branch_code'):
                    dept = Department.objects.create(department_code=row.get('branch_code'), department_name=row.get('branch_name'))
                elif not dept:
                    dept = Department.objects.first()

                subject = Subject.objects.filter(subject_code=row.get('subject_code')).first()
                if not subject and row.get('subject_code'):
                    from institution.models import Regulation, Semester
                    reg = Regulation.objects.first()
                    sem = Semester.objects.first()
                    subject = Subject.objects.create(
                        subject_code=row.get('subject_code'), 
                        subject_name=row.get('subject_name'), 
                        department=dept,
                        credits=3,
                        regulation=reg,
                        semester=sem
                    )

                student = Student.objects.filter(register_number=row.get('register_no')).first()
                if not student and row.get('register_no'):
                    batch, _ = Batch.objects.get_or_create(department=dept, batch='AUTO_IMPORT')
                    program = Program.objects.first()
                    status_obj, _ = ApplicationStatus.objects.get_or_create(status_name='APPROVED')
                    student_status_obj, _ = StudentStatus.objects.get_or_create(status_name='ACTIVE')
                    
                    email = f"dummy_{row.get('register_no')}@example.com"
                    pwd = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
                    user, _ = ApplicationUser.objects.get_or_create(
                        email=email,
                        defaults={
                            'name': row.get('student_name') or row.get('register_no'),
                            'phone_number': '0000000000',
                            'password': pwd
                        }
                    )
                    
                    app, _ = Application.objects.get_or_create(
                        application_no=f"APP-{row.get('register_no')}",
                        defaults={
                            'candidate': user,
                            'program': program,
                            'status': status_obj,
                            'form_data': {'personal_info': {'full_name': row.get('student_name') or row.get('register_no')}}
                        }
                    )
                    
                    student = Student.objects.create(
                        register_number=row.get('register_no'),
                        department=dept,
                        batch=batch,
                        application=app,
                        status=student_status_obj
                    )

                obj = ExamAttendanceImport.objects.create(
                    department=dept,
                    student=student,
                    subject=subject,
                    exam_date=row.get('exam_date'),
                    session=row.get('session'),
                    source_file=file_obj.name,
                    source_page=row.get('source_page'),
                    import_status='PENDING',
                )
            except Exception as e:
                obj = ExamAttendanceImport.objects.create(
                    exam_date=row.get('exam_date'),
                    session=row.get('session'),
                    source_file=file_obj.name,
                    source_page=row.get('source_page'),
                    import_status='ERROR',
                    error_message=str(e)
                )
            created_records.append(obj.id)

        return Response({
            'message': f'Successfully imported {len(created_records)} records',
            'imported_count': len(created_records),
            'ids': created_records,
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
                    record.error_message = f"Missing student, subject, or department references."
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
    queryset = UniversityExamSchedule.objects.select_related('department', 'subject').annotate(
        student_count=Count('attendances')
    ).all().order_by('-exam_date', 'session')
    serializer_class = UniversityExamScheduleSerializer
    permission_classes = [IsAuthenticated]

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
        ).select_related('hall__floor__block').order_by('hall__floor__block__block_code', 'hall__floor__floor_order', 'hall__hall_no'))

        if not available_halls:
            # Fall back: use all active halls if no ExamHallDate records exist
            available_halls = list(UniversityExamHall.objects.filter(
                is_active=True
            ).select_related('hall__floor__block').order_by('hall__floor__block__block_code', 'hall__floor__floor_order', 'hall__hall_no'))

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
    permission_classes = [IsAuthenticated]

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
    permission_classes = [IsAuthenticated]
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
    permission_classes = [IsAuthenticated]
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
