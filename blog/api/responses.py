import math

from ninja import Status


def _norm(errors):
    out = []
    for e in errors:
        if isinstance(e, dict):
            out.append({"field": e.get("field"), "message": e["message"]})
        else:
            out.append({"field": None, "message": str(e)})
    return out


class ApiResponse:
    @staticmethod
    def success(data, *, status: int = 200, meta: dict | None = None) -> Status:
        return Status(status, {"data": data, "meta": meta, "status_code": status, "errors": []})

    @staticmethod
    def paginated(items: list, *, page: int, limit: int, total: int) -> Status:
        total_pages = math.ceil(total / limit) if total else 0
        meta = {"page": page, "limit": limit, "total": total, "total_pages": total_pages}
        return Status(200, {"data": items, "meta": meta, "status_code": 200, "errors": []})

    @staticmethod
    def error(errors, *, status: int = 400) -> Status:
        return Status(
            status, {"data": None, "meta": None, "status_code": status, "errors": _norm(errors)}
        )
