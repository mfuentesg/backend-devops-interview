Let's now go deeper on this project, @blog/api.py is the core of this project, where all API definition is written. There are some concerns that I would like oto cover as part of this brainstorming.

1. Isolation of entities: I understand this is a small project with a couple of endpoints, but
if we are thinking to scale it, will be a mess having all together. So, let's start splitting
responsibilities, after having this we can think on creating a deeper directory structure, like
hexagaonal architecture or something else.

2. /posts is not making any validation in terms of pagination, filtering, even sorting is
hardcoded, I would like to keep this as part of the incoming query parameters.
    a. Let's define some filters, for now, `published`. true = published, false = non published, null/empty = all posts
    b. Allow to sort data by created_at field, allowed values should be desc or asc, nothing
    c. Since we are extending the capabilities of this endpoint, is not required to have a separated endpoint just for search "/posts/search", instead of this, by now let's include a "query" filter, which makes to filter by title or body content. empty/null = no filter by title or content
    d. As point c, let's include another filter called slug, which will filter those has the exact slug associated to the posts
    e. Since have added 3 filters, let's define a typed filter object including supported ones.
    f. List items keep a minimal, non-costly shape: id, title, author, tags, view_count,
    created_at. No body, no comments on the list endpoint.

3. /posts/{post_id} this endpoint looks "OK"
    a. Just use update_fields=["view_count"] on "save" to avoid side effects and keeping on desired updates
    b. Let's include a expansion query param, this for getting comments only when needed by client. include expand=comments, let's handle it as a list, in case we want to expand more entities like tags, or something like that. Use a enum of supported values.

4. POST /posts
    a. Include sanitization at incoming level of payload
    b. Add validation post creation since it is not validating if post was created correctly or not
    c. Trigger 400 include errors in case of issues

5. /users/{user_id} It looks okay

6. /users/find, in terms of privacy I don't think this should be supported, actually it is open a breach since an attacker could try to use any email or even worst, DOS attack. Let's delete it


General rules:

1. Let's use a common structure for all endpoints
    { "data": {} or [] for lists, "status_code": 200, "errors": [] }, 
    failed requests, should list of issues, it could be related to invalid inputs, they must be clear and understandable by consumers

2. Ensure to validate inputs to avoid any kind of unwanted access
3. Define pagination, using "page", and "limit" where limit is the number of items per page, let's define as maximum 100 items per page, to avoid overloads on each endpoint that respond with a list of items.
4. List endpoints shouldn't return 404, just empty lists without results and 200OK
5. Let's use parameterized queries to avoid sql injection
6. Update existing documentation referring to changed endpoints and deleted ones


Out of scope by this brainstorming:

1. Indexed search using advanced search algorithms over postgres like b-tree or full-text index, same for body
2. Include validation at query avoid sql injection on query
3. Expansion of comments in list of posts