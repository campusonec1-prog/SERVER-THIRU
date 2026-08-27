from users.permissions import BaseRolePermission

class ExamTimetablePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'exam cell', 'exam cell member']


class ClassTimetablePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['hod']


class ActivityTypePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod']
