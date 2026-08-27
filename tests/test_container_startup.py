import subprocess
import sys

import pytest

from app import container_startup


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1", True),
        ("true", True),
        ("YES", True),
        ("0", False),
        ("false", False),
        ("No", False),
    ],
)
def test_initialization_flag_accepts_declared_values(
    value: str,
    expected: bool,
) -> None:
    environment = {container_startup.INITIALIZE_APPLICATION_DATA_ENV: (value)}

    assert container_startup.initialization_is_enabled(environment) is expected


def test_initialization_flag_defaults_to_disabled() -> None:
    assert container_startup.initialization_is_enabled({}) is False


def test_initialization_flag_rejects_unknown_value() -> None:
    with pytest.raises(
        ValueError,
        match="INITIALIZE_APPLICATION_DATA",
    ):
        container_startup.initialization_is_enabled(
            {container_startup.INITIALIZE_APPLICATION_DATA_ENV: ("tru")}
        )


def test_initialization_commands_are_ordered() -> None:
    assert container_startup.build_initialization_commands() == (
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


def test_initialization_runs_every_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_commands: list[tuple[tuple[str, ...], bool]] = []

    def record_command(
        command: tuple[str, ...],
        *,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        observed_commands.append(
            (
                command,
                check,
            )
        )
        return subprocess.CompletedProcess(
            command,
            0,
        )

    monkeypatch.setattr(
        container_startup.subprocess,
        "run",
        record_command,
    )

    container_startup.initialize_application_data()

    assert observed_commands == [
        (
            command,
            True,
        )
        for command in (container_startup.build_initialization_commands())
    ]


def test_main_executes_application_without_initialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initialized: list[bool] = []
    executed: list[tuple[str, list[str]]] = []
    command = [
        "python",
        "-m",
        "uvicorn",
    ]

    monkeypatch.setenv(
        container_startup.INITIALIZE_APPLICATION_DATA_ENV,
        "false",
    )
    monkeypatch.setattr(
        container_startup,
        "initialize_application_data",
        lambda: initialized.append(True),
    )
    monkeypatch.setattr(
        container_startup.os,
        "execvp",
        lambda executable, arguments: executed.append(
            (
                executable,
                arguments,
            )
        ),
    )

    container_startup.main(command)

    assert initialized == []
    assert executed == [
        (
            "python",
            command,
        )
    ]


def test_main_initializes_before_application_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    command = [
        "python",
        "-m",
        "uvicorn",
    ]

    monkeypatch.setenv(
        container_startup.INITIALIZE_APPLICATION_DATA_ENV,
        "true",
    )
    monkeypatch.setattr(
        container_startup,
        "initialize_application_data",
        lambda: events.append("initialize"),
    )
    monkeypatch.setattr(
        container_startup.os,
        "execvp",
        lambda executable, arguments: events.append(f"execute:{executable}:{arguments[1]}"),
    )

    container_startup.main(command)

    assert events == [
        "initialize",
        "execute:python:-m",
    ]


def test_main_requires_application_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["container_startup"],
    )

    with pytest.raises(
        SystemExit,
        match="application command is required",
    ):
        container_startup.main()
