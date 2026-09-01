from blog.api.responses import ApiResponse


def test_success_wraps_data():
    status, body = ApiResponse.success({"id": 1})
    assert status == 200
    assert body == {"data": {"id": 1}, "meta": None, "status_code": 200, "errors": []}


def test_success_custom_status():
    status, body = ApiResponse.success({"id": 1}, status=201)
    assert status == 201
    assert body["status_code"] == 201


def test_paginated_computes_total_pages():
    status, body = ApiResponse.paginated([1, 2], page=1, limit=20, total=42)
    assert status == 200
    assert body["data"] == [1, 2]
    assert body["meta"] == {"page": 1, "limit": 20, "total": 42, "total_pages": 3}
    assert body["errors"] == []


def test_paginated_zero_total_is_zero_pages():
    _, body = ApiResponse.paginated([], page=1, limit=20, total=0)
    assert body["meta"]["total_pages"] == 0


def test_error_normalises_strings_and_dicts():
    status, body = ApiResponse.error(
        ["bad thing", {"field": "limit", "message": "too big"}], status=400
    )
    assert status == 400
    assert body["data"] is None and body["meta"] is None
    assert body["errors"] == [
        {"field": None, "message": "bad thing"},
        {"field": "limit", "message": "too big"},
    ]
