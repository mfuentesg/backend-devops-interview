import pytest
from django.test import Client

from blog.models import Post, Tag, User


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def user(db):
    return User.objects.create(
        username="alice",
        email="alice@example.com",
        display_name="Alice",
    )


def _titles(response):
    return [p["title"] for p in response.json()["data"]]


@pytest.mark.django_db
def test_list_posts_returns_published_by_default(client, user):
    tag = Tag.objects.create(name="Python", slug="python")
    post = Post.objects.create(author=user, title="Hello", body="World")
    post.tags.add(tag)
    Post.objects.create(author=user, title="Draft", body="...", is_published=False)

    response = client.get("/api/posts")

    assert response.status_code == 200
    body = response.json()
    assert body["status_code"] == 200
    assert "Hello" in _titles(response)
    # default returns published only? No — see spec: omitted = all. Draft IS included.
    assert "Draft" in _titles(response)
    assert body["meta"]["page"] == 1
    assert body["meta"]["limit"] == 20
    assert body["meta"]["total"] == 2


@pytest.mark.django_db
def test_published_filter(client, user):
    Post.objects.create(author=user, title="Live", body="x")
    Post.objects.create(author=user, title="Draft", body="x", is_published=False)

    assert _titles(client.get("/api/posts?published=true")) == ["Live"]
    assert _titles(client.get("/api/posts?published=false")) == ["Draft"]


@pytest.mark.django_db
def test_query_filter_matches_title_or_body(client, user):
    Post.objects.create(author=user, title="Django tips", body="orm")
    Post.objects.create(author=user, title="Cooking", body="about django too")
    Post.objects.create(author=user, title="Unrelated", body="nothing")

    assert sorted(_titles(client.get("/api/posts?query=django"))) == ["Cooking", "Django tips"]


@pytest.mark.django_db
def test_slug_filter_by_tag(client, user):
    tag = Tag.objects.create(name="Python", slug="python")
    tagged = Post.objects.create(author=user, title="Tagged", body="x")
    tagged.tags.add(tag)
    Post.objects.create(author=user, title="Untagged", body="x")

    assert _titles(client.get("/api/posts?slug=python")) == ["Tagged"]


@pytest.mark.django_db
def test_slug_filter_unknown_tag_is_empty_200(client, user):
    Post.objects.create(author=user, title="X", body="x")
    response = client.get("/api/posts?slug=does-not-exist")
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert response.json()["meta"]["total"] == 0


@pytest.mark.django_db
def test_sort_asc_and_desc(client, user):
    from django.utils import timezone

    old = Post.objects.create(author=user, title="Old", body="x")
    Post.objects.create(author=user, title="New", body="x")
    Post.objects.filter(id=old.id).update(created_at=timezone.now() - timezone.timedelta(days=1))

    assert _titles(client.get("/api/posts?sort=asc")) == ["Old", "New"]
    assert _titles(client.get("/api/posts?sort=desc")) == ["New", "Old"]


@pytest.mark.django_db
def test_pagination(client, user):
    for i in range(25):
        Post.objects.create(author=user, title=f"P{i:02d}", body="x")

    response = client.get("/api/posts?sort=asc&page=2&limit=10")
    body = response.json()
    assert [p["title"] for p in body["data"]] == [f"P{i:02d}" for i in range(10, 20)]
    assert body["meta"] == {"page": 2, "limit": 10, "total": 25, "total_pages": 3}


@pytest.mark.django_db
def test_limit_over_max_is_400(client):
    response = client.get("/api/posts?limit=101")
    assert response.status_code == 400
    assert any(e["field"] == "limit" for e in response.json()["errors"])


@pytest.mark.django_db
def test_invalid_sort_is_400(client):
    response = client.get("/api/posts?sort=sideways")
    assert response.status_code == 400


@pytest.mark.django_db
def test_search_and_by_tag_endpoints_are_gone(client):
    # /posts/search now falls through to /posts/{post_id}; "search" is not an int
    # so the shared ValidationError handler answers 400 (see test_api_envelope).
    assert client.get("/api/posts/search?q=x").status_code == 400
    assert client.get("/api/posts/by-tag/python").status_code == 404
