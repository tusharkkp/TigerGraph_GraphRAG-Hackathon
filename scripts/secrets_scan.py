"""Secrets scanner — fails if any potential secret is found in tracked files.

Scans src/, configs/, scripts/, tests/ for patterns that look like API keys,
passwords, or tokens. Ignores .env (which is gitignored).
"""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Patterns that suggest leaked secrets
SECRET_PATTERNS = [
    (r"AIza[0-9A-Za-z\-_]{35}", "Google API key"),
    (r"sk-[a-zA-Z0-9]{48}", "OpenAI API key"),
    (r"(?i)password\s*=\s*['\"][^'\"]+['\"]", "Hardcoded password"),
    (r"(?i)api[_-]?key\s*=\s*['\"][^'\"]+['\"]", "Hardcoded API key"),
    (r"(?i)secret\s*=\s*['\"][^'\"]+['\"]", "Hardcoded secret"),
    (r"(?i)token\s*=\s*['\"][^'\"]+['\"]", "Hardcoded token"),
]

# Directories to scan
SCAN_DIRS = ["src", "configs", "scripts", "tests", "graph", "docs"]

# Files to skip
SKIP_PATTERNS = {".env", ".env.example", "__pycache__", ".git", ".llm_cache"}

# Extensions to scan
SCAN_EXTENSIONS = {".py", ".yaml", ".yml", ".json", ".toml", ".md", ".gsql", ".txt"}


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Scan a single file for secret patterns. Returns [(line_no, pattern_name, line)]."""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for i, line in enumerate(text.splitlines(), 1):
        for pattern, name in SECRET_PATTERNS:
            if re.search(pattern, line):
                # Skip if it's clearly a placeholder/example
                if any(placeholder in line.lower() for placeholder in
                       ["your_", "placeholder", "example", "xxx", "changeme", "todo"]):
                    continue
                findings.append((i, name, line.strip()[:100]))
    return findings


def main() -> int:
    """Run the secrets scan. Returns 0 if clean, 1 if secrets found."""
    all_findings: list[tuple[str, int, str, str]] = []

    for dirname in SCAN_DIRS:
        scan_dir = PROJECT_ROOT / dirname
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*"):
            if path.is_dir():
                continue
            if any(skip in str(path) for skip in SKIP_PATTERNS):
                continue
            if path.suffix not in SCAN_EXTENSIONS:
                continue
            for line_no, pattern_name, line in scan_file(path):
                all_findings.append((str(path.relative_to(PROJECT_ROOT)), line_no, pattern_name, line))

    if all_findings:
        print("FAIL: SECRETS FOUND:")
        for filepath, line_no, pattern_name, line in all_findings:
            print(f"  {filepath}:{line_no} — {pattern_name}: {line}")
        return 1
    else:
        print("PASS: No secrets found.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
