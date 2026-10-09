from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied, ValidationError
from .models import User, UserDetails
from .serializers import UserSerializer, UserDetailsSerializer
from .permissions import IsAdminUser, UserPermission, UserDetailsPermission


def resolve_user_presence_data(user, role_name=None, request=None):
    from django.utils import timezone
    from django.db.models import Q

    role_str = role_name or (getattr(user.role, 'role_name', 'User') if hasattr(user, 'role') and user.role else 'User')
    user_detail = getattr(user, 'user_details', None)
    first_detail = user_detail.first() if hasattr(user_detail, 'first') else None

    dept_name = None
    if first_detail and getattr(first_detail, 'department', None):
        dept_name = getattr(first_detail.department, 'department_name', None) or getattr(first_detail.department, 'short_name', None)
    faculty_code = getattr(first_detail, 'faculty_code', '') if first_detail else ''
    user_image = getattr(first_detail, 'user_image', '') if first_detail else ''

    # If user is a Student or photo is not found in user_details, search Student & Application records
    if not user_image or 'STUDENT' in str(role_str).upper():
        try:
            from student.models import Student
            student = Student.objects.select_related('department', 'application', 'application__candidate').filter(
                Q(roll_number=user.username) |
                Q(register_number=user.username) |
                Q(roll_number__iexact=user.username) |
                Q(register_number__iexact=user.username) |
                (Q(application__candidate__phone_number=user.mobile_number) & ~Q(application__candidate__phone_number='')) |
                (Q(application__candidate__email__iexact=user.mail) & ~Q(application__candidate__email='')) |
                (Q(application__candidate__name__iexact=user.name) & ~Q(application__candidate__name=''))
            ).first()

            if student:
                if not dept_name and student.department:
                    dept_name = getattr(student.department, 'department_name', None) or getattr(student.department, 'short_name', None)

                app = student.application
                if app and isinstance(app.form_data, dict):
                    fd = app.form_data
                    if not user_image:
                        for key in ['photo', 'student_photo', 'candidate_photo', 'profile_photo', 'image', 'avatar']:
                            val = fd.get(key)
                            if isinstance(val, str) and val.strip():
                                user_image = val.strip()
                                break
                            elif isinstance(val, dict) and val.get('url'):
                                user_image = val.get('url')
                                break

                    if not user_image:
                        certs = fd.get('certificates') or []
                        if isinstance(certs, dict) and 'certificates' in certs:
                            certs = certs['certificates']
                        if isinstance(certs, list):
                            for c in certs:
                                if isinstance(c, dict):
                                    ctype = str(c.get('certificate_type', '')).upper()
                                    if any(x in ctype for x in ['PHOTO', 'PASSPORT', 'CANDIDATE', 'STUDENT', 'PROFILE']):
                                        doc_val = c.get('document')
                                        if isinstance(doc_val, str) and (doc_val.startswith('http') or doc_val.startswith('data:') or doc_val.startswith('/media')):
                                            user_image = doc_val
                                            break
                                        elif isinstance(doc_val, dict) and isinstance(doc_val.get('url'), str):
                                            user_image = doc_val.get('url')
                                            break

                    if not user_image:
                        for k, v in fd.items():
                            if isinstance(v, dict):
                                for pkey in ['photo', 'student_photo', 'candidate_photo', 'image', 'document']:
                                    pval = v.get(pkey)
                                    if isinstance(pval, str) and (pval.startswith('http') or pval.startswith('data:') or pval.startswith('/media')):
                                        user_image = pval
                                        break
                                if user_image:
                                    break

                if not user_image and getattr(student, 'student_photo', None):
                    user_image = student.student_photo
        except Exception:
            pass

    ip_addr = ''
    if request:
        ip_addr = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ip_addr and ',' in ip_addr:
            ip_addr = ip_addr.split(',')[0].strip()

    return {
        'id': user.id,
        'name': getattr(user, 'name', '') or getattr(user, 'username', 'User'),
        'username': getattr(user, 'username', ''),
        'email': getattr(user, 'mail', '') or getattr(user, 'email', ''),
        'mobile': getattr(user, 'mobile_number', '') or getattr(user, 'phone_number', ''),
        'role_name': role_str,
        'department_name': dept_name,
        'faculty_code': faculty_code,
        'user_image': user_image or '',
        'student_photo': user_image or '',
        'photo': user_image or '',
        'avatar': user_image or '',
        'last_seen': timezone.now().isoformat(),
        'ip_address': ip_addr,
        'status': 'online'
    }


