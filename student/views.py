from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from django.db.models import Q
from .models import StudentStatus, Student, StudentAdmissionSlip, StudentFees, FacultyActivity, StudentAttendance
from .serializers import StudentStatusSerializer, StudentSerializer, StudentAdmissionSlipSerializer, StudentFeesSerializer, FacultyActivitySerializer, StudentAttendanceSerializer
from users.permissions import IsAdminUser
from .permissions import StudentStatusPermission, StudentPermission, MarksPermission, CounsellingReportPermission, AttendancePermission


class StudentStatusViewSet(viewsets.ModelViewSet):
    queryset = StudentStatus.objects.all().order_by('id')
    serializer_class = StudentStatusSerializer
    permission_classes = [StudentStatusPermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Student status not found"
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
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(created_by=tracking_user, updated_by=tracking_user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student statuses listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student status retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Student status created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student status updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student status deleted successfully"
        }, status=status.HTTP_200_OK)


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all().order_by('id')
    serializer_class = StudentSerializer
    permission_classes = [StudentPermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Student not found"
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
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        self._broadcast_change(instance, 'student_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'student_updated')

    def perform_destroy(self, instance):
        student_id = instance.id
        instance.delete()
        self._broadcast_delete(student_id)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        
        # Filtering
        department_id = request.query_params.get('department_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')
        search = request.query_params.get('search')
        
        if department_id:
            queryset = queryset.filter(department_id=department_id)
        if batch_id:
            queryset = queryset.filter(batch_id=batch_id)
        if section_id:
            if str(section_id).isdigit():
                queryset = queryset.filter(section_id=section_id)
            else:
                queryset = queryset.filter(section__sections__iexact=section_id)
        if search:
            queryset = queryset.filter(
                Q(user__name__icontains=search) |
                Q(roll_number__icontains=search) |
                Q(register_number__icontains=search) |
                Q(user__email__icontains=search) |
                Q(user__phone_number__icontains=search)
            )

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)
            return Response({
                "code": 200,
                "message": "Students listed successfully",
                "data": paginated_response.data
            }, status=status.HTTP_200_OK)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Students listed successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Student created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Student deleted successfully"
        }, status=status.HTTP_200_OK)

    def _broadcast_change(self, instance, event_name):
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
                            'event': event_name,
                            'payload': StudentSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, student_id):
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
                            'event': 'student_deleted',
                            'payload': {
                                'id': student_id
                            }
                        }
                    }
                )
        except Exception:
            pass

    def admission_slip_data(self, request, pk, *args, **kwargs):
        """
        Returns rich structured data for the admission slip modal:
        - Student + application form data
        - Derived qualification (highest)
        - Academic PCM marks from application performance rows
        - Uploaded certificate documents list
        - Existing StudentAdmissionSlip record (admission fields)
        - Existing StudentFees record (fees fields)
        - All system users (for recommendation dropdown)
        """
        from django.shortcuts import get_object_or_404
        from users.models import User

        student = get_object_or_404(Student, pk=pk)
        app = student.user.applications.first() if student.user else None
        fd = app.form_data if (app and app.form_data and isinstance(app.form_data, dict)) else {}

        def get_fd(module_key, field_key=None):
            """Get value from nested form_data."""
            module_data = fd.get(module_key, {})
            if field_key is None:
                return module_data
            if isinstance(module_data, dict):
                return module_data.get(field_key, '')
            return ''

        # ── Personal Info ──────────────────────────────────────────────
        personal = get_fd('personal_information')
        candidate_name = personal.get('applicant_name', '') or (student.user.name if student.user else '')
        aadhaar_number = str(personal.get('aadhaar_number', '') or '')
        community = str(personal.get('community', '') or '')
        phone = str(personal.get('student_mobile', '') or (student.user.phone_number if student.user else ''))

        # ── Parent Info ────────────────────────────────────────────────
        parent = get_fd('parent_information')
        parent_name = str(parent.get('parent_name', '') or '')
        address = str(parent.get('address', '') or '')
        pincode = str(parent.get('pincode', '') or '')

        # ── Academic Qualifications (derive highest) ─────────────────
        qualifications = get_fd('academic_qualification', 'qualifications') or []
        if not isinstance(qualifications, list):
            qualifications = []

        QUAL_PRIORITY = {'UG': 4, 'DIPLOMA': 3, 'HSC': 2, 'SSLC': 1, 'CBSE': 2}
        highest_qual = ''
        highest_priority = 0
        for q in qualifications:
            qname = str(q.get('qualification', '')).upper().strip()
            p = QUAL_PRIORITY.get(qname, 0)
            if p > highest_priority:
                highest_priority = p
                highest_qual = qname

        # ── Academic Performance (PCM marks) ─────────────────────────
        perf_rows = get_fd('academic_performance', 'academic_performance') or []
        if not isinstance(perf_rows, list):
            perf_rows = []

        def extract_marks(rows, qual_filter=None):
            marks = {'maths': None, 'physics': None, 'chemistry': None}
            SUBJECT_MAP = {
                'maths': ['maths', 'mathematics', 'math', 'maths (m)', 'maths(m)'],
                'physics': ['physics', 'phy', 'physics (p)', 'physics(p)'],
                'chemistry': ['chemistry', 'chem', 'chemistry (c)', 'chemistry(c)'],
            }
            for row in rows:
                row_qual = str(row.get('qualification', '')).upper()
                if qual_filter and qual_filter not in row_qual:
                    continue
                subj = str(row.get('subject', '')).lower().strip()
                obtained = row.get('obtained_marks')
                for mark_key, synonyms in SUBJECT_MAP.items():
                    if any(syn in subj for syn in synonyms):
                        try:
                            marks[mark_key] = int(float(obtained))
                        except (TypeError, ValueError):
                            pass
            return marks

        pcm = extract_marks(perf_rows, highest_qual)
        if all(v is None for v in pcm.values()):
            pcm = extract_marks(perf_rows)

        # ── Certificates (uploaded documents) ────────────────────────
        cert_rows = get_fd('certificates', 'certificates') or []
        if not isinstance(cert_rows, list):
            cert_rows = []
        documents = [
            {
                'certificate_type': row.get('certificate_type', ''),
                'document': row.get('document', ''),
            }
            for row in cert_rows
            if row.get('certificate_type') or row.get('document')
        ]

        # ── Course Selection ──────────────────────────────────────────
        course_sel = get_fd('course_selection')
        program = str(course_sel.get('program', '') or '')

        # ── Fees structure lookup ─────────────────────────────────────
        from institution.models import FeesStructure
        total_fees = 0.0
        if student.department and student.batch and student.quota:
            fs = FeesStructure.objects.filter(
                department=student.department,
                batch=student.batch,
                quota=student.quota
            ).first()
            if fs:
                total_fees = float(fs.fees)

        # ── Admission Slip data (StudentAdmissionSlip) ────────────────
        admission_slip = getattr(student, 'admission_slip', None)
        
        is_pg = (student.department.program.program_level == 'PG') if (student.department and student.department.program) else False
        emis_val = ""
        umis_val = ""
        scan_failed = False

        # Scan uploaded documents (TC, HSC, SSLC, Consolidated Marksheets)
        scanned_urls = []
        for doc in documents:
            ctype = str(doc.get('certificate_type', '')).lower()
            if any(keyword in ctype for keyword in ['transfer', 'tc', 'marksheet', 'hsc', 'sslc', 'consolidated', 'degree']):
                url = doc.get('document', '')
                if url:
                    scanned_urls.append(url)

        # If we have URLs, try to parse with pypdf
        parsed_text = ""
        if scanned_urls:
            import urllib.request
            import io
            from pypdf import PdfReader
            for url in scanned_urls:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=8) as response:
                        pdf_data = response.read()
                    
                    reader = PdfReader(io.BytesIO(pdf_data))
                    for page in reader.pages:
                        t = page.extract_text()
                        if t:
                            parsed_text += t + "\n"
                except Exception:
                    pass

        # Search in extracted text
        if parsed_text:
            import re
            # Search for 12-16 digit numbers starting with 33
            emis_matches = re.findall(r'\b(33\d{10,14})\b', parsed_text)
            if emis_matches:
                for m in emis_matches:
                    if m.startswith('330'):
                        emis_val = m
                        break
                if not emis_val:
                    emis_val = emis_matches[0]
            
            # Search for UMIS
            umis_match = re.search(r'\b(UMIS\d+)\b', parsed_text, re.IGNORECASE)
            if umis_match:
                umis_val = umis_match.group(1)

        # If no EMIS or UMIS was extracted, mark scan_failed as True
        if not emis_val and not umis_val:
            scan_failed = True

        pg_semester_marks = []
        if is_pg:
            saved_sem_marks = (admission_slip.certificates_surrendered.get('pg_semester_marks', [])
                               if (admission_slip and isinstance(admission_slip.certificates_surrendered, dict))
                               else [])
            if saved_sem_marks:
                pg_semester_marks = saved_sem_marks
            else:
                perf_rows = get_fd('academic_performance', 'academic_performance') or []
                if isinstance(perf_rows, list):
                    pg_semester_marks = [
                        {
                            'semester': row.get('semester', ''),
                            'obtained_marks': row.get('obtained_marks', ''),
                            'grading_system': row.get('grading_system', 'grade'),
                        }
                        for row in perf_rows
                        if row.get('semester')
                    ]

        if admission_slip:
            admission_data = {
                'id': admission_slip.id,
                'aadhaar_number': admission_slip.aadhaar_number or aadhaar_number,
                'emis_number': admission_slip.emis_number or emis_val,
                'umis_number': admission_slip.umis_number or umis_val,
                'qualification': admission_slip.qualification or '',
                'community': admission_slip.community or '',
                'marks_maths': admission_slip.marks_maths,
                'marks_physics': admission_slip.marks_physics,
                'marks_chemistry': admission_slip.marks_chemistry,
                'marks_total': admission_slip.marks_total,
                'marks_percentage': float(admission_slip.marks_percentage) if admission_slip.marks_percentage else None,
                'mode_of_admission': admission_slip.mode_of_admission,
                'certificates_surrendered': admission_slip.certificates_surrendered or {},
                'recommendation_id': admission_slip.recommendation_id,
                'recommendation_name': admission_slip.recommendation.name if admission_slip.recommendation else '',
                'pg_semester_marks': pg_semester_marks,
            }
        else:
            admission_data = {
                'id': None,
                'aadhaar_number': aadhaar_number,
                'emis_number': emis_val,
                'umis_number': umis_val,
                'qualification': '',
                'community': '',
                'marks_maths': pcm.get('maths'),
                'marks_physics': pcm.get('physics'),
                'marks_chemistry': pcm.get('chemistry'),
                'marks_total': None,
                'marks_percentage': None,
                'mode_of_admission': 'I Sem',
                'certificates_surrendered': {},
                'recommendation_id': None,
                'recommendation_name': '',
                'pg_semester_marks': pg_semester_marks,
            }

        # ── Fees data (StudentFees) ───────────────────────────────────
        fees_payment = getattr(student, 'fees_payment', None)
        if fees_payment:
            fees_data = {
                'id': fees_payment.id,
                'total_fees': float(fees_payment.total_fees) or total_fees,
                'paid_amount': float(fees_payment.paid_amount),
                'balance_amount': float(fees_payment.balance_amount),
                'books_fees_total': float(fees_payment.books_fees_total),
                'books_fees_paid': float(fees_payment.books_fees_paid),
                'due_date': fees_payment.due_date.isoformat() if fees_payment.due_date else None,
                'payment_mode': fees_payment.payment_mode,
                'remarks': fees_payment.remarks or '',
            }
        else:
            fees_data = {
                'id': None,
                'total_fees': total_fees,
                'paid_amount': 0.0,
                'balance_amount': total_fees,
                'books_fees_total': 0.0,
                'books_fees_paid': 0.0,
                'due_date': None,
                'payment_mode': 'Cash',
                'remarks': '',
            }

        # Resolve photo_url from application form_data
        photo_url = fd.get('photo', '')
        if not photo_url:
            # Check inside certificates list
            certs = fd.get('certificates') or []
            if isinstance(certs, dict) and 'certificates' in certs:
                certs = certs['certificates']
            if isinstance(certs, list):
                for c in certs:
                    if c and isinstance(c, dict) and c.get('certificate_type') == 'Passport Size Photo':
                        doc_val = c.get('document')
                        if isinstance(doc_val, str) and doc_val.startswith('http'):
                            photo_url = doc_val
                        elif isinstance(doc_val, dict) and isinstance(doc_val.get('url'), str):
                            photo_url = doc_val.get('url')
                        break
        if not photo_url:
            for key, val in fd.items():
                if isinstance(val, dict) and val.get('photo'):
                    photo_url = val.get('photo')
                    break

        # ── Users list (for recommendation dropdown) ─────────────────
        users_list = list(
            User.objects.select_related('role').values('id', 'name', 'role__role_name')
        )

        return Response({
            'code': 200,
            'message': 'Admission slip data retrieved successfully',
            'data': {
                'student': {
                    'id': student.id,
                    'name': candidate_name,
                    'roll_number': student.roll_number,
                    'phone': phone,
                    'is_hostler': student.is_hostler,
                    'is_day_scholar': student.is_day_scholar,
                    'is_bus': student.is_bus,
                    'bus_from': student.bus_from or '',
                    'bus_to': student.bus_to or '',
                    'department': student.department.department_name if student.department else '',
                    'program': program,
                    'batch': student.batch.batch if student.batch else '',
                    'quota': student.quota.quota_name if student.quota else '',
                    'application_no': app.application_no if app else '',
                    'user_id': student.user.id if student.user else None,
                    'student_photo': photo_url,
                },
                'application': {
                    'candidate_name': candidate_name,
                    'parent_name': parent_name,
                    'address': address,
                    'pincode': pincode,
                    'phone': phone,
                    'aadhaar_number': aadhaar_number,
                    'community': community,
                    'highest_qualification': highest_qual,
                    'qualifications': qualifications,
                    'academic_performance': pcm,
                    'documents': documents,
                },
                'admission': admission_data,
                'fees': fees_data,
                'users_list': users_list,
                'scan_failed': scan_failed,
                'is_pg': is_pg,
            }
        }, status=200)

    def admission_slip_save(self, request, *args, **kwargs):
        """Save admission-specific fields into StudentAdmissionSlip."""
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({"code": 400, "message": "student_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return Response({"code": 404, "message": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        admission_slip, _ = StudentAdmissionSlip.objects.get_or_create(student=student)
        serializer = StudentAdmissionSlipSerializer(admission_slip, data=request.data, partial=True)
        if serializer.is_valid():
            user = self.request.user if self.request.user and self.request.user.is_authenticated else None
            from users.models import User as StandardUser
            tracking_user = user if isinstance(user, StandardUser) else None
            serializer.save(updated_by=tracking_user)
            return Response({
                "code": 200,
                "message": "Admission slip saved successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "code": 400,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    def fees_save(self, request, *args, **kwargs):
        """Save fee payment fields into StudentFees."""
        student_id = request.data.get('student_id')
        if not student_id:
            return Response({"code": 400, "message": "student_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return Response({"code": 404, "message": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        fees_payment, _ = StudentFees.objects.get_or_create(student=student)
        serializer = StudentFeesSerializer(fees_payment, data=request.data, partial=True)
        if serializer.is_valid():
            user = self.request.user if self.request.user and self.request.user.is_authenticated else None
            from users.models import User as StandardUser
            tracking_user = user if isinstance(user, StandardUser) else None
            serializer.save(updated_by=tracking_user)
            return Response({
                "code": 200,
                "message": "Student fees saved successfully",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                "code": 400,
                "message": "Validation failed",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    def admission_slip_pdf(self, request, pk, *args, **kwargs):
        import os
        from io import BytesIO
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from PIL import Image as PILImage
        import urllib.request
        import datetime

        from institution.models import CollegeHeader

        student = get_object_or_404(Student, pk=pk)

        # Retrieve StudentAdmissionSlip and StudentFees records if they exist
        admission_slip = getattr(student, 'admission_slip', None)
        fees_payment = getattr(student, 'fees_payment', None)

        # Fallback fields to user application form_data
        app = student.user.applications.first() if student.user else None
        app_fd = app.form_data if (app and app.form_data and isinstance(app.form_data, dict)) else {}

        def get_app_val(key):
            if key in app_fd:
                return app_fd[key]
            for m_key, m_data in app_fd.items():
                if isinstance(m_data, dict) and key in m_data:
                    return m_data[key]
            return ''

        # Extract values
        student_name = student.user.name if student.user else ''
        app_no = app.application_no if app else ''
        dept_name = student.department.department_name if student.department else ''
        batch_name = student.batch.batch if student.batch else ''
        quota_name = student.quota.quota_name if student.quota else ''

        # Address & Parents Info
        parent_name = get_app_val('parent_name') or get_app_val('father_name') or get_app_val('guardian_name') or ''
        address = get_app_val('address') or get_app_val('communication_address') or ''
        pincode = get_app_val('pincode') or ''
        phone_number = student.user.phone_number if student.user else ''

        # Qualification checkboxes — read from StudentAdmissionSlip
        qualification = (admission_slip.qualification if admission_slip else get_app_val('qualification') or '').upper()
        hsc_chk = "[X]" if "HSC" in qualification else "[   ]"
        cbse_chk = "[X]" if "CBSE" in qualification else "[   ]"
        diploma_chk = "[X]" if "DIPLOMA" in qualification or "DIP" in qualification else "[   ]"
        ug_chk = "[X]" if "UG" in qualification or "UNDER" in qualification else "[   ]"

        # Community Checkboxes — read from StudentAdmissionSlip
        community = (admission_slip.community if admission_slip else get_app_val('community') or '').upper()
        oc_chk = "[X]" if "OC" in community else "[   ]"
        bc_chk = "[X]" if "BC" in community else "[   ]"
        mbc_chk = "[X]" if "MBC" in community else "[   ]"
        sc_chk = "[X]" if "SC" in community else "[   ]"
        st_chk = "[X]" if "ST" in community else "[   ]"

        # Mode of Admission — read from StudentAdmissionSlip
        is_pg = (student.department.program.program_level == 'PG') if (student.department and student.department.program) else False
        
        # Prepare Semester Marks if PG
        sem_marks_str = ""
        avg_val_str = "—"
        if is_pg and app_fd:
            perf_rows = app_fd.get('academic_performance', {}).get('academic_performance', [])
            if isinstance(perf_rows, list):
                sem_list = []
                valid_marks = []
                for r in perf_rows:
                    sem = r.get('semester')
                    obt = r.get('obtained_marks')
                    if sem and obt:
                        sem_short = sem.replace('Semester ', 'Sem ')
                        sem_list.append(f"{sem_short}: {obt}")
                        try:
                            valid_marks.append(float(obt))
                        except ValueError:
                            pass
                sem_marks_str = ", ".join(sem_list)
                if valid_marks:
                    avg_val = sum(valid_marks) / len(valid_marks)
                    grading_system = perf_rows[0].get('grading_system', 'grade') if perf_rows else 'grade'
                    unit = "" if grading_system == 'grade' else "%"
                    avg_val_str = f"{avg_val:.2f}{unit} ({grading_system.capitalize()})"

        # Marks details — read from StudentAdmissionSlip
        marks_maths = admission_slip.marks_maths if admission_slip else None
        marks_physics = admission_slip.marks_physics if admission_slip else None
        marks_chemistry = admission_slip.marks_chemistry if admission_slip else None
        marks_total = admission_slip.marks_total if admission_slip else None
        marks_percentage = admission_slip.marks_percentage if admission_slip else None

        if not is_pg and marks_maths is None:
            # Fallback to application form
            try:
                marks_maths = int(get_app_val('marks_maths') or get_app_val('maths') or 0)
                marks_physics = int(get_app_val('marks_physics') or get_app_val('physics') or 0)
                marks_chemistry = int(get_app_val('marks_chemistry') or get_app_val('chemistry') or 0)
                marks_total = int(get_app_val('marks_total') or get_app_val('total_marks') or 0)
                marks_percentage = get_app_val('marks_percentage') or get_app_val('percentage') or 0.0
            except ValueError:
                pass

        # Mode of Admission — read from StudentAdmissionSlip
        moa = admission_slip.mode_of_admission if admission_slip else 'I Sem'
        sem1_chk = "[X]" if "I Sem" in moa or "1" in moa else "[   ]"
        sem3_chk = "[X]" if "III Sem" in moa or "3" in moa or "Lateral" in moa else "[   ]"

        # Fees Details — read from StudentFees
        total_fees = float(fees_payment.total_fees) if fees_payment else 0.0
        if total_fees == 0.0:
            # Fallback from matched FeesStructure
            from institution.models import FeesStructure
            if student.department and student.batch and student.quota:
                fs = FeesStructure.objects.filter(
                    department=student.department,
                    batch=student.batch,
                    quota=student.quota
                ).first()
                if fs:
                    total_fees = float(fs.fees)

        paid_amount = float(fees_payment.paid_amount) if fees_payment else 0.0
        balance_amount = float(fees_payment.balance_amount) if fees_payment else total_fees
        books_fees_total = float(fees_payment.books_fees_total) if fees_payment else 0.0
        books_fees_paid = float(fees_payment.books_fees_paid) if fees_payment else 0.0
        books_fees_balance = max(0.0, books_fees_total - books_fees_paid)
        grand_total = total_fees + books_fees_total
        grand_paid = paid_amount + books_fees_paid
        grand_balance = max(0.0, grand_total - grand_paid)
        due_date_str = ''
        if fees_payment and fees_payment.due_date:
            due_date_str = fees_payment.due_date.strftime('%d/%m/%Y')

        # Recommendation — read from StudentAdmissionSlip
        recommendation_name = ''
        if admission_slip and admission_slip.recommendation:
            recommendation_name = admission_slip.recommendation.name

        # Payment Mode — read from StudentFees
        pay_mode = (fees_payment.payment_mode if fees_payment else 'Cash').upper()
        cash_chk = "[X]" if "CASH" in pay_mode else "[   ]"
        dd_chk = "[X]" if "DD" in pay_mode or "D.D" in pay_mode else "[   ]"
        upi_chk = "[X]" if "UPI" in pay_mode else "[   ]"

        # Credentials — read from StudentAdmissionSlip
        aadhaar = admission_slip.aadhaar_number if admission_slip else ''
        emis = admission_slip.emis_number if admission_slip else ''
        umis = admission_slip.umis_number if admission_slip else ''

        # Certificates Surrendered checklist — read from StudentAdmissionSlip
        certs = admission_slip.certificates_surrendered if (admission_slip and admission_slip.certificates_surrendered) else {}
        def cert_chk(name):
            return "[X]" if certs.get(name) else "[   ]"

        # Hostler Details
        hostler_chk = "[X]" if student.is_hostler else "[   ]"
        day_scholar_chk = "[X]" if student.is_day_scholar else "[   ]"
        bus_chk = "[X]" if student.is_bus else "[   ]"
        bus_from = student.bus_from or ''
        bus_to = student.bus_to or ''

        # Build PDF doc
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=30,
            bottomMargin=30
        )

        # PDF Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            name='TEC_Title',
            fontName='Helvetica-Bold',
            fontSize=14,
            textColor=colors.HexColor('#0B2C5D'),
            alignment=1,
            spaceAfter=2
        )
        sub_style = ParagraphStyle(
            name='TEC_Sub',
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=colors.HexColor('#333333'),
            alignment=1,
            spaceAfter=3
        )
        addr_style = ParagraphStyle(
            name='TEC_Addr',
            fontName='Helvetica',
            fontSize=8,
            textColor=colors.HexColor('#555555'),
            alignment=1,
            spaceAfter=4
        )
        body_style = ParagraphStyle(
            name='TEC_Body',
            fontName='Helvetica',
            fontSize=8,
            textColor=colors.black,
            leading=10
        )
        body_bold = ParagraphStyle(
            name='TEC_Body_Bold',
            fontName='Helvetica-Bold',
            fontSize=8.5,
            textColor=colors.black,
            leading=10
        )

        # Define Paragraph variables using styles
        if is_pg:
            qualifying_exam_label = Paragraph("<b>6. Semester Marks (UG):</b>", body_style)
            qualifying_exam_val = Paragraph(sem_marks_str or '—', body_style)
            total_pct_label = Paragraph("<b>Average / System:</b>", body_style)
            total_pct_val = Paragraph(avg_val_str, body_bold)
        else:
            qualifying_exam_label = Paragraph("<b>6. Qualifying Examination Marks:</b>", body_style)
            qualifying_exam_val = Paragraph(f"Maths: {marks_maths or '—'}/200 &nbsp;&nbsp; Physics: {marks_physics or '—'}/200 &nbsp;&nbsp; Chemistry: {marks_chemistry or '—'}/200", body_style)
            total_pct_label = Paragraph("<b>Cutoff / 200:</b>", body_style)
            
            try:
                m = float(marks_maths or 0)
                p = float(marks_physics or 0)
                c = float(marks_chemistry or 0)
                # Cutoff calculation (out of 200)
                cutoff_val = m + ((p + c) / 2)
                cutoff_str = f"{cutoff_val:.1f}" if cutoff_val > 0 else '—'
                if cutoff_str.endswith('.0'):
                    cutoff_str = cutoff_str[:-2]
            except (ValueError, TypeError):
                cutoff_str = '—'
                
            total_pct_val = Paragraph(cutoff_str, body_bold)

        # Helper to load image
        def load_image(url_or_path, width, height):
            if not url_or_path:
                return None
            try:
                if isinstance(url_or_path, str) and url_or_path.startswith('http'):
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    req = urllib.request.Request(url_or_path, headers=headers)
                    with urllib.request.urlopen(req, timeout=5) as response:
                        img_data = response.read()
                        pil_img = PILImage.open(BytesIO(img_data))
                        out_io = BytesIO()
                        pil_img.save(out_io, format='PNG')
                        out_io.seek(0)
                        return RLImage(out_io, width=width, height=height)
                else:
                    if os.path.exists(url_or_path):
                        pil_img = PILImage.open(url_or_path)
                        out_io = BytesIO()
                        pil_img.save(out_io, format='PNG')
                        out_io.seek(0)
                        return RLImage(out_io, width=width, height=height)
            except Exception:
                pass
            return None

        college_header_obj = CollegeHeader.objects.filter(header_type='Main').first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        college_name = college_header_obj.college_name if college_header_obj else 'THIRUMALAI ENGINEERING COLLEGE'
        college_address = college_header_obj.address if college_header_obj else 'Kancheepuram, Tamil Nadu.'
        logo_url = college_header_obj.primary_logo if college_header_obj else None

        logo_flowable = None
        if logo_url:
            logo_flowable = load_image(logo_url, 44, 44)
        if not logo_flowable:
            fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
            logo_flowable = load_image(fallback_logo_path, 44, 44)

        story = []

        # 1. Header Grid with logo
        header_text = [
            [Paragraph(college_name.upper(), title_style)],
            [Paragraph("ADMISSION SLIP", sub_style)],
            [Paragraph(f"B.E., / B.Tech. / MBA / MCA / M.E. (Batch: {batch_name})", ParagraphStyle(name='TEC_Heading_Batch', fontName='Helvetica-Bold', fontSize=9, textColor=colors.HexColor('#0B2C5D'), alignment=1))],
            [Paragraph(college_address, addr_style)],
        ]
        mid_t = Table(header_text, colWidths=[450])
        mid_t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))

        header_table_cells = []
        if logo_flowable:
            header_table_cells = [[logo_flowable, mid_t]]
            header_table = Table(header_table_cells, colWidths=[55, 465])
        else:
            header_table = Table([[mid_t]], colWidths=[520])

        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        # 2. Main details grid
        curr_date = datetime.date.today().strftime("%d-%m-%Y")
        details = [
            [
                Paragraph("<b>1. Name of the Student:</b>", body_style),
                Paragraph(student_name, body_bold),
                Paragraph("<b>Date:</b>", body_style),
                Paragraph(curr_date, body_bold)
            ],
            [
                Paragraph("<b>Category:</b>", body_style),
                Paragraph(quota_name, body_bold),
                Paragraph("<b>App. No:</b>", body_style),
                Paragraph(app_no, body_bold)
            ],
            [
                Paragraph("<b>2. Course Allotted:</b>", body_style),
                Paragraph(dept_name, body_bold),
                Paragraph("", body_style),
                Paragraph("", body_bold)
            ],
            [
                Paragraph("<b>3. Qualification (Tick):</b>", body_style),
                Paragraph(f"{hsc_chk} HSC &nbsp;&nbsp;&nbsp;&nbsp; {cbse_chk} CBSE &nbsp;&nbsp;&nbsp;&nbsp; {diploma_chk} DIPLOMA &nbsp;&nbsp;&nbsp;&nbsp; {ug_chk} UG", body_style),
                Paragraph("", body_style),
                Paragraph("", body_bold)
            ],
            [
                Paragraph("<b>4. Communication Address:</b>", body_style),
                Paragraph(address, body_style),
                Paragraph("<b>Father's / Guardian Name:</b>", body_style),
                Paragraph(parent_name, body_bold)
            ],
            [
                Paragraph("<b>Pin Code:</b>", body_style),
                Paragraph(pincode, body_style),
                Paragraph("<b>Phone:</b>", body_style),
                Paragraph(phone_number, body_style)
            ],
            [
                Paragraph("<b>5. Community (Tick):</b>", body_style),
                Paragraph(f"{oc_chk} OC &nbsp;&nbsp;&nbsp;&nbsp; {bc_chk} BC &nbsp;&nbsp;&nbsp;&nbsp; {mbc_chk} MBC &nbsp;&nbsp;&nbsp;&nbsp; {sc_chk} SC &nbsp;&nbsp;&nbsp;&nbsp; {st_chk} ST", body_style),
                Paragraph("", body_style),
                Paragraph("", body_bold)
            ],
            [
                qualifying_exam_label,
                qualifying_exam_val,
                total_pct_label,
                total_pct_val
            ],
            [
                Paragraph("<b>7. Mode of Admission:</b>", body_style),
                Paragraph(f"{sem1_chk} I Sem (Regular) &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; {sem3_chk} III Sem (Lateral Entry)", body_style),
                Paragraph("", body_style),
                Paragraph("", body_bold)
            ]
        ]
        
        details_table = Table(details, colWidths=[120, 140, 120, 140])
        details_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('SPAN', (1,2), (3,2)),
            ('SPAN', (1,3), (3,3)),
            ('SPAN', (1,6), (3,6)),
            ('SPAN', (1,8), (3,8)),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,0), (2,1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,4), (2,5), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2,7), (2,7), colors.HexColor('#F8FAFC')),
        ]))
        story.append(details_table)
        story.append(Spacer(1, 10))

        # 3. Fees table
        fee_header_style = ParagraphStyle(name='TEC_FeeH', fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#475569'), alignment=1)
        fees_headers = [
            Paragraph("<b>Fees Details</b>", ParagraphStyle(name='TEC_FeeH_Left', fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor('#475569'))),
            Paragraph("<b>Fees fixed at the time of admission</b>", fee_header_style),
            Paragraph("<b>Paid amount at the time of admission</b>", fee_header_style),
            Paragraph("<b>Balance Rs.</b>", fee_header_style),
            Paragraph("<b>Remarks / Due Date</b>", fee_header_style),
        ]
        
        fees_data = [
            fees_headers,
            [
                Paragraph("Tuition Fees", body_style),
                Paragraph(f"{total_fees:,.2f}", ParagraphStyle(name='TEC_R', fontName='Helvetica', fontSize=8, alignment=2)),
                Paragraph(f"{paid_amount:,.2f}", ParagraphStyle(name='TEC_R2', fontName='Helvetica', fontSize=8, alignment=2)),
                Paragraph(f"{balance_amount:,.2f}", ParagraphStyle(name='TEC_R3', fontName='Helvetica', fontSize=8, alignment=2)),
                Paragraph(due_date_str or '—', ParagraphStyle(name='TEC_C', fontName='Helvetica', fontSize=8, alignment=1)),
            ],
            [
                Paragraph("Books Uniforms & Internet", body_style),
                Paragraph(f"{books_fees_total:,.2f}", ParagraphStyle(name='TEC_R_B2', fontName='Helvetica', fontSize=8, alignment=2)),
                Paragraph(f"{books_fees_paid:,.2f}", ParagraphStyle(name='TEC_R2_B2', fontName='Helvetica', fontSize=8, alignment=2)),
                Paragraph(f"{books_fees_balance:,.2f}", ParagraphStyle(name='TEC_R3_B2', fontName='Helvetica', fontSize=8, alignment=2)),
                Paragraph('—', ParagraphStyle(name='TEC_C2', fontName='Helvetica', fontSize=8, alignment=1)),
            ],
            [
                Paragraph("<b>Total</b>", body_bold),
                Paragraph(f"<b>{grand_total:,.2f}</b>", ParagraphStyle(name='TEC_R_B', fontName='Helvetica-Bold', fontSize=8, alignment=2)),
                Paragraph(f"<b>{grand_paid:,.2f}</b>", ParagraphStyle(name='TEC_R2_B', fontName='Helvetica-Bold', fontSize=8, alignment=2)),
                Paragraph(f"<b>{grand_balance:,.2f}</b>", ParagraphStyle(name='TEC_R3_B', fontName='Helvetica-Bold', fontSize=8, alignment=2)),
                Paragraph("—", ParagraphStyle(name='TEC_C_T', fontName='Helvetica', fontSize=8, alignment=1)),
            ]
        ]
        
        fees_table = Table(fees_data, colWidths=[150, 95, 95, 90, 90])
        fees_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F1F5F9')),
            ('BACKGROUND', (0,3), (-1,3), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        story.append(fees_table)
        story.append(Spacer(1, 10))

        # 4. Mode of payment & accommodation
        pay_info = [
            [
                Paragraph("<b>9. Mode of Payment:</b>", body_style),
                Paragraph(f"{cash_chk} Cash &nbsp;&nbsp;&nbsp;&nbsp; {dd_chk} D.D. &nbsp;&nbsp;&nbsp;&nbsp; {upi_chk} UPI", body_style),
                Paragraph("<b>Aadhaar Number:</b>", body_style),
                Paragraph(aadhaar or '—', body_bold)
            ],
            [
                Paragraph("", body_style),
                Paragraph("", body_style),
                Paragraph("<b>EMIS Number:</b>", body_style),
                Paragraph(emis or '—', body_bold)
            ],
            [
                Paragraph("", body_style),
                Paragraph("", body_style),
                Paragraph("<b>UMIS Number:</b>", body_style),
                Paragraph(umis or '—', body_bold)
            ],
            [
                Paragraph("<b>10. Recommendation:</b>", body_style),
                Paragraph(recommendation_name or '—', body_bold),
                Paragraph("", body_style),
                Paragraph("", body_style),
            ],
            [
                Paragraph("<b>12. Hosteller (Tick):</b>", body_style),
                Paragraph(f"{hostler_chk} Hosteller &nbsp;&nbsp; {day_scholar_chk} Day Scholar &nbsp;&nbsp; {bus_chk} Bus", body_style),
                Paragraph("<b>Bus Place:</b>", body_style),
                Paragraph(f"From {bus_from or '—'} to {bus_to or '—'}", body_bold)
            ]
        ]
        pay_table = Table(pay_info, colWidths=[120, 140, 120, 140])
        pay_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
            ('SPAN', (0,0), (0,2)),   # "Mode of Payment" label spans rows 0-2
            ('SPAN', (1,0), (1,2)),   # mode checkboxes span rows 0-2
            ('BACKGROUND', (0,0), (1,2), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (0,3), (-1,3), colors.HexColor('#FFF7ED')),  # recommendation row highlight
        ]))
        story.append(pay_table)
        story.append(Spacer(1, 10))

        # 5. Certificates checklist
        cert_style = ParagraphStyle(name='TEC_Cert', fontName='Helvetica', fontSize=7.5, leading=9.5)
        certs_table_data = [
            [
                Paragraph("<b>13. Original Certificates Surrendered:</b>", body_bold),
                Paragraph("", body_style)
            ],
            [
                Paragraph(f"{cert_chk('tc')} Transfer Certificate", cert_style),
                Paragraph(f"{cert_chk('counselling')} Intimation of Counselling", cert_style)
            ],
            [
                Paragraph(f"{cert_chk('mark_sheet')} Qualification Exam Mark Sheet", cert_style),
                Paragraph(f"{cert_chk('hall_ticket')} TNPCEE Hall Ticket", cert_style)
            ],
            [
                Paragraph(f"{cert_chk('community')} Community Certificate", cert_style),
                Paragraph(f"{cert_chk('tnpcee_mark_sheet')} TNPCEE Mark Sheet", cert_style)
            ],
            [
                Paragraph(f"{cert_chk('photo')} Pass Port Size Photo (3 Nos)", cert_style),
                Paragraph(f"{cert_chk('allotment')} Intimation for Allotment", cert_style)
            ],
            [
                Paragraph(f"{cert_chk('diploma')} Diploma Certificate 1st / 6th Marksheet", cert_style),
                Paragraph(f"{cert_chk('provisional')} Provisional Certificates", cert_style)
            ],
            [
                Paragraph("", cert_style),
                Paragraph(f"{cert_chk('first_graduate')} F.G. (First Graduate) Certificate", cert_style)
            ]
        ]
        
        certs_table = Table(certs_table_data, colWidths=[260, 260])
        certs_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('SPAN', (0,0), (1,0)),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(certs_table)
        story.append(Spacer(1, 12))

        # 6. Declaration & Signatures
        dec_style = ParagraphStyle(
            name='TEC_Dec',
            fontName='Helvetica-Oblique',
            fontSize=6.5,
            textColor=colors.HexColor('#475569'),
            leading=8.5,
            alignment=4
        )
        story.append(Paragraph("<b>DECLARATION:</b> I hereby declare that I will not be allowed to cancel or withdraw the admission for the reason like: 1. Getting Free / Payment Seat; 2. Getting Seat in other Engg. College or Arts Colleges; 3. Or any other reasons. If the above information is found to be incorrect, I know I will lose the admission. Under any circumstances the remitted fees cannot be refunded.", dec_style))
        story.append(Spacer(1, 20))

        # Signatures line table
        sign_style = ParagraphStyle(name='TEC_Sign', fontName='Helvetica-Bold', fontSize=8, alignment=1)
        sign_data = [
            [
                Paragraph("<b>Signature of the Candidate</b>", sign_style),
                Paragraph("<b>Signature of the Parent</b>", sign_style),
                Paragraph("<b>Principal</b>", sign_style)
            ]
        ]
        sign_table = Table(sign_data, colWidths=[173, 173, 174])
        sign_table.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,-1), 0.5, colors.HexColor('#94a3b8')),
            ('TOPPADDING', (0,0), (-1,-1), 5),
        ]))
        
        verify_data = [
            [
                Paragraph("<b>Verified by:</b> ___________________________", ParagraphStyle(name='TEC_V1', fontName='Helvetica', fontSize=7.5)),
                Paragraph("<b>Name:</b> ________________________ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; <b>Signature:</b> ________________________", ParagraphStyle(name='TEC_V2', fontName='Helvetica', fontSize=7.5))
            ]
        ]
        verify_table = Table(verify_data, colWidths=[180, 340])
        verify_table.setStyle(TableStyle([
            ('TOPPADDING', (0,0), (-1,-1), 8),
        ]))

        footer_keep = KeepTogether([
            sign_table,
            Spacer(1, 10),
            verify_table
        ])
        story.append(footer_keep)

        # Build PDF Document
        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        # HttpResponse
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Admission_Slip_{student.id}.pdf"'
        response.write(pdf)
        return response

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        import bcrypt
        from django.db import transaction
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        from datetime import datetime
        import datetime as dt
        from dynamic_forms.models import ApplicationUser, Application, ApplicationStatus
        from institution.models import Department, Batch, Section, Quota
        from student.models import Student, StudentStatus, StudentAdmissionSlip, StudentFees
        from users.models import User as StandardUser

        def parse_date(date_str):
            if not date_str:
                return None
            if isinstance(date_str, datetime):
                return date_str.date()
            if isinstance(date_str, dt.date):
                return date_str
            date_str = str(date_str).strip()
            if not date_str:
                return None
            if 'T' in date_str:
                date_str = date_str.split('T')[0]
            elif ' ' in date_str:
                date_str = date_str.split(' ')[0]
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y'):
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    pass
            return None

        students_data = request.data.get('students', [])
        if not students_data:
            return Response({
                "code": 400,
                "message": "No student data provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Cache lookups
        depts_map = {d.department_code.upper(): d for d in Department.objects.all()}
        depts_name_map = {d.department_name.upper(): d for d in Department.objects.all()}
        depts_short_map = {d.short_name.upper(): d for d in Department.objects.all()}

        batches_map = {b.batch.upper(): b for b in Batch.objects.all() if b.batch}
        
        sections_map = {}
        for s in Section.objects.all():
            if isinstance(s.sections, list):
                for sec in s.sections:
                    sections_map[(s.department_id, str(sec).upper())] = s
            else:
                sections_map[(s.department_id, str(s.sections).upper())] = s

        quotas_map = {q.quota_name.upper(): q for q in Quota.objects.all()}
        
        # Staff maps for recommendation
        staff_map_by_name = {u.name.upper(): u for u in StandardUser.objects.all()}
        staff_map_by_username = {u.username.upper(): u for u in StandardUser.objects.all()}

        # Student status
        active_status, _ = StudentStatus.objects.get_or_create(status_name='Active')

        seen_emails = set()
        seen_rolls = set()
        seen_registers = set()

        errors = []
        validated_students = []

        # Helper parsers
        def parse_int_or_none(val):
            if val is None:
                return None
            val_str = str(val).strip()
            if not val_str:
                return None
            try:
                return int(float(val_str))
            except (ValueError, TypeError):
                return None

        def parse_decimal_or_none(val):
            if val is None:
                return None
            val_str = str(val).strip()
            if not val_str:
                return None
            try:
                return float(val_str)
            except (ValueError, TypeError):
                return None

        # 1. Validation Phase (No DB writes)
        for idx, s in enumerate(students_data):
            row_num = s.get('s_no', idx + 1)
            name = str(s.get('name', '')).strip()
            email = str(s.get('email', '')).strip()
            phone_number = str(s.get('phone_number', '')).strip()
            roll_number = str(s.get('roll_number', '')).strip()
            register_number = str(s.get('register_number', '')).strip()
            
            department_name = str(s.get('department', '')).strip()
            batch_name = str(s.get('batch', '')).strip()
            section_name = str(s.get('section', '')).strip().upper()
            quota_name = str(s.get('quota', '')).strip()
            lab_batch = str(s.get('lab_batch', '')).strip()

            is_hostler_raw = str(s.get('is_hostler', '')).strip().lower()
            is_day_scholar_raw = str(s.get('is_day_scholar', '')).strip().lower()
            is_bus_raw = str(s.get('is_bus', '')).strip().lower()
            bus_from = str(s.get('bus_from', '')).strip()
            bus_to = str(s.get('bus_to', '')).strip()

            # Additional Application Slip Details
            parent_name = str(s.get('parent_name', '')).strip()
            address = str(s.get('address', '')).strip()
            pincode = str(s.get('pincode', '')).strip()
            aadhaar_number = str(s.get('aadhaar_number', '')).strip()
            emis_number = str(s.get('emis_number', '')).strip()
            umis_number = str(s.get('umis_number', '')).strip()
            community = str(s.get('community', '')).strip()
            qualification = str(s.get('qualification', '')).strip()

            marks_maths = parse_int_or_none(s.get('marks_maths'))
            marks_physics = parse_int_or_none(s.get('marks_physics'))
            marks_chemistry = parse_int_or_none(s.get('marks_chemistry'))
            marks_total = parse_int_or_none(s.get('marks_total'))
            marks_percentage = parse_decimal_or_none(s.get('marks_percentage'))
            
            mode_of_admission = str(s.get('mode_of_admission', '')).strip() or 'I Sem'
            recommendation_name = str(s.get('recommendation', '')).strip()

            row_errors = []

            # Check required fields
            if not name:
                row_errors.append("Name is required.")
            if not email:
                row_errors.append("Email is required.")
            else:
                try:
                    validate_email(email)
                except DjangoValidationError:
                    row_errors.append("Invalid email address format.")

            if not phone_number:
                row_errors.append("Phone number is required.")
            elif not (phone_number.isdigit() and len(phone_number) == 10):
                row_errors.append("Phone number must be exactly 10 digits.")

            # Resolve Department
            dept_instance = None
            if not department_name:
                row_errors.append("Department is required.")
            else:
                dept_key = department_name.upper()
                if dept_key in depts_map:
                    dept_instance = depts_map[dept_key]
                elif dept_key in depts_name_map:
                    dept_instance = depts_name_map[dept_key]
                elif dept_key in depts_short_map:
                    dept_instance = depts_short_map[dept_key]
                else:
                    row_errors.append(f"Department '{department_name}' does not exist.")

            # Resolve Batch
            batch_instance = None
            if not batch_name:
                row_errors.append("Batch is required.")
            else:
                if dept_instance:
                    from institution.models import Batch
                    batch_instance = Batch.objects.filter(department=dept_instance, batch__iexact=batch_name).first()
                    if not batch_instance:
                        row_errors.append(f"Batch '{batch_name}' does not exist for the resolved department.")
                else:
                    row_errors.append("Department must be valid to map batch.")

            # Resolve Section (optional)
            section_instance = None
            if section_name and dept_instance:
                sec_key = (dept_instance.id, section_name)
                if sec_key in sections_map:
                    section_instance = sections_map[sec_key]
                else:
                    matched_sec = Section.objects.filter(department=dept_instance, sections__iexact=section_name).first()
                    if matched_sec:
                        section_instance = matched_sec
                    else:
                        row_errors.append(f"Section '{section_name}' does not exist for the resolved department.")

            # Resolve Quota (optional)
            quota_instance = None
            if quota_name:
                quota_key = quota_name.upper()
                if quota_key in quotas_map:
                    quota_instance = quotas_map[quota_key]
                else:
                    row_errors.append(f"Quota/Category '{quota_name}' does not exist.")

            # Resolve recommendation staff (optional)
            recommendation_user = None
            if recommendation_name:
                rec_key = recommendation_name.upper()
                if rec_key in staff_map_by_name:
                    recommendation_user = staff_map_by_name[rec_key]
                elif rec_key in staff_map_by_username:
                    recommendation_user = staff_map_by_username[rec_key]
                else:
                    # Let it slide as None, but print a warning/message if needed
                    pass

            # Resolve facilities flags
            is_hostler = is_hostler_raw in ['yes', 'true', '1']
            is_day_scholar = is_day_scholar_raw in ['yes', 'true', '1']
            is_bus = is_bus_raw in ['yes', 'true', '1']

            # Check database-level uniqueness if no errors so far
            if not row_errors:
                # Check for duplicates in current sheet
                if email in seen_emails:
                    row_errors.append(f"Duplicate email '{email}' inside this sheet.")
                if roll_number and roll_number in seen_rolls:
                    row_errors.append(f"Duplicate roll number '{roll_number}' inside this sheet.")
                if register_number and register_number in seen_registers:
                    row_errors.append(f"Duplicate register number '{register_number}' inside this sheet.")

                # Check database records
                if ApplicationUser.objects.filter(email=email).exists():
                    row_errors.append(f"Email '{email}' is already registered as an application user.")
                if roll_number and Student.objects.filter(roll_number=roll_number).exists():
                    row_errors.append(f"Roll number '{roll_number}' is already assigned.")
                if register_number and Student.objects.filter(register_number=register_number).exists():
                    row_errors.append(f"Register number '{register_number}' is already assigned.")

                if not row_errors:
                    seen_emails.add(email)
                    if roll_number:
                        seen_rolls.add(roll_number)
                    if register_number:
                        seen_registers.add(register_number)

                    validated_students.append({
                        "name": name,
                        "email": email,
                        "phone_number": phone_number,
                        "roll_number": roll_number or None,
                        "register_number": register_number or None,
                        "department": dept_instance,
                        "batch": batch_instance,
                        "section": section_instance,
                        "quota": quota_instance,
                        "lab_batch": lab_batch or None,
                        "is_hostler": is_hostler,
                        "is_day_scholar": is_day_scholar,
                        "is_bus": is_bus,
                        "bus_from": bus_from or None,
                        "bus_to": bus_to or None,
                        
                        # Add slip fields
                        "parent_name": parent_name,
                        "address": address,
                        "pincode": pincode,
                        "aadhaar_number": aadhaar_number,
                        "emis_number": emis_number,
                        "umis_number": umis_number,
                        "community": community,
                        "qualification": qualification,
                        "marks_maths": marks_maths,
                        "marks_physics": marks_physics,
                        "marks_chemistry": marks_chemistry,
                        "marks_total": marks_total,
                        "marks_percentage": marks_percentage,
                        "mode_of_admission": mode_of_admission,
                        "recommendation": recommendation_user
                    })

            if row_errors:
                errors.append({
                    "row": row_num,
                    "roll_number": roll_number,
                    "name": name,
                    "errors": row_errors
                })

        # If any validation errors exist, fail and do not write to the DB
        if errors:
            return Response({
                "code": 400,
                "message": "Validation errors found in the import data.",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Writing Phase (transactional)
        tracking_user = request.user if request.user and request.user.is_authenticated else None
        tracking_user = tracking_user if isinstance(tracking_user, StandardUser) else None

        # Resolve 'Approved' Application Status
        approved_app_status, _ = ApplicationStatus.objects.get_or_create(status_name='Approved')

        imported_students_count = 0
        try:
            with transaction.atomic():
                program_indices = {}

                for item in validated_students:
                    app_user = ApplicationUser.objects.create(
                        name=item["name"],
                        email=item["email"],
                        phone_number=item["phone_number"],
                        password=item["phone_number"],
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    program = item["department"].program
                    year = datetime.now().year
                    year_str = str(year)[2:]
                    prefix = f"{program.program_level}{year_str}"

                    if prefix not in program_indices:
                        last_app = Application.objects.filter(application_no__startswith=prefix).order_by('-application_no').first()
                        next_num = 1
                        if last_app and last_app.application_no:
                            try:
                                next_num = int(last_app.application_no[len(prefix):]) + 1
                            except ValueError:
                                pass
                        program_indices[prefix] = next_num
                    
                    app_no = f"{prefix}{program_indices[prefix]:04d}"
                    program_indices[prefix] += 1

                    form_data = {
                        "personal_information": {
                            "applicant_name": item["name"],
                            "student_mobile": item["phone_number"],
                            "email": item["email"],
                            "aadhaar_number": item["aadhaar_number"] or "",
                            "community": item["community"] or "",
                        },
                        "parent_information": {
                            "parent_name": item["parent_name"] or "",
                            "address": item["address"] or "",
                            "pincode": item["pincode"] or "",
                        },
                        "course_selection": {
                            "program": program.program_name,
                            "department": item["department"].department_name,
                        },
                        "academic_qualification": {
                            "qualifications": [
                                {
                                    "qualification": item["qualification"] or "",
                                }
                            ]
                        },
                        "academic_performance": {
                            "academic_performance": [
                                {"subject": "Mathematics", "obtained_marks": str(item["marks_maths"]) if item["marks_maths"] is not None else ""},
                                {"subject": "Physics", "obtained_marks": str(item["marks_physics"]) if item["marks_physics"] is not None else ""},
                                {"subject": "Chemistry", "obtained_marks": str(item["marks_chemistry"]) if item["marks_chemistry"] is not None else ""}
                            ]
                        }
                    }

                    Application.objects.create(
                        candidate=app_user,
                        program=program,
                        application_no=app_no,
                        form_data=form_data,
                        status=approved_app_status,
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    student = Student.objects.create(
                        roll_number=item["roll_number"],
                        register_number=item["register_number"],
                        department=item["department"],
                        section=item["section"],
                        batch=item["batch"],
                        user=app_user,
                        lab_batch=item["lab_batch"],
                        quota=item["quota"],
                        is_hostler=item["is_hostler"],
                        is_day_scholar=item["is_day_scholar"],
                        is_bus=item["is_bus"],
                        bus_from=item["bus_from"],
                        bus_to=item["bus_to"],
                        status=active_status,
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    # Create StudentAdmissionSlip eagerly
                    StudentAdmissionSlip.objects.create(
                        student=student,
                        aadhaar_number=item["aadhaar_number"] or None,
                        emis_number=item["emis_number"] or f"EMIS-{app_no}",
                        umis_number=item["umis_number"] or None,
                        qualification=item["qualification"] or None,
                        community=item["community"] or None,
                        marks_maths=item["marks_maths"],
                        marks_physics=item["marks_physics"],
                        marks_chemistry=item["marks_chemistry"],
                        marks_total=item["marks_total"],
                        marks_percentage=item["marks_percentage"],
                        mode_of_admission=item["mode_of_admission"] or 'I Sem',
                        recommendation=item["recommendation"],
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    # Create StudentFees eagerly from database Fee Structure
                    from institution.models import FeesStructure
                    total_fees = 0.0
                    if student.department and student.batch and student.quota:
                        fs = FeesStructure.objects.filter(
                            department=student.department,
                            batch=student.batch,
                            quota=student.quota
                        ).first()
                        if fs:
                            total_fees = float(fs.fees)

                    StudentFees.objects.create(
                        student=student,
                        total_fees=total_fees,
                        paid_amount=0.0,
                        balance_amount=total_fees,
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    self._broadcast_change(student, 'student_created')
                    imported_students_count += 1

        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Database error during student import: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "code": 201,
            "message": f"Successfully imported {imported_students_count} students.",
            "data": {
                "count": imported_students_count
            }
        }, status=status.HTTP_201_CREATED)




from django.db import transaction
from rest_framework.permissions import IsAuthenticated
from users.permissions import IsMarksManager
from .models import Marks
from .serializers import MarksSerializer
from institution.models import Exam
from subject.models import Subject

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
        queryset = Marks.objects.all().order_by('id')
        
        user = request.user
        role_name = ""
        if user and user.is_authenticated and hasattr(user, 'role') and user.role:
            role_name = user.role.role_name.upper().replace(' ', '_')
            
        exam_id = request.query_params.get('exam_id')
        subject_id = request.query_params.get('subject_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')

        if role_name not in ['ADMIN', 'ADMINISTRATOR']:
            if not (exam_id or subject_id):
                queryset = queryset.filter(created_by=user)

        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if batch_id:
            queryset = queryset.filter(student__batch_id=batch_id)
        if section_id:
            if str(section_id).isdigit():
                queryset = queryset.filter(student__section_id=section_id)
            else:
                queryset = queryset.filter(student__section__sections__iexact=section_id)

        serializer = MarksSerializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Marks records listed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None):
        # pk represents student_id
        student_id = pk
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            raise Http404()
        
        queryset = Marks.objects.filter(student_id=student_id).order_by('id')
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
                        if Marks.objects.filter(student=student, exam=exam, subject=subject).exists():
                            raise ValidationError(f"Marks record already exists for student ID {student_id}, exam ID {exam_id}, and subject ID {subject_id}.")

                    # Create or update marks record
                    marks_instance, created = Marks.objects.get_or_create(
                        student=student,
                        exam=exam,
                        subject=subject,
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
        except Exception as e:
            # Prevent failure to broadcast from failing the HTTP request
            pass

        serializer = MarksSerializer(saved_marks, many=True)
        return Response({
            "code": 201 if is_create else 200,
            "message": "Marks recorded successfully." if is_create else "Marks updated successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED if is_create else status.HTTP_200_OK)


from .models import CounsellingReport
from .serializers import CounsellingReportSerializer

class CounsellingReportViewSet(viewsets.ModelViewSet):
    queryset = CounsellingReport.objects.all().order_by('-report_date', '-id')
    serializer_class = CounsellingReportSerializer
    permission_classes = [CounsellingReportPermission]

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Counselling report not found"
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
            errors = exc.detail
            first_msg = ""
            if isinstance(errors, dict):
                first_key = next(iter(errors))
                val = errors[first_key]
                if isinstance(val, list):
                    first_msg = f"{first_key}: {val[0]}"
                else:
                    first_msg = f"{first_key}: {val}"
            elif isinstance(errors, list):
                first_msg = str(errors[0])
            else:
                first_msg = str(errors)
            return Response({
                "code": 400,
                "message": first_msg
            }, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(created_by=tracking_user, updated_by=tracking_user)
        self._broadcast_change(instance, 'counselling_created')

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        instance = serializer.save(updated_by=tracking_user)
        self._broadcast_change(instance, 'counselling_updated')

    def perform_destroy(self, instance):
        report_id = instance.id
        student_id = instance.student.id
        instance.delete()
        self._broadcast_delete(report_id, student_id)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        student_id = request.query_params.get('student_id')
        semester_id = request.query_params.get('semester_id')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        if semester_id:
            queryset = queryset.filter(semester_id=semester_id)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "code": 200,
            "message": "Counselling reports listed successfully.",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report retrieved successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "Counselling report created successfully.",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report updated successfully.",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Counselling report deleted successfully."
        }, status=status.HTTP_200_OK)

    def _broadcast_change(self, instance, event_name):
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
                            'event': event_name,
                            'payload': CounsellingReportSerializer(instance).data
                        }
                    }
                )
        except Exception:
            pass

    def _broadcast_delete(self, report_id, student_id):
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
                            'event': 'counselling_deleted',
                            'payload': {
                                'id': report_id,
                                'student_id': student_id
                            }
                        }
                    }
                )
        except Exception:
            pass


class FacultyActivityViewSet(viewsets.ModelViewSet):
    queryset = FacultyActivity.objects.all().order_by('-date', '-id')
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

        # For non-admin users, restrict to their own activities
        # UNLESS they are querying by a date range (dashboard schedule view)
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        date = request.query_params.get('date')
        timetable_id = request.query_params.get('timetable_id')
        timetable_ids = request.query_params.get('timetable_ids')  # comma-separated bulk lookup

        # Only enforce created_by filter when no date-range query is made
        # (date-range queries are used for dashboard completion status checks)
        if role_name not in ['ADMIN', 'ADMINISTRATOR']:
            if not (date_from or date_to or date or timetable_id or timetable_ids):
                queryset = queryset.filter(created_by=user)

        # Apply date filters
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
    queryset = StudentAttendance.objects.all().order_by('id')
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



