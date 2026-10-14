from django.db import models
from common.models import TrackingModel

class Role(TrackingModel):
    role_id = models.AutoField(primary_key=True)
    role_name = models.CharField(max_length=100, unique=True)
    can_edit_student_profile = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Determines whether users with this role can edit student profiles in Student 360 View"
    )

    class Meta:
        db_table = 'roles'

    def __str__(self):
        return f"{self.role_name} ({self.role_id})"
