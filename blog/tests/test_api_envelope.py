import pytest
from django.test import Client

from blog.api.responses import ApiResponse
from blog.models import Post, User


def test_success_wraps_data():
    resp = ApiResponse.success({"id": 1})
    assert resp.status_code == 200
    assert resp.value == {"data": {"id": 1}, "meta": None, "status_code": 200, "errors": []}


def test_success_custom_status():
    resp = ApiResponse.success({"id": 1}, status=201)
    assert resp.status_code == 201
    assert resp.value["status_code"] == 201


def test_paginated_computes_total_pages():
    resp = ApiResponse.paginated([1, 2], page=1, limit=20, total=42)
    assert resp.status_code == 200
    assert resp.value["data"] == [1, 2]
    assert resp.value["meta"] == {"page": 1, "limit": 20, "total": 42, "total_pages": 3}
    assert resp.value["errors"] == []


def test_paginated_zero_total_is_zero_pages():
    resp = ApiResponse.paginated([], page=1, limit=20, total=0)
    assert resp.value["meta"]["total_pages"] == 0


def test_error_normalises_strings_and_dicts():
    resp = ApiResponse.error(
        ["bad thing", {"field": "limit", "message": "too big"}], status=400
    )
    assert resp.status_code == 400
    assert resp.value["data"] is None and resp.value["meta"] is None
    assert resp.value["errors"] == [
        {"field": None, "message": "bad thing"},
        {"field": "limit", "message": "too big"},
    ]


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_bad_path_param_returns_400_envelope(client):
    # non-integer post id -> Ninja ValidationError -> our handler
    response = client.get("/api/posts/not-an-int")
    assert response.status_code == 400
    body = response.json()
    assert body["data"] is None
    assert body["status_code"] == 400
    assert body["errors"] and "field" in body["errors"][0]


@pytest.mark.django_db
def test_paginate_helper_slices_and_counts():
    from blog.api.helpers import paginate

    u = User.objects.create(username="p", email="p@e.com", display_name="P")
    for i in range(5):
        Post.objects.create(author=u, title=f"t{i}", body="b")
    items, total = paginate(Post.objects.order_by("id"), page=2, limit=2)
    assert total == 5
    assert len(items) == 2
