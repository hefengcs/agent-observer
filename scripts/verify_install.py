#!/usr/bin/env python3
"""Verify bundle installation into an isolated, non-editable venv outside the source tree."""

import argparse
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile
import tomllib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path("reports/clean-install.json"))
    args = parser.parse_args()
    report_path = args.report.resolve()
    with tempfile.TemporaryDirectory(prefix="observer-clean-install-") as directory:
        temp = Path(directory).resolve()
        with tarfile.open(args.bundle.resolve()) as archive:
            for member in archive.getmembers():
                if not (member.isfile() or member.isdir()) or not (
                    temp / member.name
                ).resolve().is_relative_to(temp):
                    raise ValueError("Unsafe release archive member")
            # Python 3.11 patch versions before 3.11.8 lack the extraction filter.
            # All members were independently constrained to in-root regular files/directories above.
            import inspect

            if "filter" in inspect.signature(archive.extractall).parameters:
                archive.extractall(temp, filter="data")
            else:
                archive.extractall(temp)
        bundle = next(p for p in temp.iterdir() if p.is_dir())
        prefix = temp / "isolated install"
        config = temp / "empty-default.toml"
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV") and not k.startswith("AGENT_OBSERVER_")
        }
        env.update(
            PYTHON=sys.executable,
            AGENT_OBSERVER_PREFIX=str(prefix),
            AGENT_OBSERVER_CONFIG=str(config),
            AGENT_OBSERVER_BIN_DIR=str(temp / "bin"),
        )

        def run(command):
            result = subprocess.run(command, cwd=temp, env=env, capture_output=True, text=True)
            if result.returncode:
                # Diagnostic output is local-only and contains synthetic test data.
                raise RuntimeError(f"Clean-install command failed: {command[0]}\n{result.stderr[-4000:]}")
            return result

        run(["sh", str(bundle / "scripts/install.sh")])
        assert tomllib.loads(config.read_text())["projects"] == []
        before = config.read_bytes()
        run(["sh", str(bundle / "scripts/install.sh")])
        assert config.read_bytes() == before
        python = prefix / "venv/bin/python"
        run([str(python), "-m", "pip", "check"])
        run(
            [
                str(python),
                "-I",
                str(bundle / "scripts/installed_acceptance.py"),
                "--bundle",
                str(bundle),
                "--prefix",
                str(prefix),
                "--sandbox",
                str(temp / "testdata"),
                "--report",
                str(temp / "acceptance.json"),
            ]
        )
        result = json.loads((temp / "acceptance.json").read_text())
        result.update(
            platform=platform.system(),
            python=platform.python_version(),
            clean_venv=True,
            installer_repeated_without_config_overwrite=True,
            default_projects_empty=True,
            source_checkout_required=False,
            runtime_dependencies="resolved and pip check passed",
            linux_runtime_test="not performed" if sys.platform != "linux" else "passed",
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
