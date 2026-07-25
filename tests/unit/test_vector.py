from gitrag.retrieval.vector import MemoryVectorStore


def test_memory_vector_store_applies_branch_filter():
    store = MemoryVectorStore()
    store.upsert(
        [
            ("a", [1.0, 0.0], {"repo_id": "r", "branch_names": ["main"]}),
            ("b", [0.9, 0.1], {"repo_id": "r", "branch_names": ["feature"]}),
        ]
    )

    matches = store.query([1.0, 0.0], top_k=10, filters={"repo_id": "r", "branch_names": {"$in": ["feature"]}})

    assert [match.id for match in matches] == ["b"]
