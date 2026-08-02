from django.core.validators import RegexValidator
from django.db import models
from common.models import TrackingModel

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

    class Meta:
        db_table = 'users'

    def __str__(self):
        return f"{self.name} ({self.username})"

    @property
    def is_authenticated(self):
        return True
