from gitrag.ingest.chunker import chunk_file_content, should_index_path


def test_chunker_falls_back_to_whole_file_without_parser():
    chunks = chunk_file_content("app.py", "def hello():\n    return 'world'\n", None, "Python")

    assert len(chunks) == 1
    assert chunks[0].chunk_type == "file"
    assert chunks[0].line_start == 1
    assert chunks[0].line_end == 2


def test_should_index_path_skips_vendor_dependencies_by_default():
    assert should_index_path("src/app.py")
    assert not should_index_path("node_modules/package/index.js")
    assert not should_index_path("vendor/tree-sitter/parser.c")
    assert should_index_path("node_modules/package/index.js", include_vendor=True)
