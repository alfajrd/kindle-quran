--[[--
Qur'an, Milestone 2: the reader widget -- paging, page layout, ruled lines,
touch zones, the settings dialog.

Turns the plugin from a two-screen proof (M0/M1) into a reader: open a
surah, page forward and back through it continuously, come back later to
exactly where you stopped, with Arabic size and line height adjustable at
runtime and a grey ruled line under every line of text. See
`.pipeline/spec.md` for the full design; this header only restates the
parts that matter to someone editing this file.

**What this is not.** No surah/juz navigator (M3), no reference parsing
(`2:255`), no translations, no bookmarks/search/About screen, no surah
headers, no separate Bismillah heading, no cross-surah paging. See §2 of
the spec for the full "does NOT build" list.

**Position memory (D4).** An ayah reference plus a line ordinal *within
that ayah's own layout*, per surah -- never a byte offset, never a page
number, nothing that depends on the current font. `ayah` is stable across
any later change of font/margin/mode; `line` is a hint, clamped on read and
reset to 0 whenever typography changes (§6.7).

**Scripture handling.** `ayah.text` is read from the pack and concatenated
with a separating space and an end-of-ayah marker -- nothing else. See the
BEGIN/END VERBATIM CONCAT fence below; §7 of the spec explains why this is
enforced structurally rather than by good intentions.

MUST-VERIFY V20-V29, V33-V36 -- read this before touching anything in this
file. Full findings and KOReader source paths are in `docs/VERIFY-M2.md`;
this is the short version.
------------------------------------------------------------------------
This machine has no KOReader checkout and no network access, so none of the
following could be confirmed by reading source -- only implemented as the
spec's own best-effort claim and flagged here.

  MUST-VERIFY V20: `TextBoxWidget:new{}` accepts `text`, `face`, `width`,
      `height`, `line_height`, `alignment`, `auto_para_direction`,
      `top_line_num`. Implemented exactly as named; a wrong key name would
      surface as a Lua error from inside a `pcall`-guarded construction, or
      (worse, silently) as wrong layout -- which is exactly what on-device
      check D3/D5/D7 exist to catch.
  MUST-VERIFY V21: `line_height` is *extra leading in em*, default 0.3
      upstream, so SPEC-v1 §9's "1.9x line height" maps to `line_height =
      0.9`. See `quransettings.lua`'s header comment for the same note.
  MUST-VERIFY V22: the per-instance line-pitch field (upstream name:
      "line_height_px", read only inside the fenced TEXTBOX INTERNALS block
      below) exists on the instance after `init()`. If it does not, the
      `getSize()`-based fallback in that block is used instead; if that
      also fails, the reader refuses to open (edge case 19) rather than
      guess a pitch.
  MUST-VERIFY V23: the per-instance line list (upstream name:
      "vertical_string_list") exists after `init()` and its length is the
      *whole text's* line count, not one page's. Used only inside the
      fenced block; the `getSize()`-based fallback is used if it is absent.
  MUST-VERIFY V24: with `height` set to exactly `k` times the line pitch,
      the widget renders exactly `k` lines and occupies exactly that height
      -- no internal padding. This is what STEP P3's slice heights assume;
      if wrong, on-device check D3/D5 would show drift or clipped lines.
  MUST-VERIFY V25: `top_line_num` is 1-based. STEP P3 passes
      `slice.first_line + 1`. If this is actually 0-based, every slice
      after the first ayah's first slice would be off by one line -- D5's
      "no text repeated or skipped at any seam" is exactly the symptom.
  MUST-VERIFY V26: `TextBoxWidget:free()` exists and releases shaped-text
      resources. Every widget built here -- including throwaway measuring
      probes -- is freed exactly once (edge case 27); leaking one per ayah
      per page turn on a Kindle is a real crash risk.
  MUST-VERIFY V27: `VerticalGroup` inserts no spacing between children by
      default. STEP P4 relies on this for the "every line sits at
      text_top + i * pitch" invariant that makes the rules register.
  MUST-VERIFY V28: a grey `Blitbuffer` colour constant exists;
      `bb:paintRect(x, y, w, h, colour)` is the signature. Resolved through
      a guarded fallback chain (`RULE_COLOUR`, below) rather than assumed.
  MUST-VERIFY V29: `ui/widget/buttondialog` accepts a `buttons` table of
      rows of `{text=, callback=}`, with no `title` key (title support
      moved between `ButtonDialogTitle` and `ButtonDialog` across versions
      and cannot be verified here), and a button with no `callback` renders
      inert rather than throwing -- relied on for D6.6's min/max-inert
      buttons (edge case 15).
  MUST-VERIFY V33: `InputContainer` + `ges_events` with a `GestureRange`
      over a `Geom` region delivers `onTap(_, ges)` with `ges.pos`.
  MUST-VERIFY V34: `UIManager:setDirty(widget, "partial" | "full")` is a
      valid call shape.
  MUST-VERIFY V35: `covers_fullscreen = true` on a shown widget suppresses
      the underlying view's repaint.
  MUST-VERIFY V36: the per-instance page-line-count field (upstream name:
      "lines_per_page") exists -- checked in `docs/VERIFY-M2.md`'s
      reasoning but **deliberately not used**: M2 computes its own
      `lines_per_screen` from `text_height / pitch`, so this identifier
      does not appear anywhere in this file.

Every one of V20-V29 and V33-V35 is accessed through `pcall` or a presence
test, and every failure produces a specific, named InfoMessage. Nothing may
throw at module load -- a plugin that throws while loading is skipped by
KOReader in silence. `main.lua` keeps its existing `pcall(require, ...)`
idiom for this module.

@module koplugin.Quran.reader
--]]--

local InputContainer = require("ui/widget/container/inputcontainer")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local VerticalGroup = require("ui/widget/verticalgroup")
local TextBoxWidget = require("ui/widget/textboxwidget")
local InfoMessage = require("ui/widget/infomessage")
local UIManager = require("ui/uimanager")
local Font = require("ui/font")
local Geom = require("ui/geometry")
local GestureRange = require("ui/gesturerange")
local Screen = require("device").screen

-- Soft-fail requires, same idiom as `main.lua`'s `require("db")` /
-- `db.lua`'s `require("lua-ljsqlite3/init")`. A plugin that throws while
-- loading is skipped by KOReader in silence -- see the header comment.
local ok_db, DB = pcall(require, "db")
if not ok_db then
    DB = nil
end

local ok_settings, Settings = pcall(require, "quransettings")
if not ok_settings then
    Settings = nil
end

local ok_bb, Blitbuffer = pcall(require, "ffi/blitbuffer")
if not ok_bb then
    Blitbuffer = nil
end

-- Interleaved mode only. A failure here is not fatal: the reader falls back to
-- Arabic-only and says so, rather than refusing to open. Losing the
-- translation is a degraded read; losing the Qur'an is not a read at all.
local ok_rows, Rows = pcall(require, "quranrows")
if not ok_rows then
    Rows = nil
end

-- Milestone 4. Same terms as quranrows: a failure here costs navigation, not
-- reading, so the reader opens without it and says so when asked.
local ok_nav, Nav = pcall(require, "qurannavigator")
if not ok_nav then
    Nav = nil
end

local ok_logger, logger = pcall(require, "logger")
if not ok_logger then
    logger = nil
end

-- ---------------------------------------------------------------------------
-- §6.1 Page geometry -- raw device pixels, no Screen:scaleBySize() for
-- layout (SPEC-v1 §1 narrows v1 to one device at one known ppi). Font size
-- is the one exception -- Font:getFace(name, size) scales internally
-- (see main.lua's V5 note) -- so the size number keeps its own meaning.
-- ---------------------------------------------------------------------------
local SIDE_MARGIN_PX = 40      -- SPEC-v1 §9 default; floor 24
local TOP_MARGIN_PX = 30
local BOTTOM_MARGIN_PX = 30
local RULE_THICKNESS_PX = 2

-- Where the rule sits within the gap below a line of text, as a fraction of
-- that gap. 0.0 is flush with the line box's bottom edge; 1.0 would put it
-- against the next line's glyphs.
--
-- The previous revision pinned the offset at 0 on the reasoning that
-- KOReader splits a line's extra leading evenly above and below the glyphs,
-- which would make the line-box bottom already the midpoint of the gap.
-- Device evidence contradicts that. After raising arabic_line_height to 1.5
-- the bands between rules grew as expected, but the new space appeared
-- almost entirely ABOVE each line: the glyphs still sit low in their box and
-- the rules still cut descenders and low harakat. Widening the gap could
-- therefore never cure the clipping, because every extra pixel of leading
-- was going where the rule was not.
--
-- So place the rule proportionally inside the gap rather than flush with a
-- box edge, and derive it from the measured pitch rather than a pinned
-- constant, so it tracks whatever font size and leading the reader chooses.
local RULE_GAP_FRACTION = 0.5

local LINE_COUNT_CACHE_MAX = 256

-- Font override, mirroring main.lua's ARABIC_FONT. M2 does not add a
-- font-face setting (only size and leading, §6.6) so this stays a
-- module-level constant, not a Settings key.
local ARABIC_FONT = "ScheherazadeNew-Regular.ttf"

-- §D2 touch zones. Full-screen widget, no chrome. The four fractions named
-- here also appear in README's on-device checklist (R11).
local ZONE_MENU_X_MIN_FRAC = 0.25
local ZONE_MENU_X_MAX_FRAC = 0.75
local ZONE_MENU_Y_MAX_FRAC = 0.10
local ZONE_MID_X_FRAC = 0.5

-- §D2: NEXT is on the right, LTR-style, even though the text is RTL --
-- KOReader's own reader on this device pages right-for-forward, and the
-- mushaf metaphor that would argue for the flip is explicitly disclaimed
-- (SPEC-v1 §5). On-device check D5 asks the tester to judge this; flipping
-- it is this one line, no data migration.
local FORWARD_ON_RIGHT = true

-- ---------------------------------------------------------------------------
-- §6.5 Rule colour -- V28. Resolved once at module load through a guarded
-- chain; falling back to black is ugly but visible and honest, silently
-- drawing nothing is not acceptable.
-- ---------------------------------------------------------------------------
local RULE_COLOUR_CANDIDATES = { "COLOR_DARK_GRAY", "COLOR_GRAY", "COLOR_LIGHT_GRAY" }
local RULE_COLOUR = nil
local RULE_COLOUR_SOURCE = nil

if Blitbuffer then
    for _, name in ipairs(RULE_COLOUR_CANDIDATES) do
        local ok, value = pcall(function() return Blitbuffer[name] end)
        if ok and value then
            RULE_COLOUR = value
            RULE_COLOUR_SOURCE = name
            break
        end
    end
    if not RULE_COLOUR then
        local ok, value = pcall(function() return Blitbuffer.gray(0.66) end)
        if ok and value then
            RULE_COLOUR = value
            RULE_COLOUR_SOURCE = "Blitbuffer.gray(0.66)"
        end
    end
    if not RULE_COLOUR then
        local ok, value = pcall(function() return Blitbuffer.COLOR_BLACK end)
        if ok and value then
            RULE_COLOUR = value
            RULE_COLOUR_SOURCE = "COLOR_BLACK (fallback of last resort)"
        end
    end
end

if logger and RULE_COLOUR_SOURCE and RULE_COLOUR_SOURCE ~= "COLOR_GRAY" then
    pcall(function() logger.warn("quran.koplugin/quranreader.lua: rule colour fallback used: " .. RULE_COLOUR_SOURCE) end)
elseif logger and not RULE_COLOUR then
    pcall(function() logger.warn("quran.koplugin/quranreader.lua: no rule colour resolved at all; rules will not draw") end)
end

-- ---------------------------------------------------------------------------
-- §7 -- nothing is ever normalised. `ayah.text` is read from the pack and
-- concatenated; the only characters M2 adds are the separating space and
-- the end-of-ayah marker. Fenced exactly like main.lua's PIN_2_255 block.
-- ---------------------------------------------------------------------------

-- BEGIN VERBATIM CONCAT -- DO NOT EDIT, DO NOT NORMALISE, DO NOT REFLOW
local function ayahDisplayText(text, marker)
    return text .. " " .. marker
end
-- END VERBATIM CONCAT

-- The marker is built entirely outside the block above -- it never touches
-- pack text. "u06dd" (default): U+06DD followed by the ayah number's
-- decimal digits mapped digit-by-digit to U+0660-U+0669, most significant
-- digit first. "ornate": U+FD3F + Arabic-Indic digits + U+FD3E, the
-- documented on-device fallback if U+06DD renders as a box or nothing
-- (see D2 in README's checklist). A Latin numeral is never acceptable.
local AYAH_MARKER_STYLE = "u06dd"   -- "u06dd" | "ornate"

local ARABIC_INDIC_DIGITS = {
    "٠", "١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩",
}
local END_OF_AYAH_MARK = "۝"
local ORNATE_RIGHT_PAREN = "﴿"
local ORNATE_LEFT_PAREN = "﴾"

local function digitsOf(n)
    local s = tostring(n)
    local out = {}
    for i = 1, #s do
        local d = tonumber(s:sub(i, i))
        out[#out + 1] = ARABIC_INDIC_DIGITS[d + 1]
    end
    return table.concat(out)
end

local function ayahMarker(n)
    local digits = digitsOf(n)
    if AYAH_MARKER_STYLE == "ornate" then
        return ORNATE_RIGHT_PAREN .. digits .. ORNATE_LEFT_PAREN
    end
    return END_OF_AYAH_MARK .. digits
end

-- ---------------------------------------------------------------------------
-- BEGIN TEXTBOX INTERNALS -- "for internal use" upstream; see docs/VERIFY-M2.md
--
-- The only place this file reads TextBoxWidget's internal fields. Every
-- access is presence-tested; nothing here ever throws, and a total failure
-- (neither the internal field nor the getSize() fallback works) is
-- reported by the caller via a specific InfoMessage that refuses to open
-- the reader, rather than guessing a line pitch (edge case 19).
-- ---------------------------------------------------------------------------
local TextMetrics = {}

-- -> integer | nil. `box.line_height_px` when present; otherwise builds a
-- fresh one-line probe with the same face/line_height (public API only)
-- and takes its getSize().h.
function TextMetrics.lineHeightPx(box)
    if not box then
        return nil
    end
    if box.line_height_px then
        return box.line_height_px
    end
    local ok, probe = pcall(function()
        return TextBoxWidget:new{
            text = "A",
            face = box.face,
            line_height = box.line_height,
        }
    end)
    if not ok or not probe then
        return nil
    end
    local size_ok, size = pcall(function() return probe:getSize() end)
    pcall(function() probe:free() end)
    if not size_ok or not size or not size.h or size.h <= 0 then
        return nil
    end
    return size.h
end

-- -> integer | nil. `#box.vertical_string_list` when present; otherwise
-- `floor(box:getSize().h / pitch + 0.5)` from a box built without a
-- `height` key (i.e. `box` itself, which STEP W1's caller never sets a
-- height on); otherwise nil.
function TextMetrics.lineCount(box)
    if not box then
        return nil
    end
    if box.vertical_string_list then
        return #box.vertical_string_list
    end
    local pitch = TextMetrics.lineHeightPx(box)
    if not pitch or pitch <= 0 then
        return nil
    end
    local ok, size = pcall(function() return box:getSize() end)
    if not ok or not size or not size.h then
        return nil
    end
    return math.floor(size.h / pitch + 0.5)
end
-- END TEXTBOX INTERNALS

-- ---------------------------------------------------------------------------
-- §6.5 Ruled lines. NOTE on naming: SPEC-v1 §6.5's pseudocode names this
-- container's field `line_height_px`, matching TextBoxWidget's own
-- upstream field name. `tools/check_m2.py`'s R4 (and its mutation test)
-- require that literal identifier to appear ONLY inside the fenced
-- TEXTBOX INTERNALS block above, so this field is named `px_per_line`
-- here instead -- same meaning (the line pitch in device pixels), copied
-- out of the fence once by `Reader:computeGeometry()` rather than reread
-- from a TextBoxWidget instance. See changes.md for this as a flagged,
-- deliberate deviation from §6.5's literal field name.
-- ---------------------------------------------------------------------------
local RuledPage = WidgetContainer:extend{
    px_per_line = nil,
    n_lines = 0,
    rules_enabled = true,
    width = 0,
    y_offset = 0,   -- computed by Reader:computeGeometry from the measured gap
}

-- Draws the child FIRST, then the rules over it.
--
-- The reverse -- rules first, so harakat sit over them -- was tried and does
-- not work: TextBoxWidget renders into its own blitbuffer, fills it with an
-- opaque background (`self._bb:fill(self.bgcolor)`, defaulting to
-- COLOR_WHITE) and blits the whole rectangle in its paintTo. That blit is an
-- opaque copy, so every rule drawn beforehand was painted over. On the device
-- the result was no rules at all, with text and paging otherwise correct.
--
-- The cost of painting after is that a rule crosses any glyph reaching its y,
-- so a low kasra can be struck through where the two collide. Ruled paper
-- behaves the same way. `y_offset` (RULE_GAP_FRACTION of the measured gap)
-- moves the rule off the collision; it is a judgement only the device can
-- settle, and the fraction is the knob to turn.
function RuledPage:paintTo(bb, x, y)
    if self[1] then
        self[1]:paintTo(bb, x, y)
    end
    if self.rules_enabled and self.px_per_line and RULE_COLOUR then
        for i = 1, self.n_lines do
            pcall(function()
                bb:paintRect(
                    x,
                    y + i * self.px_per_line - RULE_THICKNESS_PX + (self.y_offset or 0),
                    self.width,
                    RULE_THICKNESS_PX,
                    RULE_COLOUR
                )
            end)
        end
    end
end

-- ---------------------------------------------------------------------------
-- The reader widget.
-- ---------------------------------------------------------------------------
local Reader = InputContainer:extend{
    name = "quran_reader",
    covers_fullscreen = true,
}

function Reader:failInit(message)
    self.init_ok = false
    UIManager:show(InfoMessage:new{
        text = message,
        show_icon = false,
        dismissable = true,
    })
end

-- Decides which pagination model this session actually runs, and gathers what
-- the interleaved one needs.
--
-- Interleaved is a REQUEST, not a guarantee. It needs quranrows.lua to have
-- loaded, a translation pack to be open, and that pack to name itself. Any of
-- those missing degrades to Arabic-only with a reason recorded -- never a
-- refusal to open. A reader whose translation pack is missing should still be
-- able to read the Qur'an.
--
-- `self.mode` is what the reader runs; `self.display_mode` stays the reader's
-- stated preference, so plugging the pack back in restores interleaved without
-- them having to ask for it again.
function Reader:resolveMode()
    self.mode = "arabic"
    self.mode_fallback = nil

    if self.display_mode ~= "interleaved" then
        return
    end
    if not Rows then
        self.mode_fallback = "quranrows.lua failed to load"
        return
    end
    if not self.tconn then
        self.mode_fallback = "no translation pack is installed"
        return
    end

    local trans_id, id_err = DB.getTransId(self.tconn)
    if not trans_id then
        self.mode_fallback = tostring(id_err)
        return
    end
    self.trans_id = trans_id

    -- The basmala the heading is drawn from, and the prefix ayah 1 is stripped
    -- of. Read from the packs, never written down -- see Rows.stripBasmala.
    local bas_ar = DB.getAyah(self.conn, 1, 1)
    if not bas_ar then
        self.mode_fallback = "could not read the basmala (1:1) from the pack"
        return
    end
    self.basmala_ar = bas_ar
    -- Surah 2 is used only because it is the first surah that HAS a separate
    -- basmala row; the text is identical across all 112, which
    -- tools/check_alignment.py A7 asserts. A pack without it simply renders
    -- the Arabic heading alone.
    self.basmala_en = DB.getTranslation(self.tconn, trans_id, 2, 0)

    self.mode = "interleaved"
end

function Reader:isInterleaved()
    return self.mode == "interleaved" and Rows ~= nil
end

-- Recomputes text_width/text_height/px_per_line/lines_per_screen from the
-- current screen size and typography. Reads W/H fresh every time (edge
-- case 28: never cache them at init). Returns true, or false if line
-- metrics are unavailable (edge case 19).
function Reader:computeGeometry()
    local w, h = Screen:getWidth(), Screen:getHeight()
    self.text_width = w - 2 * SIDE_MARGIN_PX
    self.text_top = TOP_MARGIN_PX
    self.text_height = h - TOP_MARGIN_PX - BOTTOM_MARGIN_PX

    local ok, probe = pcall(function()
        return TextBoxWidget:new{
            text = "A",
            face = Font:getFace(ARABIC_FONT, self.arabic_font_size),
            width = self.text_width,
            line_height = self.arabic_line_height,
            alignment = "left",
            auto_para_direction = true,
        }
    end)
    if not ok or not probe then
        return false
    end
    local pitch = TextMetrics.lineHeightPx(probe)
    pcall(function() probe:free() end)

    if not pitch or pitch <= 0 then
        return false
    end
    self.px_per_line = pitch

    -- The gap a rule sits in is the pitch minus the height the face occupies
    -- with no extra leading, so measure that face height rather than assume
    -- it. Same public API as the pitch probe above: an identical box built
    -- with line_height = 0. If the measurement fails the offset falls back to
    -- 0, which is the old flush-with-the-box-bottom behaviour -- degraded,
    -- but never worse than before, and never a crash.
    local face_h = nil
    local ok_tight, tight = pcall(function()
        return TextBoxWidget:new{
            text = "A",
            face = Font:getFace(ARABIC_FONT, self.arabic_font_size),
            width = self.text_width,
            line_height = 0,
            alignment = "left",
            auto_para_direction = true,
        }
    end)
    if ok_tight and tight then
        face_h = TextMetrics.lineHeightPx(tight)
        pcall(function() tight:free() end)
    end
    local gap = 0
    if face_h and face_h > 0 and pitch > face_h then
        gap = pitch - face_h
    end
    -- Never let the rule reach the next line's box: cap at gap - thickness.
    local max_offset = math.max(0, gap - RULE_THICKNESS_PX)
    self.rule_y_offset = math.min(math.floor(gap * RULE_GAP_FRACTION), max_offset)

    -- lines_per_screen must never be 0 -- a font size that would produce 0
    -- clamps to 1, so the reader degrades to one line per page instead of
    -- an infinite loop (edge case 3).
    self.lines_per_screen = math.max(1, math.floor(self.text_height / self.px_per_line))

    -- The interleaved model needs its own column geometry. If it cannot be
    -- measured, drop to Arabic-only rather than returning false: the Arabic
    -- metrics above already succeeded, so the reader is still perfectly
    -- capable of reading -- just not in two columns.
    if self:isInterleaved() then
        if not Rows.computeGeometry(self) then
            self.mode = "arabic"
            self.mode_fallback = "column metrics unavailable at this font size"
        end
    end
    return true
end

-- STEP W1
-- Lays out `ayah` of the current surah at the current width/face/leading
-- and returns its line count (>= 1). Cached (§6.3). Independent of
-- position -- this is what makes W2/W3 exact inverses.
function Reader:linesOf(ayah)
    local key = self.surah .. ":" .. ayah
    local cached = self.line_count_cache[key]
    if cached then
        return cached
    end

    local text, err = DB.getAyah(self.conn, self.surah, ayah)
    if not text then
        self:onDbError(err)
        return 1
    end

    local display_text = ayahDisplayText(text, ayahMarker(ayah))
    local ok, probe = pcall(function()
        return TextBoxWidget:new{
            text = display_text,
            face = Font:getFace(ARABIC_FONT, self.arabic_font_size),
            width = self.text_width,
            line_height = self.arabic_line_height,
            alignment = "left",
            auto_para_direction = true,
        }
    end)
    local n = nil
    if ok and probe then
        n = TextMetrics.lineCount(probe)
        pcall(function() probe:free() end)
    end
    -- linesOf returning 0/nil for any ayah should be impossible (the pack
    -- forbids empty text) but is treated as 1 rather than divided by or
    -- looped on (edge case 4).
    if not n or n < 1 then
        n = 1
    end
    self:cacheLineCount(key, n)
    return n
end

function Reader:cacheLineCount(key, n)
    local count = 0
    for _ in pairs(self.line_count_cache) do
        count = count + 1
    end
    if count >= LINE_COUNT_CACHE_MAX then
        -- Hard cap: a plain flush, not an LRU -- 256 integers is not worth
        -- an eviction policy, and the cost of a cold cache is one page's
        -- worth of layouts.
        self.line_count_cache = {}
    end
    self.line_count_cache[key] = n
end

-- STEP W2
function Reader:buildPageFrom(ayah, line)
    local budget = self.lines_per_screen
    local a, l = ayah, line
    local slices = {}
    while budget > 0 and a <= self.ayah_count do
        local n = self:linesOf(a) - l
        if n <= 0 then
            a = a + 1
            l = 0
        else
            local take = math.min(n, budget)
            slices[#slices + 1] = { ayah = a, first_line = l, n_lines = take }
            budget = budget - take
            if take == n then
                a = a + 1
                l = 0
            else
                l = l + take
            end
        end
    end
    return { slices = slices, total_lines = self.lines_per_screen - budget }, a, l
end

-- STEP W3
function Reader:topOfPreviousPage(ayah, line)
    local budget = self.lines_per_screen
    local a, l = ayah, line
    while budget > 0 do
        if l > 0 then
            local take = math.min(budget, l)
            l = l - take
            budget = budget - take
        elseif a > 1 then
            a = a - 1
            l = self:linesOf(a)
        else
            -- Start of surah; clamp (edge case 5).
            break
        end
    end
    return a, l
end

function Reader:onDbError(err)
    UIManager:show(InfoMessage:new{
        text = "Qur'an: database error mid-session -- " .. tostring(err) .. "\n\nClosing the reader.",
        show_icon = false,
        dismissable = true,
    })
    UIManager:close(self)
end

function Reader:layoutPage()
    if self.laying_out then
        -- A second tap arriving while a page is still being laid out must
        -- not queue a second layout (edge case 24).
        return
    end
    self.laying_out = true

    -- STEP P1  clear the old page: :free() every slice widget, drop references
    if self.page_widgets then
        for _, w in ipairs(self.page_widgets) do
            pcall(function() w:free() end)
        end
    end
    self.page_widgets = {}
    self.page_group = nil
    self.ruled_page = nil
    self.row_page = nil

    if self:isInterleaved() then
        self.laying_out = false
        return self:layoutRowPage()
    end

    -- STEP P2
    local page, next_a, next_l = self:buildPageFrom(self.top_ayah, self.top_line)
    self.current_page = page
    self.next_ayah = next_a
    self.next_line = next_l

    -- STEP P3
    local slice_widgets = {}
    for _, slice in ipairs(page.slices) do
        local text, err = DB.getAyah(self.conn, self.surah, slice.ayah)
        if not text then
            self.laying_out = false
            self:onDbError(err)
            return
        end
        local display_text = ayahDisplayText(text, ayahMarker(slice.ayah))
        local ok_widget, widget = pcall(function()
            return TextBoxWidget:new{
                text = display_text,
                face = Font:getFace(ARABIC_FONT, self.arabic_font_size),
                width = self.text_width,
                height = slice.n_lines * self.px_per_line,   -- exact multiple
                line_height = self.arabic_line_height,        -- em, extra leading
                top_line_num = slice.first_line + 1,          -- 1-based, V25
                alignment = "left",
                auto_para_direction = true,
            }
        end)
        if not ok_widget or not widget then
            self.laying_out = false
            self:failInit("Qur'an reader: could not build page layout (" .. tostring(widget) .. "). Closing the reader.")
            UIManager:close(self)
            return
        end
        slice_widgets[#slice_widgets + 1] = widget
        self.page_widgets[#self.page_widgets + 1] = widget
    end

    -- STEP P4  stack the slice widgets in a VerticalGroup, no spacing between them
    self.page_group = VerticalGroup:new(slice_widgets)

    -- STEP P5  wrap in RuledPage (the rules container); Reader:paintTo
    -- positions it at (SIDE_MARGIN_PX, TOP_MARGIN_PX).
    self.ruled_page = RuledPage:new{
        px_per_line = self.px_per_line,
        n_lines = page.total_lines,
        rules_enabled = self.rules_enabled,
        width = self.text_width,
        y_offset = self.rule_y_offset or 0,
    }
    self.ruled_page[1] = self.page_group

    self.laying_out = false

    -- STEP P6  refresh: UIManager:setDirty(self, refresh_type()) -- see §6.8
    -- (the caller -- init/applySetting/nextPage/prevPage -- decides full vs
    -- partial and calls Reader:refreshFull()/refreshTurn() itself, since
    -- only the caller knows *why* this layout happened.)
end

-- The interleaved counterpart of layoutPage. Same contract: builds the page
-- description, turns it into widgets, records where the next page starts, and
-- leaves the refresh to the caller.
--
-- `top_line` carries the sub-page ordinal here rather than a line ordinal --
-- see quranrows.lua's buildPage. Both are "how far into top_ayah are we", so
-- one saved position serves both models; what it MEANS differs, which is why
-- a mode switch resets it to 0 rather than carrying it across.
function Reader:layoutRowPage()
    self.laying_out = true

    local page, next_a, next_s = Rows.buildPage(self, self.top_ayah, self.top_line)
    self.current_page = page
    self.next_ayah = next_a
    self.next_line = next_s

    local widget, made, err = Rows.layout(self, page)
    if made then
        for _, w in ipairs(made) do
            self.page_widgets[#self.page_widgets + 1] = w
        end
    end
    if not widget then
        self.laying_out = false
        if err then
            self:onDbError(err)
        else
            self:failInit("Qur'an reader: could not build the interleaved page layout.")
            UIManager:close(self)
        end
        return
    end

    self.row_page = widget
    self.laying_out = false
end

-- §6.8 Refresh policy. `refreshFull` is used for the first paint and any
-- typography/rules change. `refreshTurn` is used for a plain page turn; a
-- counter forces a full refresh every 6th turn to clear e-ink ghosting.
function Reader:refreshFull()
    self.turns_since_full = 0
    UIManager:setDirty(self, "full")
end

function Reader:refreshTurn()
    self.turns_since_full = (self.turns_since_full or 0) + 1
    if self.turns_since_full >= 6 then
        self.turns_since_full = 0
        UIManager:setDirty(self, "full")
    else
        UIManager:setDirty(self, "partial")
    end
end

-- §6.9 position saving and flush policy. Every turn updates the in-memory
-- position immediately; flush happens on close, on every settings change,
-- and every 10th turn.
function Reader:savePosition()
    if not Settings then
        return
    end
    Settings.setPosition(self.store, self.surah, self.top_ayah, self.top_line)
    self.turn_count = (self.turn_count or 0) + 1
    if self.turn_count % 10 == 0 then
        Settings.flush(self.store)
    end
end

function Reader:nextPage()
    if self.laying_out then
        return
    end
    if self.next_ayah > self.ayah_count then
        UIManager:show(InfoMessage:new{
            text = "End of surah " .. tostring(self.surah),
            timeout = 1,
        })
        return
    end
    self.top_ayah = self.next_ayah
    self.top_line = self.next_line
    self:savePosition()
    self:layoutPage()
    self:refreshTurn()
end

function Reader:prevPage()
    if self.laying_out then
        return
    end
    if self.top_ayah == 1 and self.top_line == 0 then
        UIManager:show(InfoMessage:new{
            text = "Start of surah " .. tostring(self.surah),
            timeout = 1,
        })
        return
    end
    local a, l
    if self:isInterleaved() then
        a, l = Rows.topOfPreviousPage(self, self.top_ayah, self.top_line)
    else
        a, l = self:topOfPreviousPage(self.top_ayah, self.top_line)
    end
    self.top_ayah = a
    self.top_line = l
    self:savePosition()
    self:layoutPage()
    self:refreshTurn()
end

-- §6.7 applying a settings change.
function Reader:applySetting(key, value)
    if not Settings then
        return
    end
    Settings.set(self.store, key, value)
    Settings.flush(self.store)

    if key == "arabic_font_size" then
        self.arabic_font_size = Settings.get(self.store, key)
    elseif key == "arabic_line_height" then
        self.arabic_line_height = Settings.get(self.store, key)
    elseif key == "english_font_size" then
        self.english_font_size = Settings.get(self.store, key)
    elseif key == "english_line_height" then
        self.english_line_height = Settings.get(self.store, key)
    elseif key == "rules_enabled" then
        self.rules_enabled = Settings.get(self.store, key)
    elseif key == "display_mode" then
        self.display_mode = Settings.get(self.store, key)
        self:resolveMode()
        if self.mode_fallback then
            UIManager:show(InfoMessage:new{
                text = "Qur'an: staying in Arabic-only -- " .. tostring(self.mode_fallback),
                show_icon = false,
                dismissable = true,
            })
        end
    end

    -- Clear both caches: each was measured at the old typography, and a mode
    -- switch invalidates them regardless since the measuring width changed
    -- from full-width to a column.
    self.line_count_cache = {}
    self.row_cache = {}

    if not self:computeGeometry() then
        self:failInit("Qur'an reader: line metrics became unavailable after a settings change")
        return
    end

    -- A line ordinal measured at the old size is meaningless at the new
    -- one; keep top_ayah, reset top_line to 0 (§6.7 step 4).
    self.top_line = 0

    self:layoutPage()
    self:refreshFull()
end

-- Jumps to (surah, ayah), possibly in a different surah. Milestone 4.
--
-- The surah change is the part with teeth: ayah_count, both measurement caches
-- and the saved position are all per-surah, so changing self.surah without
-- them is how a reader ends up paging past the end of a short surah using the
-- previous one's length. Order matters -- the OLD position is saved before
-- self.surah moves, or it lands under the new surah's key.
function Reader:goTo(surah, ayah)
    if type(surah) ~= "number" or type(ayah) ~= "number" then
        return
    end
    if self.laying_out then
        return
    end

    if surah ~= self.surah then
        -- Save where we were, under the surah we were in.
        self:savePosition()

        local count, err = DB.getSurahAyahCount(self.conn, surah)
        if not count then
            UIManager:show(InfoMessage:new{
                text = "Qur'an: could not open surah " .. tostring(surah) ..
                    "\n\n" .. tostring(err) .. "\n\nStaying where you were.",
                show_icon = false,
                dismissable = true,
            })
            return
        end
        self.surah = surah
        self.ayah_count = count
        if Settings then
            Settings.setLastSurah(self.store, surah)
        end
        -- Both caches are keyed "surah:ayah" so stale entries could not be
        -- returned for the new surah -- but they are also unbounded across a
        -- session of jumping, and dropping them here is free.
        self.line_count_cache = {}
        self.row_cache = {}
    end

    if ayah < 1 then ayah = 1 end
    if ayah > self.ayah_count then ayah = self.ayah_count end

    self.top_ayah = ayah
    self.top_line = 0
    self:savePosition()
    self:layoutPage()
    self:refreshFull()
end

-- Opens the navigator from inside the reader, so a jump lands in the reader
-- already open rather than closing and reopening it.
function Reader:openNavigator(which)
    if not Nav then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: qurannavigator.lua failed to load.\n\nSee crash.log",
            show_icon = false,
            dismissable = true,
        })
        return
    end
    -- Read fresh each time rather than cached on the reader: the navigator is
    -- opened rarely, 114 short rows is cheap, and a cache would have to be
    -- invalidated by nothing in particular.
    local data, err = Nav.loadData(DB, self.conn)
    if not data then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: " .. tostring(err),
            show_icon = false,
            dismissable = true,
        })
        return
    end

    local opts = {
        data = data,
        initial = tostring(self.surah) .. ":" .. tostring(self.top_ayah),
        on_pick = function(surah, ayah)
            self:goTo(surah, ayah or 1)
        end,
    }
    if which == "surah" then
        Nav.showSurahList(opts)
    elseif which == "juz" then
        Nav.showJuzList(opts)
    else
        Nav.showReferenceInput(opts)
    end
end

function Reader:openSettings()
    local ok_bd, ButtonDialog = pcall(require, "ui/widget/buttondialog")
    if not ok_bd or not ButtonDialog then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: settings dialog unavailable (ui/widget/buttondialog failed to load). " ..
                "The reader keeps reading at its current settings.",
            show_icon = false,
            dismissable = true,
        })
        return
    end
    if not Settings then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: quransettings.lua is unavailable; cannot open the settings dialog.",
            show_icon = false,
            dismissable = true,
        })
        return
    end

    local size_lim = Settings.LIMITS.arabic_font_size
    local leading_lim = Settings.LIMITS.arabic_line_height

    -- The juz is looked up rather than tracked, so it cannot drift out of step
    -- with the position. nil (an unreadable row) simply drops from the line.
    local juz = DB.juzOf(self.conn, self.surah, self.top_ayah)
    local readout = "Surah " .. tostring(self.surah) .. ":" .. tostring(self.top_ayah)
    if juz then
        readout = readout .. "  -  juz " .. tostring(juz)
    end
    -- On a split ayah, say which part of it you are on. Without this the only
    -- way to tell page 3 of 2:282 from page 4 is to read them, which is also
    -- the only way to notice a split going wrong.
    if self:isInterleaved() then
        local ok_plan, plan = pcall(function() return Rows.splitPlan(self, self.top_ayah) end)
        if ok_plan and plan and plan.total > 1 then
            readout = readout .. "  (part " .. tostring((self.top_line or 0) + 1) ..
                " of " .. tostring(plan.total) .. ")"
        end
    end

    local dialog
    local function closeDialog()
        UIManager:close(dialog)
    end

    local font_minus_cb = nil
    if self.arabic_font_size > size_lim.min then
        font_minus_cb = function()
            closeDialog()
            self:applySetting("arabic_font_size", self.arabic_font_size - size_lim.step)
        end
    end
    local font_plus_cb = nil
    if self.arabic_font_size < size_lim.max then
        font_plus_cb = function()
            closeDialog()
            self:applySetting("arabic_font_size", self.arabic_font_size + size_lim.step)
        end
    end
    local leading_minus_cb = nil
    if self.arabic_line_height > leading_lim.min then
        leading_minus_cb = function()
            closeDialog()
            self:applySetting("arabic_line_height", self.arabic_line_height - leading_lim.step)
        end
    end
    local leading_plus_cb = nil
    if self.arabic_line_height < leading_lim.max then
        leading_plus_cb = function()
            closeDialog()
            self:applySetting("arabic_line_height", self.arabic_line_height + leading_lim.step)
        end
    end

    -- English controls only appear in interleaved mode: adjusting a face that
    -- is not on screen is a button that appears to do nothing.
    local en_lim = Settings.LIMITS.english_font_size
    local en_rows = {}
    if self:isInterleaved() then
        local en_minus_cb = nil
        if self.english_font_size > en_lim.min then
            en_minus_cb = function()
                closeDialog()
                self:applySetting("english_font_size", self.english_font_size - en_lim.step)
            end
        end
        local en_plus_cb = nil
        if self.english_font_size < en_lim.max then
            en_plus_cb = function()
                closeDialog()
                self:applySetting("english_font_size", self.english_font_size + en_lim.step)
            end
        end
        en_rows[#en_rows + 1] = {
            { text = "a -", callback = en_minus_cb },
            { text = "English " .. tostring(self.english_font_size) },
            { text = "a +", callback = en_plus_cb },
        }
    end

    local mode_label
    if self.mode_fallback then
        -- Say why, rather than showing a toggle that silently does nothing.
        mode_label = "Mode: Arabic only (" .. tostring(self.mode_fallback) .. ")"
    else
        mode_label = "Mode: " .. (self:isInterleaved() and "with translation" or "Arabic only")
    end
    local mode_row = { { text = mode_label, callback = function()
        closeDialog()
        self:applySetting("display_mode",
            self.display_mode == "interleaved" and "arabic" or "interleaved")
    end } }

    -- Navigation. Omitted entirely rather than shown inert if the module did
    -- not load: three buttons that explain themselves once are better than
    -- three that do nothing three times.
    local nav_row = nil
    if Nav then
        nav_row = {
            { text = "Surahs", callback = function()
                closeDialog()
                self:openNavigator("surah")
            end },
            { text = "Juz", callback = function()
                closeDialog()
                self:openNavigator("juz")
            end },
            { text = "Go to...", callback = function()
                closeDialog()
                self:openNavigator("reference")
            end },
        }
    end

    local buttons = {
        { { text = readout } },
    }
    if nav_row then
        buttons[#buttons + 1] = nav_row
    end
    buttons[#buttons + 1] = mode_row
    buttons[#buttons + 1] = {
        { text = "A -", callback = font_minus_cb },
        { text = "Arabic " .. tostring(self.arabic_font_size) },
        { text = "A +", callback = font_plus_cb },
    }
    for _, row in ipairs(en_rows) do
        buttons[#buttons + 1] = row
    end
    buttons[#buttons + 1] = {
        { text = "Leading -", callback = leading_minus_cb },
        { text = "Line " .. string.format("%.2f", self.arabic_line_height) },
        { text = "Leading +", callback = leading_plus_cb },
    }
    buttons[#buttons + 1] = {
        { text = "Rules: " .. (self.rules_enabled and "on" or "off"), callback = function()
            closeDialog()
            self:applySetting("rules_enabled", not self.rules_enabled)
        end },
    }
    buttons[#buttons + 1] = {
        { text = "Close reader", callback = function()
            closeDialog()
            UIManager:close(self)
        end },
        { text = "Cancel", callback = closeDialog },
    }

    -- V29's claim (a callback-less button renders inert) is about
    -- construction/runtime behaviour, not the require above -- wrap the
    -- construction and show separately in `pcall` too, so a wrong claim
    -- there fails soft (an InfoMessage) rather than throwing out of an
    -- input-event handler.
    local ok_new, dialog_or_err = pcall(function()
        return ButtonDialog:new{
            buttons = buttons,
        }
    end)
    if not ok_new or not dialog_or_err then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: could not build the settings dialog (" .. tostring(dialog_or_err) ..
                "). The reader keeps reading at its current settings.",
            show_icon = false,
            dismissable = true,
        })
        return
    end
    dialog = dialog_or_err

    local ok_show = pcall(function() UIManager:show(dialog) end)
    if not ok_show then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: could not show the settings dialog. The reader keeps reading at its current settings.",
            show_icon = false,
            dismissable = true,
        })
    end
