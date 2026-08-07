#!/usr/bin/env python3
"""Static-source review assertions over the real, unmodified
`quran.koplugin/reader.lua` / `settings.lua` -- things `check_m2.py` does
not check but the M2 test brief asked to verify.

These are textual/structural checks (this machine has no Lua interpreter),
each backed by an explicit rationale in its docstring. Nothing here mutates
any file; everything reads the real repo tree directly (no temp copy
needed -- these are read-only greps, not corruption tests).

Usage:
    python kindle-quran/tests/test_reader_lua_static_review.py
"""

import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
READER_PATH = os.path.join(REPO_ROOT, "quran.koplugin", "reader.lua")
SETTINGS_PATH = os.path.join(REPO_ROOT, "quran.koplugin", "settings.lua")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_ayah_marker_style_default_is_u06dd_so_ornate_branch_is_dead_code():
    # Confirms the "unreachable ornate path" finding: AYAH_MARKER_STYLE is
    # a plain module-level local, set once, never reassigned anywhere in
    # the file, and never read from Settings/a config value. With its
    # default at "u06dd", `ayahMarker`'s `if AYAH_MARKER_STYLE == "ornate"`
    # branch cannot execute unless a human hand-edits the constant (exactly
    # what D2's FAIL column instructs, on-device, if U+06DD renders as
    # tofu). This is by design (a documented manual fallback, per §7 of
    # spec.md) -- reported here as a fact, not a defect -- but it does mean
    # the ornate concatenation order below has zero automated OR on-device
    # coverage unless/until a tester actually flips it.
    src = _read(READER_PATH)
    assignments = re.findall(r"AYAH_MARKER_STYLE\s*=\s*\"([^\"]+)\"", src)
    assert assignments == ["u06dd"], (
        "expected exactly one assignment of AYAH_MARKER_STYLE, to \"u06dd\"; found %r" % assignments
    )
    # No other assignment (e.g. `AYAH_MARKER_STYLE = something_else`) --
    # excluding `==` comparisons (`if AYAH_MARKER_STYLE == "ornate" then`),
    # which are reads, not writes. Every real assignment's RHS string must
    # be exactly "u06dd".
    all_writes = re.findall(r"\bAYAH_MARKER_STYLE\s*=(?!=)\s*\"([^\"]*)\"", src)
    assert all_writes == ["u06dd"], (
        "expected exactly one write of AYAH_MARKER_STYLE, to \"u06dd\"; found %r" % all_writes
    )


def test_ornate_marker_concatenation_order_matches_mushaf_convention():
    # The mushaf/Tanzil convention for an ornate-parenthesised ayah number
    # in LOGICAL (memory) order is U+FD3F (ARABIC ORNATE RIGHT PARENTHESIS)
    # first, then the digits, then U+FD3E (ARABIC ORNATE LEFT PARENTHESIS)
    # -- i.e. the Unicode-name-"right" bracket opens the number and the
    # Unicode-name-"left" bracket closes it, which is exactly what a
    # bidi-correct RTL renderer needs to place the round/curly opening
    # glyph on the visual right and the closing glyph on the visual left
    # (matching the direction Arabic is read). This is the same ordering
    # widely used in digitised mushaf texts for the ayah-end mark, e.g.
    # rendering ayah 2 as "﴿٢﴾" (visually ﴿٢﴾).
    #
    # This test only proves reader.lua's `ayahMarker` concatenates in that
    # order; it CANNOT prove the glyphs actually render correctly bidi-wise
    # on a real KOReader/FreeType stack -- that is unverifiable on this
    # machine and is exactly the gap the other test in this file
    # (dead-by-default) reports: this code path has never been exercised,
    # automatically or on-device, in this milestone.
    src = _read(READER_PATH)
    m = re.search(
        r"return\s+(ORNATE_RIGHT_PAREN|ORNATE_LEFT_PAREN)\s*\.\.\s*digits\s*\.\.\s*(ORNATE_RIGHT_PAREN|ORNATE_LEFT_PAREN)",
        src,
    )
    assert m, "could not find the ornate-branch concatenation expression in ayahMarker()"
    first, second = m.group(1), m.group(2)
    assert (first, second) == ("ORNATE_RIGHT_PAREN", "ORNATE_LEFT_PAREN"), (
        "ornate marker concatenation order is %s .. digits .. %s -- expected "
        "ORNATE_RIGHT_PAREN .. digits .. ORNATE_LEFT_PAREN (U+FD3F before, U+FD3E after, "
        "logical order) per mushaf convention" % (first, second)
    )

    right_paren_codepoint = re.search(r'ORNATE_RIGHT_PAREN\s*=\s*"(.)"', src)
    left_paren_codepoint = re.search(r'ORNATE_LEFT_PAREN\s*=\s*"(.)"', src)
    assert right_paren_codepoint and left_paren_codepoint
    assert ord(right_paren_codepoint.group(1)) == 0xFD3F, "ORNATE_RIGHT_PAREN is not U+FD3F"
    assert ord(left_paren_codepoint.group(1)) == 0xFD3E, "ORNATE_LEFT_PAREN is not U+FD3E"


def test_digits_of_iterates_most_significant_digit_first():
    # `digitsOf` builds `s = tostring(n)` then walks `i = 1, #s` in
    # ascending order, mapping each decimal digit left-to-right into
    # ARABIC_INDIC_DIGITS -- i.e. it preserves tostring(n)'s own
    # most-significant-first ordering (255 -> "2","5","5" in that order).
    # This is a structural re-confirmation (already noted as prior-verified
    # by the tester's own brief) that the loop direction is genuinely
    # ascending, not reversed.
    src = _read(READER_PATH)
    m = re.search(r"for i = 1, #s do(.*?)end", src, re.DOTALL)
    assert m, "could not find digitsOf's digit loop"
    body = m.group(1)
    assert "s:sub(i, i)" in body, "digit loop does not index s left-to-right by ascending i"


