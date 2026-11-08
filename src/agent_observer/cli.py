import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import Project, load_config
from .installation import initialize, runtime_check
from .paths import config_path
from .registry import register
from .server import create_server
from .service import Observer


def main():
    parser = argparse.ArgumentParser(description="Read-only Project Agent Observer")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, default=config_path())
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve")
    serve.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    check = sub.add_parser(
        "doctor", aliases=["check"], help="Check runtime/configuration; optionally inspect a project"
    )
    check.add_argument("--project-id")
    sub.add_parser(
        "list-projects", aliases=["projects"], help="Local administrator-only registration inventory"
    )
    sub.add_parser("version", help="Print the installed version without loading configuration")
    init = sub.add_parser("init", help="Create an empty registry; never overwrite existing configuration")
    init.add_argument("--port", type=int, default=8765)
    init.add_argument("--codex-root", type=Path)
    init.add_argument("--claude-root", type=Path)
    registration = sub.add_parser(
        "register",
        aliases=["register-project"],
        help="Register an absolute project path locally, never an MCP tool",
    )
    registration.add_argument("--id", required=True)
    registration.add_argument("--name", required=True)
    registration.add_argument("--path", required=True, type=Path)
    registration.add_argument("--description", default="")
    args = parser.parse_args()
    try:
        if args.command == "version":
            print(__version__)
            return
        if args.command == "init":
            created = initialize(
                args.config, port=args.port, codex_root=args.codex_root, claude_root=args.claude_root
            )
            print(
                json.dumps(
                    {
                        "config_created": created,
                        "config": str(args.config.expanduser()),
                        "registered_projects": len(load_config(args.config).projects),
                    }
                )
            )
            return
        if args.command in ("register", "register-project"):
            register(
                args.config.expanduser(),
                Project(
                    project_id=args.id,
                    project_name=args.name,
                    absolute_path=args.path,
                    description=args.description,
                ),
            )
            print(json.dumps({"registered": args.id, "restart_required": True}))
            return
        config = load_config(args.config)
        if args.command == "serve":
            create_server(config).run(transport=args.transport)
        elif args.command in ("list-projects", "projects"):
            print(
                json.dumps(
                    [
                        {"project_id": p.project_id, "project_name": p.project_name, "enabled": p.enabled}
                        for p in config.projects
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
        elif args.project_id:
            print(
                json.dumps(
                    Observer(config).call("get_project_overview", project_id=args.project_id),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(
                json.dumps(
                    {"config_valid": True, "registered_projects": len(config.projects), **runtime_check()}
                )
            )
    except (ValueError, OSError) as exc:
        print(f"Observer: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
