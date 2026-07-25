"""Pytest reporting helpers for the backend test suite."""

from collections import defaultdict


def pytest_collection_finish(session):
    """Record test scope and modules for a concise end-of-run report."""
    scopes: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for item in session.items:
        for scope in ("unit", "integration"):
            if item.get_closest_marker(scope):
                counts[scope] += 1
                scopes[scope].add(item.nodeid.split("::", 1)[0])
    session.config._test_scope_summary = (counts, scopes)  # type: ignore[attr-defined]


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Show which application-test layers ran, not only pass/fail dots."""
    counts, scopes = getattr(config, "_test_scope_summary", ({}, {}))
    terminalreporter.write_sep("=", "Test scope")
    for scope in ("unit", "integration"):
        modules = ", ".join(sorted(scopes.get(scope, set()))) or "none"
        terminalreporter.write_line(f"{scope.title():<11} {counts.get(scope, 0)} tests — {modules}")
