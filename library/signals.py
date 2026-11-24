from django.db.models.signals import post_save
from django.dispatch import receiver
from student.models import Student
from users.models import User
from .models import LibraryMember


@receiver(post_save, sender=Student)
def auto_create_student_library_code(sender, instance, created, **kwargs):
    try:
        member = LibraryMember.objects.filter(student=instance).first()
        if not member:
            code = LibraryMember.generate_code_for_student(instance)
            # Check if user exists matching roll_number or register_number
            user_obj = None
            if instance.roll_number:
                user_obj = User.objects.filter(username__iexact=instance.roll_number).first()
            if not user_obj and instance.register_number:
                user_obj = User.objects.filter(username__iexact=instance.register_number).first()
            
            LibraryMember.objects.create(
                student=instance,
                user=user_obj,
                member_type='STUDENT',
                membership_number=code,
                is_active=True,
            )
        else:
            if not member.user:
                user_obj = None
                if instance.roll_number:
                    user_obj = User.objects.filter(username__iexact=instance.roll_number).first()
                if not user_obj and instance.register_number:
                    user_obj = User.objects.filter(username__iexact=instance.register_number).first()
                if user_obj:
                    member.user = user_obj
                    member.save(update_fields=['user', 'updated_at'])
    except Exception:
        pass


@receiver(post_save, sender=User)
def auto_create_user_library_code(sender, instance, created, **kwargs):
    try:
        # Check if user is a student (by role or matching roll/register number)
        role_name = getattr(instance.role, 'role_name', '').upper() if getattr(instance, 'role', None) else ''
        matching_student = Student.objects.filter(roll_number__iexact=instance.username).first()
        if not matching_student:
            matching_student = Student.objects.filter(register_number__iexact=instance.username).first()

        if role_name == 'STUDENT' or matching_student:
            if matching_student:
                member = LibraryMember.objects.filter(student=matching_student).first()
                if member:
                    if member.user != instance:
                        member.user = instance
                        member.save(update_fields=['user', 'updated_at'])
                    return
                else:
                    code = LibraryMember.generate_code_for_student(matching_student)
                    LibraryMember.objects.create(
                        student=matching_student,
                        user=instance,
                        member_type='STUDENT',
                        membership_number=code,
                        is_active=True,
                    )
                    return

        # Otherwise staff/faculty user
        if not LibraryMember.objects.filter(user=instance).exists():
            code = LibraryMember.generate_code_for_user(instance)
            LibraryMember.objects.create(
                user=instance,
                member_type='STAFF',
                membership_number=code,
                is_active=True,
            )
    except Exception:
        pass
