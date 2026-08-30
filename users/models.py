from django.core.validators import RegexValidator
from django.db import models
from common.models import TrackingModel

class UserStatus(models.TextChoices):
    ACTIVE = 'ACTIVE', 'Active'
    INACTIVE = 'INACTIVE', 'Inactive'
    LEFT = 'LEFT', 'Left / Relieved'
    SUSPENDED = 'SUSPENDED', 'Suspended'
    ON_LEAVE = 'ON_LEAVE', 'On Leave'

class User(TrackingModel):
    name = models.CharField(max_length=150)
    username = models.CharField(max_length=150, unique=True)
    password = models.CharField(max_length=128)
    mobile_number = models.CharField(
        max_length=15,
        validators=[RegexValidator(r'^\d{10}$', message='Mobile number must be exactly 10 digits.')]
    )
    mail = models.EmailField(unique=True)
    role = models.ForeignKey('role.Role', on_delete=models.CASCADE, db_column='role_id', related_name='users')
    status = models.CharField(
        max_length=30,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
        db_index=True
    )

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.name} ({self.username})"

    @property
    def is_authenticated(self):
        return True

    @property
    def is_superuser(self):
        if hasattr(self, 'role') and self.role and getattr(self.role, 'role_name', None):
            return self.role.role_name.upper() in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN']
        return False

    @property
    def is_staff(self):
        return self.is_superuser



class UserDetails(TrackingModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column='user_id',
        related_name='user_details'
    )
    faculty_code = models.CharField(max_length=50, unique=True)
    qualification = models.CharField(max_length=150)
    designation = models.CharField(max_length=100)
    date_of_joining = models.DateField()
    gender = models.CharField(max_length=20)
    user_image = models.CharField(max_length=500, blank=True, null=True)
    dob = models.DateField(null=True, blank=True)
    department = models.ForeignKey(
        'institution.Department',
        on_delete=models.SET_NULL,
        db_column='department_id',
        related_name='user_details',
        null=True,
        blank=True
    )

    class Meta:
        db_table = 'user_details'

    def __str__(self):
        return f"{self.user.name} - {self.faculty_code}"

