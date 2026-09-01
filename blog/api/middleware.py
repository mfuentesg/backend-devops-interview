from django.http import JsonResponse

from blog.api.responses import ApiResponse

_API_PREFIX = "/api/"


class ApiEnvelopeErrorMiddleware:
    """Return the JSON response envelope for resolver-level errors under ``/api/``.

    django-ninja only shapes responses for requests that reach one of its
    operations. A path that matches no route (404) or a route hit with the
    wrong verb (405) is handled by Django/ninja before that point and comes
    back as an HTML page or a bare string. This middleware rewrites those two
    cases under ``/api/`` into ``{data, meta, status_code, errors}`` so an API
    client always gets JSON. Unhandled 500s are left alone.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            not request.path.startswith(_API_PREFIX)
            or response.status_code not in (404, 405)
            or response.get("Content-Type", "").partition(";")[0] == "application/json"
        ):
            return response

        if response.status_code == 405:
            message = f"Method {request.method} is not allowed for {request.path}"
        else:
            message = f"No API endpoint for {request.method} {request.path}"

        enveloped = ApiResponse.error(
            [{"field": None, "message": message}], status=response.status_code
        )
        new_response = JsonResponse(enveloped.value, status=enveloped.status_code)
        if response.has_header("Allow"):
            new_response["Allow"] = response["Allow"]
        return new_response
