import structlog
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status

logger = structlog.get_logger(__name__)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        logger.warning('api_error', status=response.status_code, detail=str(exc))
        response.data = {
            'error': True,
            'status_code': response.status_code,
            'detail': response.data,
        }
    else:
        logger.error('unhandled_exception', exc_info=exc)
        response = Response(
            {'error': True, 'status_code': 500, 'detail': 'Internal server error'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    return response
