from django.db import migrations, models


def set_default_college_code(apps, schema_editor):
    CollegeHeader = apps.get_model('institution', 'CollegeHeader')
    CollegeHeader.objects.all().update(college_code='5132')


class Migration(migrations.Migration):

    dependencies = [
        ('institution', '0024_semesterfeestructure'),
    ]

    operations = [
        migrations.AddField(
            model_name='collegeheader',
            name='college_code',
            field=models.CharField(blank=True, default='5132', max_length=50, null=True),
        ),
        migrations.RunPython(set_default_college_code, reverse_code=migrations.RunPython.noop),
    ]
