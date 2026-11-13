"""Build a 0.34-patched qw from a qw checkout and (optionally) copy it into the DCSS container.

    uv run python tools/qw/build.py [--src runs/qw/src] [--out runs/qw/build] [--deploy]
                                    [--stage zr --out runs/qw/build-zr --lib-dir /data/qw/lib-zr]

Steps (the same as qw's make-qw.sh, plus our patches):
  1. read qw's Lua files (variables.lua first, then the rest sorted by name),
  2. apply the snippet patches in tools/qw/patches.py, failing loudly if one doesn't match,
  3. append tools/qw/ladder.lua (0.34 shims, error/panic reporting, action log),
  4. write qw.lua (one `< ... >` Lua block), qw-ladder.rc (qw.rc + tools/qw/ladder.rc),
     qw.lua.map.json (qw.lua line -> source file:line, for reading error messages)
     and qw-034.diff (the patches as a unified diff against qw's files).
  5. --deploy: docker cp the build to --lib-dir (default /data/qw/lib) in the container.

Plain stdlib; qw's source is never modified in place.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

from patches import STAGES, patches_for  # noqa: E402

CONTAINER = "dcss-multi-agent-dcss-1"
LIB_DIR = "/data/qw/lib"
LUA_SUBDIR = "sour" "ce"  # qw keeps its Lua in <checkout>/<this>
RC_MARKER = "# include = qw.lua"


def qw_version(src: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(src), "describe", "--always", "--tags"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        out = "unknown"
    return f"{out}+ladder-0.34"


def read_lua(src: Path) -> dict[str, str]:
    lua_dir = src / LUA_SUBDIR
    files = sorted(p.name for p in lua_dir.glob("*.lua"))
    if "variables.lua" not in files:
        raise SystemExit(f"no variables.lua in {lua_dir}: is --src a qw checkout?")
    files.remove("variables.lua")
    order = ["variables.lua", *files]
    return {name: (lua_dir / name).read_text(encoding="utf-8") for name in order}


def apply_patches(texts: dict[str, str], patches: list) -> dict[str, str]:
    out = dict(texts)
    for p in patches:
        if p.file not in out:
            raise SystemExit(f"patch target {p.file} missing")
        n = out[p.file].count(p.old)
        if n != p.count:
            raise SystemExit(
                f"patch for {p.file} expected {p.count} match(es), found {n}:\n{p.old}"
            )
        out[p.file] = out[p.file].replace(p.old, p.new)
    return out


def build(src: Path, out: Path, stock: bool = False, stage: str | None = None) -> Path:
    patches = [p for p in patches_for(stage) if not (stock and p.kind == "bugfix")]
    original = read_lua(src)
    patched = apply_patches(original, patches)
    version = qw_version(src) + ("-stock" if stock else "") + (f"-{stage}" if stage else "")

    out.mkdir(parents=True, exist_ok=True)

    diff_lines: list[str] = []
    for name, text in original.items():
        if patched[name] != text:
            diff_lines += difflib.unified_diff(
                text.splitlines(keepends=True), patched[name].splitlines(keepends=True),
                fromfile=f"a/{name}", tofile=f"b/{name}",
            )
    (out / "qw-034.diff").write_text("".join(diff_lines), encoding="utf-8")

    parts = list(patched.items()) + [("ladder.lua", (HERE / "ladder.lua").read_text("utf-8"))]
    lines = ["<"]
    line_map = []  # [first qw.lua line, file name]
    for name, text in parts:
        text = text.replace("%VERSION%", version)
        line_map.append([len(lines) + 1, name])
        lines += text.rstrip("\n").split("\n")
    lines.append(">")
    (out / "qw.lua").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "qw.lua.map.json").write_text(json.dumps(line_map), encoding="utf-8")

    rc = (src / "qw.rc").read_text(encoding="utf-8")
    if RC_MARKER not in rc:
        raise SystemExit(f"qw.rc has no '{RC_MARKER}' line")
    rc = rc.replace(RC_MARKER, "include = qw.lua")
    rc += "\n" + (HERE / "ladder.rc").read_text(encoding="utf-8")
    (out / "qw-ladder.rc").write_text(rc, encoding="utf-8")
    (out / "VERSION").write_text(version + "\n", encoding="utf-8")
    print(f"built qw {version}: {len(lines)} lines of Lua, {len(patches)} patches -> {out}")
    return out


def deploy(out: Path, container: str = CONTAINER, lib_dir: str = LIB_DIR) -> None:
    subprocess.run(["docker", "exec", container, "mkdir", "-p", lib_dir], check=True)
    for name in ("qw.lua", "qw-ladder.rc", "VERSION"):
        subprocess.run(
            ["docker", "cp", str(out / name), f"{container}:{lib_dir}/{name}"], check=True
        )
    print(f"deployed to {container}:{lib_dir}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--src", type=Path, default=REPO / "runs/qw/src")
    ap.add_argument("--out", type=Path, default=REPO / "runs/qw/build")
    ap.add_argument("--deploy", action="store_true")
    ap.add_argument("--stock", action="store_true",
                    help="only the 0.34 port patches, not fixes for qw's own bugs")
    ap.add_argument("--container", default=CONTAINER)
    ap.add_argument("--lib-dir", default=LIB_DIR, help="where --deploy puts the build")
    ap.add_argument("--stage", choices=STAGES, default=None,
                    help="include the patches of this stage and earlier ones (default: up to zk)")
    args = ap.parse_args()
    out = build(args.src, args.out, stock=args.stock, stage=args.stage)
    if args.deploy:
        deploy(out, args.container, args.lib_dir)


if __name__ == "__main__":
    main()
