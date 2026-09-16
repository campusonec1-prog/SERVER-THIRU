import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('student', '0023_hostelvisitorlog'),
        ('users', '0010_alter_user_status'),
    ]

    operations = [
        migrations.CreateModel(
            name='LibraryBook',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=255)),
                ('author', models.CharField(max_length=200)),
                ('isbn', models.CharField(blank=True, max_length=20, null=True)),
                ('category', models.CharField(blank=True, max_length=100)),
                ('publisher', models.CharField(blank=True, max_length=200)),
                ('shelf_location', models.CharField(blank=True, max_length=100)),
                ('total_copies', models.PositiveIntegerField(default=1, validators=[django.core.validators.MinValueValidator(1)])),
                ('available_copies', models.PositiveIntegerField(default=1)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_librarybook_created', to='users.user')),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_librarybook_updated', to='users.user')),
            ],
            options={'db_table': 'library_books', 'ordering': ['title', 'author']},
        ),
        migrations.CreateModel(
            name='LibraryMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('membership_number', models.CharField(max_length=50, unique=True)),
                ('joined_on', models.DateField(default=django.utils.timezone.now)),
                ('is_active', models.BooleanField(default=True)),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_librarymember_created', to='users.user')),
                ('student', models.OneToOneField(db_column='student_id', on_delete=django.db.models.deletion.CASCADE, related_name='library_membership', to='student.student')),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_librarymember_updated', to='users.user')),
            ],
            options={'db_table': 'library_members', 'ordering': ['membership_number']},
        ),
        migrations.CreateModel(
            name='LibraryTransaction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('issued_on', models.DateField(default=django.utils.timezone.now)),
                ('due_on', models.DateField()),
                ('returned_on', models.DateField(blank=True, null=True)),
                ('renewal_count', models.PositiveIntegerField(default=0)),
                ('status', models.CharField(choices=[('ISSUED', 'Issued'), ('RETURNED', 'Returned'), ('OVERDUE', 'Overdue')], default='ISSUED', max_length=20)),
                ('notes', models.TextField(blank=True)),
                ('book', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='library.librarybook')),
                ('created_by', models.ForeignKey(blank=True, db_column='created_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_librarytransaction_created', to='users.user')),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='transactions', to='library.librarymember')),
                ('updated_by', models.ForeignKey(blank=True, db_column='updated_by', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='library_librarytransaction_updated', to='users.user')),
            ],
            options={'db_table': 'library_transactions', 'ordering': ['-issued_on', '-id']},
        ),
    ]