def broadcast_user_online(online_info):
    try:
        from django.core.cache import cache
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync

        user_id = online_info['id']
        cache.set(f'online_user_{user_id}', online_info, timeout=90)
        user_ids = cache.get('online_user_ids', set())
        if not isinstance(user_ids, set):
            user_ids = set(user_ids) if isinstance(user_ids, (list, tuple)) else set()
        user_ids.add(user_id)
        cache.set('online_user_ids', user_ids, timeout=None)

        layer = get_channel_layer()
        if layer:
            async_to_sync(layer.group_send)(
                'realtime_updates',
                {
                    'type': 'broadcast_update',
                    'data': {
                        'model': 'OnlineUser',
                        'action': 'online',
                        'user': online_info
                    }
                }
            )
    except Exception:
        pass


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.select_related('role', 'created_by', 'created_by__role', 'updated_by', 'updated_by__role').prefetch_related('user_details', 'user_details__department').all().order_by('id')
    serializer_class = UserSerializer
    permission_classes = [UserPermission]

    def get_queryset(self):
        qs = super().get_queryset()
        role_param = self.request.query_params.get('role', None) or self.request.query_params.get('role_name', None)
        if role_param:
            qs = qs.filter(role__role_name__icontains=role_param.strip())
        return qs

    def perform_create(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)

    @action(detail=False, methods=['get'], url_path='dashboard-analytics')
    def dashboard_analytics(self, request, *args, **kwargs):
        from student.models import Student
        from institution.models import Department
        from django.db.models import Count, Q
        from collections import Counter

        try:
            # 1. Base querysets for strictly ACTIVE entities
            active_students_qs = Student.objects.filter(
                Q(status__is_active=True) & ~Q(status__status_name__in=['INACTIVE', 'LEFT', 'SUSPENDED', 'DISCONTINUED', 'DROPPED']),
                department__is_active=True,
                batch__is_active=True
            )
            active_users_qs = User.objects.filter(status='ACTIVE')
            active_depts_qs = Department.objects.filter(is_active=True)
            active_details_qs = UserDetails.objects.filter(user__status='ACTIVE', department__is_active=True)

            total_students = active_students_qs.count()
            teaching_faculty_count = active_users_qs.filter(role__role_name__in=['FACULTY', 'HOD']).count()
            total_users = active_users_qs.count()
            total_hods = active_users_qs.filter(role__role_name='HOD').count()
            active_depts_count = active_depts_qs.count()

            # 2. Roles breakdown (for ACTIVE users only)
            roles_data = list(active_users_qs.values('role__role_name').annotate(count=Count('id')).order_by('-count'))
            roles_list = []
            for r in roles_data:
                r_name = r['role__role_name'] or 'UNASSIGNED'
                cnt = r['count']
                pct = round((cnt / total_users * 100), 1) if total_users else 0
                roles_list.append({'role': r_name, 'count': cnt, 'percentage': pct})

            # 3. Designations breakdown (for ACTIVE faculty only)
            desigs_map = Counter()
            raw_desigs = UserDetails.objects.filter(user__status='ACTIVE').values_list('designation', flat=True)
            for d in raw_desigs:
                val = (d or '').strip().upper()
                if not val:
                    norm = 'Not Specified'
                elif 'ASST' in val or 'ASSISTANT' in val:
                    norm = 'Assistant Professor'
                elif 'ASSOC' in val or 'ASSOCIATE' in val:
                    norm = 'Associate Professor'
                elif 'PRINCIPAL' in val:
                    norm = 'Principal'
                elif 'PROF' in val:
                    norm = 'Professor'
                elif 'LECTURER' in val:
                    norm = 'Lecturer'
                elif 'LAB' in val:
                    norm = 'Lab Instructor'
                else:
                    norm = d.strip().title()
                desigs_map[norm] += 1

            total_details = sum(desigs_map.values())
            designations_list = [
                {'designation': k, 'count': v, 'percentage': round(v / total_details * 100, 1) if total_details else 0}
                for k, v in desigs_map.most_common()
            ]

            # 4. Department-wise students, faculty, active batches & sections
            dept_students = {d['department_id']: d['count'] for d in active_students_qs.values('department_id').annotate(count=Count('id'))}
            dept_faculty = {d['department_id']: d['count'] for d in active_details_qs.filter(department_id__isnull=False).values('department_id').annotate(count=Count('id'))}

            from institution.models import Batch, Section
            total_active_batches = Batch.objects.filter(is_active=True, department__is_active=True).count()
            total_active_sections = Section.objects.filter(department__is_active=True).count()

            departments_list = []
            for dept in active_depts_qs.select_related('program', 'hod', 'hod__role').order_by('department_name'):
                s_cnt = dept_students.get(dept.id, 0)
                f_cnt = dept_faculty.get(dept.id, 0)
                s_pct = round(s_cnt / total_students * 100, 1) if total_students else 0
                ratio = f"{round(s_cnt / f_cnt, 1)}:1" if f_cnt > 0 else f"{s_cnt}:0"

                # Active HOD info
                hod_info = None
                if dept.hod and dept.hod.status == 'ACTIVE':
                    hod_user = dept.hod
                    hod_detail = UserDetails.objects.filter(user=hod_user).first()
                    hod_info = {
                        'id': hod_user.id,
                        'name': hod_user.name,
                        'email': hod_user.mail,
                        'mobile': hod_user.mobile_number,
                        'role_name': getattr(hod_user.role, 'role_name', 'HOD') if hod_user.role else 'HOD',
                        'faculty_code': getattr(hod_detail, 'faculty_code', '') if hod_detail else '',
                        'designation': getattr(hod_detail, 'designation', 'Head of Department') if hod_detail else 'Head of Department',
                        'qualification': getattr(hod_detail, 'qualification', '') if hod_detail else '',
                        'user_image': getattr(hod_detail, 'user_image', '') if hod_detail else '',
                    }

                # All configured Active Batches for this department
                dept_batches = Batch.objects.filter(department=dept, is_active=True).order_by('-batch')
                batches = [
                    {
                        'id': b.id,
                        'batch': b.batch,
                        'is_active': b.is_active,
                        'count': active_students_qs.filter(department=dept, batch=b).count()
                    }
                    for b in dept_batches
                ]

                # All configured Sections for this department
                dept_sections = Section.objects.filter(department=dept).order_by('sections')
                sections = [
                    {
                        'id': s.id,
                        'section': s.sections,
                        'count': active_students_qs.filter(department=dept, section=s).count()
                    }
                    for s in dept_sections
                ]

                departments_list.append({
                    'id': dept.id,
                    'department_name': dept.department_name,
                    'department_code': dept.department_code,
                    'short_name': dept.short_name or dept.department_code,
                    'program_name': dept.program.program_name if dept.program else 'Under Graduate',
                    'program_level': dept.program.program_level if dept.program else 'UG',
                    'is_active': True,
                    'student_count': s_cnt,
                    'faculty_count': f_cnt,
                    'active_batches_count': len(batches),
                    'active_sections_count': len(sections),
                    'student_percentage': s_pct,
                    'ratio': ratio,
                    'hod': hod_info,
                    'batches': batches,
                    'sections': sections,
                })

            # 5. HODs list (ACTIVE departments & ACTIVE HOD users only)
            hods_list = []
            for dept in active_depts_qs.select_related('hod', 'hod__role').filter(hod__isnull=False, hod__status='ACTIVE').order_by('short_name'):
                hod_user = dept.hod
                if hod_user:
                    hod_detail = UserDetails.objects.filter(user=hod_user).first()
                    hods_list.append({
                        'department_id': dept.id,
                        'department_name': dept.department_name,
                        'department_code': dept.department_code,
                        'short_name': dept.short_name or dept.department_code,
                        'hod_id': hod_user.id,
                        'hod_name': hod_user.name,
                        'hod_email': hod_user.mail,
                        'hod_mobile': hod_user.mobile_number,
                        'role_name': getattr(hod_user.role, 'role_name', 'HOD') if hod_user.role else 'HOD',
                        'faculty_code': getattr(hod_detail, 'faculty_code', '') if hod_detail else '',
                        'designation': getattr(hod_detail, 'designation', 'Head of Department') if hod_detail else 'Head of Department',
                        'qualification': getattr(hod_detail, 'qualification', '') if hod_detail else '',
                        'user_image': getattr(hod_detail, 'user_image', '') if hod_detail else '',
                    })

            # Department student distribution sorted by student count descending
            dept_distribution = sorted(
                [
                    {
                        'id': d['id'],
                        'name': d['short_name'],
                        'full_name': d['department_name'],
                        'code': d['department_code'],
                        'count': d['student_count'],
                        'faculty_count': d['faculty_count'],
                        'percentage': d['student_percentage']
                    }
                    for d in departments_list if d['student_count'] > 0
                ],
                key=lambda x: x['count'],
                reverse=True
            )

            return Response({
                "code": 200,
                "message": "Active dashboard analytics retrieved successfully",
                "data": {
                    "summary": {
                        "total_students": total_students,
                        "total_faculty": teaching_faculty_count,
                        "total_users": total_users,
                        "total_hods": total_hods,
                        "total_departments": active_depts_count,
                        "active_departments": active_depts_count,
                        "total_active_batches": total_active_batches,
                        "total_active_sections": total_active_sections,
                        "student_faculty_ratio": f"{round(total_students / teaching_faculty_count, 1)}:1" if teaching_faculty_count else "0:1",
                    },
                    "departments": departments_list,
                    "dept_distribution": dept_distribution,
                    "faculty_roles_breakdown": roles_list,
                    "faculty_designation_breakdown": designations_list,
                    "hods_list": hods_list,
                }
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Failed to compute dashboard analytics: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "Users listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "User created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "deleted successfully"
        }, status=status.HTTP_200_OK)

    def login(self, request, *args, **kwargs):
        username = request.data.get('username')
        password = request.data.get('password')
        login_type = request.data.get('login_type') or request.data.get('loginType')

        if username is None or password is None:
            return Response({
                "code": 400,
                "message": "Username and password are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Convert to string to avoid AttributeError if client sends an integer password or username
        username_str = str(username).strip()
        password_str = str(password).strip()

        if not username_str or not password_str:
            return Response({
                "code": 400,
                "message": "Username and password cannot be empty."
            }, status=status.HTTP_400_BAD_REQUEST)

        import bcrypt
        import re
        from django.db import IntegrityError
        from django.db.models import Q
        from student.models import Student
        from role.models import Role
        from rest_framework_simplejwt.tokens import RefreshToken

        try:
            # 1. Fast indexed lookup on User model (eagerly loading role in a single query)
            user = User.objects.select_related('role').filter(username=username_str).first()
            if not user:
                # Try email lookup if username is an email address
                if '@' in username_str:
                    user = User.objects.select_related('role').filter(mail__iexact=username_str).first()
                # Try mobile number if username is numeric or lookup by iexact
                elif username_str.isdigit() and len(username_str) == 10:
                    user = User.objects.select_related('role').filter(mobile_number=username_str).first()
                if not user:
                    user = User.objects.select_related('role').filter(username__iexact=username_str).first()

            if user:
                if bcrypt.checkpw(password_str.encode('utf-8'), user.password.encode('utf-8')):
                    user_role_name = (user.role.role_name if user.role else '').upper()

                    # Role separation checks
                    if login_type == 'institution' and user_role_name == 'STUDENT':
                        return Response({
                            "code": 403,
                            "message": "Student accounts are not allowed to log in via Institution Login. Please use Student Login."
                        }, status=status.HTTP_403_FORBIDDEN)

                    if login_type == 'student' and user_role_name and user_role_name != 'STUDENT':
                        return Response({
                            "code": 403,
                            "message": "Only students can log in via Student Login. Please use Institution Login."
                        }, status=status.HTTP_403_FORBIDDEN)

                    refresh = RefreshToken.for_user(user)
                    user_data = UserSerializer(user).data

                    # Attach student_id ONLY if user is a student
                    if user_role_name == 'STUDENT':
                        student = Student.objects.filter(
                            Q(roll_number=username_str) |
                            Q(register_number=username_str) |
                            Q(application__candidate__phone_number=user.mobile_number) |
                            Q(application__candidate__email=user.mail)
                        ).only('id', 'roll_number').first()
                        if student:
                            user_data['student_id'] = student.id
                            user_data['student_roll'] = student.roll_number

                    # Automatically register user in online cache and broadcast
                    try:
                        online_info = resolve_user_presence_data(user, user_role_name, request)
                        broadcast_user_online(online_info)
                    except Exception:
                        pass

                    return Response({
                        "code": 200,
                        "message": "Logged in successfully",
                        "data": {
                            "access_token": str(refresh.access_token),
                            "refresh_token": str(refresh),
                            "user": user_data
                        }
                    }, status=status.HTTP_200_OK)
                else:
                    # User exists in User model but password failed -> reject immediately
                    return Response({
                        "code": 400,
                        "message": "Invalid password."
                    }, status=status.HTTP_400_BAD_REQUEST)

            # 2. Student fallback lookup by Roll Number, Register Number, Email, or Phone Number if User record does NOT exist
            student_qs = Student.objects.select_related('application', 'application__candidate')
            student = student_qs.filter(
                Q(roll_number=username_str) |
                Q(register_number=username_str) |
                Q(roll_number__iexact=username_str) |
                Q(register_number__iexact=username_str) |
                Q(application__candidate__phone_number=username_str) |
                Q(application__candidate__email__iexact=username_str)
            ).first()

            if student:
                if login_type == 'institution':
                    return Response({
                        "code": 403,
                        "message": "Student accounts are not allowed to log in via Institution Login. Please use Student Login."
                    }, status=status.HTTP_403_FORBIDDEN)

                # Extract DOB from application form_data or user details
                app = student.application
                fd = app.form_data if (app and app.form_data and isinstance(app.form_data, dict)) else {}
                personal = fd.get('personal_information', {}) if isinstance(fd, dict) else {}

                dob_val = str(
                    personal.get('date_of_birth', '') or
                    personal.get('dob', '') or
                    personal.get('dateOfBirth', '') or
                    personal.get('birth_date', '') or
                    ''
                ).strip()

                def get_digits(s):
                    return re.sub(r'\D', '', str(s))

                digits_input = get_digits(password_str)
                digits_dob = get_digits(dob_val)

                is_valid_dob = False
                if digits_input and digits_dob:
                    if digits_input == digits_dob:
                        is_valid_dob = True
                    elif len(digits_input) == 8 and len(digits_dob) == 8:
                        d_in = digits_input
                        d_dob = digits_dob
                        # Compare DDMMYYYY with YYYYMMDD
                        rev_in = d_in[4:] + d_in[2:4] + d_in[:2]
                        if rev_in == d_dob or d_in == d_dob[4:] + d_dob[2:4] + d_dob[:2]:
                            is_valid_dob = True

                if not is_valid_dob and dob_val:
                    if password_str.lower() == dob_val.lower():
                        is_valid_dob = True

                if is_valid_dob:
                    student_role = Role.objects.filter(role_name='STUDENT').first()
                    if not student_role:
                        student_role = Role.objects.create(role_name='STUDENT')
                    candidate_name = student.user.name if student.user else f"Student {student.roll_number}"
                    email = student.user.email if (student.user and student.user.email) else f"student_{student.id}@tec.edu"
                    mobile = student.user.phone_number if (student.user and student.user.phone_number) else "9999999999"

                    username_key = student.roll_number or student.register_number or f"student_{student.id}"

                    # Lookup user by username or email to avoid duplicate entry
                    user_obj = User.objects.select_related('role').filter(username=username_key).first()
                    if not user_obj and email:
                        user_obj = User.objects.select_related('role').filter(mail__iexact=email).first()

                    hashed_pass = bcrypt.hashpw(password_str.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                    valid_mobile = mobile if (len(mobile) == 10 and mobile.isdigit()) else "9999999999"

                    if not user_obj:
                        try:
                            user_obj = User.objects.create(
                                name=candidate_name,
                                username=username_key,
                                password=hashed_pass,
                                mobile_number=valid_mobile,
                                mail=email,
                                role=student_role
                            )
                        except IntegrityError:
                            # If email is duplicate, find and update that user
                            existing_user = User.objects.filter(mail__iexact=email).first()
                            if existing_user:
                                user_obj = existing_user
                                user_obj.username = username_key
                                user_obj.password = hashed_pass
                                user_obj.role = student_role
                                user_obj.save(update_fields=['username', 'password', 'role'])
                            else:
                                return Response({
                                    "code": 400,
                                    "message": "Your email already exists in the system or you don't have access to login. Please contact Technical Support."
                                }, status=status.HTTP_400_BAD_REQUEST)
                    else:
                        fields_to_update = []
                        if user_obj.role != student_role:
                            user_obj.role = student_role
                            fields_to_update.append('role')
                        if user_obj.username != username_key and not User.objects.filter(username=username_key).exclude(pk=user_obj.pk).exists():
                            user_obj.username = username_key
                            fields_to_update.append('username')
                        # Sync password with latest successful DOB login
                        user_obj.password = hashed_pass
                        fields_to_update.append('password')
                        if fields_to_update:
                            user_obj.save(update_fields=fields_to_update)

                    refresh = RefreshToken.for_user(user_obj)
                    user_data = UserSerializer(user_obj).data
                    user_data['student_id'] = student.id
                    user_data['student_roll'] = student.roll_number

                    # Automatically register student in online cache and broadcast
                    try:
                        online_info = resolve_user_presence_data(user_obj, 'STUDENT', request)
                        broadcast_user_online(online_info)
                    except Exception:
                        pass

                    return Response({
                        "code": 200,
                        "message": "Logged in successfully",
                        "data": {
                            "access_token": str(refresh.access_token),
                            "refresh_token": str(refresh),
                            "user": user_data
                        }
                    }, status=status.HTTP_200_OK)

            return Response({
                "code": 400,
                "message": "Invalid username or password."
            }, status=status.HTTP_400_BAD_REQUEST)

        except IntegrityError:
            return Response({
                "code": 400,
                "message": "Your email already exists in the system or you don't have access to login. Please contact Technical Support."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                "code": 400,
                "message": f"Unable to process login: {str(e)}. If this persists, please contact Technical Support."
            }, status=status.HTTP_400_BAD_REQUEST)

    def change_password(self, request, *args, **kwargs):
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not old_password or not new_password or not confirm_password:
            return Response({
                "code": 400,
                "message": "Old password, new password, and confirm password are required."
            }, status=status.HTTP_400_BAD_REQUEST)

        if str(new_password).strip() != str(confirm_password).strip():
            return Response({
                "code": 400,
                "message": "New password and confirm password do not match."
            }, status=status.HTTP_400_BAD_REQUEST)

        user = getattr(request, 'user', None)
        if not user or not getattr(user, 'is_authenticated', False):
            user_id = request.data.get('user_id')
            if user_id:
                user = User.objects.filter(id=user_id).first()

        if not user:
            return Response({
                "code": 401,
                "message": "Authentication required to change password."
            }, status=status.HTTP_401_UNAUTHORIZED)

        # Enforce role access: Student or Admin allowed
        user_role = (user.role.role_name if hasattr(user, 'role') and user.role else '').upper()
        if user_role not in ['STUDENT', 'ADMIN', 'ADMINISTRATOR'] and getattr(user, 'id', None) != getattr(request.user, 'id', None):
            return Response({
                "code": 403,
                "message": "Only students or administrators are allowed to change passwords."
            }, status=status.HTTP_403_FORBIDDEN)

        import bcrypt
        if not bcrypt.checkpw(str(old_password).strip().encode('utf-8'), user.password.encode('utf-8')):
            return Response({
                "code": 400,
                "message": "Old password is incorrect."
            }, status=status.HTTP_400_BAD_REQUEST)

        hashed_new = bcrypt.hashpw(str(new_password).strip().encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        user.password = hashed_new
        user.save(update_fields=['password'])

        return Response({
            "code": 200,
            "message": "Password updated successfully."
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], permission_classes=[permissions.IsAuthenticated], url_path='heartbeat')
    def heartbeat(self, request):
        from django.core.cache import cache
        from django.utils import timezone

        user = request.user
        if not user or not getattr(user, 'is_authenticated', False):
            return Response({"code": 401, "message": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)

        status_req = str(request.data.get('status', 'online')).lower()
        user_id = getattr(user, 'id', None)
        if not user_id:
            return Response({"code": 200, "message": "OK"})

        user_ids = cache.get('online_user_ids', set())
        if not isinstance(user_ids, set):
            user_ids = set(user_ids) if isinstance(user_ids, (list, tuple)) else set()

        if status_req == 'offline':
            user_ids.discard(user_id)
            cache.set('online_user_ids', user_ids, timeout=None)
            cache.delete(f'online_user_{user_id}')
            
            # Broadcast offline presence via WebSockets
            try:
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                layer = get_channel_layer()
                if layer:
                    async_to_sync(layer.group_send)(
                        'realtime_updates',
                        {
                            'type': 'broadcast_update',
                            'data': {
                                'model': 'OnlineUser',
                                'action': 'offline',
                                'user_id': user_id
                            }
                        }
                    )
            except Exception:
                pass
                
            return Response({"code": 200, "message": "Marked offline", "status": "offline"})

        # Enrich and broadcast presence
        online_data = resolve_user_presence_data(user, None, request)
        broadcast_user_online(online_data)

        return Response({
            "code": 200,
            "message": "Heartbeat updated",
            "status": "online",
            "data": online_data
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated], url_path='online-users')
    def online_users(self, request):
        from django.core.cache import cache
        from django.utils import timezone

        user = request.user
        role_name_raw = (getattr(user.role, 'role_name', '') if hasattr(user, 'role') and user.role else '').upper().strip()

        # Check permissions: Admin or Technical Support only
        is_allowed = getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False) or any(
            r in role_name_raw for r in ['ADMIN', 'SUPER', 'TECH', 'SUPPORT', 'TS', 'SYSTEM', 'OFFICER']
        )

        if not is_allowed:
            return Response({
                "code": 403,
                "message": "Access restricted: Only Admin and Technical Support can view active online users."
            }, status=status.HTTP_403_FORBIDDEN)

        user_ids = cache.get('online_user_ids', set())
        if not isinstance(user_ids, set):
            user_ids = set(user_ids) if isinstance(user_ids, (list, tuple)) else set()

        # Auto-hydrate current user if not yet in cache
        user_id = getattr(user, 'id', None)
        if user_id and not cache.get(f'online_user_{user_id}'):
            current_user_data = resolve_user_presence_data(user, None, request)
            broadcast_user_online(current_user_data)

        active_users = []
        stale_ids = set()

        for uid in list(user_ids):
            data = cache.get(f'online_user_{uid}')
            if data:
                # Ensure student photo / user image is resolved if missing
                if not data.get('student_photo') and not data.get('user_image'):
                    try:
                        u_obj = User.objects.filter(id=uid).first()
                        if u_obj:
                            data = resolve_user_presence_data(u_obj, data.get('role_name'), None)
                            cache.set(f'online_user_{uid}', data, timeout=90)
                    except Exception:
                        pass
                active_users.append(data)
            else:
                stale_ids.add(uid)

        # Clean up stale IDs
        if stale_ids:
            user_ids.difference_update(stale_ids)
            cache.set('online_user_ids', user_ids, timeout=None)

        # Search query filter if provided
        search = request.query_params.get('search', '').strip().lower()
        if search:
            active_users = [
                u for u in active_users
                if search in u.get('name', '').lower()
                or search in u.get('username', '').lower()
                or search in u.get('role_name', '').lower()
                or search in (u.get('department_name') or '').lower()
            ]

        # Sort users by last_seen descending
        active_users.sort(key=lambda x: x.get('last_seen', ''), reverse=True)

        return Response({
            "code": 200,
            "message": "Online users fetched successfully",
            "count": len(active_users),
            "data": active_users
        }, status=status.HTTP_200_OK)

    def handle_exception(self, exc):
        from django.http import Http404
        from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied

        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "User not found"
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

    @action(detail=False, methods=['post'], url_path='bulk-import')
    def bulk_import(self, request):
        import bcrypt
        from django.db import transaction
        from role.models import Role
        from institution.models import Department
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError as DjangoValidationError
        from datetime import datetime
        import datetime as dt

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
            # Strip time portion if present (e.g. "2024-05-12T00:00:00.000Z" -> "2024-05-12")
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

        users_data = request.data.get('users', [])
        if not users_data:
            return Response({
                "code": 400,
                "message": "No user data provided."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Cache roles and departments for fast lookup
        roles_map = {r.role_name.upper(): r.role_id for r in Role.objects.all()}
        depts_map = {d.department_code.upper(): d for d in Department.objects.all()}
        depts_name_map = {d.department_name.upper(): d for d in Department.objects.all()}

        # Track uniqueness of values within the upload sheet
        seen_usernames = set()
        seen_emails = set()
        seen_faculty_codes = set()

        errors = []
        validated_users = []

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
        for idx, u in enumerate(users_data):
            row_num = u.get('s_no', idx + 1)
            name = str(u.get('name', '')).strip()
            faculty_code = str(u.get('faculty_code', '')).strip()
            mail = str(u.get('mail', '')).strip()
            mobile_raw = u.get('mobile_number', '') or u.get('phone_number', '') or u.get('phone', '')
            mobile_number = sanitize_phone_number(mobile_raw)
            role_name = str(u.get('role', '')).strip().upper()
            qualification = str(u.get('qualification', '')).strip()
            designation = str(u.get('designation', '')).strip()
            gender = str(u.get('gender', '')).strip()

            raw_doj = u.get('date_of_joining') or u.get('doj')
            raw_dob = u.get('dob')

            department_name = str(u.get('department', '')).strip()
            password = str(u.get('password', '')).strip()
            if not password:
                password = mobile_number

            row_errors = []

            # Check required fields
            if not name:
                row_errors.append("Name is required.")
            if not faculty_code:
                row_errors.append("Faculty code is required.")
            if not mail:
                row_errors.append("Email is required.")
            else:
                try:
                    validate_email(mail)
                except DjangoValidationError:
                    row_errors.append("Invalid email address format.")

            if not mobile_number:
                row_errors.append("Mobile number is required.")
            elif not (mobile_number.isdigit() and len(mobile_number) == 10):
                row_errors.append("Mobile number must be exactly 10 digits.")

            if not role_name:
                row_errors.append("Role is required.")
            elif role_name not in roles_map:
                row_errors.append(f"Role '{role_name}' does not exist in the system.")

            if not qualification:
                row_errors.append("Qualification is required.")
            if not designation:
                row_errors.append("Designation is required.")
            if not gender:
                row_errors.append("Gender is required.")
            elif gender.capitalize() not in ['Male', 'Female', 'Other']:
                row_errors.append("Gender must be 'Male', 'Female', or 'Other'.")

            # Parse and validate dates
            parsed_doj = parse_date(raw_doj)
            if not raw_doj:
                row_errors.append("Date of joining (DOJ) is required.")
            elif not parsed_doj:
                row_errors.append(f"Invalid date format for DOJ: '{raw_doj}'. Expected YYYY-MM-DD.")

            parsed_dob = parse_date(raw_dob) if raw_dob else None
            if raw_dob and not parsed_dob:
                row_errors.append(f"Invalid date format for DOB: '{raw_dob}'. Expected YYYY-MM-DD.")

            # Resolve Department
            dept_instance = None
            if department_name:
                dept_key = department_name.upper()
                if dept_key in depts_map:
                    dept_instance = depts_map[dept_key]
                elif dept_key in depts_name_map:
                    dept_instance = depts_name_map[dept_key]
                else:
                    matched_dept = Department.objects.filter(short_name__iexact=department_name).first()
                    if matched_dept:
                        dept_instance = matched_dept
                    else:
                        row_errors.append(f"Department '{department_name}' does not exist in the system.")

            # Check database-level uniqueness if no errors so far
            if not row_errors:
                username = faculty_code

                # Check for duplicates in the current uploaded batch
                if username in seen_usernames:
                    row_errors.append(f"Duplicate Faculty Code '{username}' inside this sheet.")
                if mail in seen_emails:
                    row_errors.append(f"Duplicate Email '{mail}' inside this sheet.")
                if faculty_code in seen_faculty_codes:
                    row_errors.append(f"Duplicate Faculty Code '{faculty_code}' inside this sheet.")

                # Check database records
                if User.objects.filter(username=username).exists():
                    row_errors.append(f"Username/Faculty Code '{username}' is already in use.")
                if User.objects.filter(mail=mail).exists():
                    row_errors.append(f"Email '{mail}' is already registered.")
                if UserDetails.objects.filter(faculty_code=faculty_code).exists():
                    row_errors.append(f"Faculty Code '{faculty_code}' is already registered.")

                if not row_errors:
                    seen_usernames.add(username)
                    seen_emails.add(mail)
                    seen_faculty_codes.add(faculty_code)

                    validated_users.append({
                        "name": name,
                        "username": username,
                        "mail": mail,
                        "mobile_number": mobile_number,
                        "password": password,
                        "role_id": roles_map[role_name],
                        "faculty_code": faculty_code,
                        "qualification": qualification,
                        "designation": designation,
                        "gender": gender.capitalize(),
                        "date_of_joining": parsed_doj,
                        "dob": parsed_dob,
                        "department": dept_instance
                    })

            if row_errors:
                errors.append({
                    "row": row_num,
                    "faculty_code": faculty_code,
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

        # 2. Writing Phase (Inside transaction for atomicity)
        tracking_user = request.user if request.user and request.user.is_authenticated else None

        try:
            with transaction.atomic():
                for item in validated_users:
                    # Set password defaults to mobile_number if not provided
                    default_pass = item.get("password") or item["mobile_number"]
                    hashed_pass = bcrypt.hashpw(default_pass.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

                    user = User.objects.create(
                        name=item["name"],
                        username=item["username"],
                        password=hashed_pass,
                        mobile_number=item["mobile_number"],
                        mail=item["mail"],
                        role_id=item["role_id"],
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )

                    UserDetails.objects.create(
                        user=user,
                        faculty_code=item["faculty_code"],
                        qualification=item["qualification"],
                        designation=item["designation"],
                        date_of_joining=item["date_of_joining"],
                        gender=item["gender"],
                        dob=item["dob"],
                        department=item["department"],
                        created_by=tracking_user,
                        updated_by=tracking_user
                    )
        except Exception as e:
            return Response({
                "code": 500,
                "message": f"Database error during import: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "code": 201,
            "message": f"Successfully imported {len(validated_users)} faculty members.",
            "data": {
                "count": len(validated_users)
            }
        }, status=status.HTTP_201_CREATED)


class UserDetailsViewSet(viewsets.ModelViewSet):
    queryset = UserDetails.objects.select_related('user', 'role', 'department').all().order_by('id')
    serializer_class = UserDetailsSerializer
    permission_classes = [UserDetailsPermission]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return UserDetails.objects.none()

        qs = UserDetails.objects.select_related('user', 'department').all().order_by('id')

        # For GET/list requests, allow authenticated users (Faculty, HOD, Admin, etc.) to list all faculty members
        if self.action in ['list', 'retrieve'] or self.request.method in ['GET']:
            return qs

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR', 'SUPER_ADMIN', 'SUPERADMIN']:
                is_admin = True
        except AttributeError:
            pass

        if is_admin:
            return qs

        if isinstance(user, User):
            return qs.filter(user=user)

        return UserDetails.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        tracking_user = user if isinstance(user, User) else None

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        # Handle image upload to R2
        image_file = serializer.validated_data.pop('user_image_file', None)
        image_url = None
        if image_file:
            from common.r2 import upload_file_to_r2
            image_url = upload_file_to_r2(image_file, folder_name='user')

        save_kwargs = {'created_by': tracking_user, 'updated_by': tracking_user}
        if image_url:
            save_kwargs['user_image'] = image_url
        if not is_admin and isinstance(user, User):
            save_kwargs['user'] = user

        serializer.save(**save_kwargs)

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
            if instance.user != user:
                raise PermissionDenied("You do not have permission to update these user details.")

        # Handle image upload to R2
        image_file = serializer.validated_data.pop('user_image_file', None)
        image_url = None
        if image_file:
            from common.r2 import upload_file_to_r2
            image_url = upload_file_to_r2(image_file, folder_name='user')

        tracking_user = user if isinstance(user, User) else None
        save_kwargs = {'updated_by': tracking_user}
        if image_url:
            save_kwargs['user_image'] = image_url

        serializer.save(**save_kwargs)

    def destroy(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        is_admin = False
        try:
            role_name = user.role.role_name.upper()
            if role_name in ['ADMIN', 'ADMINISTRATOR']:
                is_admin = True
        except AttributeError:
            pass

        if not is_admin:
            if instance.user != user:
                raise PermissionDenied("You do not have permission to delete these user details.")

        super().destroy(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details deleted successfully"
        }, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details listed successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def retrieve(self, request, *args, **kwargs):
        response = super().retrieve(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details retrieved successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        return Response({
            "code": 201,
            "message": "User details created successfully",
            "data": response.data
        }, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        return Response({
            "code": 200,
            "message": "User details updated successfully",
            "data": response.data
        }, status=status.HTTP_200_OK)

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": "User details not found"
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


