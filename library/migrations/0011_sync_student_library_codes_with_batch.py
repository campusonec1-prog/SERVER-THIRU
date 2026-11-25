import re
from django.db import migrations


def sync_batch_codes(apps, schema_editor):
    LibraryMember = apps.get_model('library', 'LibraryMember')
    student_members = LibraryMember.objects.filter(student__isnull=False).select_related(
        'student__batch', 'student__department'
    )

    for member in student_members:
        student = member.student
        if not student:
            continue

        # Extract dept short code
        dept_short = 'STU'
        if student.department:
            if getattr(student.department, 'short_name', None):
                cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.short_name)).upper()
                if cleaned:
                    dept_short = cleaned
            elif getattr(student.department, 'department_code', None):
                cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.department_code)).upper()
                if cleaned:
                    dept_short = cleaned
            elif getattr(student.department, 'department_name', None):
                cleaned = re.sub(r'[^A-Za-z0-9]', '', str(student.department.department_name)).upper()
                if cleaned:
                    dept_short = cleaned[:4]

        # Extract 2-digit batch prefix
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

        if not batch_prefix and getattr(student, 'roll_number', None):
            r_str = str(student.roll_number).strip()
            m_year = re.match(r'^(?:20)?(\d{2})', r_str)
            if m_year:
                batch_prefix = m_year.group(1)

        if not batch_prefix and getattr(student, 'register_number', None):
            reg_str = str(student.register_number).strip()
            m_reg = re.match(r'^\d{4}(\d{2})\d+', reg_str)
            if m_reg:
                batch_prefix = m_reg.group(1)

        if not batch_prefix:
            continue

        expected_prefix = f"{batch_prefix}{dept_short}"
        current_code = str(member.membership_number or '').strip().upper()

        if not current_code.startswith(expected_prefix):
            num_match = re.search(r'(\d+)$', current_code)
            num_val = int(num_match.group(1)) if num_match else 1
            new_code = f"{expected_prefix}{num_val:03d}"

            if LibraryMember.objects.filter(membership_number=new_code).exclude(id=member.id).exists():
                existing = set(
                    LibraryMember.objects.filter(membership_number__startswith=expected_prefix)
                    .exclude(id=member.id)
                    .values_list('membership_number', flat=True)
                )
                seq = 1
                while f"{expected_prefix}{seq:03d}" in existing:
                    seq += 1
                new_code = f"{expected_prefix}{seq:03d}"

            member.membership_number = new_code
            member.save(update_fields=['membership_number'])


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('library', '0010_libraryreservation'),
    ]

    operations = [
        migrations.RunPython(sync_batch_codes, reverse_noop),
    ]
