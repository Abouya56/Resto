from rest_framework.views import exception_handler


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response
    payload = {
        "success": False,
        "errors": response.data,
        "status_code": response.status_code,
    }
    response.data = payload
    return response
