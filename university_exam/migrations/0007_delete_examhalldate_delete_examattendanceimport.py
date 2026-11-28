# Generated manually to remove redundant staging and calendar tables

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('university_exam', '0006_remove_examhallallocation_chk_hall_alloc_planned_capacity_and_more'),
    ]

    operations = [
        migrations.DeleteModel(
            name='ExamHallDate',
        ),
        migrations.DeleteModel(
            name='ExamAttendanceImport',
        ),
    ]