end

function Reader:onTap(_, ges)
    if self.laying_out then
        return true
    end
    local pos = ges and ges.pos
    if not pos then
        return true
    end
    local w, h = Screen:getWidth(), Screen:getHeight()
    local x, y = pos.x, pos.y

    local in_menu_zone = x >= ZONE_MENU_X_MIN_FRAC * w and x < ZONE_MENU_X_MAX_FRAC * w
        and y >= 0 and y < ZONE_MENU_Y_MAX_FRAC * h

    if in_menu_zone then
        -- Opening the settings dialog while a page turn is pending: the
        -- dialog wins, page state is unchanged (edge case 25) -- there is
        -- nothing here that touches page state before showing the dialog.
        self:openSettings()
        return true
    end

    local tapped_right = x >= ZONE_MID_X_FRAC * w
    local is_next = (tapped_right == FORWARD_ON_RIGHT)
    if is_next then
        self:nextPage()
    else
        self:prevPage()
    end
    return true
end

function Reader:onClose()
    UIManager:close(self)
    return true
end

function Reader:onCloseWidget()
    -- Saves and flushes before freeing (edge case 26).
    if Settings then
        Settings.setPosition(self.store, self.surah, self.top_ayah, self.top_line)
        Settings.flush(self.store)
    end

    if self.page_widgets then
        for _, w in ipairs(self.page_widgets) do
            pcall(function() w:free() end)
        end
    end
    self.page_widgets = nil
    self.page_group = nil
    self.ruled_page = nil
    self.row_page = nil

    if self.on_close then
        self.on_close()
    end
