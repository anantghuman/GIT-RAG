from gitrag.storage.snapshot import change_ratio, choose_storage_kind, storage_reduction


def test_snapshot_policy_initial_merge_periodic_and_small_delta():
    assert choose_storage_kind(
        has_parent=False,
        is_merge=False,
        version_index=1,
        current_content="a",
        parent_content=None,
        snapshot_interval=10,
        change_threshold=0.3,
    ).kind == "snapshot"

    assert choose_storage_kind(
        has_parent=True,
        is_merge=True,
        version_index=2,
        current_content="a",
        parent_content="a",
        snapshot_interval=10,
        change_threshold=0.3,
    ).reason == "merge_commit"

    assert choose_storage_kind(
        has_parent=True,
        is_merge=False,
        version_index=10,
        current_content="a",
        parent_content="a",
        snapshot_interval=10,
        change_threshold=0.3,
    ).reason == "periodic_snapshot"

    assert choose_storage_kind(
        has_parent=True,
        is_merge=False,
        version_index=11,
        current_content="one\ntwo\nthree\n",
        parent_content="one\ntwo\nthree\n",
        snapshot_interval=10,
        change_threshold=0.3,
    ).kind == "diff"


def test_storage_math():
    assert change_ratio("a\nb\n", "a\nc\n") > 0
    assert storage_reduction(1000, 150) == 0.85
