"""The image must contain every local module its entrypoints import.

The Containerfile copies application code with an explicit per-file allowlist.
Twice now a PR has added a top-level module plus its import in app.py and
forgotten the matching COPY, shipping a container that dies on boot with
ModuleNotFoundError while every unit test passed -- discussions_plugin.py
(#168) and timer_sync_plugin.py (#223, which took acquacotta.crunchtools.com
down for ~25 minutes).

The guard added after the first outage was a second hand-maintained list, so it
drifted the same way and missed the second one. These tests derive both sides
from the files themselves, so there is nothing left to keep in sync.
"""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CONTAINERFILE = ROOT / "Containerfile"

# Entrypoints that run inside the image: the WSGI app and the MCP server.
ENTRYPOINTS = ("app.py", "mcp_server.py")


def _local_modules():
    """Top-level importable names provided by this repo (modules and packages)."""
    modules = {p.stem for p in ROOT.glob("*.py") if p.stem != "setup"}
    packages = {d.name for d in ROOT.iterdir() if d.is_dir() and (d / "__init__.py").exists()}
    return modules | packages


def _copied_paths():
    """Everything the Containerfile COPYs into the image's app directory."""
    copied = set()
    for line in CONTAINERFILE.read_text().splitlines():
        match = re.match(r"\s*COPY\s+(?P<src>\S+)\s+(?P<dst>\S+)\s*$", line)
        if not match:
            continue
        src, dst = match.group("src"), match.group("dst")
        # Only care about code landing in the app dir, not config dropped into /etc.
        if dst.startswith("/"):
            continue
        copied.add(src.rstrip("/"))
    return copied


def _imports(path):
    """Top-level module names imported by a source file."""
    tree = ast.parse(path.read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _required_local_modules():
    """Transitive closure of repo-local modules reachable from the entrypoints."""
    local = _local_modules()
    seen, queue = set(), list(ENTRYPOINTS)
    while queue:
        current = queue.pop()
        path = ROOT / current
        if not path.exists():
            continue
        for name in _imports(path) & local:
            if name in seen:
                continue
            seen.add(name)
            # Follow plain modules; packages are copied wholesale as a directory.
            if (ROOT / f"{name}.py").exists():
                queue.append(f"{name}.py")
    return seen


@pytest.mark.parametrize("entrypoint", ENTRYPOINTS)
def test_entrypoint_exists(entrypoint):
    assert (ROOT / entrypoint).exists(), f"{entrypoint} is missing from the repo"


def test_every_required_local_module_is_copied_into_the_image():
    copied = _copied_paths()
    missing = sorted(
        name
        for name in _required_local_modules()
        if f"{name}.py" not in copied and name not in copied
    )
    assert not missing, (
        "These modules are imported inside the image but never COPYed into it, so the "
        "container will die on boot with ModuleNotFoundError. Add a COPY line to the "
        f"Containerfile for each: {', '.join(missing)}"
    )


def test_boot_guard_covers_every_copied_local_module():
    """The Containerfile's import guard must not drift behind the COPY list."""
    text = CONTAINERFILE.read_text()
    guard = re.search(r'RUN python3 -c "import (?P<mods>[^"]+)"', text)
    assert guard, "the Containerfile boot guard (RUN python3 -c \"import ...\") is gone"
    guarded = {name.strip() for name in guard.group("mods").split(",")}

    # app.py itself needs runtime env to import, so it is legitimately excluded.
    required = _required_local_modules() - {"app"}
    # Packages are exercised through the modules that import them.
    required = {name for name in required if (ROOT / f"{name}.py").exists()}

    missing = sorted(required - guarded)
    assert not missing, (
        "The Containerfile boot guard does not import these modules, so a missing COPY "
        f"would not fail the build: {', '.join(missing)}"
    )
