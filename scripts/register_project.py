#!/usr/bin/env python3
"""Compatibility wrapper; installed users can use agent-observer register-project."""

import argparse
from pathlib import Path

from agent_observer.config import DEFAULT_CONFIG, Project
from agent_observer.registry import register


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--description", default="")
    args = parser.parse_args()
    project = Project(
        project_id=args.id, project_name=args.name, absolute_path=args.path, description=args.description
    )
    register(args.config, project)
    print(f"Registered {project.project_id}; restart Observer to reload configuration")


if __name__ == "__main__":
    main()
