import re
from collections import defaultdict
from django.db import migrations


def populate_borrowers(apps, schema_editor):
    LibraryMember = apps.get_model('library', 'LibraryMember')
    Student = apps.get_model('student', 'Student')
    User = apps.get_model('users', 'User')
    from django.utils import timezone
    today = timezone.localdate()

    # 1. Process Students -> [DeptShortName][3-digit number] e.g. CSE001, MECH003, CIVIL168
    dept_counters = defaultdict(int)
    students = Student.objects.select_related('department').order_by('department_id', 'roll_number', 'id')
    for student in students:
        dept_short = 'STU'
        if student.department and getattr(student.department, 'short_name', None):
            cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.short_name)).upper()
            if cleaned:
                dept_short = cleaned
        elif student.department and getattr(student.department, 'department_code', None):
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
                'joined_on': today,
            }
        )
        if not created and (member.membership_number != code or member.member_type != 'STUDENT'):
            member.member_type = 'STUDENT'
            member.membership_number = code
            member.is_active = True
            member.save(update_fields=['member_type', 'membership_number', 'is_active', 'updated_at'])

    # 2. Process Staff / Other Roles -> [First 4 digits of username][3-digit number] e.g. 2656001
    user_prefix_counters = defaultdict(int)
    users = User.objects.order_by('username', 'id')
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
                'joined_on': today,
            }
        )
        if not created and (member.membership_number != code or member.member_type != 'STAFF'):
            member.member_type = 'STAFF'
            member.membership_number = code
            member.is_active = True
            member.save(update_fields=['member_type', 'membership_number', 'is_active', 'updated_at'])


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('library', '0008_librarymember_member_type_librarymember_user_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_borrowers, reverse_func),
    ]
