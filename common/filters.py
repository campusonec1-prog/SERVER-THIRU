from rest_framework.filters import BaseFilterBackend
from django.db.models import Q
import logging

logger = logging.getLogger(__name__)

class DynamicFilterBackend(BaseFilterBackend):
    def filter_queryset(self, request, queryset, view):
        model = queryset.model
        
        # Get all field names of the model
        model_fields = {f.name for f in model._meta.get_fields()}
        
        # 1. Handle exact/field filters
        filter_kwargs = {}
        for param, value in request.query_params.items():
            # Skip pagination, search, or other special params
            if param in ['page', 'page_size', 'search', 'pagination', 'ordering']:
                continue
            
            # Check if param (or param without lookup, e.g., is_active) is a field in the model
            clean_param = param.split('__')[0]
            field_name = clean_param
            is_valid_field = False
            
            if clean_param in model_fields:
                is_valid_field = True
            elif clean_param.endswith('_id'):
                fk_name = clean_param[:-3]
                if fk_name in model_fields:
                    is_valid_field = True
                    field_name = fk_name
            
            if is_valid_field:
                # Convert string 'true'/'false' to boolean if it is a boolean field
                try:
                    field = model._meta.get_field(field_name)
                    field_type = field.get_internal_type() if hasattr(field, 'get_internal_type') else ''
                    
                    if field_type in ['BooleanField', 'NullBooleanField']:
                        if value.lower() in ['true', '1']:
                            value = True
                        elif value.lower() in ['false', '0']:
                            value = False
                        elif value == '':
                            continue
                except Exception as e:
                    logger.debug(f"Error checking field type for {field_name}: {e}")
                
                # Skip empty values
                if value == '' or value is None:
                    continue
                    
                filter_kwargs[param] = value
                
        if filter_kwargs:
            try:
                queryset = queryset.filter(**filter_kwargs)
            except Exception as e:
                logger.error(f"Error filtering queryset with kwargs {filter_kwargs}: {e}")
                # Fallback: apply filters one by one, skipping the invalid ones
                for k, v in filter_kwargs.items():
                    try:
                        queryset = queryset.filter(**{k: v})
                    except Exception:
                        pass
            
        # 2. Handle search query
        search_query = request.query_params.get('search', None)
        if search_query:
            # Dynamically determine fields to search in
            search_fields = getattr(view, 'search_fields', None)
            if not search_fields:
                # Fallback: search in common text/char fields
                search_fields = []
                for field in model._meta.get_fields():
                    field_type = field.get_internal_type() if hasattr(field, 'get_internal_type') else None
                    if field_type in ['CharField', 'TextField']:
                        search_fields.append(field.name)
            
            if search_fields:
                search_filter = Q()
                for field in search_fields:
                    search_filter |= Q(**{f"{field}__icontains": search_query})
                queryset = queryset.filter(search_filter)
                
        return queryset
