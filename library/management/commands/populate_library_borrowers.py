import re
from collections import defaultdict
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from library.models import LibraryMember
from student.models import Student
from users.models import User


class Command(BaseCommand):
    help = 'Populate and generate unique library codes for all Students and Staff/Users'

    def handle(self, *args, **options):
        self.stdout.write("Starting generation of unique library codes for all users and students...")

        # 1. Process Students
        # Code format: [Batch 2-digits][Department Shortname][3-digit sequence] e.g. 23IT001, 25CSE001
        students = Student.objects.select_related('department', 'batch').order_by('batch_id', 'department_id', 'roll_number', 'id')
        batch_dept_counters = defaultdict(int)

        student_created = 0
        student_updated = 0

        with transaction.atomic():
            for student in students:
                dept_short = 'STU'
                if student.department and student.department.short_name:
                    cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.short_name)).upper()
                    if cleaned:
                        dept_short = cleaned
                elif student.department and student.department.department_code:
                    cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.department_code)).upper()
                    if cleaned:
                        dept_short = cleaned

                batch_prefix = ''
                if getattr(student, 'batch', None) and getattr(student.batch, 'batch', None):
                    batch_str = str(student.batch.batch).strip()
                    match = re.search(r'(\d{4})', batch_str)
                    if match:
                        batch_prefix = match.group(1)[-2:]
                    else:
                        m2 = re.search(r'(\d{2})', batch_str)
                        if m2:
                            batch_prefix = m2.group(1)

                full_prefix = f"{batch_prefix}{dept_short}"
                batch_dept_counters[full_prefix] += 1
                seq = batch_dept_counters[full_prefix]
                code = f"{full_prefix}{seq:03d}"

                student_active = True
                if student.status:
                    if not getattr(student.status, 'is_active', True):
                        student_active = False
                    elif getattr(student.status, 'status_name', '').upper() in ['INACTIVE', 'DISCONTINUED', 'TERMINATED', 'CANCELLED', 'DROPPED', 'SUSPENDED', 'PASSED_OUT', 'ALUMNI']:
                        student_active = False

                user_obj = None
                if student.roll_number:
                    user_obj = User.objects.filter(username__iexact=student.roll_number).first()
                if not user_obj and student.register_number:
                    user_obj = User.objects.filter(username__iexact=student.register_number).first()

                if user_obj and not getattr(user_obj, 'is_active', True):
                    student_active = False

                member, created = LibraryMember.objects.get_or_create(
                    student=student,
                    defaults={
                        'user': user_obj,
                        'member_type': 'STUDENT',
                        'membership_number': code,
                        'is_active': student_active,
                        'joined_on': timezone.localdate(),
                    }
                )

                if created:
                    student_created += 1
                else:
                    member.member_type = 'STUDENT'
                    member.membership_number = code
                    member.is_active = student_active
                    if user_obj and member.user != user_obj:
                        member.user = user_obj
                    member.save(update_fields=['member_type', 'membership_number', 'is_active', 'user', 'updated_at'])
                    student_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {len(students)} students: {student_created} created, {student_updated} updated with batch department codes (e.g. 23IT001) and active status synced."
        ))

        # 2. Process Staff / Other Roles (Faculty, HOD, Admin, etc.)
        # Code format: [First 4 digits of username][3-digit sequence] e.g. 2656001
        student_rolls = set(Student.objects.filter(roll_number__isnull=False).values_list('roll_number', flat=True))
        student_regs = set(Student.objects.filter(register_number__isnull=False).values_list('register_number', flat=True))
        student_usernames = {str(x).strip().upper() for x in (student_rolls | student_regs) if x}

        users = User.objects.order_by('username', 'id')
        user_prefix_counters = defaultdict(int)

        user_created = 0
        user_updated = 0

        with transaction.atomic():
            for user in users:
                raw_username = str(user.username or '').strip().upper()
                # If this user belongs to a student, link to student's LibraryMember record instead of creating duplicate
                if raw_username in student_usernames or getattr(getattr(user, 'role', None), 'role_name', '').upper() == 'STUDENT':
                    matching_member = LibraryMember.objects.filter(
                        Q(student__roll_number__iexact=user.username) |
                        Q(student__register_number__iexact=user.username)
                    ).first()
                    if matching_member and matching_member.user != user:
                        matching_member.user = user
                        matching_member.save(update_fields=['user', 'updated_at'])
                    continue

                clean_user = re.sub(r'[^A-Za-z0-9]', '', raw_username)
                if len(clean_user) >= 4:
                    prefix = clean_user[:4]
                elif len(clean_user) > 0:
                    prefix = clean_user.ljust(4, '0')
                else:
                    prefix = f"U{user.id:03d}"[:4]

                user_prefix_counters[prefix] += 1
                seq = user_prefix_counters[prefix]
                code = f"{prefix}{seq:03d}"
                user_active = bool(getattr(user, 'is_active', True))

                member, created = LibraryMember.objects.get_or_create(
                    user=user,
                    defaults={
                        'member_type': 'STAFF',
                        'membership_number': code,
                        'is_active': user_active,
                        'joined_on': timezone.localdate(),
                    }
                )

                if created:
                    user_created += 1
                else:
                    member.member_type = 'STAFF'
                    member.membership_number = code
                    member.is_active = user_active
                    member.save(update_fields=['member_type', 'membership_number', 'is_active', 'updated_at'])
                    user_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {len(users)} staff/users: {user_created} created, {user_updated} updated with username codes."
        ))

        total_members = LibraryMember.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Done! Total library borrowers/members saved in database: {total_members}"
        ))

        self.stdout.write("\nSample Student Codes:")
        for m in LibraryMember.objects.filter(member_type='STUDENT').select_related('student', 'student__department')[:10]:
            s_name = m.student.student_name or (m.student.application.candidate.name if hasattr(m.student, 'application') and m.student.application and hasattr(m.student.application, 'candidate') else '')
            dept = m.student.department.short_name if m.student.department else ''
            self.stdout.write(f"  {m.membership_number} -> {s_name} (Roll: {m.student.roll_number}, Dept: {dept})")

        self.stdout.write("\nSample Staff/User Codes:")
        for m in LibraryMember.objects.filter(member_type='STAFF').select_related('user', 'user__role')[:10]:
            r_name = m.user.role.role_name if m.user.role else 'STAFF'
            self.stdout.write(f"  {m.membership_number} -> {m.user.name} (User: {m.user.username}, Role: {r_name})")
