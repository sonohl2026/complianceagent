from app.services.crawling.diff import PageSnapshot, diff_snapshots, summarize_diff


def test_new_page_is_added():
    old = []
    new = [PageSnapshot(canonical_url="https://sonohl.com/", sha256="abc", title="Home")]
    entries = diff_snapshots(old, new)
    assert entries[0].change_type == "added"


def test_removed_page_is_flagged():
    old = [PageSnapshot(canonical_url="https://sonohl.com/old", sha256="abc")]
    new = []
    entries = diff_snapshots(old, new)
    assert entries[0].change_type == "removed"


def test_same_hash_is_unchanged():
    old = [PageSnapshot(canonical_url="https://sonohl.com/", sha256="same")]
    new = [PageSnapshot(canonical_url="https://sonohl.com/", sha256="same")]
    entries = diff_snapshots(old, new)
    assert entries[0].change_type == "unchanged"


def test_different_hash_is_changed():
    old = [PageSnapshot(canonical_url="https://sonohl.com/", sha256="v1", title="Old title")]
    new = [PageSnapshot(canonical_url="https://sonohl.com/", sha256="v2", title="New title")]
    entries = diff_snapshots(old, new)
    assert entries[0].change_type == "changed"
    assert entries[0].old_title == "Old title"
    assert entries[0].new_title == "New title"


def test_diff_never_relies_on_title_alone_for_change_detection():
    # Same hash but caller happened to pass a different title string (should
    # not happen in real data, but the function must trust the hash, not text).
    old = [PageSnapshot(canonical_url="https://sonohl.com/", sha256="same", title="A")]
    new = [PageSnapshot(canonical_url="https://sonohl.com/", sha256="same", title="B")]
    entries = diff_snapshots(old, new)
    assert entries[0].change_type == "unchanged"


def test_summarize_diff_counts_each_category():
    entries = diff_snapshots(
        old_pages=[
            PageSnapshot(canonical_url="https://sonohl.com/removed", sha256="x"),
            PageSnapshot(canonical_url="https://sonohl.com/changed", sha256="v1"),
            PageSnapshot(canonical_url="https://sonohl.com/same", sha256="s"),
        ],
        new_pages=[
            PageSnapshot(canonical_url="https://sonohl.com/changed", sha256="v2"),
            PageSnapshot(canonical_url="https://sonohl.com/same", sha256="s"),
            PageSnapshot(canonical_url="https://sonohl.com/added", sha256="new"),
        ],
    )
    summary = summarize_diff(entries)
    assert summary == {"added": 1, "removed": 1, "changed": 1, "unchanged": 1}
