import time
from django.core.cache import cache
from rest_framework.response import Response
from rest_framework import status


def get_option_cache_version(model_name):
    ver = cache.get(f"opt_ver_{model_name}")
    if ver is None:
        ver = int(time.time() * 1000)
        cache.set(f"opt_ver_{model_name}", ver, timeout=None)
    return ver


def invalidate_option_cache(model_name):
    ver = int(time.time() * 1000)
    cache.set(f"opt_ver_{model_name}", ver, timeout=None)


class CachedOptionViewSetMixin:
    """
    Mixin for DRF ViewSets serving option/dropdown lists.
    Provides automatic in-memory / Redis caching for list() operations with
    O(1) versioned cache invalidation on write/update/delete operations.
    """
    cache_model_name = None
    cache_timeout = 3600  # Default 1 hour

    def get_cache_model_name(self):
        if self.cache_model_name:
            return self.cache_model_name
        if hasattr(self, 'model_label'):
            return self.model_label
        if hasattr(self, 'queryset') and self.queryset is not None:
            return self.queryset.model.__name__
        return self.__class__.__name__

    def list(self, request, *args, **kwargs):
        if request.query_params.get('no_cache') == 'true':
            return super().list(request, *args, **kwargs)

        model_name = self.get_cache_model_name()
        version = get_option_cache_version(model_name)
        full_path = request.get_full_path()
        cache_key = f"opt_cache:{model_name}:v{version}:{full_path}"

        cached_data = cache.get(cache_key)
        if cached_data is not None:
            return Response(cached_data, status=status.HTTP_200_OK)

        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            cache.set(cache_key, response.data, timeout=self.cache_timeout)
        return response

    def perform_create(self, serializer):
        super().perform_create(serializer)
        invalidate_option_cache(self.get_cache_model_name())

    def perform_update(self, serializer):
        super().perform_update(serializer)
        invalidate_option_cache(self.get_cache_model_name())

    def perform_destroy(self, instance):
        super().perform_destroy(instance)
        invalidate_option_cache(self.get_cache_model_name())
