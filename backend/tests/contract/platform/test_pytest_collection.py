import tomllib
from pathlib import Path


def test_pytest_uses_path_isolated_imports_for_duplicate_module_names() -> None:
    pyproject = Path(__file__).resolve().parents[3] / "pyproject.toml"
    config = tomllib.loads(pyproject.read_text())

    assert "--import-mode=importlib" in config["tool"]["pytest"]["ini_options"]["addopts"]
