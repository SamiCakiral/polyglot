import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def migration_config() -> Config:
    package_root = Path(__file__).resolve().parents[1]
    packaged_directory = package_root / "migrations"
    if packaged_directory.is_dir():
        config_path = packaged_directory / "alembic.ini"
        script_location = packaged_directory
    else:
        backend_root = Path(__file__).resolve().parents[3]
        config_path = backend_root / "alembic.ini"
        script_location = backend_root / "migrations"
    config = Config(str(config_path))
    config.set_main_option("script_location", str(script_location))
    return config


def round_trip() -> None:
    config = migration_config()
    variable = "POLYGLOT_ALLOW_DESTRUCTIVE_IDENTITY_DOWNGRADE"
    previous = os.environ.get(variable)
    os.environ[variable] = "true"
    try:
        command.downgrade(config, "base")
    finally:
        if previous is None:
            os.environ.pop(variable, None)
        else:
            os.environ[variable] = previous
    command.upgrade(config, "head")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run packaged Polyglot migrations")
    parser.add_argument("operation", choices=("upgrade", "downgrade", "round-trip"))
    arguments = parser.parse_args(argv)
    config = migration_config()
    if arguments.operation == "round-trip":
        round_trip()
    elif arguments.operation == "upgrade":
        command.upgrade(config, "head")
    else:
        command.downgrade(config, "base")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
