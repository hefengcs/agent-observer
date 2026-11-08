import tomllib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .paths import config_path

DEFAULT_CONFIG = config_path()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Project(StrictModel):
    project_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    project_name: str = Field(max_length=200)
    absolute_path: Path
    description: str = Field(default="", max_length=2000)
    enabled: bool = True

    @field_validator("absolute_path")
    @classmethod
    def root(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute() or not value.is_dir():
            raise ValueError("Project must be an existing absolute directory")
        value = value.resolve(strict=True)
        if value in (Path("/"), Path.home().resolve()):
            raise ValueError("Register a specific project, not the machine or home directory")
        return value


class Limits(StrictModel):
    max_file_bytes: int = Field(default=2_000_000, ge=1024, le=20_000_000)
    max_session_bytes: int = Field(default=256_000_000, ge=1024, le=1_000_000_000)
    max_jsonl_line_bytes: int = Field(default=4_000_000, ge=1024, le=20_000_000)
    max_output_chars: int = Field(default=24000, ge=1024, le=100000)
    max_files: int = Field(default=20000, ge=1, le=100000)
    max_history_files: int = Field(default=20000, ge=1, le=100000)


class History(StrictModel):
    codex_root: Path = Path.home() / ".codex/sessions"
    claude_root: Path = Path.home() / ".claude/projects"

    @field_validator("codex_root", "claude_root")
    @classmethod
    def absolute_history(cls, value: Path) -> Path:
        value = value.expanduser()
        if not value.is_absolute():
            raise ValueError("History directories must be absolute paths (or start with ~)")
        return value.resolve()


class HTTP(StrictModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1024, le=65535)
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_origins: list[str] = Field(default_factory=list)

    @field_validator("host")
    @classmethod
    def loopback(cls, value: str) -> str:
        if value != "127.0.0.1":
            raise ValueError("Phase 1 HTTP binds only to 127.0.0.1")
        return value


class Config(StrictModel):
    projects: list[Project] = Field(default_factory=list)
    history: History = Field(default_factory=History)
    limits: Limits = Field(default_factory=Limits)
    http: HTTP = Field(default_factory=HTTP)

    @model_validator(mode="after")
    def unique(self):
        if len({p.project_id for p in self.projects}) != len(self.projects):
            raise ValueError("Duplicate project_id")
        if len({p.absolute_path for p in self.projects}) != len(self.projects):
            raise ValueError("Duplicate project root")
        return self

    def project(self, project_id: str) -> Project:
        for project in self.projects:
            if project.project_id == project_id and project.enabled:
                return project
        raise ValueError("Unknown or disabled project_id")


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    with path.expanduser().open("rb") as stream:
        return Config.model_validate(tomllib.load(stream))
