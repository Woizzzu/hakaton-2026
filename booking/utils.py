from rest_framework.response import Response


def success_response(data=None, status_code=200):
    return Response({
        "success": True,
        "data": data,
        "error": None
    }, status=status_code)


def error_response(message, status_code=400, code="ERROR", details=None):
    return Response({
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details or {}
        }
    }, status=status_code)