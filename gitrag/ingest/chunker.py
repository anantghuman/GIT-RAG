"""Tree-sitter backed code chunking with whole-file fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from gitrag.git import language_for_path

DEFAULT_EXCLUDED_PARTS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "gitrag.venv",
    "__pycache__",
    "node_modules",
    "vendor",
    "dist",
    "build",
    ".next",
    "coverage",
    "target",
}


@dataclass(frozen=True)
class CodeChunk:
    content: str
    path: str
    language: str
    chunk_type: str
    node_type: str
    line_start: int
    line_end: int
    symbol_name: str | None = None


NODE_TYPES = {
    "Python": {"function_definition", "class_definition"},
    "JavaScript": {
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
        "class_declaration",
        "variable_declarator",
    },
    "TypeScript": {
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
        "class_declaration",
        "interface_declaration",
    },
    "Java": {"method_declaration", "class_declaration"},
    "Go": {"function_declaration", "method_declaration"},
}


def _import_optional(module_name: str):
    try:
        return __import__(module_name)
    except Exception:
        return None


def _ts_language(tree_sitter_module, language_attr: str = "language"):
    if tree_sitter_module is None:
        return None
    try:
        import tree_sitter

        return tree_sitter.Language(getattr(tree_sitter_module, language_attr)())
    except Exception:
        return None


def build_parsers(languages: Iterable[str] | None = None) -> dict[str, object]:
    """Return language -> parser. Missing parser packages are skipped."""
    try:
        import tree_sitter
    except Exception:
        return {}

    modules = {
        "JavaScript": (_import_optional("tree_sitter_javascript"), "language"),
        "Python": (_import_optional("tree_sitter_python"), "language"),
        "TypeScript": (_import_optional("tree_sitter_typescript"), "language_typescript"),
        "Java": (_import_optional("tree_sitter_java"), "language"),
        "Go": (_import_optional("tree_sitter_go"), "language"),
    }
    wanted = set(languages or modules.keys())
    parsers: dict[str, object] = {}
    for language, (module, attr) in modules.items():
        if language not in wanted:
            continue
        ts_language = _ts_language(module, attr)
        if ts_language is None:
            continue
        parsers[language] = tree_sitter.Parser(ts_language)
    return parsers


def traverse(node):
    yield node
    for child in node.children:
        yield from traverse(child)


def extract_symbol_name(node, content: str) -> str | None:
    for child in node.children:
        if child.type in {"identifier", "property_identifier", "type_identifier"}:
            return content[child.start_byte : child.end_byte]
        if child.type in {"name"}:
            return content[child.start_byte : child.end_byte]
    return None


def should_index_path(path: str, *, include_vendor: bool = False) -> bool:
    if language_for_path(path) is None:
        return False
    if include_vendor:
        return True
    parts = {part for part in path.replace("\\", "/").split("/") if part}
    return not bool(parts & DEFAULT_EXCLUDED_PARTS)


def chunk_file_content(path: str, content: str, parser, language: str) -> list[CodeChunk]:
    if not content.strip():
        return []

    chunks: list[CodeChunk] = []
    if parser is not None:
        content_bytes = content.encode("utf-8", errors="ignore")
        tree = parser.parse(content_bytes)
        for node in traverse(tree.root_node):
            target_types = NODE_TYPES.get(language, set())
            if node.type not in target_types:
                continue
            if node.type == "variable_declarator" and language == "JavaScript":
                child_types = {child.type for child in node.children}
                if not {"arrow_function", "function_expression"} & child_types:
                    continue
            text = content[node.start_byte : node.end_byte]
            chunks.append(
                CodeChunk(
                    content=text,
                    path=path,
                    language=language,
                    chunk_type="code",
                    node_type=node.type,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    symbol_name=extract_symbol_name(node, content),
                )
            )

    if not chunks:
        chunks.append(
            CodeChunk(
                content=content[:12000],
                path=path,
                language=language,
                chunk_type="file",
                node_type="file",
                line_start=1,
                line_end=max(len(content.splitlines()), 1),
                symbol_name=None,
            )
        )
    return chunks
