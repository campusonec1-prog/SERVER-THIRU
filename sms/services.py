import os
import re
import json
import logging
import datetime
import requests
from django.conf import settings
from .models import SMSLog

logger = logging.getLogger(__name__)

# Dial4SMS Configuration (Loaded dynamically from settings/.env)
DEFAULT_DIAL4SMS_BASE_URL = getattr(settings, 'DIAL4SMS_BASE_URL', os.getenv('DIAL4SMS_BASE_URL', 'https://smsssl.dial4sms.com/api/v2/SendSMS'))
DEFAULT_API_KEY = getattr(settings, 'DIAL4SMS_API_KEY', os.getenv('DIAL4SMS_API_KEY', ''))
DEFAULT_CLIENT_ID = getattr(settings, 'DIAL4SMS_CLIENT_ID', os.getenv('DIAL4SMS_CLIENT_ID', ''))
DEFAULT_SENDER_ID = getattr(settings, 'DIAL4SMS_SENDER_ID', os.getenv('DIAL4SMS_SENDER_ID', ''))
DEFAULT_FULLDAY_TEMPLATE_ID = getattr(settings, 'DIAL4SMS_FULLDAY_ABSENT_TEMPLATE_ID', os.getenv('DIAL4SMS_FULLDAY_ABSENT_TEMPLATE_ID', ''))
DEFAULT_AFTERNOON_TEMPLATE_ID = getattr(settings, 'DIAL4SMS_AFTERNOON_ABSENT_TEMPLATE_ID', os.getenv('DIAL4SMS_AFTERNOON_ABSENT_TEMPLATE_ID', ''))


def sanitize_phone_number(phone_raw):
    """
    Cleans phone number to standard 10 digits.
    Handles +91, prefixes, spaces, brackets, hyphens.
    """
    if not phone_raw:
        return ''
    cleaned = re.sub(r'[^\d]', '', str(phone_raw).strip())
    if len(cleaned) > 10 and cleaned.startswith('91'):
        cleaned = cleaned[2:]
    if len(cleaned) > 10 and cleaned.startswith('0'):
        cleaned = cleaned.lstrip('0')
    return cleaned if len(cleaned) == 10 else cleaned


def get_student_sms_info(student):
    """
    Extracts student name, reg number, student phone, parent phone, and parent name
    from student record and dynamic application form_data.
    """
    fd = {}
    if student.application and isinstance(student.application.form_data, dict):
        fd = student.application.form_data

    personal = fd.get('personal_information', {}) or fd.get('personal_details', {}) or {}
    parent = fd.get('parent_information', {}) or fd.get('parent_details', {}) or fd.get('guardian_details', {}) or {}

    # Student Name
    cand_name = ''
    if student.application and student.application.candidate:
        cand_name = student.application.candidate.name or ''

    student_name = (
        student.student_name or
        personal.get('applicant_name') or
        personal.get('candidate_name') or
        personal.get('name') or
        cand_name or
        student.name or
        'Student'
    ).strip()

    # Register / Roll number
    reg_no = student.register_number or student.roll_number or ''

    # Candidate user phone
    cand_phone = ''
    if student.application and student.application.candidate:
        cand_phone = student.application.candidate.phone_number or ''

    # Student Mobile
    raw_student_phone = (
        personal.get('student_mobile') or
        personal.get('mobile_number') or
        personal.get('phone_number') or
        cand_phone or
        (student.user.phone_number if student.user else '') or
        ''
    )
    student_phone = sanitize_phone_number(raw_student_phone)

    # Parent Mobile
    raw_parent_phone = (
        parent.get('parent_mobile') or
        parent.get('father_mobile') or
        parent.get('mother_mobile') or
        parent.get('guardian_mobile') or
        parent.get('father_phone') or
        parent.get('mother_phone') or
        parent.get('mobile_number') or
        ''
    )
    parent_phone = sanitize_phone_number(raw_parent_phone)

    # Parent Name
    parent_name = (
        parent.get('parent_name') or
        parent.get('father_name') or
        parent.get('mother_name') or
        parent.get('guardian_name') or
        ''
    ).strip()

    return {
        'student_id': student.id,
        'student_name': student_name,
        'register_number': reg_no,
        'roll_number': student.roll_number or '',
        'department_name': student.department.department_name if student.department else '',
        'department_id': student.department_id,
        'batch_name': student.batch.batch if student.batch else '',
        'batch_id': student.batch_id,
        'section_name': student.section.sections if student.section else '',
        'section_id': student.section_id,
        'student_mobile': student_phone,
        'parent_mobile': parent_phone,
        'parent_name': parent_name,
    }


