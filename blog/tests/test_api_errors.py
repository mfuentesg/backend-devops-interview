import pytest
from django.test import Client


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_unrouted_api_path_returns_json_envelope_404(client):
    response = client.get("/api/nope")

    assert response.status_code == 404
    assert response["Content-Type"].split(";")[0] == "application/json"
    body = response.json()
    assert body["data"] is None
    assert body["status_code"] == 404
    assert body["errors"][0]["field"] is None
    assert "/api/nope" in body["errors"][0]["message"]


@pytest.mark.django_db
def test_removed_users_find_returns_json_envelope_404(client):
    response = client.get("/api/users/find?email=alice@example.com")

    assert response.status_code == 404
    assert response["Content-Type"].split(";")[0] == "application/json"
    assert response.json()["errors"][0]["message"].startswith("No API endpoint")


@pytest.mark.django_db
def test_wrong_method_returns_json_envelope_405(client):
    response = client.delete("/api/posts/1")

    assert response.status_code == 405
    assert response["Content-Type"].split(";")[0] == "application/json"
    body = response.json()
    assert body["status_code"] == 405
    assert "not allowed" in body["errors"][0]["message"]
    assert response.has_header("Allow")


@pytest.mark.django_db
def test_routed_json_responses_are_untouched(client):
    from blog.models import Post, User

    author = User.objects.create(username="z", email="z@e.com", display_name="Z")
    post = Post.objects.create(author=author, title="T", body="B")

    ok = client.get(f"/api/posts/{post.id}")
    assert ok.status_code == 200
    assert ok.json()["data"]["title"] == "T"

    missing = client.get("/api/posts/999999")
    assert missing.status_code == 404
    assert missing.json()["errors"][0]["field"] == "post_id"
