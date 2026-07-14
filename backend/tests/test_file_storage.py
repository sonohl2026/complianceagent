import pytest

from app.services.storage.file_storage import LocalFileStorage


def test_save_and_read_roundtrip(tmp_path):
    storage = LocalFileStorage(root=tmp_path)
    relative_path = storage.save_bytes("uploads", b"hello world", suffix=".txt")
    assert relative_path.startswith("uploads/")
    assert storage.read_bytes(relative_path) == b"hello world"


def test_stored_filename_is_randomized_not_client_controlled(tmp_path):
    storage = LocalFileStorage(root=tmp_path)
    path_a = storage.save_bytes("uploads", b"content", suffix=".pdf")
    path_b = storage.save_bytes("uploads", b"content", suffix=".pdf")
    assert path_a != path_b  # same bytes, different random names -> no collision/overwrite


def test_delete_removes_file(tmp_path):
    storage = LocalFileStorage(root=tmp_path)
    relative_path = storage.save_bytes("quarantine", b"bad file")
    assert storage.exists(relative_path)
    storage.delete(relative_path)
    assert not storage.exists(relative_path)


def test_abs_path_blocks_path_traversal_outside_root(tmp_path):
    storage = LocalFileStorage(root=tmp_path)
    with pytest.raises(ValueError):
        storage.abs_path("../../etc/passwd")


def test_categories_are_isolated_subdirectories(tmp_path):
    storage = LocalFileStorage(root=tmp_path)
    upload_path = storage.save_bytes("uploads", b"a")
    crawl_path = storage.save_bytes("crawls", b"b")
    assert (tmp_path / "uploads").is_dir()
    assert (tmp_path / "crawls").is_dir()
    assert upload_path.split("/")[0] == "uploads"
    assert crawl_path.split("/")[0] == "crawls"
