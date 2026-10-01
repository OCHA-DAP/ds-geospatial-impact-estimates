from gie.unosat import store


def test_drop_directory_entries_removes_strict_path_prefixes():
    sizes = {"a/b": 0, "a/b/c.zip": 5, "a/d/e.zip": 7}
    assert store.drop_directory_entries(sizes) == {"a/b/c.zip": 5, "a/d/e.zip": 7}


def test_drop_directory_entries_keeps_zero_byte_file_with_no_children():
    sizes = {"a/b/c.zip": 0, "a/d/e.zip": 7}
    assert store.drop_directory_entries(sizes) == sizes
