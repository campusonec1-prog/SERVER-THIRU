from users.permissions import BaseRolePermission

class ExamTimetablePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'exam cell', 'exam cell member', 'exam_cell', 'exam_officer']


class ClassTimetablePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class ActivityTypePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']
