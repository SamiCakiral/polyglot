import subprocess
from pathlib import Path

from polyglot.platform.security_checks import _patch_content, scan_git_repository


def _git(repository: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit_all(repository: Path, message: str) -> None:
    _git(repository, "add", ".")
    _git(
        repository,
        "-c",
        "user.name=Polyglot Tests",
        "-c",
        "user.email=tests@polyglot.invalid",
        "commit",
        "-m",
        message,
    )


def test_history_scan_ignores_secret_like_patch_filenames(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    report = tmp_path / ("task-W17-" + "shell-fix-report.md")
    report.write_text("review evidence only\n")
    _commit_all(tmp_path, "add shell report")

    assert scan_git_repository(tmp_path) == []


def test_history_scan_still_detects_secret_shaped_file_content(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    secret = "sk" + "-" + ("a" * 24)
    report = tmp_path / "report.md"
    report.write_text(f"leaked={secret}\n")
    _commit_all(tmp_path, "add unsafe content")
    report.write_text("redacted\n")
    _commit_all(tmp_path, "redact unsafe content")

    assert scan_git_repository(tmp_path) == ["history:openai_api_key"]


def test_history_scan_detects_all_secret_families_after_redaction(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    secrets = (
        "A" + "KIA" + ("A" * 16),
        "gh" + "p_" + ("a" * 20),
        "AI" + "za" + ("A" * 30),
        "prefix_" + "sk" + "-" + ("a" * 24),
        "-----BEGIN " + "PRIVATE KEY-----",
    )
    report = tmp_path / "unsafe.txt"
    report.write_text("\n".join(secrets) + "\n")
    _commit_all(tmp_path, "add unsafe content")
    report.write_text("redacted\n")
    _commit_all(tmp_path, "redact all unsafe content")

    assert scan_git_repository(tmp_path) == [
        "history:aws_access_key",
        "history:github_token",
        "history:google_api_key",
        "history:openai_api_key",
        "history:private_key",
    ]


def test_history_scan_keeps_content_that_starts_like_patch_headers(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    secret = "sk" + "-" + ("a" * 24)
    report = tmp_path / "unsafe.txt"
    report.write_text(f"++{secret}\n--{secret}\n")
    _commit_all(tmp_path, "add header-like content")
    report.write_text("redacted\n")
    _commit_all(tmp_path, "redact header-like content")

    assert scan_git_repository(tmp_path) == ["history:openai_api_key"]


def test_patch_parser_only_discards_path_headers() -> None:
    secret = "sk" + "-" + ("a" * 24)
    patch = "\n".join(
        (
            "--- a/unsafe.txt",
            "+++ b/unsafe.txt",
            f"+++{secret}",
            f"---{secret}",
        )
    )

    assert _patch_content(patch) == f"++{secret}\n--{secret}"


def test_history_scan_survives_a_pure_rename_before_redaction(tmp_path: Path) -> None:
    _git(tmp_path, "init", "--quiet")
    secret = "sk" + "-" + ("a" * 24)
    original = tmp_path / "unsafe.txt"
    renamed = tmp_path / "renamed.txt"
    original.write_text(f"leaked={secret}\n")
    _commit_all(tmp_path, "add unsafe content")
    _git(tmp_path, "mv", original.name, renamed.name)
    _commit_all(tmp_path, "rename unsafe content")
    renamed.write_text("redacted\n")
    _commit_all(tmp_path, "redact renamed content")

    assert scan_git_repository(tmp_path) == ["history:openai_api_key"]