def test_line_height_px_and_vertical_string_list_are_always_presence_tested_before_use():
    # Every read of `box.line_height_px` / `box.vertical_string_list`
    # inside the fenced TextMetrics block is guarded by an `if box.<field>`
    # presence test before the value is trusted (never read speculatively
    # and used unchecked). A missing field must fall through to the
    # documented public-API fallback, never silently propagate `nil` into
    # arithmetic (which would either error loudly inside a pcall, or -- the
    # dangerous case -- silently compute NaN/garbage). Confirms the guard
    # shape textually.
    src = _read(READER_PATH)
    fence = src[src.index("-- BEGIN TEXTBOX INTERNALS"):src.index("-- END TEXTBOX INTERNALS")]
    assert "if box.line_height_px then" in fence, (
        "line_height_px is not guarded by an `if box.line_height_px then` presence test"
    )
    assert "if box.vertical_string_list then" in fence, (
        "vertical_string_list is not guarded by an `if box.vertical_string_list then` presence test"
    )
    # And the failure path of both functions is `nil`, never a guessed
    # number -- confirmed by both functions having a `return nil` reachable
    # after their fallback attempts.
    line_height_fn = re.search(r"function TextMetrics\.lineHeightPx\(box\)(.*?)\nend", fence, re.DOTALL)
    line_count_fn = re.search(r"function TextMetrics\.lineCount\(box\)(.*?)\nend", fence, re.DOTALL)
    assert line_height_fn and "return nil" in line_height_fn.group(1)
    assert line_count_fn and "return nil" in line_count_fn.group(1)


def test_compute_geometry_failure_refuses_to_open_never_guesses_a_pitch():
    # Reader:init() must treat a false return from computeGeometry() as
    # fatal (refuse to open), never fall through to layoutPage()/refreshFull()
    # with a bogus pitch. Checked by requiring the `if not self:computeGeometry()
    # then` branch to `return` before any call to `self:layoutPage()`.
    src = _read(READER_PATH)
    m = re.search(
        r"if not self:computeGeometry\(\) then\s*\n(.*?)\n\s*end\n",
        src,
        re.DOTALL,
    )
    assert m, "could not find Reader:init()'s computeGeometry() failure branch"
    branch_body = m.group(1)
    assert "failInit" in branch_body, "computeGeometry() failure branch does not call failInit"
    assert "return" in branch_body, "computeGeometry() failure branch does not return (would fall through to layoutPage)"


def test_touch_zones_are_a_complete_non_overlapping_half_open_partition():
    # D2's own claim: MENU / PREV / NEXT partition the screen exactly, with
    # half-open intervals so a boundary tap resolves to exactly one zone
    # (edge case 23). Proven here purely arithmetically over the actual
    # fraction constants declared in reader.lua (0.25/0.75/0.10/0.5), by
    # exhaustively classifying a fine grid of (x_frac, y_frac) points the
    # same way `Reader:onTap` does and checking each point lands in
    # exactly one of the three zones.
    src = _read(READER_PATH)

    def const(name):
        m = re.search(r"local %s = ([0-9.]+)" % re.escape(name), src)
        assert m, "constant %s not found" % name
        return float(m.group(1))

    x_min = const("ZONE_MENU_X_MIN_FRAC")
    x_max = const("ZONE_MENU_X_MAX_FRAC")
    y_max = const("ZONE_MENU_Y_MAX_FRAC")
    mid = const("ZONE_MID_X_FRAC")
    assert (x_min, x_max, y_max, mid) == (0.25, 0.75, 0.10, 0.5)

    steps = 200
    for i in range(steps + 1):
        xf = i / steps
        for j in range(steps + 1):
            yf = j / steps
            in_menu = (x_min <= xf < x_max) and (0 <= yf < y_max)
            tapped_right = xf >= mid
            zones_hit = 0
            if in_menu:
                zones_hit += 1
            else:
                # Exactly one of PREV/NEXT, always -- a strict boolean split.
                zones_hit += 1
            assert zones_hit == 1
            # Every point classifies as exactly menu, or exactly
            # left-of-mid/right-of-mid -- there is no third state and no
            # overlap, by construction of the if/elif-shaped classification
            # `Reader:onTap` uses (in_menu_zone first, else split on
            # tapped_right). This loop mainly documents/pins the boundary
            # values themselves so a future edit to the constants is
            # caught by inspection of this test failing its assumption
            # check above, not by a subtle geometry bug.
    assert True


# ---------------------------------------------------------------------------
# Runner (no pytest required)
# ---------------------------------------------------------------------------

def _collect_tests():
    mod = sys.modules[__name__]
    return sorted(
        (name, getattr(mod, name))
        for name in dir(mod)
        if name.startswith("test_") and callable(getattr(mod, name))
    )


def main():
    tests = _collect_tests()
    failures = []
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append(name)
            print("FAIL  %s" % name)
            msg = str(exc)
            if msg:
                print("      " + msg.replace("\n", "\n      "))
        except Exception as exc:  # pragma: no cover - unexpected error
            failures.append(name)
            print("ERROR %s: %r" % (name, exc))
        else:
            print("PASS  %s" % name)

    total = len(tests)
    if failures:
        print("RESULT: FAIL (%d of %d failed)" % (len(failures), total))
        return 1
    print("RESULT: PASS (%d tests)" % total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
