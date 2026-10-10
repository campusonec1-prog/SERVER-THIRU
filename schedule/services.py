from datetime import datetime, date
from django.db.models import Q
from .models import Day, Period, AcademicCalendarEvent
from timetable.models import ClassTimetable
from student.models import FacultyActivity


DAY_MAP = {
    0: 'MON',
    1: 'TUE',
    2: 'WED',
    3: 'THU',
    4: 'FRI',
    5: 'SAT',
    6: 'SUN',
}


def resolve_effective_schedule_for_date(target_date, department_id=None, batch_id=None, section_id=None, semester_id=None, academic_year_id=None, faculty_id=None):
    """
    Resolves the effective class schedule for a specific date considering:
    1. Swapped Day Orders (e.g. Saturday following Monday schedule)
    2. Full Day and Partial Day Holidays / Class Suspensions (Rain, Govt, Festival)
    3. Conducted vs Suspended vs Pending Faculty Attendance Status
    """

    if isinstance(target_date, str):
        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

    natural_day_index = target_date.weekday()
    natural_day_code = DAY_MAP.get(natural_day_index, 'MON')

    # Query calendar events for target_date
    events_qs = AcademicCalendarEvent.objects.filter(date=target_date)
    if department_id:
        events_qs = events_qs.filter(Q(department_id__isnull=True) | Q(department_id=department_id))
    if batch_id:
        events_qs = events_qs.filter(Q(batch_id__isnull=True) | Q(batch_id=batch_id))

    events = list(events_qs)

    day_swap_event = next((e for e in events if e.event_type in ['DAY_ORDER', 'DAY_ORDER_SWAP'] and e.target_day), None)

    holiday_event = next((e for e in events if e.event_type in ['HOLIDAY', 'SUSPENSION']), None)

    # Determine effective day code
    effective_day_code = natural_day_code
    is_day_order_swap = False
    swapped_day_name = None

    if day_swap_event and day_swap_event.target_day:
        effective_day_code = day_swap_event.target_day.day_code
        swapped_day_name = day_swap_event.target_day.day_name
        is_day_order_swap = True

    # Determine holiday status
    is_full_day_holiday = False
    holiday_info = None

    if holiday_event:
        holiday_info = {
            'id': holiday_event.id,
            'event_type': holiday_event.event_type,
            'session_scope': holiday_event.session_scope,
            'holiday_category': holiday_event.holiday_category,
            'title': holiday_event.title,
            'reason': holiday_event.reason,
        }
        if holiday_event.session_scope == 'FULL_DAY':
            is_full_day_holiday = True

    # Fetch timetable slots matching effective day code
    timetable_qs = ClassTimetable.objects.filter(
        day__day_code=effective_day_code
    ).select_related(
        'day', 'period', 'department', 'faculty', 'section', 'semester', 'subject', 'batch', 'activity_type'
    )

    if academic_year_id:
        timetable_qs = timetable_qs.filter(academic_year_id=academic_year_id)
    if department_id:
        timetable_qs = timetable_qs.filter(department_id=department_id)
    if batch_id:
        timetable_qs = timetable_qs.filter(batch_id=batch_id)
    if section_id:
        timetable_qs = timetable_qs.filter(section_id=section_id)
    if semester_id:
        timetable_qs = timetable_qs.filter(semester_id=semester_id)
    if faculty_id:
        timetable_qs = timetable_qs.filter(faculty_id=faculty_id)


    # Active batch filter (exclude inactive batches)
    timetable_qs = timetable_qs.filter(
        Q(batch__isnull=True) | Q(batch__is_active=True)
    )

    # Date validity filter
    timetable_qs = timetable_qs.filter(
        Q(from_date__isnull=True) | Q(from_date__lte=target_date),
        Q(to_date__isnull=True) | Q(to_date__gte=target_date)
    ).order_by('period__period_no')

    timetable_slots = list(timetable_qs)

    # Existing faculty activities for this date
    timetable_ids = [t.id for t in timetable_slots]
    activities = FacultyActivity.objects.filter(date=target_date, timetable_id__in=timetable_ids)
    activity_map = {act.timetable_id: act for act in activities}

    # Pre-fetch enrolled student counts by class (department, batch, section)
    from student.models import Student, StudentAttendance
    from django.db.models import Count
    class_students_counts = {
        (row['department_id'], row['batch_id'], row['section_id']): row['count']
        for row in Student.objects.values('department_id', 'batch_id', 'section_id').annotate(count=Count('id'))
    }

    # Pre-fetch student attendance counts for matched activities to ensure real-time accuracy
    attendance_counts_qs = StudentAttendance.objects.filter(
        faculty_activity__in=activities
    ).values('faculty_activity_id', 'status').annotate(count=Count('id'))
    act_counts_map = {}
    for item in attendance_counts_qs:
        a_id = item['faculty_activity_id']
        if a_id not in act_counts_map:
            act_counts_map[a_id] = {'P': 0, 'AB': 0, 'OD': 0, 'TOTAL': 0}
        st_val = item['status']
        cnt_val = item['count']
        act_counts_map[a_id][st_val] = cnt_val
        act_counts_map[a_id]['TOTAL'] += cnt_val

    resolved_slots = []
    periods = list(Period.objects.all().order_by('period_no'))
    max_period = len(periods) if periods else 8

    for slot in timetable_slots:
        period_no = slot.period.period_no
        
        # Scope calculation
        is_suspended = False
        suspension_reason = None

        if is_full_day_holiday:
            is_suspended = True
            suspension_reason = holiday_info['title'] if holiday_info else 'Declared Holiday'
        elif holiday_event:
            scope = holiday_event.session_scope
            if scope == 'FORENOON' and period_no <= (max_period // 2):
                is_suspended = True
                suspension_reason = f"FN Suspended: {holiday_event.title}"
            elif scope == 'AFTERNOON' and period_no > (max_period // 2):
                is_suspended = True
                suspension_reason = f"AN Suspended: {holiday_event.title}"

        activity = activity_map.get(slot.id)

        if activity:
            if activity.status == 'SUSPENDED':
                slot_status = 'SUSPENDED'
                status_reason = activity.suspension_reason or 'Class Suspended'
            elif activity.status == 'CANCELLED':
                slot_status = 'CANCELLED'
                status_reason = activity.remarks or 'Class Cancelled'
            else:
                slot_status = 'CONDUCTED'
                status_reason = None
        elif is_suspended:
            slot_status = 'SUSPENDED'
            status_reason = suspension_reason
        else:
            slot_status = 'PENDING'
            status_reason = 'Attendance pending'

        enrolled_cnt = class_students_counts.get((slot.department_id, slot.batch_id, slot.section_id), 0)
        
        real_counts = act_counts_map.get(activity.id) if activity else None
        if activity and real_counts:
            tot_present = real_counts['P']
            tot_absentees = real_counts['AB']
            tot_od = real_counts['OD']
            tot_students = enrolled_cnt if enrolled_cnt > 0 else (real_counts['TOTAL'] or activity.total_students)
        elif activity:
            tot_present = activity.total_present
            tot_absentees = activity.total_absentees
            tot_od = activity.total_od
            tot_students = enrolled_cnt if enrolled_cnt > 0 else activity.total_students
        else:
            tot_present = 0
            tot_absentees = 0
            tot_od = 0
            tot_students = enrolled_cnt

        att_taken = (slot_status == 'CONDUCTED')
        att_pct = round((tot_present / tot_students * 100), 1) if (tot_students > 0 and att_taken) else 0

        # Faculty display name
        fac_name = slot.faculty.name or slot.faculty.username if slot.faculty else 'Not Assigned'
        fac_code = getattr(slot.faculty, 'faculty_code', '') if slot.faculty else ''

        resolved_slots.append({
            'timetable_id': slot.id,
            'period_id': slot.period.id,
            'period_no': slot.period.period_no,
            'start_time': str(slot.period.start_time),
            'end_time': str(slot.period.end_time),
            'subject_id': slot.subject.id if slot.subject else None,
            'subject_code': slot.subject.subject_code if slot.subject else '—',
            'subject_name': slot.subject.subject_name if slot.subject else (slot.activity_type.activity_name if slot.activity_type else 'Activity'),
            'subject_category': slot.subject_category,
            'faculty_id': slot.faculty.id if slot.faculty else None,
            'faculty_name': fac_name,
            'faculty_code': fac_code,
            'room_no': slot.room_no or '',
            'department_id': slot.department_id,
            'department_name': slot.department.department_name if slot.department else '',
            'department_code': slot.department.department_code if slot.department else '',
            'short_name': slot.department.short_name if slot.department else '',
            'batch_id': slot.batch_id,
            'batch_name': slot.batch.batch if slot.batch else '',
            'section_id': slot.section_id,
            'section_name': slot.section.sections if (slot.section and hasattr(slot.section, 'sections')) else (slot.section.section_name if (slot.section and hasattr(slot.section, 'section_name')) else str(slot.section_id)),
            'semester_id': slot.semester_id,
            'semester_name': slot.semester.semester_name if (slot.semester and hasattr(slot.semester, 'semester_name')) else f"Semester {slot.semester_id}",
            'status': slot_status,
            'status_reason': status_reason,
            'attendance_taken': att_taken,
            'activity_id': activity.id if activity else None,
            'activity_type': activity.activity_type if activity else 'lecture',
            'activity_created_at': activity.created_at.strftime('%d %b %I:%M %p') if (activity and hasattr(activity, 'created_at') and activity.created_at) else None,
            'total_enrolled': enrolled_cnt,
            'total_students': tot_students,
            'total_present': tot_present,
            'total_absentees': tot_absentees,
            'total_od': tot_od,
            'attendance_percentage': att_pct,
            'from_date': str(slot.from_date) if slot.from_date else None,
            'to_date': str(slot.to_date) if slot.to_date else None,
        })

    # Top-level KPI statistics
    total_scheduled = len(resolved_slots)
    total_taken = sum(1 for s in resolved_slots if s['attendance_taken'])
    total_suspended = sum(1 for s in resolved_slots if s['status'] == 'SUSPENDED')
    total_pending = sum(1 for s in resolved_slots if not s['attendance_taken'] and s['status'] != 'SUSPENDED')
    valid_scheduled = max(0, total_scheduled - total_suspended)
    compliance_pct = round((total_taken / valid_scheduled * 100), 1) if valid_scheduled > 0 else 0
    total_present_sum = sum(s['total_present'] for s in resolved_slots if s['attendance_taken'])
    total_enrolled_sum = sum(s['total_students'] for s in resolved_slots if s['attendance_taken'])

    return {
        'date': str(target_date),
        'natural_day': natural_day_code,
        'effective_day': effective_day_code,
        'is_day_order_swap': is_day_order_swap,
        'swapped_day_name': swapped_day_name,
        'is_holiday': is_full_day_holiday,
        'holiday_info': holiday_info,
        'periods': [
            {
                'id': p.id,
                'period_no': p.period_no,
                'start_time': str(p.start_time),
                'end_time': str(p.end_time),
            }
            for p in periods
        ],
        'stats': {
            'total_scheduled': total_scheduled,
            'total_taken': total_taken,
            'total_pending': total_pending,
            'total_suspended': total_suspended,
            'compliance_percentage': compliance_pct,
            'total_present_sum': total_present_sum,
            'total_enrolled_sum': total_enrolled_sum,
        },
        'schedule_slots': resolved_slots
    }
