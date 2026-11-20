import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('student', '0030_bonafidecertificate'),
        ('institution', '0024_semesterfeestructure'),
        ('users', '0013_devicetoken'),
    ]

    operations = [
        migrations.CreateModel(
            name='OuterStudent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('register_number', models.CharField(max_length=50, unique=True)),
                ('student_name', models.CharField(blank=True, max_length=255, null=True)),
                ('batch', models.ForeignKey(blank=True, db_column='batch_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='outer_students', to='institution.batch')),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created', to='users.user')),
                ('department', models.ForeignKey(blank=True, db_column='department_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='outer_students', to='institution.department')),
                ('program', models.ForeignKey(blank=True, db_column='program_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='outer_students', to='institution.program')),
                ('regulation', models.ForeignKey(blank=True, db_column='regulation_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='outer_students', to='institution.regulation')),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated', to='users.user')),
            ],
            options={
                'db_table': 'outer_student',
            },
        ),
    ]
