import pytest
from django.test import Client

from blog.models import User


@pytest.fixture
def client():
    return Client()


@pytest.mark.django_db
def test_get_user_envelope(client):
    u = User.objects.create(username="cara", email="cara@e.com", display_name="Cara")
    response = client.get(f"/api/users/{u.id}")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["username"] == "cara"
    assert data["post_count"] == 0


@pytest.mark.django_db
def test_get_user_missing_is_404_envelope(client):
    response = client.get("/api/users/999999")
    assert response.status_code == 404
    assert response.json()["errors"][0]["field"] == "user_id"


@pytest.mark.django_db
def test_users_find_is_gone(client):
    response = client.get("/api/users/find?email=cara@e.com")
    assert response.status_code == 404
