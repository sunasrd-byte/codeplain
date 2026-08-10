"""Verify a working git is available before GitPython is imported.

codeplain drives a git-backed render state machine, so git is required for every
command. GitPython probes for the git executable the first time it is imported,
and reports a missing or broken one as an ``ImportError`` raised from module
scope. That happens while ``plain2code`` is still importing its own modules --
long before ``main()`` runs -- so a check inside ``main()`` cannot intercept it
and the user gets a raw traceback instead of an explanation.

``require_git`` is therefore called at module scope by each module that imports
GitPython (``plain_modules`` and ``git_utils``), immediately above that import.
Guarding the importers rather than the CLI entry point keeps the check attached to
the thing that needs it: it holds however the modules are reached, including when
something imports ``git_utils`` directly without going through ``plain2code``. It
reports through ``plain2code_console``, which has no git dependency of its own.

Two distinct failures both have to be caught, because they surface differently:

- git missing entirely: no ``git`` on PATH at all.
- git present but not working: a name that resolves but cannot run ``git
  version``. On macOS this is the normal state when the Command Line Tools are
  absent -- ``/usr/bin/git`` exists as a stub that exits non-zero with an xcrun
  error -- and stale shims behave the same way. ``GIT_PYTHON_REFRESH=quiet``
  does not help here: GitPython only consults that setting for a git it cannot
  find, so a git that fails to run still raises during import.

Consequently a resolvable name is not evidence of a usable git, and this module
runs ``git version`` rather than trusting the PATH lookup alone. This mirrors the
``git_available`` check in ``install/bash/install.sh``.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

from plain2code_console import console

# Long enough for a cold-cache process spawn on a loaded machine, short enough
# that a wedged shim cannot hang the CLI indefinitely.
GIT_VERSION_TIMEOUT_SECONDS = 10

GIT_MISSING_MESSAGE = "git is not installed. Please install git and try again."
GIT_BROKEN_MESSAGE = "git is installed but not working. Please repair your git installation and try again."

# On macOS a missing Command Line Tools install is the usual cause: /usr/bin/git
# exists as a stub that exits non-zero, so git resolves but cannot run.
MACOS_BROKEN_GIT_HINT = (
    "This usually means the Command Line Tools are missing; install them with 'xcode-select --install'."
)


def broken_git_message() -> str:
    """The broken-git message, with a platform hint where there is a likely cause."""
    if sys.platform == "darwin":
        return f"{GIT_BROKEN_MESSAGE}\n{MACOS_BROKEN_GIT_HINT}"

    return GIT_BROKEN_MESSAGE


def find_git() -> str | None:
    """Return the path to the git executable, or None if it is not on PATH."""
    return shutil.which("git")


def git_runs(git_path: str) -> bool:
    """Whether ``git version`` actually succeeds for the given executable.

    A resolvable name can still be unusable -- a stub or stale shim satisfies the
    PATH lookup but exits non-zero -- so the command is run rather than assumed.
    Any failure to execute it at all (missing permissions, a hung shim, a path
    that vanished between lookup and run) counts as unusable.
    """
    try:
        result = subprocess.run(
            [git_path, "version"],
            capture_output=True,
            timeout=GIT_VERSION_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return False

    return result.returncode == 0


_checked = False


def require_git() -> None:
    """Exit with a clean message unless a working git is available.

    Called before GitPython is imported, so the diagnosis reaches the user
    instead of GitPython's import-time traceback. Every module that imports
    GitPython calls this, so the result is cached: whichever module is imported
    first pays for the ``git version`` subprocess and the rest are free.
    """
    global _checked
    if _checked:
        return

    git_path = find_git()

    if git_path is None:
        console.error(f"{GIT_MISSING_MESSAGE}\n")
        sys.exit(1)

    if not git_runs(git_path):
        console.error(f"{broken_git_message()}\n")
        sys.exit(1)

    _checked = True
