#!/usr/bin/env python3
"""Compiles every plugin Lua file with a real LuaJIT 2.1.

    python tools/check_luajit.py [--root <repo root>]

WHY THIS EXISTS
---------------
Until now nothing in this repository could execute or even compile Lua. The
checks used `luaparser`, a Python reimplementation, and the gap between it and
the real thing has been expensive:

  * `luaparser` accepted a double-quoted string containing raw newlines.
    LuaJIT rejects it as "unfinished string", KOReader skipped the plugin in
    silence, and every local check passed while the plugin was dead on the
    device. That is check L7 in check_m0.py -- one specific divergence,
    patched after it bit.

This runs the compiler KOReader actually uses, so the whole class is covered
rather than the members of it we have already met.

WHAT IT DOES NOT DO
-------------------
It COMPILES; it does not run. Nothing here loads KOReader's modules, touches a
screen or opens a database, so a file that compiles can still be wrong in every
way that matters -- `top_line_num` being silently ignored compiled perfectly
for two milestones. This closes the syntax gap and nothing else.

REQUIREMENT
-----------
`pip install lupa`. Lupa bundles LuaJIT 2.1, which is what KOReader runs, so
this needs no system Lua and no admin rights. If lupa is absent the check
reports SKIP rather than PASS: an unverifiable claim is not a passing one.
"""
import argparse
import os
import sys

CHECKS = []


def record(cid, ok, msg):
    CHECKS.append((cid, ok, msg))
    print("%-5s %-4s %s" % ("PASS" if ok else "FAIL", cid, msg))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=root)
    args = ap.parse_args()

    try:
        from lupa import luajit21 as luajit
    except ImportError:
        print("SKIP  lupa is not installed -- `pip install lupa` to enable this gate")
        print()
        print("RESULT: SKIP (0 checks)")
        # Deliberately non-zero: a gate that cannot run has not passed.
        return 2

    lua = luajit.LuaRuntime()
    version = lua.eval("jit and jit.version or _VERSION")
    print("compiler: %s" % version)
    print()

    plugin_dir = os.path.join(args.root, "quran.koplugin")
    names = sorted(n for n in os.listdir(plugin_dir) if n.endswith(".lua"))
    if not names:
        raise SystemExit("no .lua files under %s" % plugin_dir)

    for name in names:
        path = os.path.join(plugin_dir, name)
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        try:
            # Chunk name matters: LuaJIT reports it in the error, and a real
            # filename makes a failure here read like the crash.log entry the
            # device would have produced.
            lua.compile(src, name=("@" + name).encode("utf-8"))
            record(name, True, "compiles under %s" % version)
        except Exception as exc:  # lupa raises LuaSyntaxError
            record(name, False, "%s" % str(exc).strip().splitlines()[0])

    failed = [c for c in CHECKS if not c[1]]
    print()
    print("RESULT: %s (%d files)"
          % ("PASS" if not failed else "FAIL (%d of %d)" % (len(failed), len(CHECKS)),
             len(CHECKS)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
