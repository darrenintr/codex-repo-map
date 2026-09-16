from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import ParsedFile, Symbol


LANG_BY_SUFFIX = {
    ".py": "python",
    ".pyi": "python",
    ".dart": "dart",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".go": "go",
    ".swift": "swift",
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
}


def language_for(path: str) -> str:
    name = Path(path).name.lower()
    if name in {"pubspec.yaml", "package.json", "pyproject.toml", "cargo.toml", "build.gradle", "build.gradle.kts"}:
        return "manifest"
    return LANG_BY_SUFFIX.get(Path(path).suffix.lower(), "text")


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _dedupe(items: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(x for x in items if x))


def parse_python(text: str) -> ParsedFile:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ParsedFile()
    symbols: list[Symbol] = []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(Symbol(node.name, "function", node.lineno))
        elif isinstance(node, ast.ClassDef):
            symbols.append(Symbol(node.name, "class", node.lineno))
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(("." * node.level) + (node.module or ""))
    symbols.sort(key=lambda s: (s.line, s.name))
    return ParsedFile(tuple(symbols), _dedupe(imports))


def _regex_symbols(text: str, patterns: list[tuple[str, re.Pattern[str]]]) -> list[Symbol]:
    found: list[Symbol] = []
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            name = match.group("name")
            found.append(Symbol(name=name, kind=kind, line=_line(text, match.start())))
    found.sort(key=lambda s: (s.line, s.name, s.kind))
    seen: set[tuple[str, str, int]] = set()
    out: list[Symbol] = []
    for item in found:
        key = (item.name, item.kind, item.line)
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def parse_dart(text: str) -> ParsedFile:
    symbols = _regex_symbols(text, [
        ("class", re.compile(r"(?m)^\s*(?:abstract\s+|base\s+|final\s+|sealed\s+)?class\s+(?P<name>[A-Za-z_]\w*)")),
        ("mixin", re.compile(r"(?m)^\s*mixin\s+(?P<name>[A-Za-z_]\w*)")),
        ("enum", re.compile(r"(?m)^\s*enum\s+(?P<name>[A-Za-z_]\w*)")),
        ("function", re.compile(r"(?m)^\s*(?:[A-Za-z_<>,?\[\]\s]+\s+)?(?P<name>[A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:async\s*)?(?:=>|\{)")),
    ])
    imports = [m.group(1) for m in re.finditer(r"(?m)^\s*(?:import|export)\s+['\"]([^'\"]+)['\"]", text)]
    return ParsedFile(tuple(symbols), _dedupe(imports))


def parse_typescript(text: str) -> ParsedFile:
    symbols = _regex_symbols(text, [
        ("class", re.compile(r"(?m)^\s*(?:export\s+)?(?:default\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)")),
        ("interface", re.compile(r"(?m)^\s*(?:export\s+)?interface\s+(?P<name>[A-Za-z_$][\w$]*)")),
        ("type", re.compile(r"(?m)^\s*(?:export\s+)?type\s+(?P<name>[A-Za-z_$][\w$]*)\s*=")),
        ("function", re.compile(r"(?m)^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)")),
        ("function", re.compile(r"(?m)^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^\n]*\)\s*=>")),
    ])
    imports = [m.group(1) for m in re.finditer(r"(?m)(?:from\s+|import\s*\(\s*|require\s*\(\s*)['\"]([^'\"]+)['\"]", text)]
    return ParsedFile(tuple(symbols), _dedupe(imports))


def parse_rust(text: str) -> ParsedFile:
    symbols = _regex_symbols(text, [
        ("struct", re.compile(r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?struct\s+(?P<name>[A-Za-z_]\w*)")),
        ("enum", re.compile(r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?enum\s+(?P<name>[A-Za-z_]\w*)")),
        ("trait", re.compile(r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?trait\s+(?P<name>[A-Za-z_]\w*)")),
        ("function", re.compile(r"(?m)^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+(?P<name>[A-Za-z_]\w*)")),
    ])
    imports = [m.group(1).strip() for m in re.finditer(r"(?m)^\s*use\s+([^;]+);", text)]
    return ParsedFile(tuple(symbols), _dedupe(imports))


def parse_jvm(text: str, kotlin: bool) -> ParsedFile:
    patterns = [
        ("class", re.compile(r"(?m)^\s*(?:public\s+|private\s+|protected\s+|internal\s+|open\s+|data\s+|sealed\s+|abstract\s+|final\s+)*class\s+(?P<name>[A-Za-z_]\w*)")),
        ("interface", re.compile(r"(?m)^\s*(?:public\s+|private\s+|protected\s+|internal\s+)*interface\s+(?P<name>[A-Za-z_]\w*)")),
        ("enum", re.compile(r"(?m)^\s*(?:public\s+|private\s+|protected\s+|internal\s+)*enum(?:\s+class)?\s+(?P<name>[A-Za-z_]\w*)")),
    ]
    if kotlin:
        patterns.append(("function", re.compile(r"(?m)^\s*(?:public\s+|private\s+|protected\s+|internal\s+|suspend\s+|inline\s+)*fun\s+(?P<name>[A-Za-z_]\w*)")))
    imports = [m.group(1) for m in re.finditer(r"(?m)^\s*import\s+([\w.*]+)", text)]
    return ParsedFile(tuple(_regex_symbols(text, patterns)), _dedupe(imports))


def parse_generic(text: str, language: str) -> ParsedFile:
    if language == "go":
        patterns = [
            ("type", re.compile(r"(?m)^\s*type\s+(?P<name>[A-Za-z_]\w*)\s+")),
            ("function", re.compile(r"(?m)^\s*func\s+(?:\([^)]*\)\s*)?(?P<name>[A-Za-z_]\w*)\s*\(")),
        ]
        imports = [m.group(1) for m in re.finditer(r"(?m)^\s*import\s+(?:\w+\s+)?['\"]([^'\"]+)['\"]", text)]
        return ParsedFile(tuple(_regex_symbols(text, patterns)), _dedupe(imports))
    if language in {"c", "cpp"}:
        patterns = [
            ("class", re.compile(r"(?m)^\s*(?:class|struct)\s+(?P<name>[A-Za-z_]\w*)")),
            ("function", re.compile(r"(?m)^\s*[\w:<>,~*&\s]+\s+(?P<name>[A-Za-z_]\w*)\s*\([^;]*\)\s*\{")),
        ]
        imports = [m.group(1) for m in re.finditer(r"(?m)^\s*#include\s*[<\"]([^>\"]+)[>\"]", text)]
        return ParsedFile(tuple(_regex_symbols(text, patterns)), _dedupe(imports))
    return ParsedFile()


def parse_file(text: str, language: str) -> ParsedFile:
    if language == "python":
        return parse_python(text)
    if language == "dart":
        return parse_dart(text)
    if language in {"typescript", "javascript"}:
        return parse_typescript(text)
    if language == "rust":
        return parse_rust(text)
    if language == "java":
        return parse_jvm(text, False)
    if language == "kotlin":
        return parse_jvm(text, True)
    return parse_generic(text, language)
