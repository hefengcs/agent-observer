#!/usr/bin/env python3
"""Build only audited, indexed public source into the four release assets."""

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from audit_repository import audit
from release_info import version

ROOT = Path(__file__).resolve().parents[1]


def main():
    value = version()
    paths = audit()
    target = ROOT / "dist" / value
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="observer-release-") as temp:
        source = Path(temp) / "source"
        source.mkdir()
        for relative in paths:
            destination = source / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        subprocess.run([sys.executable, "-m", "build", "--outdir", str(target), str(source)], check=True)
        wheel = target / f"agent_observer-{value}-py3-none-any.whl"
        sdist = target / f"agent_observer-{value}.tar.gz"
        bundle = target / f"agent-observer-{value}-bundle.tar.gz"
        stage = Path(temp) / f"agent-observer-{value}"
        stage.mkdir()
        for name in ("scripts", "docs", "examples", "deploy", "tests", "reports"):
            shutil.copytree(source / name, stage / name)
        for name in (
            "README.md",
            "DEPLOYMENT.md",
            "CONNECTION.md",
            "config.example.toml",
            "requirements.lock.txt",
        ):
            shutil.copy2(source / name, stage / name)
        (stage / "wheels").mkdir()
        shutil.copy2(wheel, stage / "wheels" / wheel.name)
        (stage / "source").mkdir()
        shutil.copy2(sdist, stage / "source" / sdist.name)
        with tarfile.open(bundle, "w:gz") as archive:
            archive.add(stage, arcname=stage.name)
    (target / "SHA256SUMS").write_text(
        "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in (wheel, sdist, bundle))
    )
    print(f"Release ready: {target}")


if __name__ == "__main__":
    main()
