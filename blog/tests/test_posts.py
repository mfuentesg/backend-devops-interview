import json

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
def test_list_posts_returns_all_publish_states_by_default(client, user):
    tag = Tag.objects.create(name="Python", slug="python")
    post = Post.objects.create(author=user, title="Hello", body="World")
    post.tags.add(tag)
    Post.objects.create(author=user, title="Draft", body="...", is_published=False)

    response = client.get("/api/posts")

    assert response.status_code == 200
    body = response.json()
    assert body["status_code"] == 200
    assert "Hello" in _titles(response)
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
    expected = list(
        Post.objects.order_by("created_at", "id").values_list("title", flat=True)
    )[10:20]
    assert [p["title"] for p in body["data"]] == expected
    assert body["meta"] == {"page": 2, "limit": 10, "total": 25, "total_pages": 3}


@pytest.mark.django_db
def test_list_posts_query_count_is_bounded(client, user, django_assert_num_queries):
    tags = [Tag.objects.create(name=f"T{i}", slug=f"t{i}") for i in range(4)]
    for i in range(15):
        post = Post.objects.create(author=user, title=f"P{i:02d}", body="x")
        post.tags.set(tags[i % 2 : i % 2 + 2])

    # count + page + prefetch(tags); author is select_related. A regression that drops
    # select_related/prefetch_related would blow this past the fixed number.
    with django_assert_num_queries(3):
        response = client.get("/api/posts?limit=20")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 15


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


@pytest.mark.django_db
def test_get_post_detail_envelope_no_comments_by_default(client, user):
    from blog.models import Comment

    post = Post.objects.create(author=user, title="Hello", body="World")
    Comment.objects.create(post=post, author=user, body="hi")

    response = client.get(f"/api/posts/{post.id}")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["title"] == "Hello"
    assert data["author"]["username"] == "alice"
    assert data["comments"] == []


@pytest.mark.django_db
def test_get_post_expand_comments(client, user):
    from blog.models import Comment

    post = Post.objects.create(author=user, title="Hello", body="World")
    Comment.objects.create(post=post, author=user, body="hi")

    response = client.get(f"/api/posts/{post.id}?expand=comments")

    data = response.json()["data"]
    assert [c["body"] for c in data["comments"]] == ["hi"]


@pytest.mark.django_db
def test_get_post_invalid_expand_is_400(client, user):
    post = Post.objects.create(author=user, title="Hello", body="World")
    assert client.get(f"/api/posts/{post.id}?expand=nope").status_code == 400


@pytest.mark.django_db
def test_get_post_missing_is_404_envelope(client):
    response = client.get("/api/posts/999999")
    assert response.status_code == 404
    body = response.json()
    assert body["data"] is None
    assert body["errors"][0]["field"] == "post_id"


@pytest.mark.django_db
def test_get_post_increments_view_count(client, user):
    post = Post.objects.create(author=user, title="Hello", body="World")
    client.get(f"/api/posts/{post.id}")
    post.refresh_from_db()
    assert post.view_count == 1


def _post(client, payload):
    return client.post(
        "/api/posts", data=json.dumps(payload), content_type="application/json"
    )


@pytest.mark.django_db
def test_create_post_success_returns_201_detail_shape(client, user):
    Tag.objects.create(name="Python", slug="python")
    response = _post(
        client,
        {"author_id": user.id, "title": "  Hi  ", "body": "Body text", "tag_slugs": ["python"]},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "Hi"  # stripped
    assert data["comments"] == []
    assert [t["slug"] for t in data["tags"]] == ["python"]
    assert Post.objects.filter(title="Hi").exists()


@pytest.mark.django_db
def test_create_post_strips_html(client, user):
    response = _post(
        client,
        {"author_id": user.id, "title": "<b>Bold</b>", "body": "<script>evil()</script>safe"},
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["title"] == "Bold"
    assert "<script>" not in data["body"] and "safe" in data["body"]


@pytest.mark.django_db
def test_create_post_empty_title_is_400(client, user):
    response = _post(client, {"author_id": user.id, "title": "   ", "body": "x"})
    assert response.status_code == 400
    assert any(e["field"] == "title" for e in response.json()["errors"])


@pytest.mark.django_db
def test_create_post_unknown_author_and_tag_reports_both(client):
    response = _post(
        client,
        {"author_id": 999999, "title": "T", "body": "B", "tag_slugs": ["ghost"]},
    )
    assert response.status_code == 400
    fields = {e["field"] for e in response.json()["errors"]}
    assert fields == {"author_id", "tag_slugs"}
    assert Post.objects.count() == 0


@pytest.mark.django_db
def test_create_post_invalid_slug_format_is_400(client, user):
    response = _post(
        client, {"author_id": user.id, "title": "T", "body": "B", "tag_slugs": ["Bad Slug!"]}
    )
    assert response.status_code == 400
    assert any(e["field"] == "tag_slugs" for e in response.json()["errors"])
