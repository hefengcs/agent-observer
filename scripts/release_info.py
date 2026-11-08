#!/usr/bin/env python3
"""Validate the stable release tag against package and runtime versions."""

import argparse
import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version(root=ROOT):
    value = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    module = ast.parse((root / "src/agent_observer/__init__.py").read_text())
    runtime = next(
        ast.literal_eval(node.value)
        for node in module.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)
    )
    if value != runtime or not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("pyproject and runtime version must match stable x.y.z")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    value = version()
    if args.tag is not None and args.tag != "v" + value:
        raise SystemExit(f"Tag must equal v{value}")
    if args.github_output:
        with args.github_output.open("a") as stream:
            stream.write(f"version={value}\n")
    print(value)


if __name__ == "__main__":
    main()
