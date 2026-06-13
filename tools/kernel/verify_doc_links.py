#!/usr/bin/env python3
"""README と docs 内の Markdown ローカルリンクを検証する。"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def is_local_link(target: str) -> bool:
    if not target or target.startswith(("http://", "https://", "mailto:", "#")):
        return False
    if "://" in target:
        return False
    return True


def resolve_link(source: Path, target: str, root: Path) -> Path:
    clean = target.split("#", 1)[0].strip()
    if not clean:
        return source
    candidate = (source.parent / clean).resolve()
    if candidate.exists():
        return candidate
    return (root / clean).resolve()


def collect_markdown_files(paths: list[Path], root: Path) -> tuple[list[Path], list[str]]:
    files: list[Path] = []
    errors: list[str] = []

    for path in paths:
        if not path.exists():
            errors.append(f"input path does not exist: {path}")
            continue
        if path.is_file():
            if path.suffix.lower() != ".md":
                errors.append(f"input is not a Markdown file: {path}")
            else:
                files.append(path.resolve())
            continue
        if path.is_dir():
            files.extend(sorted(path.rglob("*.md")))
            continue
        errors.append(f"input path is not a file or directory: {path}")

    unique_files = sorted(set(files))
    return unique_files, errors


def verify_files(files: list[Path], root: Path) -> list[str]:
    errors: list[str] = []
    for md_file in files:
        text = md_file.read_text(encoding="utf-8")
        for match in LINK_RE.finditer(text):
            target = match.group(1).strip()
            if not is_local_link(target):
                continue
            resolved = resolve_link(md_file, target, root)
            if not resolved.exists():
                rel = md_file.relative_to(root)
                errors.append(f"{rel}: broken link -> {target}")
    return errors


def run_check(paths: list[Path], root: Path) -> tuple[int, list[str], int]:
    files, input_errors = collect_markdown_files(paths, root)
    if not files:
        input_errors.append("no Markdown files to verify")
    link_errors = verify_files(files, root) if files else []
    all_errors = input_errors + link_errors
    return (0 if not all_errors else 1, all_errors, len(files))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify local Markdown links.")
    parser.add_argument("paths", nargs="+", help="Markdown files or directories")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root")
    args = parser.parse_args(argv)

    root = args.root.resolve()
    inputs = [Path(p) for p in args.paths]
    exit_code, errors, file_count = run_check(inputs, root)

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"link check failed: {len(errors)} error(s)", file=sys.stderr)
        return exit_code

    print(f"link check OK: {file_count} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
