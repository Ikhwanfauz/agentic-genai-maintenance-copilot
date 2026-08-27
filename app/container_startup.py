import os
import subprocess
import sys
from collections.abc import Mapping, Sequence

INITIALIZE_APPLICATION_DATA_ENV = "INITIALIZE_APPLICATION_DATA"
TRUE_VALUES = frozenset(
    {
        "1",
        "true",
        "yes",
    }
)
FALSE_VALUES = frozenset(
    {
        "0",
        "false",
        "no",
    }
)


def initialization_is_enabled(
    environment: Mapping[str, str],
) -> bool:
    raw_value = environment.get(
        INITIALIZE_APPLICATION_DATA_ENV,
        "false",
    )
    normalized_value = raw_value.strip().lower()

    if normalized_value in TRUE_VALUES:
        return True

    if normalized_value in FALSE_VALUES:
        return False

    raise ValueError(
        f"{INITIALIZE_APPLICATION_DATA_ENV} must be one of {sorted(TRUE_VALUES | FALSE_VALUES)}."
    )


def build_initialization_commands() -> tuple[
    tuple[str, ...],
    ...,
]:
    return (
        (
            sys.executable,
            "-m",
            "alembic",
            "upgrade",
            "head",
        ),
        (
            sys.executable,
            "-m",
            "app.db.seed",
        ),
        (
            sys.executable,
            "-m",
            "app.rag.indexer",
        ),
    )


def initialize_application_data() -> None:
    for command in build_initialization_commands():
        subprocess.run(
            command,
            check=True,
        )


def main(
    arguments: Sequence[str] | None = None,
) -> None:
    command = list(sys.argv[1:] if arguments is None else arguments)

    if not command:
        raise SystemExit("A container application command is required.")

    if initialization_is_enabled(os.environ):
        initialize_application_data()

    os.execvp(
        command[0],
        command,
    )


if __name__ == "__main__":
    main()
