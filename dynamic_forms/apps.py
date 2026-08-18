from django.apps import AppConfig


class DynamicFormsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dynamic_forms'

    def ready(self):
        # Avoid querying database during migrations or tests to prevent startup warnings/errors
        import sys
        ignored_cmds = {'migrate', 'makemigrations', 'test', 'collectstatic', 'check', 'showmigrations'}
        if any(cmd in sys.argv for cmd in ignored_cmds):
            return

        # Run self-healing department sync on startup
        try:
            self.sync_application_departments()
        except Exception:
            pass

    def sync_application_departments(self):
        try:
            from dynamic_forms.models import Application
            from institution.models import Department
            
            departments = list(Department.objects.all())
            if not departments:
                return
                
            apps = Application.objects.all()
            for app in apps:
                form_data = app.form_data or {}
                course_sel = form_data.get('course_selection', {})
                dept_name = course_sel.get('department')
                if dept_name:
                    exact_match = any(d.department_name == dept_name for d in departments)
                    if exact_match:
                        continue
                    
                    matched_dept = None
                    # Map legacy "Computer Science Engineering Updated" name
                    if dept_name == "Computer Science Engineering Updated":
                        matched_dept = next((d for d in departments if d.department_name == "Computer Science Engineering"), None)
                    
                    if not matched_dept:
                        # Attempt to find closest match under the same program
                        prog_depts = [d for d in departments if d.program_id == app.program_id]
                        for d in prog_depts:
                            if d.department_name.lower() in dept_name.lower() or dept_name.lower() in d.department_name.lower():
                                matched_dept = d
                                break
                            if d.short_name.lower() in dept_name.lower() or dept_name.lower() in d.short_name.lower():
                                matched_dept = d
                                break
                                
                    if matched_dept and matched_dept.department_name != dept_name:
                        course_sel['department'] = matched_dept.department_name
                        form_data['course_selection'] = course_sel
                        app.form_data = form_data
                        app.save(update_fields=['form_data'])
                        print(f"[Self-Healing Sync] Updated application {app.application_no} department from '{dept_name}' to '{matched_dept.department_name}'.")
        except Exception as e:
            # Silent fallback during migrations or db setup
            pass
