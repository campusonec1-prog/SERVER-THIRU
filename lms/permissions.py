from users.permissions import BaseRolePermission

class LMSPermission(BaseRolePermission):
    read_roles = ['admin', 'administrator', 'hod', 'faculty', 'student']
    write_roles = ['admin', 'administrator', 'hod', 'faculty']

class AssessmentQuestionPermission(BaseRolePermission):
    """
    Role-based permission for Question Bank / Assessment Questions.
    Allowed roles: admin, hod, faculty, exam_cell.
    """
    read_roles = ['admin', 'administrator', 'hod', 'faculty', 'exam_cell', 'exam cell', 'exam cell member', 'exam_officer']
    write_roles = ['admin', 'administrator', 'hod', 'faculty', 'exam_cell', 'exam cell', 'exam cell member', 'exam_officer']
