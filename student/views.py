from rest_framework import viewsets, status, permissions
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from django.db.models import Q
from .models import StudentStatus, Student
from .serializers import StudentStatusSerializer, StudentSerializer
from users.permissions import IsAdminUser
from .permissions import StudentStatusPermission, StudentPermission, MarksPermission, CounsellingReportPermission


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
            queryset = queryset.filter(section_id=section_id)
        if search:
            queryset = queryset.filter(
                Q(user__name__icontains=search) |
                Q(roll_number__icontains=search) |
                Q(register_number__icontains=search) |
                Q(user__email__icontains=search)
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
        - Existing fees payment record
        - All system users (for recommendation dropdown)
        """
        from django.shortcuts import get_object_or_404
        from .models import Student, StudentFees
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

        # Match performance rows to the highest qualification (or any if not matched)
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
        # If not matched by qual filter, try without filter as fallback
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

        # ── Fees data ────────────────────────────────────────────────
        fees_payment = getattr(student, 'fees_payment', None)
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

        fees_data = {}
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
                'aadhaar_number': fees_payment.aadhaar_number or aadhaar_number,
                'emis_number': fees_payment.emis_number or '',
                'umis_number': fees_payment.umis_number or '',
                'remarks': fees_payment.remarks or '',
                'certificates_surrendered': fees_payment.certificates_surrendered or {},
                'qualification': fees_payment.qualification or '',
                'community': fees_payment.community or '',
                'marks_maths': fees_payment.marks_maths,
                'marks_physics': fees_payment.marks_physics,
                'marks_chemistry': fees_payment.marks_chemistry,
                'marks_total': fees_payment.marks_total,
                'marks_percentage': float(fees_payment.marks_percentage) if fees_payment.marks_percentage else None,
                'mode_of_admission': fees_payment.mode_of_admission,
                'recommendation_id': fees_payment.recommendation_id,
                'recommendation_name': fees_payment.recommendation.name if fees_payment.recommendation else '',
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
                'aadhaar_number': aadhaar_number,
                'emis_number': '',
                'umis_number': '',
                'remarks': '',
                'certificates_surrendered': {},
                'qualification': '',
                'community': '',
                'marks_maths': pcm.get('maths'),
                'marks_physics': pcm.get('physics'),
                'marks_chemistry': pcm.get('chemistry'),
                'marks_total': None,
                'marks_percentage': None,
                'mode_of_admission': 'I Sem',
                'recommendation_id': None,
                'recommendation_name': '',
            }

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
                'fees': fees_data,
                'users_list': users_list,
            }
        }, status=200)

    def admission_slip_save(self, request, *args, **kwargs):

        student_id = request.data.get('student_id')
        if not student_id:
            return Response({"code": 400, "message": "student_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return Response({"code": 404, "message": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        from .models import StudentFees
        from .serializers import StudentFeesSerializer

        fees_payment, created = StudentFees.objects.get_or_create(student=student)
        serializer = StudentFeesSerializer(fees_payment, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "code": 200,
                "message": "Admission slip fees and credentials saved successfully",
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

        from .models import Student, StudentFees
        from institution.models import CollegeHeader

        student = get_object_or_404(Student, pk=pk)

        # Retrieve StudentFees record if exists, otherwise fallback to empty object
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

        # Qualification checkboxes
        qualification = (fees_payment.qualification if fees_payment else get_app_val('qualification') or '').upper()
        hsc_chk = "[X]" if "HSC" in qualification else "[   ]"
        cbse_chk = "[X]" if "CBSE" in qualification else "[   ]"
        diploma_chk = "[X]" if "DIPLOMA" in qualification or "DIP" in qualification else "[   ]"

        # Community Checkboxes
        community = (fees_payment.community if fees_payment else get_app_val('community') or '').upper()
        oc_chk = "[X]" if "OC" in community else "[   ]"
        bc_chk = "[X]" if "BC" in community else "[   ]"
        mbc_chk = "[X]" if "MBC" in community else "[   ]"
        sc_chk = "[X]" if "SC" in community else "[   ]"
        st_chk = "[X]" if "ST" in community else "[   ]"

        # Marks details
        marks_maths = fees_payment.marks_maths if fees_payment else None
        marks_physics = fees_payment.marks_physics if fees_payment else None
        marks_chemistry = fees_payment.marks_chemistry if fees_payment else None
        marks_total = fees_payment.marks_total if fees_payment else None
        marks_percentage = fees_payment.marks_percentage if fees_payment else None

        if marks_maths is None:
            # Fallback to application form
            try:
                marks_maths = int(get_app_val('marks_maths') or get_app_val('maths') or 0)
                marks_physics = int(get_app_val('marks_physics') or get_app_val('physics') or 0)
                marks_chemistry = int(get_app_val('marks_chemistry') or get_app_val('chemistry') or 0)
                marks_total = int(get_app_val('marks_total') or get_app_val('total_marks') or 0)
                marks_percentage = get_app_val('marks_percentage') or get_app_val('percentage') or 0.0
            except ValueError:
                pass

        # Mode of Admission
        moa = fees_payment.mode_of_admission if fees_payment else 'I Sem'
        sem1_chk = "[X]" if "I Sem" in moa or "1" in moa else "[   ]"
        sem3_chk = "[X]" if "III Sem" in moa or "3" in moa or "Lateral" in moa else "[   ]"

        # Fees Details
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
        recommendation_name = ''
        if fees_payment and fees_payment.recommendation:
            recommendation_name = fees_payment.recommendation.name

        # Payment Mode Chk
        pay_mode = (fees_payment.payment_mode if fees_payment else 'Cash').upper()
        cash_chk = "[X]" if "CASH" in pay_mode else "[   ]"
        dd_chk = "[X]" if "DD" in pay_mode or "D.D" in pay_mode else "[   ]"
        upi_chk = "[X]" if "UPI" in pay_mode else "[   ]"

        # Credentials
        aadhaar = fees_payment.aadhaar_number if fees_payment else ''
        emis = fees_payment.emis_number if fees_payment else ''
        umis = fees_payment.umis_number if fees_payment else ''


        # Certificates Surrendered checklist
        certs = fees_payment.certificates_surrendered if (fees_payment and fees_payment.certificates_surrendered) else {}
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
                Paragraph(f"{hsc_chk} HSC &nbsp;&nbsp;&nbsp;&nbsp; {cbse_chk} CBSE &nbsp;&nbsp;&nbsp;&nbsp; {diploma_chk} DIPLOMA", body_style),
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
                Paragraph("<b>6. Qualifying Examination Marks:</b>", body_style),
                Paragraph(f"Maths: {marks_maths or '—'}/200 &nbsp;&nbsp; Physics: {marks_physics or '—'}/200 &nbsp;&nbsp; Chemistry: {marks_chemistry or '—'}/200", body_style),
                Paragraph("<b>Total / %:</b>", body_style),
                Paragraph(f"{marks_total or '—'}/600 &nbsp;&nbsp; ({marks_percentage or '—'}%)", body_bold)
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
        exam_id = request.query_params.get('exam_id')
        subject_id = request.query_params.get('subject_id')
        batch_id = request.query_params.get('batch_id')
        section_id = request.query_params.get('section_id')

        if exam_id:
            queryset = queryset.filter(exam_id=exam_id)
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)
        if batch_id:
            queryset = queryset.filter(student__batch_id=batch_id)
        if section_id:
            queryset = queryset.filter(student__section_id=section_id)

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



