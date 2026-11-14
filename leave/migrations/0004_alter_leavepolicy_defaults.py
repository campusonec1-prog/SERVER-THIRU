# Generated for leave policy defaults

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leave', '0003_classsubstitution_class_subst_substit_405fc5_idx_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='leavepolicy',
            name='total_cl',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='leavepolicy',
            name='total_od',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name='leavepolicy',
            name='total_permissions',
            field=models.PositiveIntegerField(default=0),
        ),
    ]

