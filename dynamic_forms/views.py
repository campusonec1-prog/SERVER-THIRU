from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from .models import FormModule, FormField, Application, ApplicationStatus, ApplicationUser
from .serializers import (
    FormModuleSerializer, FormFieldSerializer, ApplicationSerializer, 
    ApplicationStatusSerializer, ApplicationUserSerializer
)
from users.permissions import IsAdminUser
from .permissions import (
    FormModulePermission, FormFieldPermission, ApplicationPermission,
    ApplicationStatusPermission, ApplicationUserPermission
)


from django.db import transaction


class AdminWriteMixin:
    """Provides standard exception handling and user auditing for creation and updates."""

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": f"{self.model_label} not found"
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


class FormModuleViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FormModule.objects.all().order_by('display_order', 'id')
    serializer_class = FormModuleSerializer
    permission_classes = [FormModulePermission]
    model_label = "Form Module"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Modules listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        is_bulk = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=is_bulk)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)

        msg = "Form Modules created successfully" if is_bulk else "Form Module created successfully"
        return Response({
            "code": 201,
            "message": msg,
            "data": serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Module deleted successfully"}, status=status.HTTP_200_OK)


class FormFieldViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FormField.objects.all().order_by('display_order', 'id')
    serializer_class = FormFieldSerializer
    permission_classes = [FormFieldPermission]
    model_label = "Form Field"

    def list(self, request, *args, **kwargs):
        # Allow filtering by form_module_id
        module_id = request.query_params.get('form_module_id')
        if module_id:
            self.queryset = self.queryset.filter(form_module_id=module_id)
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Fields listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        is_bulk = isinstance(request.data, list)
        serializer = self.get_serializer(data=request.data, many=is_bulk)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)

        msg = "Form Fields created successfully" if is_bulk else "Form Field created successfully"
        return Response({
            "code": 201,
            "message": msg,
            "data": serializer.data
        }, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Form Field deleted successfully"}, status=status.HTTP_200_OK)


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all().order_by('-id')
    serializer_class = ApplicationSerializer
    permission_classes = [ApplicationPermission]
    model_label = "Application"

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Application.objects.none()
        
        if user.__class__.__name__ == 'ApplicationUser':
            return Application.objects.filter(candidate=user).order_by('-id')
        
        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if is_admin:
            return Application.objects.all().order_by('-id')
        return Application.objects.none()

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "Application not found"
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

        return super().handle_exception(exc)

    def perform_create(self, serializer):
        program = serializer.validated_data.get('program')
        import datetime
        year = datetime.datetime.now().year
        year_str = str(year)[2:] # E.g. "26"
        prefix = f"{program.program_level}{year_str}"
        
        count = Application.objects.filter(application_no__startswith=prefix).count() + 1
        app_no = f"{prefix}{count:04d}"
        
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        
        # Candidate is automatically assigned via validate method in serializer
        serializer.save(application_no=app_no, created_by=tracking_user, updated_by=tracking_user)

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            if user.__class__.__name__ != 'ApplicationUser' or instance.candidate != user:
                raise PermissionDenied("You do not have permission to edit this application.")
            
            if instance.status.status_name.lower() != 'draft':
                raise PermissionDenied("You cannot modify a submitted or completed application.")
            
            new_status = serializer.validated_data.get('status')
            if new_status and new_status.status_name.lower() in ['approved', 'rejected', 'waiting list']:
                raise PermissionDenied("You do not have permission to approve, reject, or waitlist applications.")

        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            if user.__class__.__name__ != 'ApplicationUser' or instance.candidate != user:
                raise PermissionDenied("You do not have permission to delete this application.")
            if instance.status.status_name.lower() != 'draft':
                raise PermissionDenied("You cannot delete a submitted application.")

        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application deleted successfully"}, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Applications listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Application created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application updated successfully", "data": response.data}, status=status.HTTP_200_OK)


class ApplicationStatusViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = ApplicationStatus.objects.all().order_by('id')
    serializer_class = ApplicationStatusSerializer
    permission_classes = [ApplicationStatusPermission]
    model_label = "Application Status"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Statuses listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Status retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Application Status created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Status updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Status deleted successfully"}, status=status.HTTP_200_OK)


class ApplicationUserViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = ApplicationUser.objects.all().order_by('id')
    serializer_class = ApplicationUserSerializer
    permission_classes = [ApplicationUserPermission]
    model_label = "Application User"

    def perform_update(self, serializer):
        user = self.request.user
        instance = self.get_object()

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            user_email = getattr(user, 'mail', getattr(user, 'email', None))
            if instance.email != user_email:
                raise PermissionDenied("You do not have permission to update this profile.")

        from users.models import User as StandardUser
        tracking_user = user if isinstance(user, StandardUser) else None
        serializer.save(updated_by=tracking_user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application Users listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application User retrieved successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({"code": 201, "message": "Application User created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application User updated successfully", "data": response.data}, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({"code": 200, "message": "Application User deleted successfully"}, status=status.HTTP_200_OK)


class ApplicationUserLoginView(APIView):
    permission_classes = []

    def post(self, request, *args, **kwargs):
        email = request.data.get('email')
        password = request.data.get('password')

        if not email or not password:
            return Response({
                "code": 400,
                "message": "Email and password are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        email = str(email).strip()
        password = str(password).strip()

        try:
            cand = ApplicationUser.objects.get(email=email)
        except ApplicationUser.DoesNotExist:
            return Response({
                "code": 400,
                "message": "Invalid email or password."
            }, status=status.HTTP_400_BAD_REQUEST)

        import bcrypt
        if not bcrypt.checkpw(password.encode('utf-8'), cand.password.encode('utf-8')):
            return Response({
                "code": 400,
                "message": "Invalid email or password."
            }, status=status.HTTP_400_BAD_REQUEST)

        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken()
        refresh['user_id'] = cand.id
        refresh['email'] = cand.email
        refresh['user_type'] = 'candidate'
        
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return Response({
            "code": 200,
            "message": "Logged in successfully",
            "data": {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": ApplicationUserSerializer(cand).data
            }
        }, status=status.HTTP_200_OK)


class DocumentUploadView(APIView):
    from rest_framework.permissions import IsAuthenticated
    from rest_framework.parsers import MultiPartParser, FormParser
    
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        # Retrieve all files from request.FILES list
        files = request.FILES.getlist('files')
        if not files:
            files = request.FILES.getlist('file')
        if not files:
            files = [file_obj for key in request.FILES for file_obj in request.FILES.getlist(key)]

        if not files:
            return Response({
                "code": 400,
                "message": "No files were uploaded."
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            from common.r2 import upload_file_to_r2
            doc_type = request.data.get('docType', 'documents')
            uploaded_data = []

            for file_obj in files:
                file_url = upload_file_to_r2(file_obj, folder_name=doc_type)
                uploaded_data.append({
                    "file_name": file_obj.name,
                    "file_url": file_url
                })

            return Response({
                "code": 200,
                "message": "Files uploaded successfully.",
                "data": uploaded_data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"File upload failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ApplicationPDFDownloadView(APIView):
    from rest_framework.permissions import IsAuthenticated
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        import os
        from io import BytesIO
        from django.http import HttpResponse
        from django.shortcuts import get_object_or_404
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image as RLImage
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from PIL import Image as PILImage
        import urllib.request

        from .models import Application, ApplicationStatus, ApplicationUser
        from institution.models import CollegeHeader, Program

        application = get_object_or_404(Application, pk=pk)
        
        # Security check: candidates can only download their own application
        if request.user.role.role_name == 'CANDIDATE' and application.candidate.email != request.user.email:
            return HttpResponse("Unauthorized", status=403)

        # Create BytesIO buffer
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=30,
            rightMargin=30,
            topMargin=25,
            bottomMargin=25
        )

        form_data = application.form_data or {}

        # -------------------------------------------------------------
        # Helper to get field value safely
        # -------------------------------------------------------------
        def get_val(key):
            if not form_data:
                return ''
            if key in form_data:
                return form_data[key]
            for m_key, m_data in form_data.items():
                if isinstance(m_data, dict) and key in m_data:
                    return m_data[key]
            return ''

        # -------------------------------------------------------------
        # Load College Header Data
        # -------------------------------------------------------------
        college_header_obj = CollegeHeader.objects.filter(header_type='Main').first()
        if not college_header_obj:
            college_header_obj = CollegeHeader.objects.first()

        college_name = college_header_obj.college_name if college_header_obj else 'THIRUMALAI ENGINEERING COLLEGE'
        college_address = college_header_obj.address if college_header_obj else 'Kilambi, Krishnapuram Post - 631 551, Kancheepuram Taluk & District, Tamil Nadu.'
        logo_url = college_header_obj.primary_logo if college_header_obj else None

        # -------------------------------------------------------------
        # Helper to load image securely & convert WebP/PNG for ReportLab
        # -------------------------------------------------------------
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
                        # Convert WebP/etc to PNG in memory
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
            except Exception as e:
                print(f"[PDF Gen] Failed to load image {url_or_path}: {e}")
            return None

        # Resolve primary college logo
        logo_flowable = None
        if logo_url:
            logo_flowable = load_image(logo_url, 52, 52)
        if not logo_flowable:
            # Fallback to local logo path in frontend assets
            fallback_logo_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\logo.webp'
            logo_flowable = load_image(fallback_logo_path, 52, 52)

        # Resolve secondary emblem (BMQR)
        emblem_flowable = None
        fallback_emblem_path = 'd:\\IMS-Thirumalai\\APP-THIRU\\src\\assets\\emblem.png'
        emblem_flowable = load_image(fallback_emblem_path, 52, 17)

        # Resolve candidate photo
        photo_url = get_val('photo')
        if not photo_url:
            # Check inside certificates list
            certs = get_val('certificates') or []
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

        photo_flowable = None
        if photo_url:
            photo_flowable = load_image(photo_url, 66, 80)

        # -------------------------------------------------------------
        # PDF Styles
        # -------------------------------------------------------------
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            name='CollegeTitle',
            fontName='Helvetica-Bold',
            fontSize=13,
            textColor=colors.HexColor('#0B2C5D'),
            alignment=1, # Centered
            spaceAfter=2
        )
        
        sub_style = ParagraphStyle(
            name='CollegeSub',
            fontName='Helvetica-Oblique',
            fontSize=7,
            textColor=colors.HexColor('#333333'),
            alignment=1,
            spaceAfter=3
        )
        
        addr_style = ParagraphStyle(
            name='CollegeAddr',
            fontName='Helvetica-Bold',
            fontSize=8,
            textColor=colors.HexColor('#000000'),
            alignment=1,
            spaceAfter=2
        )

        app_title_style = ParagraphStyle(
            name='AppTitle',
            fontName='Helvetica-Bold',
            fontSize=8.5,
            textColor=colors.white,
            alignment=1,
        )

        # -------------------------------------------------------------
        # PAGE 1 STORY
        # -------------------------------------------------------------
        story = []

        # 1. Gold top line
        line_t = Table([['']], colWidths=[535], rowHeights=[2])
        line_t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#D4A017')),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(line_t)
        story.append(Spacer(1, 4))

        # 2. Header Grid (Logo, Titles, Photo Box)
        # Left cell container for logo and emblem
        logo_cells = []
        if logo_flowable:
            logo_cells.append([logo_flowable])
        if emblem_flowable:
            logo_cells.append([emblem_flowable])
        
        left_t = Table(logo_cells if logo_cells else [['']], colWidths=[55])
        left_t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))

        # Middle Titles Container
        app_heading = Table(
            [[Paragraph('Application Form for Admission to B.E. / B.Tech. / M.E. / MBA / MCA Degree Course', app_title_style)]],
            colWidths=[385],
            rowHeights=[16]
        )
        app_heading.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#0B2C5D')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
        ]))

        mid_cells = [
            [Paragraph(college_name.upper(), title_style)],
            [Paragraph('(Approved by AICTE & Govt. of Tamilnadu, Affiliated to Anna University)', sub_style)],
            [Paragraph(college_address, addr_style)],
            [Spacer(1, 2)],
            [app_heading]
        ]
        mid_t = Table(mid_cells, colWidths=[395])
        mid_t.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))

        # Right Photo Box
        photo_box_t = None
        if photo_flowable:
            photo_box_t = Table([[photo_flowable]], colWidths=[70], rowHeights=[85])
            photo_box_t.setStyle(TableStyle([
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 0),
                ('TOPPADDING', (0,0), (-1,-1), 0),
                ('LEFTPADDING', (0,0), (-1,-1), 0),
                ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ]))
        else:
            photo_label_style = ParagraphStyle(
                name='PhotoLabel',
                fontName='Helvetica-Bold',
                fontSize=6.5,
                textColor=colors.HexColor('#666666'),
                alignment=1,
            )
            photo_box_t = Table(
                [
                    [''],
                    [Paragraph('Affix', photo_label_style)],
                    [Paragraph('Passport Size', photo_label_style)],
                    [Paragraph('Photo', photo_label_style)],
                    ['']
                ],
                colWidths=[70],
                rowHeights=[8, 16, 16, 16, 29]
            )
            photo_box_t.setStyle(TableStyle([
                ('BOX', (0,0), (-1,-1), 0.75, colors.HexColor('#475569')),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
            ]))

        # Assemble Header
        header_table = Table([[left_t, mid_t, photo_box_t]], colWidths=[60, 400, 75])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))

        # -------------------------------------------------------------
        # Helper to generate Section Headers and Tables
        # -------------------------------------------------------------
        def make_header(title):
            h_style = ParagraphStyle(
                name='HStyle_' + title.replace(' ', '_'),
                fontName='Helvetica-Bold',
                fontSize=9,
                textColor=colors.HexColor('#0B2C5D')
            )
            t = Table([[Paragraph(title.upper(), h_style)]], colWidths=[535], rowHeights=[18])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F1F5F9')),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
                ('LINELEFT', (0,0), (0,-1), 3.5, colors.HexColor('#D4A017')),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ]))
            return t

        def make_kv_table(pairs):
            k_style = ParagraphStyle(
                name='KStyle',
                fontName='Helvetica-Bold',
                fontSize=7.5,
                textColor=colors.HexColor('#475569')
            )
            v_style = ParagraphStyle(
                name='VStyle',
                fontName='Helvetica',
                fontSize=8,
                textColor=colors.HexColor('#0F172A')
            )
            
            data = []
            for i in range(0, len(pairs), 2):
                row = []
                k1, v1 = pairs[i]
                row.append(Paragraph(k1, k_style))
                row.append(Paragraph(str(v1) if v1 is not None and v1 != '' else '-', v_style))
                if i + 1 < len(pairs):
                    k2, v2 = pairs[i+1]
                    row.append(Paragraph(k2, k_style))
                    row.append(Paragraph(str(v2) if v2 is not None and v2 != '' else '-', v_style))
                else:
                    row.append('')
                    row.append('')
                data.append(row)
                
            t = Table(data, colWidths=[110, 157, 110, 158])
            t.setStyle(TableStyle([
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
                ('BACKGROUND', (0,0), (0,-1), colors.HexColor('#F8FAFC')),
                ('BACKGROUND', (2,0), (2,-1), colors.HexColor('#F8FAFC')),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING', (0,0), (-1,-1), 4.5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
                ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ]))
            return t

        # SECTION A: PROGRAM & BRANCH
        story.append(make_header('A. Program & Branch Details'))
        story.append(Spacer(1, 4))
        
        dept_val = get_val('department')
        if isinstance(dept_val, list):
            dept_str = ", ".join(dept_val)
        else:
            dept_str = str(dept_val)
            
        prog_name = application.program.program_name if application.program else get_val('program')
        
        program_pairs = [
            ('Course Applied', prog_name),
            ('Application Ref No', application.application_no),
            ('Selected Department(s)', dept_str),
            ('Admission Batch Year', '2026 - 2027')
        ]
        story.append(make_kv_table(program_pairs))
        story.append(Spacer(1, 10))

        # SECTION B: PERSONAL INFORMATION
        story.append(make_header('B. Personal Information'))
        story.append(Spacer(1, 4))
        
        personal_pairs = [
            ('Applicant Name', get_val('applicant_name')),
            ('Date of Birth', get_val('date_of_birth')),
            ('Gender', get_val('gender')),
            ('Community / Cast', get_val('community')),
            ('Religion', get_val('religion')),
            ('Nationality', get_val('nationality')),
            ('Mother Tongue', get_val('mother_tongue')),
            ('Aadhaar Number', get_val('aadhaar_number')),
            ('Email Address', get_val('email')),
            ('Mobile Number', get_val('student_mobile'))
        ]
        story.append(make_kv_table(personal_pairs))
        story.append(Spacer(1, 10))

        # SECTION C: PARENT & CONTACT DETAILS
        story.append(make_header('C. Parent / Guardian & Contact Details'))
        story.append(Spacer(1, 4))
        
        parent_pairs = [
            ('Father / Guardian Name', get_val('parent_name')),
            ('Occupation', get_val('occupation')),
            ('Annual Income (Rs.)', get_val('annual_income')),
            ('Contact Mobile No', get_val('parent_mobile')),
            ('Residential Address', get_val('address')),
            ('Area Pincode', get_val('pincode'))
        ]
        story.append(make_kv_table(parent_pairs))
        
        # End of Page 1 -> Add Page Break to guarantee exactly 2 pages!
        story.append(PageBreak())

        # -------------------------------------------------------------
        # PAGE 2 STORY
        # -------------------------------------------------------------
        
        # SECTION D: ACADEMIC QUALIFICATIONS
        story.append(make_header('D. Academic Qualifications'))
        story.append(Spacer(1, 4))
        
        # Qual Table Headers
        qual_header_style = ParagraphStyle(
            name='QualHeaderStyle',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            textColor=colors.HexColor('#475569')
        )
        qual_cell_style = ParagraphStyle(
            name='QualCellStyle',
            fontName='Helvetica',
            fontSize=7.5,
            textColor=colors.HexColor('#0F172A')
        )
        
        qual_data = [[
            Paragraph('Qualification', qual_header_style),
            Paragraph('Institution Name', qual_header_style),
            Paragraph('Board of Study', qual_header_style),
            Paragraph('Register No.', qual_header_style),
            Paragraph('Passing Year', qual_header_style),
            Paragraph('Percentage (%)', qual_header_style)
        ]]
        
        qual_list = get_val('qualifications') or get_val('academic_qualification') or []
        if isinstance(qual_list, dict) and 'qualifications' in qual_list:
            qual_list = qual_list['qualifications']
        elif isinstance(qual_list, dict) and 'academic_qualification' in qual_list:
            qual_list = qual_list['academic_qualification']
            
        if not isinstance(qual_list, list):
            qual_list = []
            
        # Ensure we always show at least SSLC and HSC rows
        display_quals = qual_list
        if len(display_quals) == 0:
            display_quals = [
                {'qualification': 'SSLC', 'institution': '', 'board': '', 'register_number': '', 'year_of_passing': '', 'percentage': ''},
                {'qualification': 'HSC', 'institution': '', 'board': '', 'register_number': '', 'year_of_passing': '', 'percentage': ''}
            ]
            
        for q in display_quals:
            qual_data.append([
                Paragraph(str(q.get('qualification', '')), qual_cell_style),
                Paragraph(str(q.get('institution', '')), qual_cell_style),
                Paragraph(str(q.get('board', '')), qual_cell_style),
                Paragraph(str(q.get('register_number', '')), qual_cell_style),
                Paragraph(str(q.get('year_of_passing', '')), qual_cell_style),
                Paragraph(str(q.get('percentage', '')), qual_cell_style),
            ])
            
        qual_table = Table(qual_data, colWidths=[90, 160, 95, 70, 60, 60])
        qual_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(qual_table)
        story.append(Spacer(1, 10))

        # SECTION E: ACADEMIC PERFORMANCE (MARKS DETAILS)
        story.append(make_header('E. Subject-wise Academic Performance'))
        story.append(Spacer(1, 4))
        
        marks_data = [[
            Paragraph('Qualification / Semester', qual_header_style),
            Paragraph('Subject / Course Title', qual_header_style),
            Paragraph('Max. Marks', qual_header_style),
            Paragraph('Obtained Marks', qual_header_style),
            Paragraph('Percentage (%)', qual_header_style)
        ]]
        
        marks_list = get_val('academic_performance') or []
        if isinstance(marks_list, dict) and 'academic_performance' in marks_list:
            marks_list = marks_list['academic_performance']
            
        if not isinstance(marks_list, list):
            marks_list = []
            
        if len(marks_list) == 0:
            # Fallback placeholder row
            marks_list = [{'qualification': 'HSC', 'subject': 'Mathematics', 'maximum_marks': 100, 'obtained_marks': '', 'percentage': ''}]
            
        for m in marks_list:
            marks_data.append([
                Paragraph(str(m.get('qualification', '')), qual_cell_style),
                Paragraph(str(m.get('subject', '')), qual_cell_style),
                Paragraph(str(m.get('maximum_marks', '')), qual_cell_style),
                Paragraph(str(m.get('obtained_marks', '')), qual_cell_style),
                Paragraph(str(m.get('percentage', '')), qual_cell_style),
            ])
            
        marks_table = Table(marks_data, colWidths=[120, 175, 80, 80, 80])
        marks_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(marks_table)
        story.append(Spacer(1, 10))

        # SECTION F: UPLOADED CERTIFICATES CHECKLIST
        story.append(make_header('F. Certificates & Uploaded Documents Checklist'))
        story.append(Spacer(1, 4))
        
        cert_data = [[
            Paragraph('S.No.', qual_header_style),
            Paragraph('Certificate / Document Type', qual_header_style),
            Paragraph('Upload Status', qual_header_style),
            Paragraph('Document Reference Link', qual_header_style)
        ]]
        
        cert_list = get_val('certificates') or []
        if isinstance(cert_list, dict) and 'certificates' in cert_list:
            cert_list = cert_list['certificates']
            
        if not isinstance(cert_list, list):
            cert_list = []
            
        if len(cert_list) == 0:
            cert_list = [{'certificate_type': 'Aadhaar Card', 'document': ''}]
            
        for idx, c in enumerate(cert_list):
            doc_val = c.get('document', '')
            doc_link = '-'
            status_text = 'Not Uploaded'
            status_style = ParagraphStyle(
                name='StatusStyleErr_' + str(idx),
                fontName='Helvetica-Bold',
                fontSize=7.5,
                textColor=colors.HexColor('#E11D48')
            )
            
            if doc_val:
                status_text = 'Uploaded'
                status_style = ParagraphStyle(
                    name='StatusStyleOk_' + str(idx),
                    fontName='Helvetica-Bold',
                    fontSize=7.5,
                    textColor=colors.HexColor('#059669')
                )
                if isinstance(doc_val, str) and doc_val.startswith('http'):
                    doc_link = doc_val.split('/')[-1]
                elif isinstance(doc_val, dict) and isinstance(doc_val.get('name'), str):
                    doc_link = doc_val.get('name')
                    
            cert_data.append([
                Paragraph(str(idx + 1), qual_cell_style),
                Paragraph(str(c.get('certificate_type', '')), qual_cell_style),
                Paragraph(status_text, status_style),
                Paragraph(doc_link, qual_cell_style)
            ])
            
        cert_table = Table(cert_data, colWidths=[40, 205, 90, 200])
        cert_table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#F8FAFC')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 4.5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4.5),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(cert_table)
        story.append(Spacer(1, 10))

        # SECTION G: DECLARATION & SIGNATURES
        story.append(make_header('G. Declaration & Signatures'))
        story.append(Spacer(1, 4))
        
        dec_text = (
            "I hereby declare that all the particulars furnished in this application form are true and "
            "correct to the best of my knowledge and belief. I agree to abide by the rules and regulations "
            "of the institution currently in force and as amended from time to time."
        )
        dec_style = ParagraphStyle(
            name='DeclarationTextStyle',
            fontName='Helvetica',
            fontSize=7.5,
            textColor=colors.HexColor('#334155'),
            leading=11
        )
        story.append(Paragraph(dec_text, dec_style))
        story.append(Spacer(1, 25))

        # Signatures Row
        sig_label_style = ParagraphStyle(
            name='SigLabelStyle',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            textColor=colors.HexColor('#475569')
        )
        
        place_str = get_val('place') or '-'
        date_str = get_val('application_date') or '-'
        
        sig_data = [
            [
                Paragraph(f"<b>Place:</b> {place_str}", sig_label_style),
                Paragraph("<b>Signature of Parent / Guardian</b>", sig_label_style)
            ],
            [
                Paragraph(f"<b>Date:</b> {date_str}", sig_label_style),
                Paragraph("<b>Signature of Candidate</b>", sig_label_style)
            ]
        ]
        
        sig_table = Table(sig_data, colWidths=[265, 270], rowHeights=[20, 20])
        sig_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
            ('ALIGN', (1,0), (1,-1), 'RIGHT'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(sig_table)

        # Build PDF Document
        doc.build(story)

        # Get response from buffer
        pdf = buffer.getvalue()
        buffer.close()

        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Application_{application.application_no}.pdf"'
        response.write(pdf)
        return response






