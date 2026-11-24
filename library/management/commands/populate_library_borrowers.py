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
        # Code format: [Department Shortname][3-digit sequence] e.g. CSE001, MECH003, CIVIL168
        students = Student.objects.select_related('department').order_by('department_id', 'roll_number', 'id')
        dept_counters = defaultdict(int)

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

                dept_counters[dept_short] += 1
                seq = dept_counters[dept_short]
                code = f"{dept_short}{seq:03d}"

                member, created = LibraryMember.objects.get_or_create(
                    student=student,
                    defaults={
                        'member_type': 'STUDENT',
                        'membership_number': code,
                        'is_active': True,
                        'joined_on': timezone.localdate(),
                    }
                )

                if created:
                    student_created += 1
                else:
                    member.member_type = 'STUDENT'
                    member.membership_number = code
                    member.is_active = True
                    member.save(update_fields=['member_type', 'membership_number', 'is_active', 'updated_at'])
                    student_updated += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {len(students)} students: {student_created} created, {student_updated} updated with department codes."
        ))

        # 2. Process Staff / Other Roles (Faculty, HOD, Admin, etc.)
        # Code format: [First 4 digits of username][3-digit sequence] e.g. 2656001
        users = User.objects.order_by('username', 'id')
        user_prefix_counters = defaultdict(int)

        user_created = 0
        user_updated = 0

        with transaction.atomic():
            for user in users:
                raw_username = re.sub(r'[^A-Za-z0-9]', '', str(user.username or '')).upper()
                if len(raw_username) >= 4:
                    prefix = raw_username[:4]
                elif len(raw_username) > 0:
                    prefix = raw_username.ljust(4, '0')
                else:
                    prefix = f"U{user.id:03d}"[:4]

                user_prefix_counters[prefix] += 1
                seq = user_prefix_counters[prefix]
                code = f"{prefix}{seq:03d}"

                member, created = LibraryMember.objects.get_or_create(
                    user=user,
                    defaults={
                        'member_type': 'STAFF',
                        'membership_number': code,
                        'is_active': True,
                        'joined_on': timezone.localdate(),
                    }
                )

                if created:
                    user_created += 1
                else:
                    member.member_type = 'STAFF'
                    member.membership_number = code
                    member.is_active = True
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
