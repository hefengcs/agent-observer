#!/usr/bin/env python3
"""Exercise a tagged Git clone install, an upgrade, and data-preserving uninstall."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from audit_repository import audit
from release_info import version

ROOT = Path(__file__).resolve().parents[1]


def main():
    value = version()
    with tempfile.TemporaryDirectory(prefix="observer-git-install-") as directory:
        temp = Path(directory).resolve()
        source = temp / "public-source"
        source.mkdir()
        for relative in audit():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("AGENT_OBSERVER_", "GIT_"))
            and k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
        }
        env.update(
            PYTHON=sys.executable,
            XDG_DATA_HOME=str(temp / "xdg-data"),
            XDG_CONFIG_HOME=str(temp / "xdg-config"),
            XDG_STATE_HOME=str(temp / "xdg-state"),
            AGENT_OBSERVER_BIN_DIR=str(temp / "bin"),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
        )

        def run(args, cwd=None, ok=True):
            r = subprocess.run([str(a) for a in args], cwd=cwd, env=env, capture_output=True, text=True)
            if ok and r.returncode:
                raise RuntimeError(f"Git install verification failed: {args[0]}\n{r.stderr[-4000:]}")
            return r

        run(["git", "init", "-b", "main"], source)
        run(["git", "add", "."], source)
        run(
            [
                "git",
                "-c",
                "user.name=Synthetic",
                "-c",
                "user.email=fixture@example.test",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                "commit",
                "-m",
                "Synthetic release",
            ],
            source,
        )
        denied = run(["sh", "scripts/install.sh"], source, ok=False)
        assert denied.returncode and "--allow-unreleased" in denied.stderr
        run(["git", "tag", "v" + value], source)
        checkout = temp / "clone"
        run(["git", "clone", "--branch", "v" + value, "--depth", "1", source.as_uri(), checkout])
        run(["sh", "scripts/install.sh"], checkout)
        prefix = temp / "xdg-data/agent-observer"
        cli = temp / "bin/agent-observer"
        assert run([cli, "version"]).stdout.strip() == value
        run([cli, "doctor"])
        project = temp / "synthetic-project"
        project.mkdir()
        run([cli, "register", "--id", "example", "--name", "Synthetic", "--path", project])
        assert "example" in run([cli, "list-projects"]).stdout
        config = temp / "xdg-config/agent_observer/config.toml"
        before = config.read_bytes()
        run(["sh", "scripts/install.sh", "--upgrade"], checkout)
        assert config.read_bytes() == before
        run([cli, "doctor"])
        run(["sh", prefix / "bin/uninstall.sh"])
        assert not prefix.exists() and not cli.is_symlink()
        assert config.read_bytes() == before and project.is_dir()
    result = {
        "tagged_clone_install": "passed",
        "default_main_install_rejected": True,
        "xdg_locations": "passed",
        "canonical_cli": "passed",
        "upgrade_preserves_registration": "passed",
        "uninstall_preserves_configuration_and_projects": "passed",
    }
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/repository-install.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
