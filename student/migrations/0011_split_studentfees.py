"""
Migration: Split students_fees into students_admission_slip + students_fees

Strategy:
1. Create new students_admission_slip table (StudentAdmissionSlip model).
2. Copy admission-only data from existing students_fees rows into
   the new students_admission_slip table (RunPython data migration).
3. Remove admission-only columns from students_fees, leaving only fee columns.
"""

import django.db.models.deletion
from django.db import migrations, models


def migrate_data_forward(apps, schema_editor):
    """Copy admission fields from old StudentFees rows into new StudentAdmissionSlip rows."""
    with schema_editor.connection.cursor() as cursor:
        # Read all existing rows from students_fees (which still has all columns at this
        # point — RemoveField operations come AFTER this RunPython in the migration).
        cursor.execute("""
            SELECT
                student_id,
                aadhaar_number, emis_number, umis_number,
                qualification, community,
                marks_maths, marks_physics, marks_chemistry, marks_total, marks_percentage,
                mode_of_admission, certificates_surrendered,
                recommendation_id,
                created_at, updated_at, created_by, updated_by
            FROM students_fees
        """)
        rows = cursor.fetchall()

        for row in rows:
            (
                student_id,
                aadhaar_number, emis_number, umis_number,
                qualification, community,
                marks_maths, marks_physics, marks_chemistry, marks_total, marks_percentage,
                mode_of_admission, certificates_surrendered,
                recommendation_id,
                created_at, updated_at, created_by, updated_by,
            ) = row

            cursor.execute("""
                INSERT INTO students_admission_slip (
                    student_id,
                    aadhaar_number, emis_number, umis_number,
                    qualification, community,
                    marks_maths, marks_physics, marks_chemistry, marks_total, marks_percentage,
                    mode_of_admission, certificates_surrendered,
                    recommendation_id,
                    created_at, updated_at, created_by, updated_by
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """, [
                student_id,
                aadhaar_number, emis_number, umis_number,
                qualification, community,
                marks_maths, marks_physics, marks_chemistry, marks_total, marks_percentage,
                mode_of_admission, certificates_surrendered,
                recommendation_id,
                created_at, updated_at, created_by, updated_by,
            ])


def migrate_data_backward(apps, schema_editor):
    """Reverse: copy admission data back to students_fees columns (best-effort, MySQL-compatible)."""
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            UPDATE students_fees sf
            INNER JOIN students_admission_slip sa ON sf.student_id = sa.student_id
            SET
                sf.aadhaar_number = sa.aadhaar_number,
                sf.emis_number = sa.emis_number,
                sf.umis_number = sa.umis_number,
                sf.qualification = sa.qualification,
                sf.community = sa.community,
                sf.marks_maths = sa.marks_maths,
                sf.marks_physics = sa.marks_physics,
                sf.marks_chemistry = sa.marks_chemistry,
                sf.marks_total = sa.marks_total,
                sf.marks_percentage = sa.marks_percentage,
                sf.mode_of_admission = sa.mode_of_admission,
                sf.certificates_surrendered = sa.certificates_surrendered,
                sf.recommendation_id = sa.recommendation_id
        """)


class Migration(migrations.Migration):

    dependencies = [
        ('student', '0010_studentfees_books_fees_paid_and_more'),
        ('users', '0007_userdetails_user_image'),
    ]

    operations = [
        # ── 1. Create the new students_admission_slip table ──────────────
        migrations.CreateModel(
            name='StudentAdmissionSlip',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('aadhaar_number', models.CharField(blank=True, max_length=20, null=True)),
                ('emis_number', models.CharField(blank=True, max_length=50, null=True)),
                ('umis_number', models.CharField(blank=True, max_length=50, null=True)),
                ('qualification', models.CharField(blank=True, max_length=50, null=True)),
                ('community', models.CharField(blank=True, max_length=50, null=True)),
                ('marks_maths', models.IntegerField(blank=True, null=True)),
                ('marks_physics', models.IntegerField(blank=True, null=True)),
                ('marks_chemistry', models.IntegerField(blank=True, null=True)),
                ('marks_total', models.IntegerField(blank=True, null=True)),
                ('marks_percentage', models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
                ('mode_of_admission', models.CharField(default='I Sem', max_length=50)),
                ('certificates_surrendered', models.JSONField(default=dict)),
                ('student', models.OneToOneField(
                    db_column='student_id',
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='admission_slip',
                    to='student.student',
                )),
                ('recommendation', models.ForeignKey(
                    blank=True,
                    db_column='recommendation_id',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='recommended_students',
                    to='users.user',
                )),
                ('created_by', models.ForeignKey(
                    blank=True,
                    db_column='created_by',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='student_studentadmissionslip_created',
                    to='users.user',
                )),
                ('updated_by', models.ForeignKey(
                    blank=True,
                    db_column='updated_by',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='student_studentadmissionslip_updated',
                    to='users.user',
                )),
            ],
            options={
                'db_table': 'students_admission_slip',
            },
        ),

        # ── 2. Migrate existing data from students_fees into new table ───
        migrations.RunPython(migrate_data_forward, migrate_data_backward),

        # ── 3. Remove admission-only columns from students_fees ──────────
        migrations.RemoveField(model_name='studentfees', name='aadhaar_number'),
        migrations.RemoveField(model_name='studentfees', name='emis_number'),
        migrations.RemoveField(model_name='studentfees', name='umis_number'),
        migrations.RemoveField(model_name='studentfees', name='qualification'),
        migrations.RemoveField(model_name='studentfees', name='community'),
        migrations.RemoveField(model_name='studentfees', name='marks_maths'),
        migrations.RemoveField(model_name='studentfees', name='marks_physics'),
        migrations.RemoveField(model_name='studentfees', name='marks_chemistry'),
        migrations.RemoveField(model_name='studentfees', name='marks_total'),
        migrations.RemoveField(model_name='studentfees', name='marks_percentage'),
        migrations.RemoveField(model_name='studentfees', name='mode_of_admission'),
        migrations.RemoveField(model_name='studentfees', name='certificates_surrendered'),
        migrations.RemoveField(model_name='studentfees', name='recommendation'),
    ]
