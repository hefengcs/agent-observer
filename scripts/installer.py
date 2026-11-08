#!/usr/bin/env python3
"""User-local install/upgrade/uninstall; never imported into the MCP server."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def base(variable, fallback):
    value = os.environ.get(variable)
    return Path(value) if value and Path(value).is_absolute() else Path.home() / fallback


def locations():
    prefix = Path(
        os.environ.get("AGENT_OBSERVER_PREFIX") or base("XDG_DATA_HOME", ".local/share") / "agent-observer"
    ).expanduser()
    config = Path(
        os.environ.get("AGENT_OBSERVER_CONFIG")
        or base("XDG_CONFIG_HOME", ".config") / "agent_observer/config.toml"
    ).expanduser()
    bindir = Path(os.environ.get("AGENT_OBSERVER_BIN_DIR") or Path.home() / ".local/bin").expanduser()
    if not all(p.is_absolute() for p in (prefix, config, bindir)):
        raise ValueError("Installation, config and bin paths must be absolute")
    if prefix.is_symlink() or prefix.resolve() in (Path("/"), Path.home().resolve()):
        raise ValueError("Unsafe installation prefix")
    prefix = prefix.resolve()
    if config.resolve().is_relative_to(prefix):
        raise ValueError("Configuration must be outside the install prefix so uninstall preserves it")
    return prefix, config, bindir


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, **kwargs)


def source_version(root, allow_unreleased=False):
    version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Installer requires a stable x.y.z version")
    if not allow_unreleased:
        try:
            tags = subprocess.check_output(
                ["git", "-C", str(root), "tag", "--points-at", "HEAD"], text=True
            ).splitlines()
            dirty = subprocess.check_output(
                ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"], text=True
            )
        except subprocess.CalledProcessError as exc:
            raise ValueError(
                "Source install requires an exact release tag; use a release Bundle for archives"
            ) from exc
        if "v" + version not in tags or dirty:
            raise ValueError(
                f"Checkout a clean v{version} release tag first. Development/CI only: --allow-unreleased"
            )
    return version


def active_service():
    if sys.platform == "linux" and shutil.which("systemctl"):
        return (
            subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", "agent-observer.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
    if sys.platform == "darwin":
        return (
            subprocess.run(
                ["launchctl", "print", f"gui/{os.getuid()}/local.agent-observer.http"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
    return False


def uninstall(prefix):
    marker = prefix / ".agent-observer-install"
    if not marker.is_file():
        raise ValueError("Refusing to remove an installation without the Observer marker")
    try:
        metadata = json.loads(marker.read_text())
    except ValueError as exc:
        raise ValueError("Legacy installation: reinstall once to record uninstall ownership") from exc
    if metadata.get("prefix") != str(prefix):
        raise ValueError("Installation marker does not match this prefix")
    if active_service():
        raise ValueError("Stop and disable the Observer service before uninstalling")
    launcher = Path(metadata["launcher"])
    if launcher.is_symlink() and launcher.resolve() == (prefix / "venv/bin/agent-observer").resolve():
        launcher.unlink()
    shutil.rmtree(prefix)
    print("Observer removed. Configuration, registrations, project files, Agent history and logs preserved.")


def install(args, prefix, config, bindir):
    if prefix == ROOT.resolve():
        raise ValueError("Installation prefix must be separate from the source tree")
    if sys.version_info < (3, 11):
        raise ValueError("Python 3.11+ required; set PYTHON to its executable")
    if not shutil.which("git"):
        raise ValueError("Git is required")
    if active_service():
        raise ValueError(
            "Stop the Observer service before installing/upgrading, then restart it after doctor"
        )
    wheels = list((ROOT / "wheels").glob("agent_observer-*.whl"))
    if wheels:
        if len(wheels) != 1:
            raise ValueError("Expected exactly one Observer wheel")
        package = wheels[0]
        with zipfile.ZipFile(package) as archive:
            metadata = next(n for n in archive.namelist() if n.endswith(".dist-info/METADATA"))
            version = re.search(r"^Version: (.+)$", archive.read(metadata).decode(), re.M)[1]
    elif (ROOT / "pyproject.toml").is_file():
        version = source_version(ROOT, args.allow_unreleased)
        package = ROOT
    else:
        raise ValueError("Use install.sh from a tagged repository root or an extracted deployment Bundle")
    marker = prefix / ".agent-observer-install"
    if prefix.exists() and any(prefix.iterdir()) and not marker.is_file():
        raise ValueError("Refusing to overwrite a nonempty directory without an Observer marker")
    launcher = bindir / "agent-observer"
    expected = prefix / "venv/bin/agent-observer"
    if launcher.exists() or launcher.is_symlink():
        if not launcher.is_symlink() or launcher.resolve() != expected.resolve():
            raise ValueError(f"Another program owns {launcher}; choose AGENT_OBSERVER_BIN_DIR")
    prefix.mkdir(parents=True, exist_ok=True, mode=0o700)
    # The marker also allows a failed first install to be retried safely.
    if not marker.exists():
        marker.write_text(json.dumps({"prefix": str(prefix), "launcher": str(launcher)}))
    python = prefix / "venv/bin/python"
    if not python.exists():
        run([sys.executable, "-m", "venv", prefix / "venv"])
    pip = [python, "-m", "pip", "install", "--upgrade"]
    wheelhouse = os.environ.get("AGENT_OBSERVER_WHEELHOUSE")
    if wheelhouse:
        pip += ["--no-index", "--find-links", wheelhouse]
    run([*pip, package])
    run([expected, "--config", config, "init"])
    run([expected, "--config", config, "doctor"])
    for name in ("bin", "docs", "deploy", "examples"):
        (prefix / name).mkdir(exist_ok=True)
    for name in ("run_http.sh", "run_stdio.sh", "manage_http.py", "installer.py", "uninstall.sh"):
        shutil.copy2(ROOT / "scripts" / name, prefix / "bin" / name)
    # Keep a scripts entry point for invoking this installer from the installed tree.
    (prefix / "scripts").mkdir(exist_ok=True)
    for name in ("installer.py", "uninstall.sh"):
        shutil.copy2(ROOT / "scripts" / name, prefix / "scripts" / name)
    for name in ("docs", "deploy", "examples"):
        shutil.copytree(ROOT / name, prefix / name, dirs_exist_ok=True)
    for name in ("run_http.sh", "run_stdio.sh", "uninstall.sh"):
        (prefix / "bin" / name).chmod(0o755)
    bindir.mkdir(parents=True, exist_ok=True)
    if not launcher.is_symlink():
        launcher.symlink_to(expected)
    marker.write_text(
        json.dumps({"prefix": str(prefix), "launcher": str(launcher), "version": version}, indent=2) + "\n"
    )
    marker.chmod(0o600)
    print(f"Installed Agent Observer {version} in {prefix}")
    print(f"CLI: {launcher}; add {bindir} to PATH if necessary. No shell startup file was changed.")
    print(f"Configuration retained at {config}; no project or service was automatically registered.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unreleased",
        action="store_true",
        help="Explicit opt-in for local development/CI source installs",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Install the selected pinned version, preserving all configuration",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove this installation and owned launcher; keep all user data",
    )
    args = parser.parse_args()
    os.umask(0o077)
    try:
        prefix, config, bindir = locations()
        if args.uninstall:
            uninstall(prefix)
        else:
            install(args, prefix, config, bindir)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Installer: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
