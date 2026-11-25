from django.db.models.signals import post_save
from django.dispatch import receiver
from student.models import Student
from users.models import User
from .models import LibraryMember


@receiver(post_save, sender=Student)
def auto_create_student_library_code(sender, instance, created, **kwargs):
    try:
        # Determine student active status
        student_active = True
        if instance.status:
            if not getattr(instance.status, 'is_active', True):
                student_active = False
            elif getattr(instance.status, 'status_name', '').upper() in ['INACTIVE', 'DISCONTINUED', 'TERMINATED', 'CANCELLED', 'DROPPED', 'SUSPENDED', 'PASSED_OUT', 'ALUMNI']:
                student_active = False

        user_obj = None
        if instance.roll_number:
            user_obj = User.objects.filter(username__iexact=instance.roll_number).first()
        if not user_obj and instance.register_number:
            user_obj = User.objects.filter(username__iexact=instance.register_number).first()

        if user_obj and not getattr(user_obj, 'is_active', True):
            student_active = False

        member = LibraryMember.objects.filter(student=instance).first()
        if not member:
            code = LibraryMember.generate_code_for_student(instance)
            LibraryMember.objects.create(
                student=instance,
                user=user_obj,
                member_type='STUDENT',
                membership_number=code,
                is_active=student_active,
            )
        else:
            fields_to_update = []
            if member.is_active != student_active:
                member.is_active = student_active
                fields_to_update.append('is_active')
            if user_obj and member.user != user_obj:
                member.user = user_obj
                fields_to_update.append('user')
            if fields_to_update:
                fields_to_update.append('updated_at')
                member.save(update_fields=fields_to_update)
    except Exception:
        pass


@receiver(post_save, sender=User)
def auto_create_user_library_code(sender, instance, created, **kwargs):
    try:
        user_active = bool(getattr(instance, 'is_active', True))
        role_name = getattr(instance.role, 'role_name', '').upper() if getattr(instance, 'role', None) else ''
        matching_student = Student.objects.filter(roll_number__iexact=instance.username).first()
        if not matching_student:
            matching_student = Student.objects.filter(register_number__iexact=instance.username).first()

        if role_name == 'STUDENT' or matching_student:
            if matching_student:
                stu_active = user_active
                if matching_student.status:
                    if not getattr(matching_student.status, 'is_active', True):
                        stu_active = False
                    elif getattr(matching_student.status, 'status_name', '').upper() in ['INACTIVE', 'DISCONTINUED', 'TERMINATED', 'CANCELLED', 'DROPPED', 'SUSPENDED', 'PASSED_OUT', 'ALUMNI']:
                        stu_active = False

                member = LibraryMember.objects.filter(student=matching_student).first()
                if member:
                    fields = []
                    if member.user != instance:
                        member.user = instance
                        fields.append('user')
                    if member.is_active != stu_active:
                        member.is_active = stu_active
                        fields.append('is_active')
                    if fields:
                        fields.append('updated_at')
                        member.save(update_fields=fields)
                    return
                else:
                    code = LibraryMember.generate_code_for_student(matching_student)
                    LibraryMember.objects.create(
                        student=matching_student,
                        user=instance,
                        member_type='STUDENT',
                        membership_number=code,
                        is_active=stu_active,
                    )
                    return

        # Otherwise staff/faculty user
        member = LibraryMember.objects.filter(user=instance).first()
        if not member:
            code = LibraryMember.generate_code_for_user(instance)
            LibraryMember.objects.create(
                user=instance,
                member_type='STAFF',
                membership_number=code,
                is_active=user_active,
            )
        else:
            if member.is_active != user_active:
                member.is_active = user_active
                member.save(update_fields=['is_active', 'updated_at'])
    except Exception:
        pass
