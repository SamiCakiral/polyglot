import argparse
import re
import subprocess
from pathlib import Path

_SECRET_PATTERNS = (
    ("aws_access_key", re.compile("A" + r"KIA[0-9A-Z]{16}")),
    ("github_token", re.compile("gh" + r"[pousr]_[A-Za-z0-9]{20,}")),
    ("google_api_key", re.compile("AI" + r"za[0-9A-Za-z_-]{30,}")),
    ("openai_api_key", re.compile("sk" + r"-[A-Za-z0-9_-]{20,}")),
    (
        "private_key",
        re.compile("-----BEGIN " + r"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)


def _find_secrets(content: str, scope: str) -> list[str]:
    return [f"{scope}:{label}" for label, pattern in _SECRET_PATTERNS if pattern.search(content)]


def scan_git_repository(root: Path) -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=True,
        timeout=20,
    ).stdout.split(b"\0")
    findings: list[str] = []
    for relative_bytes in tracked:
        if not relative_bytes:
            continue
        relative = relative_bytes.decode()
        path = root / relative
        try:
            content = path.read_text(errors="ignore")
        except (FileNotFoundError, IsADirectoryError):
            continue
        findings.extend(_find_secrets(content, f"tracked:{relative}"))

    history = subprocess.run(
        ["git", "log", "--format=", "--all", "-p", "--", "."],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    findings.extend(_find_secrets(history, "history"))
    return sorted(set(findings))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local Polyglot security checks")
    parser.add_argument("--repository-root", type=Path, required=True)
    arguments = parser.parse_args(argv)
    findings = scan_git_repository(arguments.repository_root.resolve())
    if findings:
        for finding in findings:
            print(f"secret finding: {finding}")
        return 1
    print("repository and history secret scan clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