def format_full_day_absent_message(student_name, absent_date):
    """
    Template:
    Dear Parent, {#var#} is absent today {#var#}. Principal - Thirumalai Engineering College
    """
    if isinstance(absent_date, (datetime.date, datetime.datetime)):
        date_str = absent_date.strftime('%d-%m-%Y')
    else:
        try:
            parsed = datetime.datetime.strptime(str(absent_date).strip(), '%Y-%m-%d')
            date_str = parsed.strftime('%d-%m-%Y')
        except Exception:
            date_str = str(absent_date).strip()

    # DLT Registered Template strictly requires matching text
    message = f"Dear Parent, {student_name} is absent today {date_str}. Principal - Thirumalai Engineering College"
    return message, date_str


def format_afternoon_absent_message(student_name, absent_date):
    """
    Template:
    Dear Parent, {#var#} is absent today Afternoon {#var#}. Principal - Thirumalai Engineering Collge
    """
    if isinstance(absent_date, (datetime.date, datetime.datetime)):
        date_str = absent_date.strftime('%d.%m.%Y')
    else:
        try:
            parsed = datetime.datetime.strptime(str(absent_date).strip(), '%Y-%m-%d')
            date_str = parsed.strftime('%d.%m.%Y')
        except Exception:
            date_str = str(absent_date).strip()

    # DLT Registered Template strictly requires matching text ("Collge" as registered in DLT)
    message = f"Dear Parent, {student_name} is absent today Afternoon {date_str}. Principal - Thirumalai Engineering Collge"
    return message, date_str


