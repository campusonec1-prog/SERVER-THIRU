import logging
import os
import io
import re
import urllib.request
import datetime
from datetime import datetime as dt_datetime
from io import BytesIO

from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q
from django.core.validators import validate_email
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Image as RLImage
from PIL import Image as PILImage

from common.report_utils import build_standard_college_header, build_centered_report_title

from ..models import StudentStatus, Student, StudentAdmissionSlip, StudentFees, StudentSemesterFee, FeePayment
from ..serializers import StudentSerializer, StudentAdmissionSlipSerializer, StudentFeesSerializer, StudentSemesterFeeSerializer, FeePaymentSerializer
from ..permissions import StudentPermission

logger = logging.getLogger(__name__)


def _get_bus_from(student):
    if getattr(student, 'stop', None):
        return student.stop.stop_name
    if getattr(student, 'route', None):
        return student.route.route_name or student.route.start_location
    if getattr(student, 'bus', None):
        return student.bus.bus_number
    return getattr(student, 'bus_from', '') or ''


def _get_bus_to(student):
    if getattr(student, 'bus', None) and getattr(student, 'route', None):
        return f"{student.bus.bus_number} ({student.route.route_name})"
    if getattr(student, 'route', None):
        return student.route.end_location
    return getattr(student, 'bus_to', '') or ''


class StudentViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.select_related(
        'department', 'department__program', 'batch', 'section', 'status', 'quota',
        'bus', 'route', 'stop', 'application', 'application__candidate',
        'created_by', 'created_by__role', 'updated_by', 'updated_by__role'
    ).all().order_by('id')
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
        is_bus = request.query_params.get('is_bus')
        is_hostler = request.query_params.get('is_hostler')
        bus_id = request.query_params.get('bus_id')
        route_id = request.query_params.get('route_id')
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
        if is_bus is not None:
            if str(is_bus).lower() in ['true', '1']:
                queryset = queryset.filter(is_bus=True)
            elif str(is_bus).lower() in ['false', '0']:
                queryset = queryset.filter(is_bus=False)
        if is_hostler is not None:
            if str(is_hostler).lower() in ['true', '1']:
                queryset = queryset.filter(is_hostler=True)
            elif str(is_hostler).lower() in ['false', '0']:
                queryset = queryset.filter(is_hostler=False)
        if bus_id:
            queryset = queryset.filter(bus_id=bus_id)
        if route_id:
            queryset = queryset.filter(route_id=route_id)
        if search:
            queryset = queryset.filter(
                Q(student_name__icontains=search) |
                Q(application__candidate__name__icontains=search) |
                Q(application__application_no__icontains=search) |
                Q(roll_number__icontains=search) |
                Q(register_number__icontains=search) |
                Q(application__candidate__email__icontains=search) |
                Q(application__candidate__phone_number__icontains=search) |
                Q(bus__bus_number__icontains=search) |
                Q(route__route_name__icontains=search) |
                Q(stop__stop_name__icontains=search)
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
        partial = kwargs.pop('partial', True)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}
        return Response({
            "code": 200,
            "message": "Student updated successfully",
            "data": serializer.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        student_id = instance.id
        StudentAdmissionSlip.objects.filter(student=instance).delete()
        StudentFees.objects.filter(student=instance).delete()
        super().destroy(request, *args, **kwargs)
        self._broadcast_delete(student_id)
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

    @staticmethod
    def _reconcile_student_semester_fees(fees_payment, tracking_user=None):
        """
        Ensures that StudentSemesterFee records exist and that cumulative
        paid_amount on StudentFees is cleanly reconciled FIFO across semesters.
        """
        from decimal import Decimal
        from student.models import StudentSemesterFee
        from institution.models import FeesStructure, SemesterFeeStructure

        if not fees_payment:
            return

        student = fees_payment.student
        sem_fees = list(StudentSemesterFee.objects.filter(student_fees=fees_payment).order_by('semester__semester_number'))

        # If no semester fees exist, auto-create them from SemesterFeeStructure or FeesStructure
        if len(sem_fees) == 0:
            fs = FeesStructure.objects.filter(department=student.department, batch=student.batch, quota=student.quota).first()
            if fs:
                sfs_qs = SemesterFeeStructure.objects.filter(fee_structure=fs).order_by('semester__semester_number')
                if sfs_qs.exists():
                    for sfs in sfs_qs:
                        sem_fee, _ = StudentSemesterFee.objects.get_or_create(
                            student_fees=fees_payment,
                            semester=sfs.semester,
                            defaults={
                                'semester_fee_structure': sfs,
                                'total_amount': sfs.amount,
                                'paid_amount': Decimal('0.00'),
                                'concession_amount': Decimal('0.00'),
                                'balance_amount': sfs.amount,
                                'status': 'PENDING',
                            }
                        )
                        sem_fees.append(sem_fee)

        if len(sem_fees) == 0:
            return

        current_sem_paid_sum = sum(s.paid_amount for s in sem_fees)
        target_tuition_paid = fees_payment.paid_amount or Decimal('0.00')

        if current_sem_paid_sum != target_tuition_paid:
            unallocated = target_tuition_paid
            for s in sem_fees:
                net_payable = max(Decimal('0.00'), (s.total_amount or Decimal('0.00')) - (s.concession_amount or Decimal('0.00')))
                alloc = min(unallocated, net_payable)
                s.paid_amount = alloc
                s.recalculate_balance()
                if tracking_user:
                    s.updated_by = tracking_user
                s.save()
                unallocated -= alloc

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
        from users.models import User

        student = get_object_or_404(
            Student.objects.select_related('department', 'department__program', 'batch', 'quota', 'status', 'bus', 'route', 'stop', 'application', 'application__candidate', 'admission_slip', 'fees_payment'),
            pk=pk
        )
        app = student.application
        cand = app.candidate if app else None
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
        candidate_name = personal.get('applicant_name', '') or (cand.name if cand else '') or (student.name if hasattr(student, 'name') else '') or (student.student_name or '')
        aadhaar_number = str(personal.get('aadhaar_number', '') or '')
        community = str(personal.get('community', '') or '')
        phone = str(personal.get('student_mobile', '') or (cand.phone_number if cand else ''))

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

        # If we have URLs, try to parse with pypdf ONLY when scan_pdf parameter is explicitly passed
        # and admission_slip does not already exist with saved EMIS/UMIS numbers.
        # Synchronous HTTP downloads over the network block response times by 3-8+ seconds per request.
        parsed_text = ""
        should_scan_pdf = (
            request.GET.get('scan_pdf') == 'true' and 
            (not admission_slip or not (admission_slip.emis_number and admission_slip.umis_number))
        )
        if scanned_urls and should_scan_pdf:
            from pypdf import PdfReader
            for url in scanned_urls:
                try:
                    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req, timeout=8) as response:
                        pdf_data = response.read()
                    
                    reader = PdfReader(BytesIO(pdf_data))
                    for page in reader.pages:
                        t = page.extract_text()
                        if t:
                            parsed_text += t + "\n"
                except Exception:
                    pass

        # Search in extracted text
        if parsed_text:
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
        from decimal import Decimal
        from institution.models import SemesterFeeStructure
        fees_payment = getattr(student, 'fees_payment', None)
        if not fees_payment:
            fees_payment, _ = StudentFees.objects.get_or_create(
                student=student,
                defaults={'total_fees': Decimal(str(total_fees)), 'balance_amount': Decimal(str(total_fees))}
            )

        StudentViewSet._reconcile_student_semester_fees(fees_payment)

        resolved_total = float(fees_payment.total_fees) if float(fees_payment.total_fees) > 0 else total_fees
        resolved_paid = float(fees_payment.paid_amount)
        resolved_balance = float(fees_payment.balance_amount) if float(fees_payment.total_fees) > 0 else max(0.0, resolved_total - resolved_paid)
        sem_list = StudentSemesterFeeSerializer(fees_payment.semester_fees.all().order_by('semester__semester_number'), many=True).data

        fees_data = {
            'id': fees_payment.id,
            'total_fees': resolved_total,
            'paid_amount': resolved_paid,
            'balance_amount': resolved_balance,
            'books_fees_total': float(fees_payment.books_fees_total),
            'books_fees_paid': float(fees_payment.books_fees_paid),
            'due_date': fees_payment.due_date.isoformat() if fees_payment.due_date else None,
            'payment_mode': fees_payment.payment_mode,
            'remarks': fees_payment.remarks or '',
            'semester_fees': sem_list,
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
                    'name': candidate_name or (student.name if hasattr(student, 'name') else '') or (student.student_name or ''),
                    'student_name': candidate_name or (student.name if hasattr(student, 'name') else '') or (student.student_name or ''),
                    'roll_number': student.roll_number or '',
                    'register_number': student.register_number or '',
                    'phone': phone or (student.user.phone_number if getattr(student, 'user', None) else ''),
                    'is_hostler': student.is_hostler,
                    'is_day_scholar': student.is_day_scholar,
                    'is_bus': student.is_bus,
                    'bus_from': _get_bus_from(student),
                    'bus_to': _get_bus_to(student),
                    'department': student.department.department_name if student.department else '',
                    'department_id': student.department_id,
                    'program': program,
                    'batch': student.batch.batch if student.batch else '',
                    'batch_id': student.batch_id,
                    'status_id': student.status_id,
                    'quota': student.quota.quota_name if student.quota else '',
                    'quota_id': student.quota_id,
                    'bus_id': student.bus_id,
                    'route_id': student.route_id,
                    'stop_id': student.stop_id,
                    'application_id': student.application_id,
                    'application_no': app.application_no if app else '',
                    'user_id': student.user_id,
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

    def _generate_receipt_number(self):
        from django.utils import timezone
        prefix = timezone.now().strftime('REC-%Y%m-')
        last_payment = FeePayment.objects.select_for_update().filter(receipt_number__startswith=prefix).order_by('-id').first()
        if last_payment and last_payment.receipt_number:
            try:
                seq = int(last_payment.receipt_number.replace(prefix, '').split('-')[0]) + 1
            except Exception:
                seq = FeePayment.objects.count() + 1
        else:
            seq = 1
        return f"{prefix}{seq:05d}"

    def fees_save(self, request, *args, **kwargs):
        """
        Authoritative fee payment and ledger update endpoint.
        Safeguards:
        - Atomic transaction with select_for_update() row locking to prevent race conditions.
        - Idempotency key checking to prevent duplicate network submissions.
        - Consistent decimal math and positive payment validation.
        - Synchronous reconciliation between semester ledgers and overall tuition balance.
        - Backward-compatible with legacy fees_save payloads from existing admission & cashier screens.
        """
        from decimal import Decimal
        from django.db import transaction
        from django.utils import timezone
        from users.models import User as StandardUser

        student_id = request.data.get('student_id')
        if not student_id:
            return Response({"code": 400, "message": "student_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        tracking_user = user if isinstance(user, StandardUser) else None

        # 1. Idempotency check before acquiring lock
        idempotency_key = request.data.get('idempotency_key')
        if idempotency_key:
            existing_payment = FeePayment.objects.filter(idempotency_key=idempotency_key).first()
            if existing_payment:
                fees_record = StudentFees.objects.filter(student_id=student_id).first()
                return Response({
                    "code": 200,
                    "message": "Payment already processed (idempotent duplicate request)",
                    "data": StudentFeesSerializer(fees_record).data if fees_record else None,
                    "receipt": FeePaymentSerializer(existing_payment).data
                }, status=status.HTTP_200_OK)

        with transaction.atomic():
            try:
                student = Student.objects.select_for_update().get(pk=student_id)
            except Student.DoesNotExist:
                return Response({"code": 404, "message": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

            fees_payment, created = StudentFees.objects.select_for_update().get_or_create(student=student)

            # If total_fees was passed and record was just created or had 0 fees
            if 'total_fees' in request.data:
                try:
                    passed_total = Decimal(str(request.data['total_fees']))
                    if fees_payment.total_fees == Decimal('0.00') or created:
                        fees_payment.total_fees = passed_total
                        fees_payment.balance_amount = max(Decimal('0.00'), passed_total - fees_payment.paid_amount)
                except Exception:
                    pass

            if 'books_fees_total' in request.data:
                try:
                    fees_payment.books_fees_total = Decimal(str(request.data['books_fees_total']))
                except Exception:
                    pass

            # Payment mode & due date updates
            if 'payment_mode' in request.data and request.data['payment_mode']:
                fees_payment.payment_mode = str(request.data['payment_mode']).strip()

            if 'due_date' in request.data:
                fees_payment.due_date = request.data['due_date'] or None

            if 'remarks' in request.data:
                fees_payment.remarks = request.data['remarks']

            # Determine tuition amount being paid right now
            pay_tuition_now = Decimal('0.00')
            if 'amount_paying_now' in request.data or 'amount_paid' in request.data:
                raw_amt = request.data.get('amount_paying_now') or request.data.get('amount_paid')
                try:
                    pay_tuition_now = Decimal(str(raw_amt))
                except Exception:
                    return Response({"code": 400, "message": "Invalid amount_paying_now or amount_paid"}, status=status.HTTP_400_BAD_REQUEST)
            elif 'paid_amount' in request.data:
                # Legacy frontend: sent cumulative paid total
                try:
                    target_cumulative = Decimal(str(request.data['paid_amount']))
                    pay_tuition_now = max(Decimal('0.00'), target_cumulative - fees_payment.paid_amount)
                except Exception:
                    pass

            if pay_tuition_now < 0:
                return Response({"code": 400, "message": "Payment amount cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)

            # Determine books amount being paid right now
            pay_books_now = Decimal('0.00')
            if 'book_paid_today' in request.data or 'books_paid_now' in request.data:
                raw_book = request.data.get('book_paid_today') or request.data.get('books_paid_now')
                try:
                    pay_books_now = Decimal(str(raw_book))
                except Exception:
                    pass
            elif 'books_fees_paid' in request.data:
                try:
                    target_books = Decimal(str(request.data['books_fees_paid']))
                    pay_books_now = max(Decimal('0.00'), target_books - fees_payment.books_fees_paid)
                except Exception:
                    pass

            if pay_books_now < 0:
                return Response({"code": 400, "message": "Books payment amount cannot be negative"}, status=status.HTTP_400_BAD_REQUEST)

            # Process tuition payment
            receipt_records = []
            if pay_tuition_now > Decimal('0.00'):
                # Validate against total tuition outstanding balance
                if pay_tuition_now > fees_payment.balance_amount and fees_payment.balance_amount > Decimal('0.00'):
                    return Response({
                        "code": 400,
                        "message": f"Payment amount ₹{pay_tuition_now:,.2f} exceeds outstanding tuition balance ₹{fees_payment.balance_amount:,.2f}."
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Semester-specific allocation check
                semester_id = request.data.get('semester_id')
                student_semester_fee_id = request.data.get('student_semester_fee_id')
                sem_fee = None

                if student_semester_fee_id:
                    sem_fee = StudentSemesterFee.objects.select_for_update().filter(pk=student_semester_fee_id, student_fees=fees_payment).first()
                elif semester_id:
                    sem_fee = StudentSemesterFee.objects.select_for_update().filter(semester_id=semester_id, student_fees=fees_payment).first()

                if sem_fee:
                    if pay_tuition_now > sem_fee.balance_amount and sem_fee.balance_amount > Decimal('0.00'):
                        return Response({
                            "code": 400,
                            "message": f"Payment amount ₹{pay_tuition_now:,.2f} exceeds outstanding semester balance ₹{sem_fee.balance_amount:,.2f}."
                        }, status=status.HTTP_400_BAD_REQUEST)
                    sem_fee.paid_amount += pay_tuition_now
                    sem_fee.recalculate_balance()
                    sem_fee.updated_by = tracking_user
                    sem_fee.save()

                # Generate unique receipt number safely
                receipt_no = self._generate_receipt_number()

                # Create Payment transaction
                tuit_payment = FeePayment.objects.create(
                    student_fees=fees_payment,
                    student_semester_fee=sem_fee,
                    amount_paid=pay_tuition_now,
                    fee_category='TUITION',
                    payment_mode=fees_payment.payment_mode or 'Cash',
                    payment_date=timezone.now().date(),
                    payment_timestamp=timezone.now(),
                    receipt_number=receipt_no,
                    transaction_reference=request.data.get('transaction_reference') or '',
                    idempotency_key=idempotency_key,
                    remarks=request.data.get('notes') or ('Tuition fee payment' if not sem_fee else f"Tuition payment for {sem_fee.semester.semester_name}"),
                    recorded_by=tracking_user,
                    created_by=tracking_user,
                    updated_by=tracking_user,
                    is_reconciled=True
                )
                receipt_records.append(tuit_payment)

                # Reconcile overall tuition ledger
                fees_payment.paid_amount += pay_tuition_now
                fees_payment.balance_amount = max(Decimal('0.00'), fees_payment.total_fees - fees_payment.paid_amount)

            # Process books payment
            if pay_books_now > Decimal('0.00'):
                book_receipt_no = self._generate_receipt_number()
                book_payment = FeePayment.objects.create(
                    student_fees=fees_payment,
                    student_semester_fee=None,
                    amount_paid=pay_books_now,
                    fee_category='BOOKS',
                    payment_mode=fees_payment.payment_mode or 'Cash',
                    payment_date=timezone.now().date(),
                    payment_timestamp=timezone.now(),
                    receipt_number=book_receipt_no,
                    transaction_reference=request.data.get('transaction_reference') or '',
                    idempotency_key=f"{idempotency_key}-BOOKS" if idempotency_key else None,
                    remarks=request.data.get('notes') or 'Books & uniform fee payment',
                    recorded_by=tracking_user,
                    created_by=tracking_user,
                    updated_by=tracking_user,
                    is_reconciled=True
                )
                fees_payment.books_fees_paid += pay_books_now
                receipt_records.append(book_payment)

            fees_payment.updated_by = tracking_user
            fees_payment.save()
            StudentViewSet._reconcile_student_semester_fees(fees_payment, tracking_user)

        # Reload with fresh relationships
        updated_fees = StudentFees.objects.prefetch_related('semester_fees', 'payments').get(pk=fees_payment.pk)
        return Response({
            "code": 200,
            "message": "Student fees and payment transaction saved successfully",
            "data": StudentFeesSerializer(updated_fees).data,
            "receipts": FeePaymentSerializer(receipt_records, many=True).data if receipt_records else []
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='fees-overview')
    def fees_overview(self, request, pk=None):
        """
        Comprehensive financial dossier for a student:
        - Overall tuition and books ledger
        - Semester-wise breakdown with individual balances and concessions
        - Complete transaction payment history with receipt numbers and cashier details
        """
        try:
            student = Student.objects.select_related(
                'department', 'batch', 'quota', 'status'
            ).get(pk=pk)
        except Student.DoesNotExist:
            return Response({"code": 404, "message": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        fees_payment = StudentFees.objects.prefetch_related(
            'semester_fees__semester',
            'payments__student_semester_fee__semester',
            'payments__recorded_by'
        ).filter(student=student).first()

        if not fees_payment:
            fees_payment, _ = StudentFees.objects.get_or_create(student=student)

        StudentViewSet._reconcile_student_semester_fees(fees_payment)
        fees_payment = StudentFees.objects.prefetch_related(
            'semester_fees__semester',
            'payments__student_semester_fee__semester',
            'payments__recorded_by'
        ).filter(student=student).first()

        data = {
            "student": {
                "id": student.id,
                "student_name": student.student_name,
                "roll_number": student.roll_number,
                "register_number": student.register_number,
                "department_id": student.department_id,
                "department_name": getattr(student.department, 'department_name', ''),
                "batch_id": student.batch_id,
                "batch_name": getattr(student.batch, 'batch', ''),
                "quota_id": student.quota_id,
                "quota_name": getattr(student.quota, 'quota_name', ''),
            },
            "ledger": StudentFeesSerializer(fees_payment).data if fees_payment else None
        }
        return Response({
            "code": 200,
            "message": "Student fees overview retrieved successfully",
            "data": data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='fees-apply-concession')
    def fees_apply_concession(self, request):
        """
        Applies student-specific scholarship or fee concession for a semester
        without altering the institution's standard fee structure.
        """
        from decimal import Decimal
        from django.db import transaction
        from users.models import User as StandardUser

        student_id = request.data.get('student_id')
        semester_id = request.data.get('semester_id')
        raw_concession = request.data.get('concession_amount')

        if not student_id or not semester_id or raw_concession is None:
            return Response({
                "code": 400,
                "message": "student_id, semester_id, and concession_amount are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            concession = Decimal(str(raw_concession))
            if concession < 0:
                raise ValueError()
        except Exception:
            return Response({"code": 400, "message": "Invalid concession_amount."}, status=status.HTTP_400_BAD_REQUEST)

        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        tracking_user = user if isinstance(user, StandardUser) else None

        with transaction.atomic():
            sem_fee = StudentSemesterFee.objects.select_for_update().filter(
                student_fees__student_id=student_id,
                semester_id=semester_id
            ).first()

            if not sem_fee:
                return Response({
                    "code": 404,
                    "message": "Student semester fee record not found for this semester."
                }, status=status.HTTP_404_NOT_FOUND)

            if concession > sem_fee.total_amount:
                return Response({
                    "code": 400,
                    "message": f"Concession amount ₹{concession:,.2f} cannot exceed the semester tuition fee ₹{sem_fee.total_amount:,.2f}."
                }, status=status.HTTP_400_BAD_REQUEST)

            sem_fee.concession_amount = concession
            sem_fee.recalculate_balance()
            sem_fee.updated_by = tracking_user
            sem_fee.save()

            # Reconcile overall student fees balance
            sf = sem_fee.student_fees
            total_concessions = sum(s.concession_amount for s in sf.semester_fees.all())
            sf.balance_amount = max(Decimal('0.00'), sf.total_fees - total_concessions - sf.paid_amount)
            sf.updated_by = tracking_user
            sf.save()
            StudentViewSet._reconcile_student_semester_fees(sf, tracking_user)

        return Response({
            "code": 200,
            "message": "Concession applied and semester balance recalculated successfully.",
            "data": StudentSemesterFeeSerializer(sem_fee).data
        }, status=status.HTTP_200_OK)


    @action(detail=True, methods=['put', 'post', 'patch'], url_path='full-profile-edit')
    def full_profile_update(self, request, pk=None, *args, **kwargs):
        """
        Comprehensive Student Full Profile Update API.
        Updates all aspects of a student:
        - Student model: roll_number, register_number, department, batch, section, quota, status, lab_batch, is_hostler, hostel_building_type, hostel_room_number, is_day_scholar, is_bus, bus, route, stop
        - Candidate / User (ApplicationUser): name, email, phone_number
        - Application form_data JSON: personal_information, parent_information, etc.
        - StudentAdmissionSlip: aadhaar_number, emis_number, umis_number, qualification, community, mode_of_admission, recommendation, marks_maths, marks_physics, marks_chemistry, marks_total, marks_percentage
        """
        try:
            student = Student.objects.select_related(
                'application', 'application__candidate', 'admission_slip', 'department', 'batch', 'section', 'quota', 'status'
            ).get(pk=pk)
        except Student.DoesNotExist:
            return Response({"code": 404, "message": "Student not found"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        if not user:
            return Response({"code": 401, "message": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        user_role = getattr(user, 'role', None)
        can_edit = (
            getattr(user, 'is_superuser', False) or
            getattr(user, 'is_staff', False) or
            bool(getattr(user_role, 'can_edit_student_profile', False))
        )
        if not can_edit:
            return Response({
                "code": 403,
                "message": "Your role does not have permission to edit student profiles. Please contact an Administrator or Tech Supporter."
            }, status=status.HTTP_403_FORBIDDEN)

        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None

        # 1. Validation for unique fields
        roll_num = data.get('roll_number')
        if roll_num is not None:
            roll_num = str(roll_num).strip() or None
            if roll_num:
                if Student.objects.filter(roll_number__iexact=roll_num).exclude(pk=student.pk).exists():
                    return Response({
                        "code": 400,
                        "message": f"Roll number '{roll_num}' is already assigned to another student."
                    }, status=status.HTTP_400_BAD_REQUEST)

        reg_num = data.get('register_number')
        if reg_num is not None:
            reg_num = str(reg_num).strip() or None
            if reg_num:
                if Student.objects.filter(register_number__iexact=reg_num).exclude(pk=student.pk).exists():
                    return Response({
                        "code": 400,
                        "message": f"Register number '{reg_num}' is already assigned to another student."
                    }, status=status.HTTP_400_BAD_REQUEST)

        email = data.get('email')
        if email:
            email = str(email).strip().lower()
            try:
                validate_email(email)
            except DjangoValidationError:
                return Response({
                    "code": 400,
                    "message": "Please enter a valid email address."
                }, status=status.HTTP_400_BAD_REQUEST)

        phone = data.get('phone') or data.get('phone_number') or data.get('mobile_number')
        if phone:
            phone = str(phone).strip()
            if not re.match(r'^\d{10}$', phone):
                return Response({
                    "code": 400,
                    "message": "Student phone number must be exactly 10 digits."
                }, status=status.HTTP_400_BAD_REQUEST)

        parent_phone = data.get('parent_phone') or data.get('parent_mobile')
        if parent_phone:
            parent_phone = str(parent_phone).strip()
            if parent_phone and not re.match(r'^\d{10}$', parent_phone):
                return Response({
                    "code": 400,
                    "message": "Parent phone number must be exactly 10 digits."
                }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # ── A. Update Student model ──
            if roll_num is not None:
                student.roll_number = roll_num
            if reg_num is not None:
                student.register_number = reg_num

            if 'department_id' in data and data['department_id']:
                student.department_id = int(data['department_id'])
            if 'batch_id' in data and data['batch_id']:
                student.batch_id = int(data['batch_id'])
            if 'section_id' in data:
                student.section_id = int(data['section_id']) if data['section_id'] else None
            if 'quota_id' in data:
                student.quota_id = int(data['quota_id']) if data['quota_id'] else None
            if 'status_id' in data and data['status_id']:
                student.status_id = int(data['status_id'])
            if 'lab_batch' in data:
                student.lab_batch = str(data['lab_batch']).strip() if data['lab_batch'] else None

            # Accommodation
            is_hostler = data.get('is_hostler')
            if is_hostler is not None:
                student.is_hostler = bool(is_hostler)
                if student.is_hostler:
                    student.is_day_scholar = False
                    student.hostel_building_type = data.get('hostel_building_type') or None
                    student.hostel_room_number = str(data.get('hostel_room_number', '')).strip() or None
                else:
                    student.hostel_building_type = None
                    student.hostel_room_number = None

            is_day_scholar = data.get('is_day_scholar')
            if is_day_scholar is not None and bool(is_day_scholar):
                student.is_day_scholar = True
                student.is_hostler = False
                student.hostel_building_type = None
                student.hostel_room_number = None

            # Transport
            is_bus = data.get('is_bus')
            if is_bus is not None:
                student.is_bus = bool(is_bus)
                if student.is_bus:
                    student.bus_id = int(data['bus_id']) if data.get('bus_id') else None
                    student.route_id = int(data['route_id']) if data.get('route_id') else None
                    student.stop_id = int(data['stop_id']) if data.get('stop_id') else None
                else:
                    student.bus_id = None
                    student.route_id = None
                    student.stop_id = None

            student.updated_by = tracking_user
            student.save()

            # ── B. Update Candidate (ApplicationUser) & Application form_data ──
            app = student.application
            if app:
                cand = app.candidate
                if cand:
                    if 'name' in data and data['name']:
                        cand.name = str(data['name']).strip()
                    if email:
                        from dynamic_forms.models import ApplicationUser
                        if not ApplicationUser.objects.filter(email__iexact=email).exclude(pk=cand.pk).exists():
                            cand.email = email
                    if phone:
                        cand.phone_number = phone
                    cand.updated_by = tracking_user
                    cand.save()

                # Update nested form_data
                fd = dict(app.form_data) if (app.form_data and isinstance(app.form_data, dict)) else {}
                personal = dict(fd.get('personal_information', {})) if isinstance(fd.get('personal_information'), dict) else {}
                parent = dict(fd.get('parent_information', {})) if isinstance(fd.get('parent_information'), dict) else {}

                if 'name' in data and data['name']:
                    personal['applicant_name'] = str(data['name']).strip()
                if email:
                    personal['email'] = email
                if phone:
                    personal['student_mobile'] = phone
                if 'gender' in data and data['gender']:
                    personal['gender'] = data['gender']
                if 'dob' in data and data['dob']:
                    personal['date_of_birth'] = data['dob']
                    personal['dob'] = data['dob']
                if 'community' in data and data['community']:
                    personal['community'] = data['community']
                if 'aadhaar_number' in data:
                    personal['aadhaar_number'] = str(data['aadhaar_number']).strip()
                if 'district' in data:
                    personal['district'] = str(data['district']).strip()
                    fd['district'] = str(data['district']).strip()

                if 'parent_name' in data:
                    parent['parent_name'] = str(data['parent_name']).strip()
                    parent['father_name'] = str(data['parent_name']).strip()
                if 'mother_name' in data:
                    parent['mother_name'] = str(data['mother_name']).strip()
                if parent_phone:
                    parent['parent_mobile'] = parent_phone
                    parent['father_mobile'] = parent_phone
                if 'district' in data:
                    parent['district'] = str(data['district']).strip()
                if 'pincode' in data:
                    parent['pincode'] = str(data['pincode']).strip()
                if 'address' in data:
                    parent['address'] = str(data['address']).strip()
                    parent['communication_address'] = str(data['address']).strip()

                fd['personal_information'] = personal
                fd['parent_information'] = parent
                app.form_data = fd
                app.updated_by = tracking_user
                app.save()

            # ── C. Update StudentAdmissionSlip ──
            admission_slip, _ = StudentAdmissionSlip.objects.get_or_create(student=student)
            if 'aadhaar_number' in data:
                admission_slip.aadhaar_number = str(data['aadhaar_number']).strip() or None
            if 'emis_number' in data:
                admission_slip.emis_number = str(data['emis_number']).strip() or None
            if 'umis_number' in data:
                admission_slip.umis_number = str(data['umis_number']).strip() or None
            if 'qualification' in data:
                admission_slip.qualification = str(data['qualification']).strip() or None
            if 'community' in data:
                admission_slip.community = str(data['community']).strip() or None
            if 'mode_of_admission' in data:
                admission_slip.mode_of_admission = str(data['mode_of_admission']).strip() or 'Regular Entry'
            if 'recommendation_id' in data:
                admission_slip.recommendation_id = int(data['recommendation_id']) if data['recommendation_id'] else None

            # Qualifying Marks
            m_maths = data.get('marks_maths')
            m_physics = data.get('marks_physics')
            m_chemistry = data.get('marks_chemistry')

            if m_maths is not None and str(m_maths).strip() != '':
                admission_slip.marks_maths = int(float(m_maths))
            elif 'marks_maths' in data and (m_maths is None or str(m_maths).strip() == ''):
                admission_slip.marks_maths = None

            if m_physics is not None and str(m_physics).strip() != '':
                admission_slip.marks_physics = int(float(m_physics))
            elif 'marks_physics' in data and (m_physics is None or str(m_physics).strip() == ''):
                admission_slip.marks_physics = None

            if m_chemistry is not None and str(m_chemistry).strip() != '':
                admission_slip.marks_chemistry = int(float(m_chemistry))
            elif 'marks_chemistry' in data and (m_chemistry is None or str(m_chemistry).strip() == ''):
                admission_slip.marks_chemistry = None

            # Calculate or set total & percentage
            if 'marks_total' in data and data['marks_total'] is not None and str(data['marks_total']).strip() != '':
                admission_slip.marks_total = int(float(data['marks_total']))
            elif admission_slip.marks_maths is not None or admission_slip.marks_physics is not None or admission_slip.marks_chemistry is not None:
                admission_slip.marks_total = (admission_slip.marks_maths or 0) + (admission_slip.marks_physics or 0) + (admission_slip.marks_chemistry or 0)

            if 'marks_percentage' in data and data['marks_percentage'] is not None and str(data['marks_percentage']).strip() != '':
                admission_slip.marks_percentage = float(data['marks_percentage'])

            admission_slip.updated_by = tracking_user
            admission_slip.save()

            # ── D. Sync User account if exists for login ──
            try:
                from users.models import User as AuthUser
                auth_user = None
                if student.roll_number:
                    auth_user = AuthUser.objects.filter(username__iexact=student.roll_number).first()
                if not auth_user and email:
                    auth_user = AuthUser.objects.filter(mail__iexact=email).first()
                if auth_user:
                    if 'name' in data and data['name']:
                        auth_user.name = str(data['name']).strip()
                    if email and not AuthUser.objects.filter(mail__iexact=email).exclude(pk=auth_user.pk).exists():
                        auth_user.mail = email
                    if phone and re.match(r'^\d{10}$', phone):
                        auth_user.mobile_number = phone
                    if student.roll_number:
                        auth_user.username = student.roll_number
                    auth_user.updated_by = tracking_user
                    auth_user.save()
            except Exception as e:
                logger.warning(f"Failed to sync AuthUser for student {student.id}: {e}")

        # Broadcast real-time update
        self._broadcast_change(student, 'student_updated')

        return Response({
            "code": 200,
            "message": "Student complete profile updated successfully",
            "data": {
                "id": student.id,
                "roll_number": student.roll_number,
                "register_number": student.register_number,
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='comprehensive-view')
    def comprehensive_view(self, request, *args, **kwargs):
        """
        Comprehensive Student View API Endpoint.
        Allows searching/retrieving student profile, application details, admission slip, fees,
        marks (semester-wise & exam type breakdown), and attendance (subject-wise & overall).
        Query params:
        - search: Roll number, Register number, or Mobile number (or partial match)
        - student_id: Direct Student primary key ID
        """
        search_query = request.query_params.get('search', '').strip()
        student_id = request.query_params.get('student_id', '').strip()

        base_qs = Student.objects.select_related(
            'department', 'department__program', 'batch', 'section', 'status', 'quota', 'bus', 'route', 'stop', 'application', 'application__candidate', 'admission_slip', 'fees_payment'
        )

        if student_id and student_id.isdigit():
            students = base_qs.filter(pk=int(student_id))
        elif search_query:
            students = base_qs.filter(
                Q(roll_number=search_query) |
                Q(register_number=search_query) |
                Q(roll_number__iexact=search_query) |
                Q(register_number__iexact=search_query) |
                Q(application__application_no=search_query) |
                Q(application__candidate__phone_number=search_query) |
                Q(application__candidate__name__icontains=search_query) |
                Q(roll_number__icontains=search_query) |
                Q(register_number__icontains=search_query)
            )
        else:
            user = request.user
            if user and user.is_authenticated:
                user_role = ""
                if hasattr(user, 'role') and user.role:
                    user_role = user.role.role_name.upper()

                phone_val = str(getattr(user, 'mobile_number', getattr(user, 'phone_number', '')) or '').strip()
                email_val = str(getattr(user, 'mail', getattr(user, 'email', '')) or '').strip()
                username_val = str(getattr(user, 'username', '') or '').strip()

                q_filter = Q()
                if username_val:
                    q_filter |= Q(roll_number=username_val) | Q(register_number=username_val) | Q(roll_number__iexact=username_val) | Q(register_number__iexact=username_val)
                if phone_val:
                    q_filter |= Q(application__candidate__phone_number=phone_val)
                if email_val:
                    q_filter |= Q(application__candidate__email=email_val)

                students = base_qs.filter(q_filter) if q_filter else Student.objects.none()

                if not students.exists() and user_role != 'STUDENT':
                    return Response({
                        "code": 400,
                        "message": "Please enter a Roll Number, Register Number, or Phone Number to search"
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({
                    "code": 400,
                    "message": "Please enter a Roll Number, Register Number, or Phone Number to search"
                }, status=status.HTTP_400_BAD_REQUEST)

        if students.count() > 1 and not student_id:
            results = []
            for s in students[:20]:
                app = s.application
                cand = app.candidate if app else None
                fd = app.form_data if (app and app.form_data and isinstance(app.form_data, dict)) else {}
                candidate_name = cand.name if cand else ''
                photo_url = fd.get('photo', '')
                results.append({
                    'id': s.id,
                    'name': candidate_name,
                    'roll_number': s.roll_number,
                    'register_number': s.register_number,
                    'phone': cand.phone_number if cand else '',
                    'department': s.department.department_name if s.department else '',
                    'batch': s.batch.batch if s.batch else '',
                    'section': s.section.sections if s.section else '',
                    'student_photo': photo_url
                })
            return Response({
                "code": 200,
                "multiple": True,
                "message": f"Found {students.count()} matching students",
                "data": results
            }, status=status.HTTP_200_OK)

        student = students.first()
        if not student:
            return Response({
                "code": 404,
                "message": f"No student found matching query '{search_query}'"
            }, status=status.HTTP_404_NOT_FOUND)

        # ── 1. Profile & Application Data ──────────────────────────────────────
        app = student.application
        fd = app.form_data if (app and app.form_data and isinstance(app.form_data, dict)) else {}

        def get_fd(module_key, field_key=None):
            module_data = fd.get(module_key, {})
            if field_key is None:
                return module_data
            if isinstance(module_data, dict):
                return module_data.get(field_key, '')
            return ''

        personal = get_fd('personal_information')
        candidate_name = personal.get('applicant_name', '') or (student.user.name if student.user else '')
        aadhaar_number = str(personal.get('aadhaar_number', '') or '')
        community = str(personal.get('community', '') or '')
        phone = str(personal.get('student_mobile', '') or (student.user.phone_number if student.user else ''))
        email = str(personal.get('email', '') or (student.user.email if student.user else ''))
        dob = str(
            personal.get('date_of_birth', '') or
            personal.get('dob', '') or
            personal.get('dateOfBirth', '') or
            personal.get('birth_date', '') or
            ''
        )
        gender = str(personal.get('gender', '') or '')

        parent = get_fd('parent_information')
        parent_name = str(parent.get('parent_name', '') or parent.get('father_name', '') or '')
        mother_name = str(parent.get('mother_name', '') or '')
        parent_phone = str(parent.get('parent_mobile', '') or parent.get('father_mobile', '') or '')
        address = str(parent.get('address', '') or parent.get('communication_address', '') or '')
        pincode = str(parent.get('pincode', '') or '')

        photo_url = fd.get('photo', '')
        if not photo_url:
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

        certs_list = []
        if isinstance(certs, list):
            for c in certs:
                if isinstance(c, dict):
                    doc_url = ''
                    d_val = c.get('document')
                    if isinstance(d_val, str) and d_val.startswith('http'):
                        doc_url = d_val
                    elif isinstance(d_val, dict) and isinstance(d_val.get('url'), str):
                        doc_url = d_val.get('url')

                    certs_list.append({
                        'name': c.get('certificate_type') or c.get('name') or 'Submitted Document',
                        'url': doc_url,
                        'status': 'Uploaded'
                    })

        admission_slip = getattr(student, 'admission_slip', None)
        admission_data = {}

        def resolve_admission_type(raw_type):
            if not raw_type:
                return 'Regular Entry'
            s = str(raw_type).strip().lower()
            if 'iii' in s or 'lateral' in s or 'sem 3' in s or '3rd' in s:
                return 'Lateral Entry'
            if 'i' in s or 'regular' in s or 'sem 1' in s or '1st' in s:
                return 'Regular Entry'
            return raw_type

        if admission_slip:
            m = float(admission_slip.marks_maths) if admission_slip.marks_maths is not None else 0.0
            p = float(admission_slip.marks_physics) if admission_slip.marks_physics is not None else 0.0
            c = float(admission_slip.marks_chemistry) if admission_slip.marks_chemistry is not None else 0.0
            cutoff_calc = round(m + ((p + c) / 2), 2) if (admission_slip.marks_maths or admission_slip.marks_physics or admission_slip.marks_chemistry) else None

            admission_data = {
                'aadhaar_number': admission_slip.aadhaar_number or aadhaar_number,
                'emis_number': admission_slip.emis_number or '',
                'umis_number': admission_slip.umis_number or '',
                'qualification': admission_slip.qualification or '',
                'community': admission_slip.community or community,
                'marks_maths': admission_slip.marks_maths,
                'marks_physics': admission_slip.marks_physics,
                'marks_chemistry': admission_slip.marks_chemistry,
                'marks_total': admission_slip.marks_total,
                'marks_percentage': float(admission_slip.marks_percentage) if admission_slip.marks_percentage else None,
                'cutoff_marks': cutoff_calc,
                'mode_of_admission': resolve_admission_type(admission_slip.mode_of_admission),
                'recommendation_name': admission_slip.recommendation.name if admission_slip.recommendation else '',
                'certificates_surrendered': admission_slip.certificates_surrendered or {},
                'uploaded_documents': certs_list,
            }
        else:
            admission_data = {
                'aadhaar_number': aadhaar_number,
                'emis_number': '',
                'umis_number': '',
                'qualification': '',
                'community': community,
                'marks_maths': None,
                'marks_physics': None,
                'marks_chemistry': None,
                'marks_total': None,
                'marks_percentage': None,
                'cutoff_marks': None,
                'mode_of_admission': 'Regular Entry',
                'recommendation_name': '',
                'certificates_surrendered': {},
                'uploaded_documents': certs_list,
            }

        fees_payment = getattr(student, 'fees_payment', None)
        fees_data = {}
        if fees_payment:
            fees_data = {
                'total_fees': float(fees_payment.total_fees),
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
                'total_fees': 0.0,
                'paid_amount': 0.0,
                'balance_amount': 0.0,
                'books_fees_total': 0.0,
                'books_fees_paid': 0.0,
                'due_date': None,
                'payment_mode': 'Cash',
                'remarks': '',
            }

        def format_ddmmyyyy(d_str):
            if not d_str:
                return ''
            d_str = str(d_str).strip()
            if not d_str:
                return ''
            if '-' in d_str:
                parts = d_str.split('-')
                if len(parts) == 3:
                    if len(parts[0]) == 4:
                        return f"{parts[2].zfill(2)}-{parts[1].zfill(2)}-{parts[0]}"
                    elif len(parts[2]) == 4:
                        return f"{parts[0].zfill(2)}-{parts[1].zfill(2)}-{parts[2]}"
            if '/' in d_str:
                parts = d_str.split('/')
                if len(parts) == 3:
                    if len(parts[0]) == 4:
                        return f"{parts[2].zfill(2)}-{parts[1].zfill(2)}-{parts[0]}"
                    elif len(parts[2]) == 4:
                        return f"{parts[0].zfill(2)}-{parts[1].zfill(2)}-{parts[2]}"
            return d_str

        dob_formatted = format_ddmmyyyy(dob)
        district = str(parent.get('district', '') or personal.get('district', '') or fd.get('district', '') or '')

        profile_data = {
            'id': student.id,
            'roll_number': student.roll_number or '',
            'register_number': student.register_number or '',
            'name': candidate_name,
            'email': email,
            'phone': phone,
            'dob': dob_formatted,
            'gender': gender,
            'community': community,
            'student_photo': photo_url,
            'department_id': student.department_id,
            'department_name': student.department.department_name if student.department else '',
            'program_name': student.department.program.program_name if (student.department and student.department.program) else '',
            'batch_id': student.batch_id,
            'batch_name': student.batch.batch if student.batch else '',
            'section_id': student.section_id,
            'section_name': student.section.sections if student.section else '',
            'quota_name': student.quota.quota_name if student.quota else '',
            'status_name': student.status.status_name if student.status else '',
            'is_hostler': student.is_hostler,
            'is_day_scholar': student.is_day_scholar,
            'is_bus': student.is_bus,
            'bus_from': _get_bus_from(student),
            'bus_to': _get_bus_to(student),
            'parent_name': parent_name,
            'parent_phone': parent_phone,
            'district': district,
            'address': address,
            'pincode': pincode,
            'admission': admission_data,
            'fees': fees_data,
        }

        # ── 2. Academic Marks & Anna University GPA / CGPA Calculation ────────
        from ..models import Marks, GradeSystem
        import re

        grade_systems = list(GradeSystem.objects.filter(is_active=True).order_by('-points'))
        marks_qs = Marks.objects.filter(student=student).select_related(
            'exam', 'exam__exam_type', 'subject', 'subject__semester'
        )

        def extract_sem_num(subject_obj):
            if not subject_obj:
                return 1
            code = getattr(subject_obj, 'subject_code', '') or ''
            m = re.search(r'^[A-Za-z]+(\d)(\d)', code)
            if m:
                try:
                    sem_digit = int(m.group(2))
                    if 1 <= sem_digit <= 8:
                        return sem_digit
                except (ValueError, TypeError):
                    pass
            if hasattr(subject_obj, 'semester_id') and subject_obj.semester_id:
                try:
                    s_id = int(subject_obj.semester_id)
                    if 1 <= s_id <= 8:
                        return s_id
                except (ValueError, TypeError):
                    pass
            return 1

        def resolve_sem_label(subject_obj):
            sem_num = extract_sem_num(subject_obj)
            return f"Semester {sem_num}"

        def get_grade_point_and_pass(val):
            if val is None or str(val).strip() == '':
                return 0.0, False, '—'
            str_val = str(val).strip().upper()
            
            # 1. Match by Letter Grade in GradeSystem table (e.g. O, A+, A, B+, B, C, U, RA, UA, AB)
            for g in grade_systems:
                if g.grade.strip().upper() == str_val:
                    return float(g.points), bool(g.is_pass), g.grade
            
            # 2. Match by Numeric Mark range in GradeSystem table
            try:
                num = float(str_val)
                for g in grade_systems:
                    if g.min_mark is not None and g.max_mark is not None:
                        if float(g.min_mark) <= num <= float(g.max_mark):
                            return float(g.points), bool(g.is_pass), g.grade
            except ValueError:
                pass
            
            # 3. If not matched in GradeSystem, return 0.0 points and fail status
            is_absent = str_val in ['AB', 'ABSENT', 'UA', 'W']
            return 0.0, False, str_val

        marks_list = []
        univ_marks_by_sem = {}  # { sem_num: [ { mark_info } ] }
        all_univ_subject_attempts = {}  # { subject_key: [ { sem_num, credits, gp, is_pass, mark } ] }
        history_arrears_count = 0

        for m in marks_qs:
            sem_num = extract_sem_num(m.subject) if m.subject else 1
            sem_name = resolve_sem_label(m.subject) if m.subject else f"Semester {sem_num}"
            
            exam_type_label = 'CIA'
            is_univ_exam = False
            if m.exam:
                if m.exam.exam_type:
                    exam_type_label = getattr(m.exam.exam_type, 'exam_type_name', str(m.exam.exam_type))
                else:
                    exam_type_label = m.exam.exam_name or 'Internal'
            
            type_str = str(exam_type_label).lower()
            if 'university' in type_str or 'external' in type_str or 'end sem' in type_str or 'semester exam' in type_str:
                is_univ_exam = True

            credits_val = float(m.subject.credits) if (m.subject and m.subject.credits is not None) else 0.0
            gp, is_pass_val, grade_letter = get_grade_point_and_pass(m.marks_obtained)
            credit_points = round(credits_val * gp, 2)

            mark_record = {
                'id': m.id,
                'exam_id': m.exam_id,
                'exam_name': m.exam.exam_name if m.exam else '',
                'exam_type': exam_type_label,
                'is_university_exam': is_univ_exam,
                'subject_id': m.subject_id,
                'subject_code': m.subject.subject_code if m.subject else '',
                'subject_name': m.subject.subject_name if m.subject else '',
                'subject_category': m.subject_category or 'THEORY',
                'credits': credits_val,
                'semester_name': sem_name,
                'semester_num': sem_num,
                'marks_obtained': m.marks_obtained,
                'grade_point': gp,
                'is_pass': is_pass_val,
                'grade_letter': grade_letter,
                'credit_points': credit_points,
            }
            marks_list.append(mark_record)

            # Accumulate university examination entries for GPA / CGPA computation
            if is_univ_exam:
                if not is_pass_val and m.marks_obtained:
                    history_arrears_count += 1

                if sem_num not in univ_marks_by_sem:
                    univ_marks_by_sem[sem_num] = []
                univ_marks_by_sem[sem_num].append(mark_record)

                subj_key = f"{m.subject_id}_{m.subject_category or 'THEORY'}"
                if subj_key not in all_univ_subject_attempts:
                    all_univ_subject_attempts[subj_key] = []
                all_univ_subject_attempts[subj_key].append(mark_record)

        # ── Process Chronological Attempts & Standing Arrears Tracker ──────────
        standing_arrears_list = []
        for subj_key, attempts in all_univ_subject_attempts.items():
            origin_sem = attempts[0]['semester_num'] if attempts else 1
            for idx, att in enumerate(attempts):
                att_num = idx + 1
                app_sem = min(8, origin_sem + idx)
                att['origin_sem_num'] = origin_sem
                att['origin_semester'] = f"Semester {origin_sem}"
                att['attempt_count'] = att_num
                att['appearance_sem_num'] = app_sem
                att['appearance_semester'] = f"Semester {app_sem}"
                att['is_arrear_appearance'] = (att_num > 1)

            latest_att = attempts[-1]
            if not latest_att['is_pass']:
                standing_arrears_list.append({
                    'subject_id': latest_att['subject_id'],
                    'subject_code': latest_att['subject_code'],
                    'subject_name': latest_att['subject_name'],
                    'subject_category': latest_att['subject_category'],
                    'origin_sem_num': origin_sem,
                    'origin_semester': f"Semester {origin_sem}",
                    'latest_attempt_count': len(attempts),
                    'latest_grade': latest_att['marks_obtained'],
                    'credits': latest_att['credits'],
                    'next_appearance_sem': min(8, latest_att.get('appearance_sem_num', origin_sem) + 1),
                })

        # ── Calculate Anna University GPA & CGPA for Semesters 1 to 8 ──────────
        semester_performance_map = {}
        for s_idx in range(1, 9):
            s_marks = univ_marks_by_sem.get(s_idx, [])
            
            # Deduplicate by unique subject for that semester (latest attempt)
            unique_sem_subjects = {}
            for rec in s_marks:
                skey = f"{rec['subject_id']}_{rec['subject_category']}"
                unique_sem_subjects[skey] = rec

            sem_total_credits = 0.0
            sem_earned_credits = 0.0
            sem_credit_points = 0.0
            sem_has_arrear = False

            for rec in unique_sem_subjects.values():
                c = rec['credits']
                gp = rec['grade_point']
                if c > 0:
                    sem_total_credits += c
                    sem_credit_points += (c * gp)
                    if rec['is_pass']:
                        sem_earned_credits += c
                    else:
                        sem_has_arrear = True
                elif not rec['is_pass']:
                    sem_has_arrear = True

            gpa = round(sem_credit_points / sem_earned_credits, 2) if sem_earned_credits > 0 else 0.00

            # Cumulative CGPA up to Semester s_idx:
            # Considers all university subjects registered from Sem 1 up to Sem s_idx
            # For subjects with multiple attempts up to Sem s_idx, take the latest attempt
            cum_subjects = {}
            for past_sem in range(1, s_idx + 1):
                for rec in univ_marks_by_sem.get(past_sem, []):
                    skey = f"{rec['subject_id']}_{rec['subject_category']}"
                    cum_subjects[skey] = rec  # overwrites with latest attempt up to past_sem

            cum_total_credits = 0.0
            cum_earned_credits = 0.0
            cum_credit_points = 0.0
            for s_entry in cum_subjects.values():
                c = s_entry['credits']
                gp = s_entry['grade_point']
                if c > 0:
                    cum_total_credits += c
                    cum_credit_points += (c * gp)
                    if s_entry['is_pass']:
                        cum_earned_credits += c

            cgpa_up_to_sem = round(cum_credit_points / cum_earned_credits, 2) if (cum_earned_credits > 0 and len(unique_sem_subjects) > 0) else 0.00

            semester_performance_map[s_idx] = {
                'semester_num': s_idx,
                'semester_name': f"Semester {s_idx}",
                'gpa': gpa,
                'cgpa': cgpa_up_to_sem,
                'total_credits': sem_total_credits,
                'earned_credits': sem_earned_credits,
                'credit_points': round(sem_credit_points, 2),
                'cumulative_credits': cum_total_credits,
                'cumulative_earned_credits': cum_earned_credits,
                'has_arrear': sem_has_arrear,
                'subject_count': len(unique_sem_subjects),
                'has_records': len(unique_sem_subjects) > 0,
            }

        # Overall Latest Cumulative CGPA & Standing Arrears Count
        overall_unique_subjects = {}
        for s_idx in range(1, 9):
            for rec in univ_marks_by_sem.get(s_idx, []):
                skey = f"{rec['subject_id']}_{rec['subject_category']}"
                overall_unique_subjects[skey] = rec

        tot_reg_credits = 0.0
        tot_earned_credits = 0.0
        tot_cum_points = 0.0
        standing_arrears_count = 0

        for rec in overall_unique_subjects.values():
            c = rec['credits']
            gp = rec['grade_point']
            if c > 0:
                tot_reg_credits += c
                tot_cum_points += (c * gp)
                if rec['is_pass']:
                    tot_earned_credits += c
                else:
                    standing_arrears_count += 1
            else:
                if not rec['is_pass']:
                    standing_arrears_count += 1

        overall_cgpa = round(tot_cum_points / tot_earned_credits, 2) if tot_earned_credits > 0 else 0.00

        academics_summary = {
            'overall_cgpa': overall_cgpa,
            'total_credits_registered': tot_reg_credits,
            'total_credits_earned': tot_earned_credits,
            'standing_arrears': standing_arrears_count,
            'history_arrears': history_arrears_count,
            'standing_arrears_list': standing_arrears_list,
            'semesters': semester_performance_map,
        }

        # ── 3. Attendance Percentage (Subject-wise & Overall) ─────────────────
        from ..models import StudentAttendance
        att_qs = StudentAttendance.objects.filter(student=student).select_related(
            'faculty_activity__timetable__subject',
            'faculty_activity__timetable__subject__semester'
        )

        overall_total = 0
        overall_present = 0
        overall_absent = 0
        overall_od = 0

        subj_map = {}
        for a in att_qs:
            overall_total += 1
            if a.status == 'P':
                overall_present += 1
            elif a.status == 'AB':
                overall_absent += 1
            elif a.status == 'OD':
                overall_od += 1

            activity = a.faculty_activity
            tt = activity.timetable if activity else None
            subj = tt.subject if tt else None
            if not subj:
                continue

            sid = subj.id
            if sid not in subj_map:
                sem_title = resolve_sem_label(subj.semester) if subj.semester else "Semester 1"
                subj_map[sid] = {
                    'subject_id': sid,
                    'subject_code': subj.subject_code,
                    'subject_name': subj.subject_name,
                    'semester_name': sem_title,
                    'total_classes': 0,
                    'present_count': 0,
                    'absent_count': 0,
                    'od_count': 0,
                }

            subj_map[sid]['total_classes'] += 1
            if a.status == 'P':
                subj_map[sid]['present_count'] += 1
            elif a.status == 'AB':
                subj_map[sid]['absent_count'] += 1
            elif a.status == 'OD':
                subj_map[sid]['od_count'] += 1

        subject_wise_attendance = []
        for sinfo in subj_map.values():
            total = sinfo['total_classes']
            attended = sinfo['present_count'] + sinfo['od_count']
            pct = round((attended / total * 100), 2) if total > 0 else 0.0
            subject_wise_attendance.append({
                **sinfo,
                'percentage': pct,
            })

        subject_wise_attendance.sort(key=lambda x: x['subject_code'])

        overall_attended = overall_present + overall_od
        overall_percentage = round((overall_attended / overall_total * 100), 2) if overall_total > 0 else 0.0

        # ── 4. Counselling Reports ─────────────────────────────────────
        from ..models import CounsellingReport
        counselling_qs = CounsellingReport.objects.filter(student=student).select_related('semester', 'created_by').order_by('-report_date')
        counselling_list = []
        for c in counselling_qs:
            sem_title = resolve_sem_label(c.semester) if c.semester else "Semester 1"
            counselor_name = "—"
            if c.created_by:
                cb = c.created_by
                full_name_func = getattr(cb, 'get_full_name', None)
                if getattr(cb, 'name', None):
                    counselor_name = cb.name
                elif callable(full_name_func):
                    counselor_name = full_name_func()
                elif getattr(cb, 'first_name', None):
                    counselor_name = cb.first_name
                elif getattr(cb, 'username', None):
                    counselor_name = cb.username
            counselling_list.append({
                'id': c.id,
                'semester_name': sem_title,
                'report_date': c.report_date.strftime('%Y-%m-%d') if c.report_date else '',
                'remarks': c.remarks,
                'counselled_by': counselor_name,
            })

        return Response({
            "code": 200,
            "multiple": False,
            "message": "Student comprehensive view retrieved successfully",
            "data": {
                "profile": profile_data,
                "marks": marks_list,
                "academics": academics_summary,
                "counselling": counselling_list,
                "attendance": {
                    "overall": {
                        "total_classes": overall_total,
                        "present_count": overall_present,
                        "absent_count": overall_absent,
                        "od_count": overall_od,
                        "attended_count": overall_attended,
                        "percentage": overall_percentage,
                    },
                    "subject_wise": subject_wise_attendance,
                }
            }
        }, status=status.HTTP_200_OK)

    def admission_slip_pdf(self, request, pk, *args, **kwargs):
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
        bus_from = _get_bus_from(student)
        bus_to = _get_bus_to(student)

        hostel_bldg_dict = dict(getattr(Student, 'HOSTEL_BUILDING_CHOICES', []))
        hostel_bldg_name = hostel_bldg_dict.get(student.hostel_building_type, student.hostel_building_type or '—')
        if student.is_hostler:
            acc_details_str = f"Hostel: {hostel_bldg_name} | Room: {student.hostel_room_number or '—'}"
        elif student.is_bus:
            acc_details_str = (
                f"Bus: {student.bus.bus_number if student.bus else '—'}"
                f" &nbsp;|&nbsp; Route: {student.route.route_name if student.route else '—'}"
                f"{f' &nbsp;|&nbsp; Stop: {student.stop.stop_name}' if student.stop else ''}"
            )
        else:
            acc_details_str = "—"

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

        college_name = college_header_obj.college_name if college_header_obj else ''
        college_address = college_header_obj.address if college_header_obj else ''
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
                Paragraph("<b>Hostel / Bus Info:</b>", body_style),
                Paragraph(acc_details_str, body_bold)
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
        from dynamic_forms.models import ApplicationUser, Application, ApplicationStatus
        from institution.models import Department, Batch, Section, Quota
        from users.models import User as StandardUser

        def parse_date(date_str):
            if not date_str:
                return None
            if isinstance(date_str, datetime.date):
                return date_str
            if isinstance(date_str, dt_datetime):
                return date_str.date()
            date_str = str(date_str).strip()
            if not date_str:
                return None
            if 'T' in date_str:
                date_str = date_str.split('T')[0]
            elif ' ' in date_str:
                date_str = date_str.split(' ')[0]
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%m/%d/%Y'):
                try:
                    return dt_datetime.strptime(date_str, fmt).date()
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

        def parse_decimal_or_none(val, is_percentage=False):
            if val is None:
                return None
            val_str = str(val).strip()
            if not val_str:
                return None
            if val_str.endswith('%'):
                val_str = val_str[:-1].strip()
            try:
                num = float(val_str)
                if is_percentage and 0 < num <= 1.0:
                    num = round(num * 100, 2)
                return num
            except (ValueError, TypeError):
                return None

        def sanitize_phone_number(val):
            if not val:
                return ''
            s = str(val).strip()
            if s.endswith('.0'):
                s = s[:-2]
            digits = re.sub(r'\D', '', s)
            if len(digits) == 12 and digits.startswith('91'):
                return digits[2:]
            if len(digits) == 11 and digits.startswith('0'):
                return digits[1:]
            return digits

        # 1. Validation Phase (No DB writes)
        for idx, s in enumerate(students_data):
            row_num = s.get('s_no', idx + 1)
            name = str(s.get('name', '')).strip()
            raw_gender = str(s.get('gender', '') or s.get('sex', '')).strip()
            if raw_gender.lower() in ['m', 'male']:
                gender = 'Male'
            elif raw_gender.lower() in ['f', 'female']:
                gender = 'Female'
            elif raw_gender.lower() in ['o', 'other']:
                gender = 'Other'
            else:
                gender = raw_gender.capitalize() if raw_gender else ''

            email = str(s.get('email', '')).strip()
            phone_raw = s.get('phone_number', '') or s.get('mobile_number', '') or s.get('phone', '')
            phone_number = sanitize_phone_number(phone_raw)
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
            dob = str(s.get('dob', '') or s.get('date_of_birth', '')).strip()
            nationality = str(s.get('nationality', '')).strip()
            mother_tongue = str(s.get('mother_tongue', '')).strip()
            parent_name = str(s.get('parent_name', '')).strip()
            parent_phone_raw = s.get('parent_phone', '') or s.get('parent_mobile', '') or s.get('father_mobile', '')
            parent_phone = sanitize_phone_number(parent_phone_raw)
            parent_occupation = str(s.get('parent_occupation', '') or s.get('occupation', '')).strip()
            annual_income = str(s.get('annual_income', '') or s.get('income', '')).strip()
            district = str(s.get('district', '')).strip()
            state = str(s.get('state', '')).strip()
            address = str(s.get('address', '')).strip()
            pincode = str(s.get('pincode', '')).strip()
            aadhaar_number = str(s.get('aadhaar_number', '')).strip()
            emis_number = str(s.get('emis_number', '')).strip()
            umis_number = str(s.get('umis_number', '')).strip()
            community = str(s.get('community', '')).strip()
            qualification = str(s.get('qualification', '')).strip()
            year_of_passing = str(s.get('year_of_passing', '')).strip()

            marks_percentage = parse_decimal_or_none(s.get('marks_percentage'), is_percentage=True)
            
            row_errors = []

            # Check required fields
            if not name:
                row_errors.append("Name is required.")

            if email:
                try:
                    validate_email(email)
                except DjangoValidationError:
                    row_errors.append("Invalid email address format.")
            else:
                # Auto-generate a unique system email if not provided in sheet
                base_id = roll_number or register_number or phone_number
                clean_base = re.sub(r'[^a-zA-Z0-9]', '', str(base_id)).lower() if base_id else f"student_{idx + 1}"
                generated_email = f"{clean_base}@student.ims"
                counter = 1
                candidate_email = generated_email
                while candidate_email in seen_emails or ApplicationUser.objects.filter(email=candidate_email).exists():
                    candidate_email = f"{clean_base}_{counter}@student.ims"
                    counter += 1
                email = candidate_email

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
                        "gender": gender,
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
                        "dob": dob,
                        "nationality": nationality,
                        "mother_tongue": mother_tongue,
                        "parent_name": parent_name,
                        "parent_phone": parent_phone,
                        "parent_occupation": parent_occupation,
                        "annual_income": annual_income,
                        "district": district,
                        "state": state,
                        "address": address,
                        "pincode": pincode,
                        "aadhaar_number": aadhaar_number,
                        "emis_number": emis_number,
                        "umis_number": umis_number,
                        "community": community,
                        "qualification": qualification,
                        "year_of_passing": year_of_passing,
                        "marks_percentage": marks_percentage,
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

                    program = getattr(item["department"], 'program', None)
                    if not program:
                        from institution.models import Program
                        program = Program.objects.first()
                    program_level = getattr(program, 'program_level', 'UG') or 'UG'
                    year = dt_datetime.now().year
                    year_str = str(year)[2:]
                    prefix = f"{program_level}{year_str}"

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
                            "gender": item["gender"] or "",
                            "dob": item["dob"] or "",
                            "date_of_birth": item["dob"] or "",
                            "nationality": item["nationality"] or "Indian",
                            "mother_tongue": item["mother_tongue"] or "",
                            "aadhaar_number": item["aadhaar_number"] or "",
                            "community": item["community"] or "",
                        },
                        "parent_information": {
                            "parent_name": item["parent_name"] or "",
                            "parent_mobile": item["parent_phone"] or "",
                            "parent_occupation": item["parent_occupation"] or "",
                            "annual_income": item["annual_income"] or "",
                            "district": item["district"] or "",
                            "state": item["state"] or "",
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
                                    "year_of_passing": item["year_of_passing"] or "",
                                }
                            ]
                        }
                    }

                    application = Application.objects.create(
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
                        application=application,
                        lab_batch=item["lab_batch"],
                        quota=item["quota"],
                        is_hostler=item["is_hostler"],
                        is_day_scholar=item["is_day_scholar"],
                        is_bus=item["is_bus"],
                        status=active_status,
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    # Create / update StudentAdmissionSlip eagerly
                    StudentAdmissionSlip.objects.update_or_create(
                        student=student,
                        defaults={
                            "aadhaar_number": item["aadhaar_number"] or None,
                            "emis_number": item["emis_number"] or f"EMIS-{app_no}",
                            "umis_number": item["umis_number"] or None,
                            "qualification": item["qualification"] or None,
                            "community": item["community"] or None,
                            "marks_percentage": item["marks_percentage"],
                            "created_by": tracking_user,
                            "updated_by": tracking_user
                        }
                    )

                    # Create / preserve StudentFees safely from database Fee Structure
                    from institution.models import FeesStructure
                    from decimal import Decimal
                    total_fees = Decimal('0.00')
                    matching_fs = None
                    if student.department and student.batch and student.quota:
                        matching_fs = FeesStructure.objects.filter(
                            department=student.department,
                            batch=student.batch,
                            quota=student.quota
                        ).first()
                        if matching_fs:
                            total_fees = matching_fs.fees

                    sf = StudentFees.objects.filter(student=student).first()
                    if not sf:
                        sf = StudentFees.objects.create(
                            student=student,
                            total_fees=total_fees,
                            paid_amount=Decimal('0.00'),
                            balance_amount=total_fees,
                            created_by=tracking_user,
                            updated_by=tracking_user
                        )
                    else:
                        # SAFEGUARD: Existing student record — NEVER overwrite paid_amount or concessions!
                        if sf.paid_amount == Decimal('0.00') and sf.total_fees == Decimal('0.00') and total_fees > Decimal('0.00'):
                            sf.total_fees = total_fees
                            sf.balance_amount = total_fees
                            sf.updated_by = tracking_user
                            sf.save(update_fields=['total_fees', 'balance_amount', 'updated_by', 'updated_at'])

                    # Initialize Semester Allocations if applicable and complete
                    if matching_fs and matching_fs.is_allocation_complete:
                        for alloc in matching_fs.semester_allocations.select_related('semester').all():
                            if not StudentSemesterFee.objects.filter(student_fees=sf, semester=alloc.semester).exists():
                                StudentSemesterFee.objects.create(
                                    student_fees=sf,
                                    semester=alloc.semester,
                                    semester_fee_structure=alloc,
                                    total_amount=alloc.amount,
                                    concession_amount=Decimal('0.00'),
                                    paid_amount=Decimal('0.00'),
                                    balance_amount=alloc.amount,
                                    due_date=alloc.due_date,
                                    status='PENDING',
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

    @action(detail=False, methods=['get', 'post'], url_path='name-list-report/pdf')
    def name_list_report_pdf(self, request, *args, **kwargs):
        dept_id = request.data.get('department') or request.query_params.get('department')
        batch_id = request.data.get('batch') or request.query_params.get('batch')
        section_id = request.data.get('section') or request.query_params.get('section')
        program_id = request.data.get('program') or request.query_params.get('program')
        header_type = request.data.get('report_header') or request.query_params.get('report_header')

        from institution.models import Department, Batch, Section, Program, CollegeHeader

        department = None
        if dept_id:
            if str(dept_id).isdigit():
                department = Department.objects.filter(id=int(dept_id)).first()
            if not department:
                department = Department.objects.filter(department_code=dept_id).first()
            if not department:
                department = Department.objects.filter(department_name__iexact=dept_id).first()

        batch = None
        if batch_id:
            if str(batch_id).isdigit():
                batch = Batch.objects.filter(id=int(batch_id)).first()
            if not batch:
                batch = Batch.objects.filter(batch=batch_id).first()

        section_obj = None
        if section_id:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=int(section_id)).first()
            if not section_obj:
                section_obj = Section.objects.filter(sections__iexact=section_id).first()

        program_obj = None
        if program_id:
            if str(program_id).isdigit():
                program_obj = Program.objects.filter(id=int(program_id)).first()
            if not program_obj:
                program_obj = Program.objects.filter(program_name__iexact=program_id).first()
        elif department and getattr(department, 'program', None):
            program_obj = department.program

        college_header_obj = None
        if header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type=header_type).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        students_qs = Student.objects.select_related(
            'department', 'department__program', 'batch', 'section', 'quota',
            'application', 'application__candidate'
        ).all()

        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)
        elif section_id:
            students_qs = students_qs.filter(section__sections__iexact=str(section_id))
        if program_obj:
            students_qs = students_qs.filter(department__program=program_obj)

        students = list(students_qs.order_by('roll_number', 'register_number', 'student_name'))

        if not students:
            return HttpResponse("No students found matching the selected criteria.", status=400)

        # ── PDF Generation ──
        buffer = BytesIO()
        page_size = A4
        doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)

        story = []

        page_w = page_size[0] - 40  # 555.27 pt
        col_widths = [45, 135, 145, 230]  # Sum = 555 pt (S.No, Roll No, Register No, Student Name)

        # 1. College Header (ONLY on first page if header configured)
        header_table = build_standard_college_header(college_header_obj, page_w=page_w, logo_size=62)
        if header_table:
            story.append(header_table)
            story.append(Spacer(1, 6))

        # 2. Report Name centered after college header (ONLY on first page)
        story.append(build_centered_report_title("STUDENT NAME LIST", font_size=12, leading=15))
        story.append(Spacer(1, 6))

        sec_name = section_obj.sections if section_obj else (section_id if section_id else '—')
        batch_str = batch.batch if batch else '—'
        dept_str = department.department_name.title() if department else '—'
        prog_str = program_obj.program_name.upper() if program_obj else (department.program.program_name.upper() if department and department.program else '—')

        lbl_bold = ParagraphStyle(name='NLLbl', fontName='Times-Bold', fontSize=9, leading=12, textColor=colors.black)
        val_norm = ParagraphStyle(name='NLVal', fontName='Times-Roman', fontSize=9, leading=12, textColor=colors.black)

        tbl_hdr_style = ParagraphStyle(name='NLTH', fontName='Times-Bold', fontSize=10.5, leading=13, alignment=1, textColor=colors.black)
        tbl_cell_center = ParagraphStyle(name='NLCC', fontName='Times-Roman', fontSize=9.5, leading=13, alignment=1, textColor=colors.black)
        tbl_cell_left = ParagraphStyle(name='NLCL', fontName='Times-Roman', fontSize=9.5, leading=13, alignment=0, textColor=colors.black)

        # 3. Meta Info Table (Program, Department, Batch, Section)
        meta_data = [
            [Paragraph("<b>Program:</b>", lbl_bold), Paragraph(prog_str, val_norm),
             Paragraph("<b>Department:</b>", lbl_bold), Paragraph(dept_str, val_norm)],
            [Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(str(batch_str), val_norm),
             Paragraph("<b>Section:</b>", lbl_bold), Paragraph(str(sec_name), val_norm)],
        ]
        meta_table = Table(meta_data, colWidths=[90, 185, 95, 185])
        meta_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        # 4. Continuous Student Table (Repeats column headers only on upcoming pages, no college header)
        header_row = [
            Paragraph("<b>S.No</b>", tbl_hdr_style),
            Paragraph("<b>Roll No</b>", tbl_hdr_style),
            Paragraph("<b>Register No</b>", tbl_hdr_style),
            Paragraph("<b>Student Name</b>", tbl_hdr_style),
        ]
        table_rows = [header_row]

        for i, st in enumerate(students, start=1):
            st_name = (st.name if hasattr(st, 'name') and st.name else (st.student_name or ''))
            roll_no = st.roll_number or '—'
            reg_no = st.register_number or '—'

            row = [
                Paragraph(str(i), tbl_cell_center),
                Paragraph(roll_no, tbl_cell_center),
                Paragraph(reg_no, tbl_cell_center),
                Paragraph(st_name.upper(), tbl_cell_left),
            ]
            table_rows.append(row)

        student_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        ts = [
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#64748B')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
        ]
        for r in range(1, len(table_rows)):
            if r % 2 == 0:
                ts.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor('#F8FAFC')))
        student_table.setStyle(TableStyle(ts))
        story.append(student_table)

        # 5. Institutional Sign-off Block at the end of the report
        story.append(Spacer(1, 28))
        sig_data = [[
            Paragraph("<b>Class In-Charge</b>", val_norm),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='NLSigHOD', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1)),
            Paragraph("<b>Principal</b>", ParagraphStyle(name='NLSigPrin', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2))
        ]]
        sig_table = Table(sig_data, colWidths=[185, 185, 185])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether(sig_table))

        doc.build(story)
        buffer.seek(0)

        dept_file_str = (department.department_code or department.department_name or '').replace(' ', '_') if department else 'All'
        batch_file_str = str(batch_str).replace(' ', '_')
        sec_file_str = str(sec_name).replace(' ', '_')
        filename = f"Student_Name_List_{dept_file_str}_{batch_file_str}_Sec_{sec_file_str}.pdf"

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    def _get_fees_semester_data_helper(self, request):
        req_data = getattr(request, 'data', None) or {}
        req_params = getattr(request, 'query_params', None) or getattr(request, 'GET', {})
        dept_id = req_data.get('department') or req_params.get('department') or req_data.get('department_id') or req_params.get('department_id')
        batch_id = req_data.get('batch') or req_params.get('batch') or req_data.get('batch_id') or req_params.get('batch_id')
        section_id = req_data.get('section') or req_params.get('section') or req_data.get('section_id') or req_params.get('section_id')
        program_id = req_data.get('program') or req_params.get('program')
        sem_param = req_data.get('semester') or req_params.get('semester') or 1
        header_type = req_data.get('report_header') or req_params.get('report_header')

        from institution.models import Department, Batch, Section, Program, CollegeHeader, Semester, FeesStructure
        from student.models import StudentFees, StudentSemesterFee

        try:
            sem_num = int(sem_param)
        except (ValueError, TypeError):
            sem_num = 1

        department = None
        if dept_id:
            if str(dept_id).isdigit():
                department = Department.objects.filter(id=int(dept_id)).first()
            if not department:
                department = Department.objects.filter(department_code=dept_id).first()
            if not department:
                department = Department.objects.filter(department_name__iexact=dept_id).first()

        batch = None
        if batch_id:
            if str(batch_id).isdigit():
                batch = Batch.objects.filter(id=int(batch_id)).first()
            if not batch:
                batch = Batch.objects.filter(batch=batch_id).first()

        section_obj = None
        if section_id:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=int(section_id)).first()
            if not section_obj:
                section_obj = Section.objects.filter(sections__iexact=section_id).first()

        program_obj = None
        if program_id:
            if str(program_id).isdigit():
                program_obj = Program.objects.filter(id=int(program_id)).first()
            if not program_obj:
                program_obj = Program.objects.filter(program_name__iexact=program_id).first()
        elif department and getattr(department, 'program', None):
            program_obj = department.program

        college_header_obj = None
        if header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type=header_type).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        # Only students who have a quota assigned fetch fees
        students_qs = Student.objects.select_related(
            'department', 'department__program', 'batch', 'section', 'quota',
            'application', 'application__candidate'
        ).filter(quota__isnull=False)

        quota_param = req_data.get('quota') or req_params.get('quota') or req_data.get('quota_id') or req_params.get('quota_id')
        if quota_param and str(quota_param).strip().lower() not in ['', 'all', 'all_quotas', 'undefined', 'null']:
            if str(quota_param).isdigit():
                students_qs = students_qs.filter(quota_id=int(quota_param))
            else:
                students_qs = students_qs.filter(quota__quota_name__iexact=str(quota_param).strip())

        if department:
            students_qs = students_qs.filter(department=department)
        if batch:
            students_qs = students_qs.filter(batch=batch)
        if section_obj:
            students_qs = students_qs.filter(section=section_obj)
        elif section_id:
            students_qs = students_qs.filter(section__sections__iexact=str(section_id))
        if program_obj:
            students_qs = students_qs.filter(department__program=program_obj)

        students = list(students_qs.order_by('roll_number', 'register_number', 'student_name'))

        # Bulk fetch fees to ensure fast response
        st_ids = [s.id for s in students]
        sf_list = StudentFees.objects.filter(student_id__in=st_ids)
        sf_map = {sf.student_id: sf for sf in sf_list}
        sf_ids = [sf.id for sf in sf_list]

        sem_fee_list = StudentSemesterFee.objects.filter(student_fees_id__in=sf_ids, semester__semester_number=sem_num).select_related('semester')
        sem_fee_map = {sm.student_fees_id: sm for sm in sem_fee_list}

        fs_list = FeesStructure.objects.all()
        fs_map = {(fs.department_id, fs.batch_id, fs.quota_id): fs for fs in fs_list}

        records = []
        tot_fee = 0.0
        tot_paid = 0.0
        tot_concession = 0.0
        tot_bal = 0.0

        for i, st in enumerate(students, start=1):
            st_name = (st.name if hasattr(st, 'name') and st.name else (st.student_name or 'Student'))
            reg_no = st.register_number or st.roll_number or '—'
            quota_name = st.quota.quota_name if st.quota else 'Regular'

            sf = sf_map.get(st.id)
            sem_fee = sem_fee_map.get(sf.id) if sf else None

            if sem_fee:
                cur_total = float(sem_fee.total_amount or 0)
                cur_paid = float(sem_fee.paid_amount or 0)
                cur_concession = float(sem_fee.concession_amount or 0)
                cur_bal = float(sem_fee.balance_amount or 0)
                cur_status = sem_fee.status
            elif sf and sf.total_fees:
                cur_total = float(sf.total_fees or 0) / 8.0
                cur_paid = 0.0
                cur_concession = 0.0
                cur_bal = cur_total
                cur_status = 'PENDING' if cur_total > 0 else 'NOT SET'
            elif st.quota_id:
                fs = fs_map.get((st.department_id, st.batch_id, st.quota_id))
                cur_total = float(fs.fees or 0) / 8.0 if fs else 0.0
                cur_paid = 0.0
                cur_concession = 0.0
                cur_bal = cur_total
                cur_status = 'PENDING' if cur_total > 0 else 'NOT SET'
            else:
                cur_total = 0.0
                cur_paid = 0.0
                cur_concession = 0.0
                cur_bal = 0.0
                cur_status = 'NOT SET'

            tot_fee += cur_total
            tot_paid += cur_paid
            tot_concession += cur_concession
            tot_bal += cur_bal

            records.append({
                'sno': i,
                'student_id': st.id,
                'register_no': reg_no,
                'roll_no': st.roll_number or '—',
                'name': st_name,
                'quota': quota_name,
                'total_fee': cur_total,
                'paid_fee': cur_paid,
                'concession_fee': cur_concession,
                'balance_fee': cur_bal,
                'status': cur_status,
            })

        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'All Sections')
        batch_str = batch.batch if batch else 'All Batches'
        dept_str = department.department_name if department else 'All Departments'
        prog_str = program_obj.program_name if program_obj else (department.program.program_name if department and department.program else 'All Programs')

        meta = {
            'program': prog_str,
            'department': dept_str,
            'batch': str(batch_str),
            'section': str(sec_name),
            'semester': sem_num,
            'semester_name': f"Semester {sem_num}",
        }

        summary = {
            'total_students': len(students),
            'total_semester_fees': tot_fee,
            'total_paid_fees': tot_paid,
            'total_concession_fees': tot_concession,
            'total_balance_fees': tot_bal,
        }

        return meta, summary, records, college_header_obj, department, batch, sec_name, sem_num

    def fees_semester_report(self, request, *args, **kwargs):
        """JSON endpoint returning filtered semester fee records."""
        meta, summary, records, _, _, _, _, _ = self._get_fees_semester_data_helper(request)
        return Response({
            'success': True,
            'metadata': meta,
            'summary': summary,
            'students': records
        }, status=status.HTTP_200_OK)

    def fees_semester_report_pdf(self, request, *args, **kwargs):
        """Generates and streams an official PDF report of semester fees."""
        meta, summary, records, college_header_obj, department, batch, sec_name, sem_num = self._get_fees_semester_data_helper(request)

        if not records:
            return HttpResponse("No students found matching the selected criteria.", status=400)

        buffer = BytesIO()
        page_size = A4
        doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)

        story = []
        page_w = page_size[0] - 40  # 555.27 pt

        # 1. College Header (only if header is configured in database)
        header_table = build_standard_college_header(college_header_obj, page_w=page_w, logo_size=62)
        if header_table:
            story.append(header_table)
            story.append(Spacer(1, 6))

        # 2. Centered Report Title
        story.append(build_centered_report_title(f"FEES REPORT — SEMESTER {sem_num}", font_size=12, leading=15))
        story.append(Spacer(1, 6))

        # 3. Meta Info Table
        lbl_bold = ParagraphStyle(name='FRLbl', fontName='Times-Bold', fontSize=9, leading=12, textColor=colors.black)
        val_norm = ParagraphStyle(name='FRVal', fontName='Times-Roman', fontSize=9, leading=12, textColor=colors.black)

        meta_data = [
            [Paragraph("<b>Program:</b>", lbl_bold), Paragraph(str(meta['program']), val_norm),
             Paragraph("<b>Department:</b>", lbl_bold), Paragraph(str(meta['department']), val_norm)],
            [Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(str(meta['batch']), val_norm),
             Paragraph("<b>Section:</b>", lbl_bold), Paragraph(str(meta['section']), val_norm)],
            [Paragraph("<b>Semester:</b>", lbl_bold), Paragraph(str(meta['semester_name']), val_norm),
             Paragraph("<b>Total Students:</b>", lbl_bold), Paragraph(str(summary['total_students']), val_norm)],
        ]
        meta_table = Table(meta_data, colWidths=[90, 185, 95, 185])
        meta_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 8))

        # 4. Student Fee Table
        # Columns: S.No (35), Reg No (95), Name (155), Quota (70), Total Fee (65), Paid Fee (65), Balance (70) -> Sum = 555 pt
        col_widths = [35, 95, 155, 70, 65, 65, 70]
        tbl_hdr_style = ParagraphStyle(name='FRTH', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1, textColor=colors.black)
        tbl_hdr_right = ParagraphStyle(name='FRTHR', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2, textColor=colors.black)
        tbl_cell_center = ParagraphStyle(name='FRCC', fontName='Times-Roman', fontSize=9, leading=12, alignment=1, textColor=colors.black)
        tbl_cell_left = ParagraphStyle(name='FRCL', fontName='Times-Roman', fontSize=9, leading=12, alignment=0, textColor=colors.black)
        tbl_cell_right = ParagraphStyle(name='FRCR', fontName='Times-Roman', fontSize=9, leading=12, alignment=2, textColor=colors.black)
        tbl_tot_bold = ParagraphStyle(name='FRTB', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2, textColor=colors.black)

        header_row = [
            Paragraph("<b>S.No</b>", tbl_hdr_style),
            Paragraph("<b>Register No</b>", tbl_hdr_style),
            Paragraph("<b>Student Name</b>", tbl_hdr_style),
            Paragraph("<b>Quota</b>", tbl_hdr_style),
            Paragraph("<b>Total Fee</b>", tbl_hdr_right),
            Paragraph("<b>Paid Fee</b>", tbl_hdr_right),
            Paragraph("<b>Balance</b>", tbl_hdr_right),
        ]
        table_rows = [header_row]

        for r in records:
            row = [
                Paragraph(str(r['sno']), tbl_cell_center),
                Paragraph(str(r['register_no']), tbl_cell_center),
                Paragraph(str(r['name']).upper(), tbl_cell_left),
                Paragraph(str(r['quota']), tbl_cell_center),
                Paragraph(f"{r['total_fee']:,.2f}", tbl_cell_right),
                Paragraph(f"{r['paid_fee']:,.2f}", tbl_cell_right),
                Paragraph(f"{r['balance_fee']:,.2f}", tbl_cell_right),
            ]
            table_rows.append(row)

        # Totals footer row
        total_row = [
            Paragraph("<b>TOTAL</b>", ParagraphStyle(name='FRTotL', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1)),
            Paragraph("", tbl_cell_center),
            Paragraph(f"<b>{summary['total_students']} Students</b>", ParagraphStyle(name='FRTotSt', fontName='Times-Bold', fontSize=9, leading=12, alignment=0)),
            Paragraph("", tbl_cell_center),
            Paragraph(f"<b>{summary['total_semester_fees']:,.2f}</b>", tbl_tot_bold),
            Paragraph(f"<b>{summary['total_paid_fees']:,.2f}</b>", tbl_tot_bold),
            Paragraph(f"<b>{summary['total_balance_fees']:,.2f}</b>", tbl_tot_bold),
        ]
        table_rows.append(total_row)

        fee_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        ts = [
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#64748B')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F1F5F9')),
        ]
        for r_idx in range(1, len(table_rows) - 1):
            if r_idx % 2 == 0:
                ts.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#F8FAFC')))
        fee_table.setStyle(TableStyle(ts))
        story.append(fee_table)

        # 5. Signatures
        story.append(Spacer(1, 26))
        sig_data = [[
            Paragraph("<b>Class In-Charge</b>", val_norm),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='FRSigHOD', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1)),
            Paragraph("<b>Principal / Cashier</b>", ParagraphStyle(name='FRSigPrin', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2))
        ]]
        sig_table = Table(sig_data, colWidths=[185, 185, 185])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether(sig_table))

        doc.build(story)
        buffer.seek(0)

        dept_str_clean = (department.department_code or department.department_name or 'Dept').replace(' ', '_') if department else 'All'
        batch_str_clean = str(batch.batch if batch else 'Batch').replace(' ', '_')
        filename = f"Fees_Report_Sem_{sem_num}_{dept_str_clean}_{batch_str_clean}.pdf"

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response

    def _get_fees_academic_year_data_helper(self, request):
        import re
        from decimal import Decimal
        from institution.models import AcademicYear, Department, Batch, Section, Program, CollegeHeader, Semester, FeesStructure
        from student.models import StudentFees, StudentSemesterFee

        req_data = getattr(request, 'data', None) or {}
        req_params = getattr(request, 'query_params', None) or getattr(request, 'GET', {})

        acad_year_param = req_data.get('academic_year') or req_params.get('academic_year')
        dept_id = req_data.get('department') or req_params.get('department') or req_data.get('department_id') or req_params.get('department_id')
        batch_id = req_data.get('batch') or req_params.get('batch') or req_data.get('batch_id') or req_params.get('batch_id')
        section_id = req_data.get('section') or req_params.get('section') or req_data.get('section_id') or req_params.get('section_id')
        header_type = req_data.get('report_header') or req_params.get('report_header')

        # 1. Resolve Academic Year
        acad_year_obj = None
        if acad_year_param and str(acad_year_param).strip().lower() not in ['', 'all', 'undefined', 'null']:
            if str(acad_year_param).isdigit():
                acad_year_obj = AcademicYear.objects.filter(id=int(acad_year_param)).first()
            if not acad_year_obj:
                acad_year_obj = AcademicYear.objects.filter(academic_year__iexact=str(acad_year_param)).first()
        if not acad_year_obj:
            acad_year_obj = (AcademicYear.objects.filter(is_display=True).first() or 
                             AcademicYear.objects.filter(is_active=True).first() or 
                             AcademicYear.objects.first())

        acad_year_str = acad_year_obj.academic_year if acad_year_obj else '2025-2026'

        # Extract start & end year from Academic Year string (e.g. 2025 from "2025-2026")
        ay_years = [int(y) for y in re.findall(r'\b\d{4}\b', str(acad_year_str))]
        if len(ay_years) >= 2:
            ay_start, ay_end = ay_years[0], ay_years[1]
        elif len(ay_years) == 1:
            ay_start, ay_end = ay_years[0], ay_years[0] + 1
        else:
            ay_start, ay_end = 2025, 2026

        # 2. Batch eligibility helper for academic year
        def check_batch_eligibility(b_name, start_year):
            if not b_name or not start_year:
                return False, None, None, None
            years = [int(y) for y in re.findall(r'\b\d{4}\b', str(b_name))]
            if len(years) < 2:
                return False, None, None, None
            b_start, b_end = years[0], years[1]
            if b_start <= start_year < b_end:
                y_study = start_year - b_start + 1
                s1 = (y_study - 1) * 2 + 1
                s2 = (y_study - 1) * 2 + 2
                return True, y_study, s1, s2
            return False, None, None, None

        # Build map of all eligible batches for this AY
        all_batches_qs = Batch.objects.select_related('department').all()
        eligible_batch_map = {}  # batch_id -> (y_study, s1, s2, batch_name)
        eligible_batch_names = set()
        for b in all_batches_qs:
            is_elig, y_st, s1, s2 = check_batch_eligibility(b.batch, ay_start)
            if is_elig:
                eligible_batch_map[b.id] = (y_st, s1, s2, b.batch)
                eligible_batch_names.add(b.batch)

        # 3. Resolve Department (optional)
        department = None
        if dept_id and str(dept_id).strip().lower() not in ['', 'all', 'all_departments', 'undefined', 'null']:
            if str(dept_id).isdigit():
                department = Department.objects.filter(id=int(dept_id)).first()
            if not department:
                department = Department.objects.filter(department_code=dept_id).first()
            if not department:
                department = Department.objects.filter(department_name__iexact=dept_id).first()

        # 4. Resolve Batch (optional)
        batch = None
        batch_filter_str = None
        if batch_id and str(batch_id).strip().lower() not in ['', 'all', 'all_batches', 'undefined', 'null']:
            if str(batch_id).isdigit():
                batch = Batch.objects.filter(id=int(batch_id)).first()
            if not batch:
                b_match = Batch.objects.filter(batch=batch_id).first()
                if b_match:
                    batch = b_match
                else:
                    batch_filter_str = str(batch_id).strip()
            if batch:
                batch_filter_str = batch.batch

        # 5. Resolve Section (optional)
        section_obj = None
        if section_id and str(section_id).strip().lower() not in ['', 'all', 'all_sections', 'undefined', 'null']:
            if str(section_id).isdigit():
                section_obj = Section.objects.filter(id=int(section_id)).first()
            if not section_obj:
                section_obj = Section.objects.filter(sections__iexact=str(section_id).strip()).first()

        # 6. Resolve College Header
        college_header_obj = None
        if header_type:
            college_header_obj = CollegeHeader.objects.filter(header_type=header_type).first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        # 7. Query Students - Only students who have a quota assigned fetch fees
        students_qs = Student.objects.select_related(
            'department', 'department__program', 'batch', 'section', 'quota',
            'application', 'application__candidate'
        ).filter(quota__isnull=False)

        quota_param = req_data.get('quota') or req_params.get('quota') or req_data.get('quota_id') or req_params.get('quota_id')
        if quota_param and str(quota_param).strip().lower() not in ['', 'all', 'all_quotas', 'undefined', 'null']:
            if str(quota_param).isdigit():
                students_qs = students_qs.filter(quota_id=int(quota_param))
            else:
                students_qs = students_qs.filter(quota__quota_name__iexact=str(quota_param).strip())

        if department:
            students_qs = students_qs.filter(department=department)

        if batch:
            students_qs = students_qs.filter(batch=batch)
        elif batch_filter_str:
            students_qs = students_qs.filter(batch__batch=batch_filter_str)
        else:
            # All Batches: only students in eligible batches for this AY
            students_qs = students_qs.filter(batch_id__in=list(eligible_batch_map.keys()))

        if section_obj:
            students_qs = students_qs.filter(section=section_obj)
        elif section_id and str(section_id).strip().lower() not in ['', 'all', 'all_sections', 'undefined', 'null']:
            students_qs = students_qs.filter(section__sections__iexact=str(section_id).strip())

        students = list(students_qs.order_by('department__department_name', 'batch__batch', 'roll_number', 'register_number', 'student_name'))

        # 8. Bulk fetch fees to ensure fast response
        st_ids = [s.id for s in students]
        sf_list = StudentFees.objects.filter(student_id__in=st_ids)
        sf_map = {sf.student_id: sf for sf in sf_list}
        sf_ids = [sf.id for sf in sf_list]

        sem_fee_list = StudentSemesterFee.objects.filter(student_fees_id__in=sf_ids).select_related('semester')
        sem_fee_map = {(sm.student_fees_id, sm.semester.semester_number): sm for sm in sem_fee_list}

        fs_list = FeesStructure.objects.all()
        fs_map = {(fs.department_id, fs.batch_id, fs.quota_id): fs for fs in fs_list}

        records = []
        tot_fee_sum = 0.0
        tot_paid_sum = 0.0
        tot_conc_sum = 0.0
        tot_bal_sum = 0.0

        for i, st in enumerate(students, start=1):
            b_obj = st.batch
            b_name = b_obj.batch if b_obj else ''

            if b_obj and b_obj.id in eligible_batch_map:
                y_study, s1, s2, _ = eligible_batch_map[b_obj.id]
            else:
                is_elig, y_study, s1, s2 = check_batch_eligibility(b_name, ay_start)
                if not is_elig:
                    continue

            st_name = (st.name if hasattr(st, 'name') and st.name else (st.student_name or 'Student'))
            reg_no = st.register_number or st.roll_number or '—'
            quota_name = st.quota.quota_name if st.quota else 'Regular'

            sf = sf_map.get(st.id)

            def _calc_sem(sem_num):
                sm = sem_fee_map.get((sf.id, sem_num)) if sf else None
                if sm:
                    return float(sm.total_amount or 0), float(sm.paid_amount or 0), float(sm.concession_amount or 0), float(sm.balance_amount or 0), sm.status
                elif sf and sf.total_fees:
                    t = float(sf.total_fees or 0) / 8.0
                    return t, 0.0, 0.0, t, ('PENDING' if t > 0 else 'NOT SET')
                elif st.quota_id:
                    fs_entry = fs_map.get((st.department_id, st.batch_id, st.quota_id))
                    t = float(fs_entry.fees or 0) / 8.0 if fs_entry else 0.0
                    return t, 0.0, 0.0, t, ('PENDING' if t > 0 else 'NOT SET')
                else:
                    return 0.0, 0.0, 0.0, 0.0, 'NOT SET'

            s1_tot, s1_paid, s1_conc, s1_bal, s1_status = _calc_sem(s1)
            s2_tot, s2_paid, s2_conc, s2_bal, s2_status = _calc_sem(s2)

            cur_tot = s1_tot + s2_tot
            cur_paid = s1_paid + s2_paid
            cur_conc = s1_conc + s2_conc
            cur_bal = s1_bal + s2_bal

            if cur_bal <= 0 and cur_tot > 0:
                cur_status = 'PAID'
            elif cur_paid > 0:
                cur_status = 'PARTIAL'
            elif cur_tot > 0:
                cur_status = 'PENDING'
            else:
                cur_status = 'NOT SET'

            tot_fee_sum += cur_tot
            tot_paid_sum += cur_paid
            tot_conc_sum += cur_conc
            tot_bal_sum += cur_bal

            records.append({
                'sno': i,
                'student_id': st.id,
                'register_no': reg_no,
                'roll_no': st.roll_number or '—',
                'name': st_name,
                'department_name': st.department.department_name if st.department else '—',
                'department_code': st.department.department_code if st.department else '—',
                'batch': b_name or '—',
                'section': st.section.sections if st.section else 'A',
                'year_of_study': y_study,
                'semesters': [s1, s2],
                'semesters_label': f"Sem {s1} & {s2}",
                'quota': quota_name,
                'total_fee': cur_tot,
                'paid_fee': cur_paid,
                'concession_fee': cur_conc,
                'balance_fee': cur_bal,
                'status': cur_status,
                'sem1': {
                    'semester_number': s1,
                    'total_amount': s1_tot,
                    'paid_amount': s1_paid,
                    'concession_amount': s1_conc,
                    'balance_amount': s1_bal,
                    'status': s1_status,
                },
                'sem2': {
                    'semester_number': s2,
                    'total_amount': s2_tot,
                    'paid_amount': s2_paid,
                    'concession_amount': s2_conc,
                    'balance_amount': s2_bal,
                    'status': s2_status,
                }
            })

        # Group records by (Department, Batch, Section)
        from collections import OrderedDict
        grouped_dict = OrderedDict()

        for st_rec in records:
            dept_k = st_rec['department_name']
            batch_k = st_rec['batch']
            sec_k = st_rec.get('section', 'A')
            g_key = (dept_k, batch_k, sec_k)
            if g_key not in grouped_dict:
                grouped_dict[g_key] = {
                    'department_name': dept_k,
                    'department_code': st_rec.get('department_code', ''),
                    'batch': batch_k,
                    'year_of_study': st_rec.get('year_of_study', 1),
                    'semesters': st_rec.get('semesters', [1, 2]),
                    'semesters_label': st_rec.get('semesters_label', ''),
                    'section': sec_k,
                    'total_students': 0,
                    'total_fee': 0.0,
                    'paid_fee': 0.0,
                    'concession_fee': 0.0,
                    'balance_fee': 0.0,
                    'students': []
                }
            g_item = grouped_dict[g_key]
            g_item['total_students'] += 1
            g_item['total_fee'] += st_rec['total_fee']
            g_item['paid_fee'] += st_rec['paid_fee']
            g_item['concession_fee'] += st_rec['concession_fee']
            g_item['balance_fee'] += st_rec['balance_fee']

            rec_in_g = dict(st_rec)
            rec_in_g['group_sno'] = len(g_item['students']) + 1
            g_item['students'].append(rec_in_g)

        groups_list = list(grouped_dict.values())

        sec_name = section_obj.sections if section_obj else (section_id if section_id else 'All Sections')
        batch_display = batch_filter_str if batch_filter_str else (batch.batch if batch else 'All Batches')
        dept_display = department.department_name if department else 'All Departments'

        if batch and batch.id in eligible_batch_map:
            _, s1_m, s2_m, _ = eligible_batch_map[batch.id]
            sems_display = f"Semesters {s1_m} & {s2_m}"
        elif batch_filter_str:
            is_elig_m, _, s1_m, s2_m = check_batch_eligibility(batch_filter_str, ay_start)
            sems_display = f"Semesters {s1_m} & {s2_m}" if is_elig_m else "2 Semesters (Academic Year)"
        else:
            sems_display = "2 Semesters each (Across Batches)"

        meta = {
            'academic_year': acad_year_str,
            'academic_year_id': acad_year_obj.id if acad_year_obj else None,
            'department': dept_display,
            'batch': batch_display,
            'section': str(sec_name),
            'semesters_covered': sems_display,
            'total_groups': len(groups_list),
        }

        summary = {
            'total_students': len(records),
            'total_groups': len(groups_list),
            'total_academic_year_fees': tot_fee_sum,
            'total_paid_fees': tot_paid_sum,
            'total_concession_fees': tot_conc_sum,
            'total_balance_fees': tot_bal_sum,
        }

        student_map = {s.id: s for s in students}
        return meta, summary, records, groups_list, college_header_obj, department, batch, sec_name, acad_year_str, student_map

    def fees_academic_year_report(self, request, *args, **kwargs):
        """JSON endpoint returning filtered academic year fee records, grouped by department, batch, and section."""
        meta, summary, records, groups_list, _, department, batch, sec_name, acad_year_str, *rest = self._get_fees_academic_year_data_helper(request)
        return Response({
            'success': True,
            'metadata': meta,
            'summary': summary,
            'groups': groups_list,
            'students': records
        }, status=status.HTTP_200_OK)

    def fees_academic_year_report_pdf(self, request, *args, **kwargs):
        """Generates and streams an official PDF report of academic year fees, grouped by Department, Batch, and Section."""
        meta, summary, records, groups_list, college_header_obj, department, batch, sec_name, acad_year_str, *rest = self._get_fees_academic_year_data_helper(request)

        if not records:
            return HttpResponse("No students found matching the selected criteria.", status=400)

        buffer = BytesIO()
        page_size = A4
        doc = SimpleDocTemplate(buffer, pagesize=page_size, leftMargin=20, rightMargin=20, topMargin=20, bottomMargin=20)

        story = []
        page_w = page_size[0] - 40  # 555.27 pt

        # 1. College Header
        header_table = build_standard_college_header(college_header_obj, page_w=page_w, logo_size=62)
        if header_table:
            story.append(header_table)
            story.append(Spacer(1, 6))

        # 2. Centered Report Title
        story.append(build_centered_report_title(f"FEES REPORT — ACADEMIC YEAR {acad_year_str.upper()}", font_size=12, leading=15))
        story.append(Spacer(1, 6))

        # 3. Meta Info Table
        lbl_bold = ParagraphStyle(name='AYFRLbl', fontName='Times-Bold', fontSize=9, leading=12, textColor=colors.black)
        val_norm = ParagraphStyle(name='AYFRVal', fontName='Times-Roman', fontSize=9, leading=12, textColor=colors.black)

        meta_data = [
            [Paragraph("<b>Academic Year:</b>", lbl_bold), Paragraph(str(meta['academic_year']), val_norm),
             Paragraph("<b>Department:</b>", lbl_bold), Paragraph(str(meta['department']), val_norm)],
            [Paragraph("<b>Batch:</b>", lbl_bold), Paragraph(str(meta['batch']), val_norm),
             Paragraph("<b>Section:</b>", lbl_bold), Paragraph(str(meta['section']), val_norm)],
            [Paragraph("<b>Semesters:</b>", lbl_bold), Paragraph(str(meta['semesters_covered']), val_norm),
             Paragraph("<b>Total Students / Groups:</b>", lbl_bold), Paragraph(f"<b>{summary['total_students']} Students</b> ({len(groups_list)} Groups)", val_norm)],
        ]
        meta_table = Table(meta_data, colWidths=[90, 185, 105, 175])
        meta_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#F8FAFC')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#F8FAFC')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 5),
            ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 10))

        # 4. Student Fee Table(s) Grouped by Department, Batch, and Section
        col_widths = [35, 95, 155, 70, 65, 65, 70]  # Sum = 555 pt
        tbl_hdr_style = ParagraphStyle(name='AYFRTH', fontName='Times-Bold', fontSize=9, leading=11, alignment=1, textColor=colors.black)
        tbl_hdr_right = ParagraphStyle(name='AYFRTHR', fontName='Times-Bold', fontSize=9, leading=11, alignment=2, textColor=colors.black)
        tbl_cell_center = ParagraphStyle(name='AYFRCC', fontName='Times-Roman', fontSize=8.5, leading=11, alignment=1, textColor=colors.black)
        tbl_cell_left = ParagraphStyle(name='AYFRCL', fontName='Times-Roman', fontSize=8.5, leading=11, alignment=0, textColor=colors.black)
        tbl_cell_right = ParagraphStyle(name='AYFRCR', fontName='Times-Roman', fontSize=8.5, leading=11, alignment=2, textColor=colors.black)
        tbl_tot_bold = ParagraphStyle(name='AYFRTB', fontName='Times-Bold', fontSize=9, leading=11, alignment=2, textColor=colors.black)
        grp_hdr_style = ParagraphStyle(name='AYFRGH', fontName='Times-Bold', fontSize=9, leading=12, textColor=colors.white)
        grp_hdr_right = ParagraphStyle(name='AYFRGHR', fontName='Times-Bold', fontSize=9, leading=12, alignment=2, textColor=colors.HexColor('#38BDF8'))

        header_row = [
            Paragraph("<b>S.No</b>", tbl_hdr_style),
            Paragraph("<b>Register No</b>", tbl_hdr_style),
            Paragraph("<b>Student Name</b>", tbl_hdr_style),
            Paragraph("<b>Quota</b>", tbl_hdr_style),
            Paragraph("<b>Total Fee</b>", tbl_hdr_right),
            Paragraph("<b>Paid Fee</b>", tbl_hdr_right),
            Paragraph("<b>Balance</b>", tbl_hdr_right),
        ]

        for g_idx, grp in enumerate(groups_list, start=1):
            # Group Header Banner
            grp_banner_text = f"<b>GROUP {g_idx}: {grp['department_name'].upper()} &nbsp;|&nbsp; BATCH: {grp['batch']} ({grp['semesters_label']}) &nbsp;|&nbsp; SECTION: {grp['section']}</b>"
            grp_banner_table = Table([
                [Paragraph(grp_banner_text, grp_hdr_style),
                 Paragraph(f"<b>{grp['total_students']} Students</b>", grp_hdr_right)]
            ], colWidths=[450, 105])
            grp_banner_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1E293B')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3.5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3.5),
                ('LEFTPADDING', (0, 0), (-1, -1), 5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 5),
            ]))

            # Group Student Rows
            grp_rows = [header_row]
            for st_in_g in grp['students']:
                row = [
                    Paragraph(str(st_in_g.get('group_sno', 1)), tbl_cell_center),
                    Paragraph(str(st_in_g['register_no']), tbl_cell_center),
                    Paragraph(str(st_in_g['name']).upper(), tbl_cell_left),
                    Paragraph(str(st_in_g['quota']), tbl_cell_center),
                    Paragraph(f"{st_in_g['total_fee']:,.2f}", tbl_cell_right),
                    Paragraph(f"{st_in_g['paid_fee']:,.2f}", tbl_cell_right),
                    Paragraph(f"{st_in_g['balance_fee']:,.2f}", tbl_cell_right),
                ]
                grp_rows.append(row)

            # Subtotal Row
            subtot_row = [
                Paragraph("<b>SUBTOTAL</b>", ParagraphStyle(name=f'AYFRSubL_{g_idx}', fontName='Times-Bold', fontSize=8.5, leading=11, alignment=1)),
                Paragraph("", tbl_cell_center),
                Paragraph(f"<b>{grp['total_students']} Students</b>", ParagraphStyle(name=f'AYFRSubSt_{g_idx}', fontName='Times-Bold', fontSize=8.5, leading=11, alignment=0)),
                Paragraph("", tbl_cell_center),
                Paragraph(f"<b>{grp['total_fee']:,.2f}</b>", tbl_tot_bold),
                Paragraph(f"<b>{grp['paid_fee']:,.2f}</b>", tbl_tot_bold),
                Paragraph(f"<b>{grp['balance_fee']:,.2f}</b>", tbl_tot_bold),
            ]
            grp_rows.append(subtot_row)

            fee_table = Table(grp_rows, colWidths=col_widths, repeatRows=1)
            ts = [
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#64748B')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LEFTPADDING', (0, 0), (-1, -1), 3.5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3.5),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#E2E8F0')),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EEF2F6')),
            ]
            for r_idx in range(1, len(grp_rows) - 1):
                if r_idx % 2 == 0:
                    ts.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#F8FAFC')))
            fee_table.setStyle(TableStyle(ts))

            # Add to story with banner
            story.append(grp_banner_table)
            story.append(fee_table)
            story.append(Spacer(1, 10))

        # Grand Total Table if multiple groups
        if len(groups_list) > 1:
            grand_tot_table = Table([
                [
                    Paragraph("<b>GRAND TOTAL (ALL GROUPS)</b>", ParagraphStyle(name='AYFRGTotL', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1)),
                    Paragraph("", tbl_cell_center),
                    Paragraph(f"<b>{summary['total_students']} Students ({len(groups_list)} Groups)</b>", ParagraphStyle(name='AYFRGTotSt', fontName='Times-Bold', fontSize=9, leading=12, alignment=0)),
                    Paragraph("", tbl_cell_center),
                    Paragraph(f"<b>{summary['total_academic_year_fees']:,.2f}</b>", ParagraphStyle(name='AYFRGTot1', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2)),
                    Paragraph(f"<b>{summary['total_paid_fees']:,.2f}</b>", ParagraphStyle(name='AYFRGTot2', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2)),
                    Paragraph(f"<b>{summary['total_balance_fees']:,.2f}</b>", ParagraphStyle(name='AYFRGTot3', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2)),
                ]
            ], colWidths=col_widths)
            grand_tot_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#1E293B')),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E2E8F0')),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LEFTPADDING', (0, 0), (-1, -1), 3.5),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3.5),
            ]))
            story.append(grand_tot_table)
            story.append(Spacer(1, 12))

        # 5. Signatures
        story.append(Spacer(1, 20))
        sig_data = [[
            Paragraph("<b>Class In-Charge</b>", val_norm),
            Paragraph("<b>HOD</b>", ParagraphStyle(name='AYFRSigHOD', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=1)),
            Paragraph("<b>Principal / Cashier</b>", ParagraphStyle(name='AYFRSigPrin', fontName='Times-Bold', fontSize=9.5, leading=12, alignment=2))
        ]]
        sig_table = Table(sig_data, colWidths=[185, 185, 185])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether(sig_table))

        doc.build(story)
        buffer.seek(0)

        dept_str_clean = (department.department_code or department.department_name or 'Dept').replace(' ', '_') if department else 'All_Depts'
        batch_str_clean = str(meta['batch']).replace(' ', '_')
        ay_str_clean = str(acad_year_str).replace(' ', '_')
        filename = f"Fees_Report_AY_{ay_str_clean}_{dept_str_clean}_{batch_str_clean}.pdf"

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
