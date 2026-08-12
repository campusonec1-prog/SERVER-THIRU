from users.permissions import BaseRolePermission

# ─── Public Read, Admin/HOD/Principal Write ───────────────────

class ProgramPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class DepartmentPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class AcademicYearPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


# ─── Authenticated Read, Admin/HOD/Principal Write ────────────

class BatchPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class RegulationPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class SemesterPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class SectionPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class CollegeHeaderPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class ExamTypePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class ExamPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class QuotaPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']


class FeesStructurePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal']