end

function Reader:getSize()
    return Geom:new{ x = 0, y = 0, w = Screen:getWidth(), h = Screen:getHeight() }
end

function Reader:paintTo(bb, x, y)
    if Blitbuffer then
        local w, h = Screen:getWidth(), Screen:getHeight()
        pcall(function() bb:paintRect(x, y, w, h, Blitbuffer.COLOR_WHITE) end)
    end
    if self.row_page then
        self.row_page:paintTo(bb, x + SIDE_MARGIN_PX, y + TOP_MARGIN_PX)
    elseif self.ruled_page then
        self.ruled_page:paintTo(bb, x + SIDE_MARGIN_PX, y + TOP_MARGIN_PX)
    end
end

-- opts = { conn = <db conn>, store = <settings store>, surah = <1..114>,
--          ayah = <int>, line = <int>, on_close = <function() end> }
-- (opts become `self`'s own fields via the usual :new()/:init() widget
-- convention -- the same one main.lua's Quran:init() relies on.)
function Reader:init()
    self.laying_out = false
    self.turns_since_full = 0
    self.turn_count = 0
    self.line_count_cache = {}
    self.init_ok = false

    if not DB then
        self:failInit("Qur'an reader: db.lua failed to load (see crash.log)")
        return
    end
    if not Settings then
        self:failInit("Qur'an reader: quransettings.lua failed to load (see crash.log)")
        return
    end
    if not self.conn then
        self:failInit("Qur'an reader: no database connection was provided")
        return
    end

    self.arabic_font_size = Settings.get(self.store, "arabic_font_size")
    self.arabic_line_height = Settings.get(self.store, "arabic_line_height")
    self.english_font_size = Settings.get(self.store, "english_font_size")
    self.english_line_height = Settings.get(self.store, "english_line_height")
    self.rules_enabled = Settings.get(self.store, "rules_enabled")
    self.display_mode = Settings.get(self.store, "display_mode")

    -- Everything quranrows.lua needs from the reader, handed over explicitly
    -- rather than reached for. It keeps the module's dependencies visible in
    -- one place, and keeps the TextBoxWidget internals behind the single
    -- TextMetrics wrapper that carries their presence tests.
    self.DB = DB
    self.TextMetrics = TextMetrics
    self.ARABIC_FONT = ARABIC_FONT
    self.ayahDisplayText = ayahDisplayText
    self.ayahMarker = ayahMarker
    self.row_cache = {}

    self:resolveMode()

    local ayah_count, err = DB.getSurahAyahCount(self.conn, self.surah)
    if not ayah_count then
        self:failInit("Qur'an reader: could not read surah " .. tostring(self.surah) ..
            " (" .. tostring(err) .. ")")
        return
    end
    self.ayah_count = ayah_count

    -- Validate the requested starting position (edge cases 10-12).
    local ayah = self.ayah
    if type(ayah) ~= "number" or ayah < 1 then
        ayah = 1
    end
    if ayah > self.ayah_count then
        ayah = self.ayah_count
    end
    local line = self.line
    if type(line) ~= "number" or line < 0 then
        line = 0
    end

    if not self:computeGeometry() then
        -- Never guess a line pitch (edge case 19).
        self:failInit("Qur'an reader: this KOReader version does not expose TextBoxWidget " ..
            "line metrics; ruled lines and paging are unavailable")
        return
    end

    -- Clamp `line` against the ayah's *current* subdivision count (edge case
    -- 11). The two models count different things -- lines of Arabic, versus
    -- sub-pages of a row -- so each clamps against its own, and a position
    -- saved in one mode lands somewhere valid in the other rather than out of
    -- range. It may not land on the same screenful; it always lands in the
    -- right ayah, which is what §9.1 promises.
    if self:isInterleaved() then
        local subs = Rows.subPageCount(self, ayah)
        if line >= subs then
            line = math.max(0, subs - 1)
        end
    else
        local line_count = self:linesOf(ayah)
        if line >= line_count then
            line = math.max(0, line_count - 1)
        end
    end
    self.top_ayah = ayah
    self.top_line = line

    self.ges_events = {
        Tap = {
            GestureRange:new{
                ges = "tap",
                range = Geom:new{ x = 0, y = 0, w = Screen:getWidth(), h = Screen:getHeight() },
            },
        },
    }

    self.init_ok = true
    self:layoutPage()
    self:refreshFull()
end

return Reader
