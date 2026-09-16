from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any


def _read(root: Path, name: str) -> str | None:
    path = root / name
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _yaml_dependency_names(text: str) -> list[str]:
    names: list[str] = []
    in_section = False
    for line in text.splitlines():
        if re.match(r"^(dependencies|dev_dependencies):\s*$", line):
            in_section = True
            continue
        if not in_section:
            continue
        if line and not line.startswith(" ") and not line.startswith("\t"):
            in_section = False
            continue
        match = re.match(r"^\s{2,}([A-Za-z0-9_\-]+):", line)
        if match:
            names.append(match.group(1))
    return list(dict.fromkeys(names))[:40]


def detect_project(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": root.name,
        "type": "unknown",
        "languages": [],
        "frameworks": [],
        "dependencies": [],
        "manifests": [],
    }

    pubspec = _read(root, "pubspec.yaml")
    if pubspec is not None:
        result["manifests"].append("pubspec.yaml")
        result["languages"].append("dart")
        result["type"] = "flutter" if re.search(r"(?m)^\s*flutter:\s*$", pubspec) else "dart"
        if result["type"] == "flutter":
            result["frameworks"].append("flutter")
        result["dependencies"].extend(_yaml_dependency_names(pubspec))
        name_match = re.search(r"(?m)^name:\s*([^\s#]+)", pubspec)
        if name_match:
            result["name"] = name_match.group(1)

    package = _read(root, "package.json")
    if package is not None:
        result["manifests"].append("package.json")
        if "javascript" not in result["languages"]:
            result["languages"].append("typescript/javascript")
        if result["type"] == "unknown":
            result["type"] = "node"
        try:
            data = json.loads(package)
            if isinstance(data.get("name"), str):
                result["name"] = data["name"]
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
            for candidate in ("react", "next", "vue", "svelte", "electron", "express"):
                if candidate in deps:
                    result["frameworks"].append(candidate)
            result["dependencies"].extend(list(deps)[:40])
        except (json.JSONDecodeError, TypeError):
            pass

    pyproject = _read(root, "pyproject.toml")
    if pyproject is not None:
        result["manifests"].append("pyproject.toml")
        result["languages"].append("python")
        if result["type"] == "unknown":
            result["type"] = "python"
        try:
            data = tomllib.loads(pyproject)
            project = data.get("project", {})
            if isinstance(project.get("name"), str):
                result["name"] = project["name"]
            deps = project.get("dependencies", [])
            if isinstance(deps, list):
                result["dependencies"].extend(str(x).split(" ", 1)[0] for x in deps[:40])
        except tomllib.TOMLDecodeError:
            pass

    cargo = _read(root, "Cargo.toml")
    if cargo is not None:
        result["manifests"].append("Cargo.toml")
        result["languages"].append("rust")
        if result["type"] == "unknown":
            result["type"] = "rust"
        try:
            data = tomllib.loads(cargo)
            package_data = data.get("package", {})
            if isinstance(package_data.get("name"), str):
                result["name"] = package_data["name"]
            deps = data.get("dependencies", {})
            if isinstance(deps, dict):
                result["dependencies"].extend(list(deps)[:40])
        except tomllib.TOMLDecodeError:
            pass

    for gradle in ("build.gradle.kts", "build.gradle"):
        if (root / gradle).is_file():
            result["manifests"].append(gradle)
            result["languages"].append("kotlin/java")
            if result["type"] == "unknown":
                result["type"] = "jvm"
            break

    result["languages"] = list(dict.fromkeys(result["languages"]))
    result["frameworks"] = list(dict.fromkeys(result["frameworks"]))
    result["dependencies"] = list(dict.fromkeys(result["dependencies"]))[:40]
    return result
