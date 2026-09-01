import json

import pytest
from django.test import Client

from blog.models import Comment, Post, User


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create(username="bob", email="bob@example.com", display_name="Bob")


@pytest.mark.django_db
def test_create_comment_returns_201_envelope(client, user):
    post = Post.objects.create(author=user, title="T", body="B")

    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": user.id, "body": "Nice post!"}),
        content_type="application/json",
    )

    assert response.status_code == 201
    data = response.json()["data"]
    assert data["body"] == "Nice post!"
    assert data["author"]["username"] == "bob"
    assert Comment.objects.filter(post=post, body="Nice post!").exists()


@pytest.mark.django_db
def test_create_comment_strips_html(client, user):
    post = Post.objects.create(author=user, title="T", body="B")
    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": user.id, "body": "<script>x</script>ok"}),
        content_type="application/json",
    )
    assert response.status_code == 201
    assert "<script>" not in response.json()["data"]["body"]


@pytest.mark.django_db
def test_create_comment_missing_post_is_404(client, user):
    response = client.post(
        "/api/posts/999999/comments",
        data=json.dumps({"author_id": user.id, "body": "hi"}),
        content_type="application/json",
    )
    assert response.status_code == 404
    assert response.json()["errors"][0]["field"] == "post_id"


@pytest.mark.django_db
def test_create_comment_missing_author_is_400(client, user):
    post = Post.objects.create(author=user, title="T", body="B")
    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": 999999, "body": "hi"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.json()["errors"][0]["field"] == "author_id"


@pytest.mark.django_db
def test_create_comment_empty_body_is_400(client, user):
    post = Post.objects.create(author=user, title="T", body="B")
    response = client.post(
        f"/api/posts/{post.id}/comments",
        data=json.dumps({"author_id": user.id, "body": "   "}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert any(e["field"] == "body" for e in response.json()["errors"])
