from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from unlawful.config import ConfigError, load_config
from unlawful.project_templates import apply_template

VALID_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
STANDARDS = {11, 14, 17, 20, 23, 26}
USAGE = "Usage: ul cpp <project-name> [--std 11|14|17|20|23|26] [--git]"


def _parse(args: list[str]) -> tuple[str, int | None, bool] | None:
    if not args or not VALID_NAME.fullmatch(args[0]):
        return None
    standard: int | None = None
    initialize_git = False
    index = 1
    while index < len(args):
        if args[index] == "--git":
            initialize_git = True
            index += 1
        elif args[index] == "--std" and index + 1 < len(args):
            try:
                standard = int(args[index + 1])
            except ValueError:
                return None
            if standard not in STANDARDS:
                return None
            index += 2
        else:
            return None
    return args[0], standard, initialize_git


def main(argv: Sequence[str] | None = None) -> int:
    parsed = _parse(list(sys.argv[1:] if argv is None else argv))
    if parsed is None:
        print(USAGE, file=sys.stderr)
        return 2
    name, requested_standard, git_flag = parsed
    try:
        settings = load_config()["projects"]["cpp"]
    except ConfigError as error:
        print(f"unlaw cpp: {error}", file=sys.stderr)
        return 2
    project = Path(name)
    if project.exists():
        print(f"unlaw cpp: Destination already exists: {project}", file=sys.stderr)
        return 1
    standard = requested_standard or settings["standard"]
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.cpp").write_text(
        '#include <iostream>\n\nint main() {\n    std::cout << "Hello from Unlaw\\n";\n    return 0;\n}\n',
        encoding="utf-8",
    )
    (project / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\n"
        f"project({name} LANGUAGES CXX)\n\n"
        f"set(CMAKE_CXX_STANDARD {standard})\n"
        "set(CMAKE_CXX_STANDARD_REQUIRED ON)\n\n"
        f"add_executable({name} src/main.cpp)\n",
        encoding="utf-8",
    )
    (project / ".gitignore").write_text("build/\n.DS_Store\n", encoding="utf-8")
    apply_template(
        "cpp",
        project,
        {"project_name": name, "cpp_standard": str(standard)},
    )
    if git_flag or settings["initialize_git"]:
        try:
            code = subprocess.run(["git", "init", str(project)], check=False).returncode
        except OSError as error:
            print(f"unlaw cpp: {error}", file=sys.stderr)
            return 1
        if code:
            return code
    print(f"Created C++ project: {project} (C++{standard})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
