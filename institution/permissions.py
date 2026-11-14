from users.permissions import BaseRolePermission

# ─── Public Read, Admin/HOD/Principal/Office Write ───────────

class ProgramPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class DepartmentPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class AcademicYearPermission(BaseRolePermission):
    read_roles = ['anyone']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


# ─── Authenticated Read, Admin/HOD/Principal/Office Write ─────

class BatchPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class RegulationPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class SemesterPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class SectionPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class CollegeHeaderPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager']


class ExamTypePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'exam_cell', 'exam cell', 'exam cell member', 'exam_officer', 'office', 'manager']


class ExamPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'exam_cell', 'exam cell', 'exam cell member', 'exam_officer', 'office', 'manager']


class QuotaPermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager', 'tech_supporter', 'administration_officer']


class FeesStructurePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager', 'tech_supporter', 'administration_officer']


class SemesterFeeStructurePermission(BaseRolePermission):
    read_roles = ['authenticated']
    write_roles = ['admin', 'administrator', 'hod', 'principal', 'office', 'manager', 'tech_supporter', 'administration_officer']

