from users.permissions import BaseRolePermission

class LMSPermission(BaseRolePermission):
    read_roles = ['admin', 'administrator', 'hod', 'faculty', 'student']
    write_roles = ['admin', 'administrator', 'hod', 'faculty']

class AssessmentQuestionPermission(BaseRolePermission):
    """
    Role-based permission for Question Bank / Assessment Questions.
    Allowed roles: admin, hod, faculty.
    """
    read_roles = ['admin', 'administrator', 'hod', 'faculty']
    write_roles = ['admin', 'administrator', 'hod', 'faculty']
