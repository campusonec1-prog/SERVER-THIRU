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
                    # Get the first field that caused the validation failure
                    first_field = next(iter(data))
                    first_err = data[first_field]
                    if isinstance(first_err, list) and len(first_err) > 0:
                        err_msg = str(first_err[0])
                    else:
                        err_msg = str(first_err)

                    err_msg_lower = err_msg.lower()
                    
                    # 1. Handle unique constraints (e.g. "role with this role name already exists.")
                    if 'already exists' in err_msg_lower:
                        if 'with this' in err_msg_lower:
                            parts = err_msg_lower.split(' with this ')
                            model_name = parts[0].strip().title()
                            message = f"{model_name} is already exist"
                        else:
                            field_name = first_field.replace('_', ' ').title()
                            message = f"{field_name} already exists."
                            
                    # 2. Handle missing required fields
                    elif err_msg_lower == "this field is required.":
                        field_name = first_field.replace('_', ' ').title()
                        message = f"{field_name} is required."
                        
                    # 3. Handle null fields
                    elif err_msg_lower == "this field may not be null.":
                        field_name = first_field.replace('_', ' ').title()
                        message = f"{field_name} cannot be null."
                        
                    # 4. Handle blank fields
                    elif err_msg_lower == "this field may not be blank.":
                        field_name = first_field.replace('_', ' ').title()
                        message = f"{field_name} cannot be blank."
                        
                    # 5. Handle invalid formats
                    elif err_msg_lower == "this field is invalid.":
                        field_name = first_field.replace('_', ' ').title()
                        message = f"Invalid {field_name.lower()}."
                        
                    # 6. Fallback for other errors
                    else:
                        if first_field in ['non_field_errors', 'detail']:
                            message = err_msg
                        else:
                            field_name = first_field.replace('_', ' ').title()
                            message = f"{field_name}: {err_msg}"
                except Exception as e:
                    logger.error(f"Error parsing validation exception: {e}")
                    message = str(data)
        elif isinstance(data, list):
            if len(data) > 0:
                message = str(data[0])
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
