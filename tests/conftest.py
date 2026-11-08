import pytest
from synthetic_project import claude, codex, create_environment, initialize_git, jsonl  # noqa: F401

from agent_observer.service import Observer


@pytest.fixture
def env(tmp_path):
    config, root, other = create_environment(tmp_path)
    return Observer(config), config, root, other


@pytest.fixture
def repo(env):
    observer, config, root, _ = env
    first, commit = initialize_git(root)
    return observer, config, root, first, commit
