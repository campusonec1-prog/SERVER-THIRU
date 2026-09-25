import django.db.models.deletion
from django.db import migrations, models


def populate_application_for_students(apps, schema_editor):
    Student = apps.get_model('student', 'Student')
    Application = apps.get_model('dynamic_forms', 'Application')
    ApplicationStatus = apps.get_model('dynamic_forms', 'ApplicationStatus')
    ApplicationUser = apps.get_model('dynamic_forms', 'ApplicationUser')

    default_status = (
        ApplicationStatus.objects.filter(status_name__iexact='Approved').first() or
        ApplicationStatus.objects.filter(status_name__iexact='Submitted').first() or
        ApplicationStatus.objects.first()
    )

    for student in Student.objects.all():
        user_id = getattr(student, 'user_id', None)
        if user_id:
            app = Application.objects.filter(candidate_id=user_id).first()
            if not app:
                cand = ApplicationUser.objects.filter(id=user_id).first()
                if cand:
                    dept = getattr(student, 'department', None)
                    prog = dept.program if dept else None
                    app_no = f"APP-{student.roll_number or student.register_number or student.id}"
                    app = Application.objects.create(
                        candidate=cand,
                        program=prog,
                        application_no=app_no,
                        status=default_status,
                        form_data={'personal_details': {'candidate_name': cand.name, 'phone': getattr(cand, 'phone_number', '')}},
                        payment_status='PAID',
                        paid_amount=1050.00
                    )
            if app:
                student.application = app
                student.save(update_fields=['application'])


class Migration(migrations.Migration):

    dependencies = [
        ('student', '0023_hostelvisitorlog'),
        ('dynamic_forms', '0010_application_paid_amount_application_paid_at_and_more'),
    ]

    operations = [
        # 1. Add application field with null=True
        migrations.AddField(
            model_name='student',
            name='application',
            field=models.OneToOneField(
                blank=True,
                db_column='application_id',
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='student',
                to='dynamic_forms.application'
            ),
        ),
        # 2. Populate application for all existing students
        migrations.RunPython(populate_application_for_students, reverse_code=migrations.RunPython.noop),
        # 3. Remove index on user
        migrations.RemoveIndex(
            model_name='student',
            name='students_user_id_b061ff_idx',
        ),
        # 4. Remove user field
        migrations.RemoveField(
            model_name='student',
            name='user',
        ),
        # 5. Make application field non-nullable
        migrations.AlterField(
            model_name='student',
            name='application',
            field=models.OneToOneField(
                db_column='application_id',
                on_delete=django.db.models.deletion.CASCADE,
                related_name='student',
                to='dynamic_forms.application'
            ),
        ),
        # 6. Add index on application
        migrations.AddIndex(
            model_name='student',
            index=models.Index(fields=['application'], name='students_applica_idx'),
        ),
    ]