def send_dial4sms_single(phone_number, message, template_id=None, sender_id=None):
    """
    Sends SMS using Dial4SMS HTTP API and returns gateway response details.
    """
    api_key = getattr(settings, 'DIAL4SMS_API_KEY', os.getenv('DIAL4SMS_API_KEY', DEFAULT_API_KEY))
    client_id = getattr(settings, 'DIAL4SMS_CLIENT_ID', os.getenv('DIAL4SMS_CLIENT_ID', DEFAULT_CLIENT_ID))
    sender = sender_id or getattr(settings, 'DIAL4SMS_SENDER_ID', os.getenv('DIAL4SMS_SENDER_ID', DEFAULT_SENDER_ID))
    template = template_id or getattr(settings, 'DIAL4SMS_FULLDAY_ABSENT_TEMPLATE_ID', os.getenv('DIAL4SMS_FULLDAY_ABSENT_TEMPLATE_ID', DEFAULT_FULLDAY_TEMPLATE_ID))
    base_url = getattr(settings, 'DIAL4SMS_BASE_URL', os.getenv('DIAL4SMS_BASE_URL', DEFAULT_DIAL4SMS_BASE_URL))

    clean_phone = sanitize_phone_number(phone_number)
    if not clean_phone or len(clean_phone) != 10:
        return {
            'success': False,
            'status': 'FAILED',
            'error': f"Invalid 10-digit mobile number: '{phone_number}'",
            'gateway_response': {'error': 'Invalid mobile number', 'input': str(phone_number)},
            'response_id': None
        }

    params = {
        'SenderId': sender,
        'Message': message,
        'MobileNumbers': clean_phone,
        'TemplateId': template,
        'ApiKey': api_key,
        'ClientId': client_id,
    }

    # Attempt sending via HTTP GET
    try:
        logger.info(f"Sending Dial4SMS to {clean_phone} with template {template}")
        response = requests.get(base_url, params=params, timeout=12)
        status_code = response.status_code
        text_content = response.text

        parsed_json = None
        try:
            parsed_json = response.json()
        except Exception:
            parsed_json = {'raw_text': text_content, 'status_code': status_code}

        response_id = None
        success = False
        error_msg = None

        if isinstance(parsed_json, dict):
            # SendSMS v2 response structure:
            # {"ErrorCode":0,"ErrorDescription":null,"Data":[{"MessageErrorCode":0,"MessageErrorDescription":"Success","MobileNumber":"919876543210","MessageId":"..."}]}
            error_code = parsed_json.get('ErrorCode')
            error_desc = parsed_json.get('ErrorDescription')
            data_list = parsed_json.get('Data')

            if error_code == 0:
                if isinstance(data_list, list) and len(data_list) > 0:
                    first_item = data_list[0]
                    if isinstance(first_item, dict):
                        msg_err = first_item.get('MessageErrorCode')
                        if msg_err == 0:
                            success = True
                            response_id = first_item.get('MessageId')
                        else:
                            error_msg = first_item.get('MessageErrorDescription') or error_desc or 'Gateway rejected message'
                    else:
                        success = True
                else:
                    success = True
            elif error_code is not None:
                error_msg = error_desc or f"Dial4SMS Error Code {error_code}"

        if not success and status_code in [200, 201]:
            lower_text = text_content.lower()
            if 'success' in lower_text or 'submitted' in lower_text or 'queued' in lower_text:
                success = True

        if not success and not error_msg:
            if status_code == 502:
                error_msg = "Dial4SMS Gateway Error (502 Bad Gateway): The SMS provider server is temporarily down or under maintenance."
            elif status_code == 503:
                error_msg = "Dial4SMS Gateway Error (503 Service Unavailable): The SMS provider is currently unavailable."
            elif status_code == 504:
                error_msg = "Dial4SMS Gateway Error (504 Gateway Timeout): The SMS provider took too long to respond."
            elif '<html' in text_content.lower():
                error_msg = f"Dial4SMS Gateway Error ({status_code}): SMS provider server returned an HTTP error page."
            else:
                error_msg = text_content[:300]

        return {
            'success': success,
            'status': 'SUCCESS' if success else 'FAILED',
            'error': error_msg,
            'gateway_response': parsed_json,
            'response_id': str(response_id) if response_id else None,
            'status_code': status_code
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Dial4SMS request exception for {clean_phone}: {str(e)}")
        return {
            'success': False,
            'status': 'FAILED',
            'error': f"Connection Error: {str(e)}",
            'gateway_response': {'error': str(e)},
            'response_id': None
        }


def send_full_day_absent_sms_to_student(student, absent_date, user=None, recipient_type='PARENT'):
    """
    Prepares, sends, and records full day absentee SMS for a student.
    """
    info = get_student_sms_info(student)
    student_name = info['student_name']
    parent_phone = info['parent_mobile']
    student_phone = info['student_mobile']

    target_phone = parent_phone if recipient_type == 'PARENT' else (student_phone or parent_phone)

    message, date_str = format_full_day_absent_message(student_name, absent_date)
    template_id = getattr(settings, 'DIAL4SMS_FULLDAY_ABSENT_TEMPLATE_ID', os.getenv('DIAL4SMS_FULLDAY_ABSENT_TEMPLATE_ID', DEFAULT_FULLDAY_TEMPLATE_ID))

    if not target_phone:
        log_entry = SMSLog.objects.create(
            student=student,
            recipient_type=recipient_type,
            phone_number='N/A',
            student_name=student_name,
            register_number=info['register_number'],
            sms_type='FULL_DAY_ABSENT',
            template_id=template_id,
            message=message,
            sent_date=absent_date,
            status='FAILED',
            gateway_response={'error': f'No {recipient_type.lower()} phone number available for student'},
            error_message=f'No {recipient_type.lower()} phone number available for student',
            created_by=user,
            updated_by=user
        )
        return {
            'student_id': student.id,
            'student_name': student_name,
            'register_number': info['register_number'],
            'phone_number': '',
            'status': 'FAILED',
            'error': f'No valid {recipient_type.lower()} phone number on file',
            'log_id': log_entry.id
        }

    # Dispatch to Gateway
    gw_result = send_dial4sms_single(
        phone_number=target_phone,
        message=message,
        template_id=template_id
    )

    # Save to SMSLog
    log_entry = SMSLog.objects.create(
        student=student,
        recipient_type=recipient_type,
        phone_number=target_phone,
        student_name=student_name,
        register_number=info['register_number'],
        sms_type='FULL_DAY_ABSENT',
        template_id=template_id,
        message=message,
        sent_date=absent_date,
        status=gw_result['status'],
        gateway_response=gw_result['gateway_response'],
        response_id=gw_result['response_id'],
        error_message=gw_result['error'],
        created_by=user,
        updated_by=user
    )

    return {
        'student_id': student.id,
        'student_name': student_name,
        'register_number': info['register_number'],
        'phone_number': target_phone,
        'status': gw_result['status'],
        'response_id': gw_result['response_id'],
        'error': gw_result['error'],
        'log_id': log_entry.id,
        'gateway_response': gw_result['gateway_response']
    }


def send_afternoon_absent_sms_to_student(student, absent_date, user=None, recipient_type='PARENT'):
    """
    Prepares, sends, and records afternoon absentee SMS for a student.
    Template: Dear Parent, {#var#} is absent today Afternoon {#var#}. Principal - Thirumalai Engineering Collge
    """
    info = get_student_sms_info(student)
    student_name = info['student_name']
    parent_phone = info['parent_mobile']
    student_phone = info['student_mobile']

    target_phone = parent_phone if recipient_type == 'PARENT' else (student_phone or parent_phone)

    message, date_str = format_afternoon_absent_message(student_name, absent_date)
    template_id = getattr(settings, 'DIAL4SMS_AFTERNOON_ABSENT_TEMPLATE_ID', os.getenv('DIAL4SMS_AFTERNOON_ABSENT_TEMPLATE_ID', DEFAULT_AFTERNOON_TEMPLATE_ID))

    if not target_phone:
        log_entry = SMSLog.objects.create(
            student=student,
            recipient_type=recipient_type,
            phone_number='N/A',
            student_name=student_name,
            register_number=info['register_number'],
            sms_type='AFTERNOON_ABSENT',
            template_id=template_id,
            message=message,
            sent_date=absent_date,
            status='FAILED',
            gateway_response={'error': f'No {recipient_type.lower()} phone number available for student'},
            error_message=f'No {recipient_type.lower()} phone number available for student',
            created_by=user,
            updated_by=user
        )
        return {
            'student_id': student.id,
            'student_name': student_name,
            'register_number': info['register_number'],
            'phone_number': '',
            'status': 'FAILED',
            'error': f'No valid {recipient_type.lower()} phone number on file',
            'log_id': log_entry.id
        }

    # Dispatch to Gateway
    gw_result = send_dial4sms_single(
        phone_number=target_phone,
        message=message,
        template_id=template_id
    )

    # Save to SMSLog
    log_entry = SMSLog.objects.create(
        student=student,
        recipient_type=recipient_type,
        phone_number=target_phone,
        student_name=student_name,
        register_number=info['register_number'],
        sms_type='AFTERNOON_ABSENT',
        template_id=template_id,
        message=message,
        sent_date=absent_date,
        status=gw_result['status'],
        gateway_response=gw_result['gateway_response'],
        response_id=gw_result['response_id'],
        error_message=gw_result['error'],
        created_by=user,
        updated_by=user
    )

    return {
        'student_id': student.id,
        'student_name': student_name,
        'register_number': info['register_number'],
        'phone_number': target_phone,
        'status': gw_result['status'],
        'response_id': gw_result['response_id'],
        'error': gw_result['error'],
        'log_id': log_entry.id,
        'gateway_response': gw_result['gateway_response']
    }
