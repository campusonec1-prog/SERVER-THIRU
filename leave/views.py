from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.http import Http404
from rest_framework.exceptions import NotFound, NotAuthenticated, PermissionDenied
from django.db import transaction, models
from django.db.models import Q
from datetime import datetime, timedelta


from .models import LeavePolicy, FacultyLeave, ClassSubstitution, Notification
from .serializers import (
    LeavePolicySerializer, FacultyLeaveSerializer,
    ClassSubstitutionSerializer, NotificationSerializer
)
from .permissions import (
    LeavePolicyPermission, FacultyLeavePermission,
    ClassSubstitutionPermission, NotificationPermission
)
from users.models import User
from institution.models import Department, AcademicYear, Semester, Section, Batch
from schedule.models import Day, Period, AcademicCalendarEvent
from timetable.models import ClassTimetable
from subject.models import Subject



class AdminWriteMixin:
    """Provides standard exception handling and user auditing for creation and updates."""

    def handle_exception(self, exc):
        if isinstance(exc, (Http404, NotFound)):
            return Response({
                "code": 404,
                "message": f"{getattr(self, 'model_label', 'Resource')} not found"
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
        serializer.save(created_by=user, updated_by=user)

    def perform_update(self, serializer):
        user = self.request.user if self.request.user and self.request.user.is_authenticated else None
        serializer.save(updated_by=user)


def _broadcast_realtime(payload, event_name, target_user_id=None):
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
                        'model': 'Leave',
                        'target_user_id': target_user_id,
                        'payload': payload
                    }
                }
            )
    except Exception:
        pass


class LeavePolicyViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = LeavePolicy.objects.all().order_by('-id')
    serializer_class = LeavePolicySerializer
    permission_classes = [LeavePolicyPermission]
    model_label = "Leave Policy"

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Leave policies listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        _broadcast_realtime(response.data.get('data'), 'leave_policy_updated')
        return Response({"code": 201, "message": "Leave policy created successfully", "data": response.data}, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        _broadcast_realtime(response.data.get('data'), 'leave_policy_updated')
        return Response({"code": 200, "message": "Leave policy updated successfully", "data": response.data}, status=status.HTTP_200_OK)


class FacultyLeaveViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = FacultyLeave.objects.all().order_by('-id')
    serializer_class = FacultyLeaveSerializer
    permission_classes = [FacultyLeavePermission]
    model_label = "Faculty Leave"

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user or not user.is_authenticated:
            return qs.none()

        role = getattr(user.role, 'role_name', '').upper() if hasattr(user, 'role') and user.role else ''
        
        # Admins & Principals see all leaves
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False) or role in ['ADMIN', 'ADMINISTRATOR', 'PRINCIPAL', 'VICE_PRINCIPAL']:
            return qs


        # HOD sees department leaves
        if role == 'HOD':
            dept_ids = list(user.hod_departments.values_list('id', flat=True))
            if hasattr(user, 'user_details') and user.user_details.exists():
                u_dept = user.user_details.first().department
                if u_dept and u_dept.id not in dept_ids:
                    dept_ids.append(u_dept.id)
            if dept_ids:
                return qs.filter(department_id__in=dept_ids)
            return qs

        # Faculty sees own leaves
        return qs.filter(applicant=user)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Leave applications listed successfully", "data": response.data}, status=status.HTTP_200_OK)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        data = request.data
        user = request.user

        from_date_str = data.get('from_date')
        to_date_str = data.get('to_date')
        leave_type = data.get('leave_type')
        reason = data.get('reason', '').strip()
        substitutions_input = data.get('substitutions', [])

        if not from_date_str or not to_date_str:
            return Response({"code": 400, "message": "From date and To date are required."}, status=status.HTTP_400_BAD_REQUEST)

        if not leave_type or not reason:
            return Response({"code": 400, "message": "Leave type and reason are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            d_from = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            d_to = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"code": 400, "message": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        if d_to < d_from:
            return Response({"code": 400, "message": "To date must be after or equal to From date."}, status=status.HTTP_400_BAD_REQUEST)

        # Auto calculate total days
        if leave_type in ['HALF_DAY_FN', 'HALF_DAY_AN']:
            total_days = 0.5
        elif leave_type == 'PERMISSION':
            total_days = 0.2
        else:
            total_days = float((d_to - d_from).days + 1)

        # Identify applicant's primary department
        dept = None
        if hasattr(user, 'hod_departments') and user.hod_departments.exists():
            dept = user.hod_departments.first()
        elif hasattr(user, 'user_details') and user.user_details.exists() and user.user_details.first().department:
            dept = user.user_details.first().department

        
        if not dept:
            dept = Department.objects.first()

        # Active Academic Year
        acad_year = AcademicYear.objects.filter(is_display=True).first() or AcademicYear.objects.filter(is_active=True).first()

        initial_status = 'PENDING_SUBSTITUTION' if len(substitutions_input) > 0 else 'PENDING_APPROVAL'

        leave_app = FacultyLeave.objects.create(
            applicant=user,
            department=dept,
            academic_year=acad_year,
            leave_type=leave_type,
            from_date=d_from,
            to_date=d_to,
            total_days=total_days,
            reason=reason,
            status=initial_status,
            created_by=user,
            updated_by=user
        )

        # Create substitutions and inbox notifications
        created_subs = []
        for sub_item in substitutions_input:
            sub_fac_id = sub_item.get('substitute_faculty_id')
            if not sub_fac_id:
                continue

            try:
                sub_fac = User.objects.get(id=sub_fac_id)
            except User.DoesNotExist:
                continue

            sub_date = datetime.strptime(sub_item.get('date'), '%Y-%m-%d').date()
            period_inst = Period.objects.get(id=sub_item.get('period_id'))
            day_inst = Day.objects.get(id=sub_item.get('day_id'))

            class_tt = None
            if sub_item.get('class_timetable_id'):
                class_tt = ClassTimetable.objects.filter(id=sub_item.get('class_timetable_id')).first()

            sub_dept = Department.objects.get(id=sub_item.get('department_id'))
            sub_batch = Batch.objects.get(id=sub_item.get('batch_id'))
            sub_sem = Semester.objects.get(id=sub_item.get('semester_id'))
            sub_sec = Section.objects.get(id=sub_item.get('section_id'))
            sub_subj = Subject.objects.filter(id=sub_item.get('subject_id')).first() if sub_item.get('subject_id') else None

            sub_obj = ClassSubstitution.objects.create(
                leave_application=leave_app,
                date=sub_date,
                period=period_inst,
                day=day_inst,
                original_faculty=user,
                substitute_faculty=sub_fac,
                class_timetable=class_tt,
                department=sub_dept,
                batch=sub_batch,
                semester=sub_sem,
                section=sub_sec,
                subject=sub_subj,
                status='PENDING',
                created_by=user,
                updated_by=user
            )
            created_subs.append(sub_obj)

            # Create Notification in Header Inbox for substitute faculty
            applicant_name = user.name or user.username

            p_time = f"{period_inst.start_time.strftime('%I:%M %p')}"
            notif_msg = (
                f"{applicant_name} has requested you to substitute for Period {period_inst.period_no} ({p_time}) "
                f"on {sub_date.strftime('%d-%m-%Y')} for {sub_dept.department_code} (Sec {sub_sec.sections})."
            )

            Notification.objects.create(
                user=sub_fac,
                sender=user,
                title="Class Substitution Request",
                message=notif_msg,
                notification_type='SUBSTITUTION_REQUEST',
                related_substitution=sub_obj,
                related_leave=leave_app,
                created_by=user,
                updated_by=user
            )

            _broadcast_realtime({'substitution_id': sub_obj.id}, 'notification_received', target_user_id=sub_fac.id)

        serializer = self.get_serializer(leave_app)
        _broadcast_realtime(serializer.data, 'leave_created')

        return Response({
            "code": 201,
            "message": "Leave application submitted successfully.",
            "data": serializer.data
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='approve')
    def approve_leave(self, request, pk=None):
        leave_app = self.get_object()
        user = request.user
        role = getattr(user.role, 'role_name', '').upper() if hasattr(user, 'role') and user.role else ''

        if not getattr(user, 'is_superuser', False) and role not in ['HOD', 'ADMIN', 'ADMINISTRATOR', 'PRINCIPAL', 'VICE_PRINCIPAL']:
            return Response({"code": 403, "message": "Only HOD or Admin can approve leaves."}, status=status.HTTP_403_FORBIDDEN)

        leave_app.status = 'APPROVED'
        leave_app.approved_by = user
        leave_app.save(update_fields=['status', 'approved_by', 'updated_at'])

        # Notify applicant
        Notification.objects.create(
            user=leave_app.applicant,
            sender=user,
            title="Leave Application Approved",
            message=f"Your leave application from {leave_app.from_date.strftime('%d-%m-%Y')} to {leave_app.to_date.strftime('%d-%m-%Y')} has been approved by HOD.",
            notification_type='LEAVE_STATUS',
            related_leave=leave_app,
            created_by=user,
            updated_by=user
        )

        Notification.objects.filter(related_leave=leave_app, user=user).update(is_read=True)
        _broadcast_realtime({'leave_id': leave_app.id}, 'leave_updated')

        serializer = self.get_serializer(leave_app)
        return Response({"code": 200, "message": "Leave application approved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject_leave(self, request, pk=None):
        leave_app = self.get_object()
        user = request.user
        reason = request.data.get('rejection_reason', '').strip()

        leave_app.status = 'REJECTED'
        leave_app.rejection_reason = reason
        leave_app.approved_by = user
        leave_app.save(update_fields=['status', 'rejection_reason', 'approved_by', 'updated_at'])

        Notification.objects.create(
            user=leave_app.applicant,
            sender=user,
            title="Leave Application Rejected",
            message=f"Your leave application from {leave_app.from_date.strftime('%d-%m-%Y')} to {leave_app.to_date.strftime('%d-%m-%Y')} was rejected by HOD. Reason: {reason or 'N/A'}",
            notification_type='LEAVE_STATUS',
            related_leave=leave_app,
            created_by=user,
            updated_by=user
        )

        Notification.objects.filter(related_leave=leave_app, user=user).update(is_read=True)
        _broadcast_realtime({'leave_id': leave_app.id}, 'leave_updated')

        serializer = self.get_serializer(leave_app)
        return Response({"code": 200, "message": "Leave application rejected.", "data": serializer.data}, status=status.HTTP_200_OK)


class ClassSubstitutionViewSet(AdminWriteMixin, viewsets.ModelViewSet):
    queryset = ClassSubstitution.objects.all().order_by('-id')
    serializer_class = ClassSubstitutionSerializer
    permission_classes = [ClassSubstitutionPermission]
    model_label = "Class Substitution"

    def get_queryset(self):

        user = self.request.user
        if not user or not user.is_authenticated:
            return ClassSubstitution.objects.none()
        if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False) or (getattr(user, 'role', None) and user.role.role_name.upper() in ['ADMIN', 'ADMINISTRATOR', 'PRINCIPAL', 'VICE_PRINCIPAL', 'HOD']):
            return ClassSubstitution.objects.all().order_by('-id')
        return ClassSubstitution.objects.filter(
            Q(substitute_faculty=user) | Q(original_faculty=user)
        ).order_by('-id')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Substitutions listed successfully", "data": response.data}, status=status.HTTP_200_OK)



    @action(detail=True, methods=['post'], url_path='respond')
    @transaction.atomic
    def respond_substitution(self, request, pk=None):
        sub_obj = self.get_object()
        user = request.user
        action_type = request.data.get('action', '').upper()
        rejection_reason = request.data.get('rejection_reason', '').strip()

        if sub_obj.substitute_faculty != user and not getattr(user, 'is_superuser', False):
            return Response({"code": 403, "message": "You are not authorized to respond to this substitution request."}, status=status.HTTP_403_FORBIDDEN)


        if action_type not in ['ACCEPT', 'REJECT']:
            return Response({"code": 400, "message": "Invalid action. Choose ACCEPT or REJECT."}, status=status.HTTP_400_BAD_REQUEST)

        orig_fac = sub_obj.original_faculty
        sub_fac_name = user.name or user.username


        if action_type == 'ACCEPT':
            sub_obj.status = 'ACCEPTED'
            sub_obj.save(update_fields=['status', 'updated_at'])

            # Send Notification to Original Faculty
            Notification.objects.create(
                user=orig_fac,
                sender=user,
                title="Substitution Accepted",
                message=f"{sub_fac_name} accepted your substitution request for P{sub_obj.period.period_no} on {sub_obj.date.strftime('%d-%m-%Y')}.",
                notification_type='SUBSTITUTION_RESPONSE',
                related_substitution=sub_obj,
                related_leave=sub_obj.leave_application,
                created_by=user,
                updated_by=user
            )

            # Mark associated substitution request notification as read
            Notification.objects.filter(related_substitution=sub_obj, user=user).update(is_read=True)

            # Check if all substitutions for the leave application are accepted
            leave_app = sub_obj.leave_application
            all_subs = leave_app.substitutions.all()
            if all_subs.exists() and all(s.status == 'ACCEPTED' for s in all_subs):
                leave_app.status = 'PENDING_APPROVAL'
                leave_app.save(update_fields=['status', 'updated_at'])

                # Notify Department HOD(s) for final leave approval
                applicant_name = leave_app.applicant.name or leave_app.applicant.username
                sub_lines = []
                for s in all_subs:
                    p_num = s.period.period_no if s.period else 'N/A'
                    sub_fac_name = s.substitute_faculty.name or s.substitute_faculty.username
                    sec_name = s.section.sections if s.section else 'N/A'
                    dept_code = s.department.department_code if s.department else ''
                    sub_lines.append(f"Period {p_num}: Transferred to {sub_fac_name} ({dept_code} Sec {sec_name})")

                sub_summary = "\n".join(sub_lines)
                
                hod_qs = User.objects.filter(
                    Q(hod_departments=leave_app.department) |
                    Q(user_details__department=leave_app.department, role__role_name__iexact='HOD') |
                    Q(role__role_name__iexact='HOD')
                ).distinct()


                for hod in hod_qs:
                    Notification.objects.create(
                        user=hod,
                        sender=leave_app.applicant,
                        title=f"Leave Application Approval Required: {applicant_name}",
                        message=(
                            f"{applicant_name} has requested leave from {leave_app.from_date.strftime('%d-%m-%Y')} "
                            f"to {leave_app.to_date.strftime('%d-%m-%Y')}.\n"
                            f"All class substitutions have been accepted:\n{sub_summary}\n\n"
                            f"Please review and approve this leave application."
                        ),
                        notification_type='LEAVE_APPROVAL_REQUEST',
                        related_leave=leave_app,
                        created_by=user,
                        updated_by=user
                    )
                    _broadcast_realtime({'leave_id': leave_app.id}, 'notification_received', target_user_id=hod.id)

            _broadcast_realtime({'substitution_id': sub_obj.id}, 'substitution_accepted')
            return Response({"code": 200, "message": "Substitution request accepted successfully.", "data": self.get_serializer(sub_obj).data}, status=status.HTTP_200_OK)


        else: # REJECT
            sub_obj.status = 'REJECTED'
            sub_obj.rejection_reason = rejection_reason
            sub_obj.save(update_fields=['status', 'rejection_reason', 'updated_at'])

            Notification.objects.create(
                user=orig_fac,
                sender=user,
                title="Substitution Rejected",
                message=f"{sub_fac_name} rejected your substitution request for P{sub_obj.period.period_no} on {sub_obj.date.strftime('%d-%m-%Y')}. Reason: {rejection_reason or 'N/A'}",
                notification_type='SUBSTITUTION_RESPONSE',
                related_substitution=sub_obj,
                related_leave=sub_obj.leave_application,
                created_by=user,
                updated_by=user
            )

            Notification.objects.filter(related_substitution=sub_obj, user=user).update(is_read=True)

            _broadcast_realtime({'substitution_id': sub_obj.id}, 'substitution_rejected')
            return Response({"code": 200, "message": "Substitution request rejected.", "data": self.get_serializer(sub_obj).data}, status=status.HTTP_200_OK)


    @action(detail=True, methods=['post'], url_path='reassign')
    @transaction.atomic
    def reassign_substitute(self, request, pk=None):
        sub_obj = self.get_object()
        user = request.user
        new_substitute_id = request.data.get('substitute_faculty_id')

        if sub_obj.original_faculty != user and not getattr(user, 'is_superuser', False):
            return Response({"code": 403, "message": "Only the requesting faculty can reassign this substitution."}, status=status.HTTP_403_FORBIDDEN)


        try:
            new_sub_fac = User.objects.get(id=new_substitute_id)
        except User.DoesNotExist:
            return Response({"code": 404, "message": "Selected substitute faculty not found."}, status=status.HTTP_404_NOT_FOUND)

        sub_obj.substitute_faculty = new_sub_fac
        sub_obj.status = 'PENDING'
        sub_obj.rejection_reason = None
        sub_obj.save(update_fields=['substitute_faculty', 'status', 'rejection_reason', 'updated_at'])

        applicant_name = user.name or user.username

        p_time = f"{sub_obj.period.start_time.strftime('%I:%M %p')}"
        notif_msg = (
            f"{applicant_name} has requested you to substitute for Period {sub_obj.period.period_no} ({p_time}) "
            f"on {sub_obj.date.strftime('%d-%m-%Y')} for {sub_obj.department.department_code} (Sec {sub_obj.section.sections})."
        )

        Notification.objects.create(
            user=new_sub_fac,
            sender=user,
            title="Class Substitution Request",
            message=notif_msg,
            notification_type='SUBSTITUTION_REQUEST',
            related_substitution=sub_obj,
            related_leave=sub_obj.leave_application,
            created_by=user,
            updated_by=user
        )

        _broadcast_realtime({'substitution_id': sub_obj.id}, 'notification_received', target_user_id=new_sub_fac.id)
        return Response({"code": 200, "message": "Substitution reassigned successfully.", "data": self.get_serializer(sub_obj).data}, status=status.HTTP_200_OK)


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by('-created_at')
    serializer_class = NotificationSerializer
    permission_classes = [NotificationPermission]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(user=user).order_by('-created_at')

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return Response({"code": 200, "message": "Notifications listed successfully", "data": response.data}, status=status.HTTP_200_OK)



    @action(detail=False, methods=['post'], url_path='mark-read')
    def mark_read(self, request):
        notification_ids = request.data.get('notification_ids', [])
        user = request.user
        if notification_ids:
            Notification.objects.filter(user=user, id__in=notification_ids).update(is_read=True)
        else:
            Notification.objects.filter(user=user).update(is_read=True)
        return Response({"code": 200, "message": "Notifications marked as read."}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        user = request.user
        if not user or not user.is_authenticated:
            return Response({"code": 200, "unread_count": 0}, status=status.HTTP_200_OK)
        cnt = Notification.objects.filter(user=user, is_read=False).count()
        return Response({"code": 200, "unread_count": cnt}, status=status.HTTP_200_OK)


# ─── Custom Helper APIs ───────────────────────────────────────────────────────

class LeaveHelperViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='affected-slots')
    def get_affected_slots(self, request):
        """Fetches class timetable slots taught by logged-in faculty between from_date and to_date."""
        user = request.user
        from_date_str = request.query_params.get('from_date')
        to_date_str = request.query_params.get('to_date')

        if not from_date_str or not to_date_str:
            return Response({"code": 400, "message": "from_date and to_date query parameters are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            d_from = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            d_to = datetime.strptime(to_date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"code": 400, "message": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        slots_data = []
        curr_date = d_from
        while curr_date <= d_to:
            # Determine effective Day Order for curr_date
            cal_evt = AcademicCalendarEvent.objects.filter(date=curr_date).first()
            if cal_evt and cal_evt.event_type in ['HOLIDAY', 'SUSPENSION'] and cal_evt.session_scope == 'FULL_DAY':
                curr_date += timedelta(days=1)
                continue

            day_code = curr_date.strftime('%A').upper()[:3]
            if cal_evt and cal_evt.event_type in ['DAY_ORDER', 'DAY_ORDER_SWAP'] and cal_evt.target_day_code:
                day_code = cal_evt.target_day_code.upper()[:3]

            try:
                day_inst = Day.objects.get(day_code__iexact=day_code)
            except Day.DoesNotExist:
                curr_date += timedelta(days=1)
                continue

            # Query ClassTimetables taught by this faculty on this day
            timetables = ClassTimetable.objects.filter(
                faculty=user,
                day=day_inst
            ).select_related('period', 'department', 'batch', 'semester', 'section', 'subject').order_by('period__period_no')

            for tt in timetables:
                p_time = f"{tt.period.start_time.strftime('%I:%M %p')} - {tt.period.end_time.strftime('%I:%M %p')}"
                slots_data.append({
                    'date': curr_date.strftime('%Y-%m-%d'),
                    'day_id': day_inst.id,
                    'day_code': day_code,
                    'period_id': tt.period.id,
                    'period_no': tt.period.period_no,
                    'period_time': p_time,
                    'department_id': tt.department.id,
                    'department_code': tt.department.department_code,
                    'batch_id': tt.batch.id,
                    'batch_name': tt.batch.batch,
                    'semester_id': tt.semester.id,
                    'section_id': tt.section.id,
                    'section_name': tt.section.sections,
                    'subject_id': tt.subject.id if tt.subject else None,
                    'subject_code': tt.subject.subject_code if tt.subject else '',
                    'subject_name': tt.subject.subject_name if tt.subject else 'Activity',
                    'class_timetable_id': tt.id
                })

            curr_date += timedelta(days=1)

        return Response({"code": 200, "message": "Affected slots fetched successfully.", "data": slots_data}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='available-substitutes')
    def get_available_substitutes(self, request):
        """Lists free faculty members from the SAME department (+ HOD) for a given date, period, and department."""
        user = request.user
        date_str = request.query_params.get('date')
        period_id = request.query_params.get('period_id')
        department_id = request.query_params.get('department_id')

        if not date_str or not period_id or not department_id:
            return Response({"code": 400, "message": "date, period_id, and department_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            period_inst = Period.objects.get(id=period_id)
            dept_inst = Department.objects.get(id=department_id)
        except (ValueError, Period.DoesNotExist, Department.DoesNotExist):
            return Response({"code": 400, "message": "Invalid date, period, or department."}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve day order code for target_date
        cal_evt = AcademicCalendarEvent.objects.filter(date=target_date).first()
        day_code = target_date.strftime('%A').upper()[:3]
        if cal_evt and cal_evt.event_type in ['DAY_ORDER', 'DAY_ORDER_SWAP'] and cal_evt.target_day_code:
            day_code = cal_evt.target_day_code.upper()[:3]

        day_inst = Day.objects.filter(day_code__iexact=day_code).first()

        # Find all faculty/HOD in this department
        dept_faculties = User.objects.filter(
            status='ACTIVE'
        ).filter(
            Q(user_details__department=dept_inst) |
            Q(hod_departments=dept_inst) |
            Q(class_timetables__department=dept_inst)
        ).exclude(id=user.id).distinct()



        # Fallback: if department has no specific assigned users in user_details, get all active FACULTY and HOD users
        if not dept_faculties.exists():
            dept_faculties = User.objects.filter(
                status='ACTIVE',
                role__role_name__in=['FACULTY', 'HOD', 'Faculty', 'Hod']
            ).exclude(id=user.id).distinct()


        # Faculties busy teaching in ClassTimetable during this period
        busy_faculty_ids = []
        if day_inst:
            busy_faculty_ids = list(ClassTimetable.objects.filter(
                day=day_inst,
                period=period_inst
            ).values_list('faculty_id', flat=True))

        # Faculties busy taking an accepted or pending substitution during this period
        busy_substitute_ids = list(ClassSubstitution.objects.filter(
            date=target_date,
            period=period_inst,
            status__in=['PENDING', 'ACCEPTED']
        ).values_list('substitute_faculty_id', flat=True))

        all_busy_ids = set(busy_faculty_ids + busy_substitute_ids)

        available_list = []
        for fac in dept_faculties:
            if fac.id in all_busy_ids:
                continue

            full_name = fac.name or fac.username
            is_hod = fac.hod_departments.filter(id=dept_inst.id).exists()

            available_list.append({
                'id': fac.id,
                'username': fac.username,
                'name': full_name,
                'is_hod': is_hod
            })

        return Response({"code": 200, "message": "Available substitutes fetched.", "data": available_list}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='my-substitute-slots')
    def get_my_substitute_slots(self, request):
        """Returns accepted substitution slots for logged-in faculty for Attendance Entry."""
        user = request.user
        date_str = request.query_params.get('date')

        if not date_str:
            return Response({"code": 400, "message": "date parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return Response({"code": 400, "message": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        subs = ClassSubstitution.objects.filter(
            substitute_faculty=user,
            date=target_date,
            status='ACCEPTED'
        ).select_related('period', 'department', 'batch', 'semester', 'section', 'subject', 'original_faculty')

        results = []
        for s in subs:
            p_time = f"{s.period.start_time.strftime('%I:%M %p')} - {s.period.end_time.strftime('%I:%M %p')}"
            orig_name = s.original_faculty.name or s.original_faculty.username

            results.append({
                'id': s.id,
                'class_timetable_id': s.class_timetable_id,
                'date': s.date.strftime('%Y-%m-%d'),
                'period_id': s.period.id,
                'period_no': s.period.period_no,
                'period_time': p_time,
                'department_id': s.department.id,
                'department_code': s.department.department_code,
                'batch_id': s.batch.id,
                'batch_name': s.batch.batch,
                'semester_id': s.semester.id,
                'section_id': s.section.id,
                'section_name': s.section.sections,
                'subject_id': s.subject.id if s.subject else None,
                'subject_code': s.subject.subject_code if s.subject else '',
                'subject_name': s.subject.subject_name if s.subject else 'Activity',
                'original_faculty_name': orig_name
            })

        return Response({"code": 200, "message": "Substitute slots fetched.", "data": results}, status=status.HTTP_200_OK)
