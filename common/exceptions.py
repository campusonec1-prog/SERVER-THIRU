import logging
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

def custom_exception_handler(exc, context):
    # Call REST framework's default exception handler first to get the standard error response
    response = exception_handler(exc, context)

    if response is None:
        # Catch generic unhandled exceptions (e.g. database connections, index errors)
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return Response({
            "code": 500,
            "message": "Internal server error."
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if response is not None:
        data = response.data
        message = ""

        if isinstance(data, dict):
            if 'message' in data:
                message = str(data['message'])
            elif 'detail' in data:
                message = str(data['detail'])
            else:
                try:
                    def extract_first_error(err_obj, parent_key=""):
                        if isinstance(err_obj, dict) and err_obj:
                            key = next(iter(err_obj))
                            label = key.replace('_', ' ').title()
                            return extract_first_error(err_obj[key], label)
                        elif isinstance(err_obj, list) and len(err_obj) > 0:
                            return extract_first_error(err_obj[0], parent_key)
                        else:
                            return parent_key, str(err_obj)

                    field_name, err_msg = extract_first_error(data)
                    err_msg_lower = err_msg.lower()
                    
                    # 1. Handle unique constraints (e.g. "role with this role name already exists.")
                    if 'already exists' in err_msg_lower:
                        if 'with this' in err_msg_lower:
                            parts = err_msg_lower.split(' with this ')
                            model_name = parts[0].strip().title()
                            message = f"{model_name} already exists"
                        else:
                            message = f"{field_name or 'Record'} already exists."
                            
                    # 2. Handle missing required fields
                    elif err_msg_lower == "this field is required.":
                        message = f"{field_name or 'Field'} is required."
                        
                    # 3. Handle null fields
                    elif err_msg_lower == "this field may not be null.":
                        message = f"{field_name or 'Field'} cannot be null."
                        
                    # 4. Handle blank fields
                    elif err_msg_lower == "this field may not be blank.":
                        message = f"{field_name or 'Field'} cannot be blank."
                        
                    # 5. Handle invalid formats
                    elif err_msg_lower == "this field is invalid.":
                        message = f"Invalid {(field_name or 'Field').lower()}."
                        
                    # 6. Fallback for other errors
                    else:
                        if field_name in ['Non Field Errors', 'Detail', ''] or not field_name:
                            message = err_msg
                        else:
                            message = f"{field_name}: {err_msg}"
                except Exception as e:
                    logger.error(f"Error parsing validation exception: {e}")
                    message = str(data)
        elif isinstance(data, list):
            if len(data) > 0:
                item = data[0]
                if isinstance(item, (dict, list)):
                    def extract_first(obj):
                        if isinstance(obj, dict) and obj:
                            k = next(iter(obj))
                            return extract_first(obj[k])
                        elif isinstance(obj, list) and obj:
                            return extract_first(obj[0])
                        return str(obj)
                    message = extract_first(item)
                else:
                    message = str(item)
            else:
                message = "An error occurred."
        else:
            message = str(data)

        # Standardize capitalization
        if message and isinstance(message, str):
            message = message.strip()
            if len(message) > 0:
                message = message[0].upper() + message[1:]

        response.data = {
            "code": response.status_code,
            "message": message
        }

    return response
