from gitrag.ids import chunk_id, content_hash, normalize_repo_id, query_cache_key


def test_chunk_id_is_deterministic_and_model_scoped():
    first = chunk_id(
        repo_id="repo",
        sha="a" * 40,
        path="app.py",
        symbol="handler",
        line_start=1,
        line_end=10,
        chunk_type="code",
        hash_value=content_hash("def handler(): pass"),
        embedding_model="text-embedding-3-small",
    )
    second = chunk_id(
        repo_id="repo",
        sha="a" * 40,
        path="app.py",
        symbol="handler",
        line_start=1,
        line_end=10,
        chunk_type="code",
        hash_value=content_hash("def handler(): pass"),
        embedding_model="text-embedding-3-small",
    )
    third = chunk_id(
        repo_id="repo",
        sha="a" * 40,
        path="app.py",
        symbol="handler",
        line_start=1,
        line_end=10,
        chunk_type="code",
        hash_value=content_hash("def handler(): pass"),
        embedding_model="text-embedding-3-large",
    )
    assert first == second
    assert first != third


def test_repo_id_and_query_key_normalize_inputs():
    assert normalize_repo_id("https://github.com/acme/My Repo.git").startswith("my-repo-")
    first = query_cache_key(
        model="m",
        repo_id="r",
        question="Where  is Auth?",
        branch="main",
        sha=None,
        path_prefix=None,
        top_k=8,
        index_generation=3,
        include_answer=True,
    )
    second = query_cache_key(
        model="m",
        repo_id="r",
        question="where is auth?",
        branch="main",
        sha=None,
        path_prefix=None,
        top_k=8,
        index_generation=3,
        include_answer=True,
    )
    assert first == second
