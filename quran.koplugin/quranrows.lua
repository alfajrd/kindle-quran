--[[--
Qur'an, Milestone 3: the interleaved side-by-side layout (SPEC-v1 §9.1).

Translation left, Arabic right, one row per ayah, a rule in the gutter below
each row. Loaded and used only in interleaved mode; Arabic-only mode never
touches this file and keeps the line-based pagination in `quranreader.lua`.

WHY THIS IS A SEPARATE FILE
---------------------------
The two modes are not a display toggle over one engine, they are two
pagination models (docs/BACKLOG.md B1). Arabic-only packs a page by LINES;
interleaved packs it by ROWS whose height is the taller of two cells. Trying
to express both in one set of functions produced a knot; keeping them apart
costs a little duplication and buys the ability to reason about either one.

WHY THE RULES ARE SIMPLER HERE
------------------------------
`quranreader.lua`'s rules are drawn every `line_height_px` and can land on any
glyph -- the clipping that RULE_GAP_FRACTION exists to tune. A row rule sits in
a gutter this file computed, between two rows it also computed. No glyph is in
that band, so none can be cut, and there is nothing to tune. Do not "unify"
the two rule models: the per-line one is only correct because it is tuned, and
this one is only simple because it is not needed there.

MUST-VERIFY (device)
--------------------
  V40 `TextBoxWidget` honours `para_direction_rtl` together with
      `auto_para_direction = false`. §9.1 requires each cell's direction to be
      SET rather than detected: a translation opening with "39." is exactly
      where detection is least reliable. If the key is ignored, the failure is
      visible (English right-aligned or Arabic laid out LTR) rather than
      silent, and `auto_para_direction` is the fallback.
  V41 A `TextBoxWidget` given `height` shorter than its text renders the
      window starting at `top_line_num` and clips the rest. Already relied on
      by the Arabic-only pager (V25), reused here for oversized rows.
  V42 Two `TextBoxWidget`s painted at different x within one parent do not
      interfere. Each owns its blitbuffer and blits opaquely (that opacity is
      what forced the paint-order fix in quranreader.lua), so the columns must
      not overlap: COLUMN_GUTTER_PX is what keeps them apart.

@module koplugin.Quran.rows
--]]--

local TextBoxWidget = require("ui/widget/textboxwidget")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local Font = require("ui/font")

local ok_bb, Blitbuffer = pcall(require, "ffi/blitbuffer")
if not ok_bb then
    Blitbuffer = nil
end

local Rows = {}

-- Space between the two columns. Must be > 0: each TextBoxWidget blits its
-- own opaque rectangle, so overlapping columns would erase each other (V42).
Rows.COLUMN_GUTTER_PX = 32
-- Vertical space below a row. The rule sits inside it, which is the whole
-- reason a row rule cannot clip a glyph.
Rows.ROW_GAP_PX = 22
Rows.RULE_THICKNESS_PX = 2
-- Space below the basmala heading, before the surah's first row.
Rows.BASMALA_GAP_PX = 26

Rows.ENGLISH_FONT = "cfont"   -- KOReader's default content face

local function ruleColour()
    if not Blitbuffer then
        return nil
    end
    return Blitbuffer.COLOR_DARK_GRAY or Blitbuffer.COLOR_GRAY or Blitbuffer.COLOR_BLACK
end

-- ---------------------------------------------------------------------------
-- Text preparation
-- ---------------------------------------------------------------------------

-- Strips the basmala prefix from ayah 1 where SPEC-v1 §6 says it is a heading
-- rather than a numbered ayah.
--
-- The corpus stores the basmala INSIDE ayah 1 for all 113 surahs that have
-- one; the translation stores it as a separate ayah 0. Left alone the first
-- row of 112 surahs shows it on the Arabic side only. See
-- `tools/check_alignment.py`, which proves the precondition this relies on.
--
-- This is a deletion at a verified offset, never a search-and-replace: the
-- prefix is compared against Al-Fatiha's ayah 1 read from the pack, and the
-- text is only cut when it genuinely starts with those exact bytes. No Arabic
-- is written down anywhere in this file. If the prefix is absent -- a pack
-- that stores the basmala differently -- the text is returned untouched, and
-- the reader shows a slightly redundant basmala instead of a corrupted ayah.
function Rows.stripBasmala(self, ayah, text)
    if ayah ~= 1 or not text then
        return text
    end
    if self.surah == 1 or self.surah == 9 then
        -- Al-Fatiha: the basmala IS ayah 1, and stays numbered.
        -- At-Tawbah: there is none.
        return text
    end
    local prefix = self.basmala_ar
    if not prefix or prefix == "" then
        return text
    end
    if text:sub(1, #prefix) ~= prefix then
        return text
    end
    local rest = text:sub(#prefix + 1)
    -- Never return an empty ayah: if the prefix were the whole text, the row
    -- would collapse and the ayah would vanish. Falling back to the original
    -- is wrong-looking; vanishing scripture is worse.
    if rest:gsub("%s", "") == "" then
        return text
    end
    return (rest:gsub("^%s+", ""))
end

function Rows.arabicText(self, ayah)
    local text, err = self.DB.getAyah(self.conn, self.surah, ayah)
    if not text then
        return nil, err
    end
    text = Rows.stripBasmala(self, ayah, text)
    return self.ayahDisplayText(text, self.ayahMarker(ayah)), nil
end

-- The translation cell. The verse number is a Latin numeral prefixed to the
-- English, matching the reference layout; the Arabic cell carries U+06DD with
-- Arabic-Indic digits instead. Never a Latin numeral inside the Arabic.
function Rows.englishText(self, ayah)
    if not self.tconn then
        return nil, "no translation pack"
    end
    local text, err = self.DB.getTranslation(self.tconn, self.trans_id, self.surah, ayah)
    if not text then
        return nil, err
    end
    return tostring(ayah) .. ". " .. text, nil
end

-- ---------------------------------------------------------------------------
-- Measurement
-- ---------------------------------------------------------------------------

-- -> (line_count, line_pitch_px), either possibly nil.
--
-- Goes through the reader's TextMetrics rather than reading
-- `vertical_string_list` / `line_height_px` directly. Those fields are
-- commented "for internal use" upstream, and TextMetrics already carries the
-- presence tests and the public-API fallbacks for when they are absent
-- (docs/VERIFY-M2.md). One place to fix on a KOReader upgrade, not two.
local function measureBox(self, text, face, width, line_height, rtl)
    local ok, box = pcall(function()
        return TextBoxWidget:new{
            text = text,
            face = face,
            width = width,
            line_height = line_height,
            alignment = rtl and "right" or "left",
            auto_para_direction = false,
            para_direction_rtl = rtl and true or false,
        }
    end)
    if not ok or not box then
        return nil, nil
    end
    local M = self.TextMetrics
    local lines = M and M.lineCount(box) or nil
    local pitch = M and M.lineHeightPx(box) or nil
    pcall(function() box:free() end)
    return lines, pitch
end

function Rows.arabicFace(self)
    return Font:getFace(self.ARABIC_FONT, self.arabic_font_size)
end

function Rows.englishFace(self)
    return Font:getFace(Rows.ENGLISH_FONT, self.english_font_size)
end

-- Recomputes the column geometry. Returns true, or false if either face's
-- line pitch is unavailable -- never guessed (edge case 19).
function Rows.computeGeometry(self)
    self.col_width = math.floor((self.text_width - Rows.COLUMN_GUTTER_PX) / 2)
    if self.col_width < 80 then
        return false
    end

    local _, pitch_ar = measureBox(self, "A", Rows.arabicFace(self), self.col_width,
                                   self.arabic_line_height, true)
    local _, pitch_en = measureBox(self, "A", Rows.englishFace(self), self.col_width,
                                   self.english_line_height, false)
    if not pitch_ar or pitch_ar <= 0 or not pitch_en or pitch_en <= 0 then
        return false
    end
    self.row_pitch_ar = pitch_ar
    self.row_pitch_en = pitch_en

    -- Lines of each face that fit one page. Never 0: a face too large for the
    -- page clamps to 1 line, degrading to a very slow read rather than an
    -- infinite loop (edge case 3).
    self.lines_per_page_ar = math.max(1, math.floor(self.text_height / pitch_ar))
    self.lines_per_page_en = math.max(1, math.floor(self.text_height / pitch_en))
    return true
end

-- -> { n_ar, n_en, height } for one ayah's row, cached.
function Rows.metrics(self, ayah)
    local key = self.surah .. ":" .. ayah
    local cached = self.row_cache and self.row_cache[key]
    if cached then
        return cached
    end

    local ar = Rows.arabicText(self, ayah)
    local en = Rows.englishText(self, ayah)

    local n_ar = nil
    if ar then
        n_ar = measureBox(self, ar, Rows.arabicFace(self), self.col_width,
                          self.arabic_line_height, true)
    end
    local n_en = nil
    if en then
        n_en = measureBox(self, en, Rows.englishFace(self), self.col_width,
                          self.english_line_height, false)
    end
    -- A missing or unmeasurable cell counts as one line rather than zero, so
    -- a row is never height 0 and the pager can never fail to advance.
    if not n_ar or n_ar < 1 then n_ar = 1 end
    if not n_en or n_en < 1 then n_en = 1 end

    local m = {
        n_ar = n_ar,
        n_en = n_en,
        height = math.max(n_ar * self.row_pitch_ar, n_en * self.row_pitch_en),
    }
    if not self.row_cache then
        self.row_cache = {}
    end
    -- Same hard-flush cap as the line cache: a few hundred small tables are
    -- not worth an eviction policy.
    local count = 0
    for _ in pairs(self.row_cache) do count = count + 1 end
    if count >= 256 then
        self.row_cache = {}
    end
    self.row_cache[key] = m
    return m
end

-- How many pages an oversized row needs. 1 when it fits.
--
-- Each column paginates independently against its own lines-per-page, and
-- sub-page k pairs Arabic lines [k*La+1 ..] with English lines [k*Le+1 ..].
-- The two cells drift apart within an oversized ayah -- unavoidable when one
-- language needs more lines than the other -- but both start together and
-- both end together, which is what a reader tracking a long ayah needs.
function Rows.subPageCount(self, ayah)
    local m = Rows.metrics(self, ayah)
    if m.height + Rows.ROW_GAP_PX <= self.text_height then
        return 1
    end
    local pages_ar = math.ceil(m.n_ar / self.lines_per_page_ar)
    local pages_en = math.ceil(m.n_en / self.lines_per_page_en)
    return math.max(1, pages_ar, pages_en)
end

-- ---------------------------------------------------------------------------
-- Pagination
-- ---------------------------------------------------------------------------

-- Builds the page starting at (ayah, sub). Returns (page, next_ayah, next_sub).
--
-- `sub` is the sub-page index within an oversized ayah, 0 for a normal row.
-- It reuses the `line` slot in the saved position, which is why a position is
-- an ayah reference plus an ordinal rather than a byte offset -- see §9.1.
function Rows.buildPage(self, ayah, sub)
    local items = {}
    local budget = self.text_height

    -- The basmala heading, above ayah 1 of every surah but 1 and 9. It spans
    -- both columns rather than being a row (§9.1), and it is drawn only at
    -- the true top of the surah, never when resuming mid-ayah.
    if ayah == 1 and (sub or 0) == 0 and self.surah ~= 1 and self.surah ~= 9
       and self.basmala_ar and self.basmala_ar ~= "" then
        local h = self.row_pitch_ar + self.row_pitch_en + Rows.BASMALA_GAP_PX
        if h < budget then
            items[#items + 1] = { kind = "basmala", height = h }
            budget = budget - h
        end
    end

    local a, s = ayah, sub or 0

    -- Case 1: resuming inside an oversized ayah. That sub-page owns the whole
    -- screen; nothing else is packed beside it.
    if s > 0 then
        local total = Rows.subPageCount(self, a)
        items[#items + 1] = { kind = "row", ayah = a, sub = s, of = total }
        if s + 1 < total then
            return { items = items }, a, s + 1
        end
        return { items = items }, a + 1, 0
    end

    while a <= self.ayah_count do
        local m = Rows.metrics(self, a)
        local need = m.height + Rows.ROW_GAP_PX

        if need <= budget then
            items[#items + 1] = { kind = "row", ayah = a, sub = 0, of = 1 }
            budget = budget - need
            a = a + 1
        elseif #items == 0 or (#items == 1 and items[1].kind == "basmala") then
            -- Case 2: this ayah cannot fit a page even alone. Split it rather
            -- than looping forever or dropping it. 2:282 is the case that
            -- forces this to exist and the one to test it against.
            local total = Rows.subPageCount(self, a)
            items[#items + 1] = { kind = "row", ayah = a, sub = 0, of = total }
            if total > 1 then
                return { items = items }, a, 1
            end
            -- `of == 1` while not fitting means the row is taller than the
            -- page but only one line in each column -- a font size so large a
            -- single line overflows. Show it clipped and move on; refusing to
            -- advance would hang the reader.
            return { items = items }, a + 1, 0
        else
            -- Case 3: does not fit, but the page has content. Never cut a row
            -- to squeeze it in -- it starts the next page whole (§9.1).
            break
        end
    end

    return { items = items }, a, 0
end

-- Walks back to the top of the page that ENDS just before (ayah, sub).
--
-- Backward paging is derived by re-running the forward packer, not by
-- inverting it arithmetically: forward packing depends on measured heights,
-- and an inverse that "looks right" drifts out of step with it as soon as a
-- row splits. Slower, and always consistent with what forward paging shows.
function Rows.topOfPreviousPage(self, ayah, sub)
    if (sub or 0) > 0 then
        return ayah, sub - 1
    end
    if ayah <= 1 then
        return 1, 0
    end

    -- Find the last ayah of the previous page by stepping back one row at a
    -- time and asking the forward packer where a page started there would
    -- end. The first candidate whose page ends exactly at `ayah` is the top.
    local target = ayah
    local candidate = target - 1
    local floor_a = math.max(1, target - 64)   -- bound the search
    local best_a, best_s = candidate, 0

    while candidate >= floor_a do
        local total = Rows.subPageCount(self, candidate)
        local start_s = total > 1 and (total - 1) or 0
        local _, next_a, next_s = Rows.buildPage(self, candidate, start_s)
        if next_a == target and (next_s or 0) == 0 then
            best_a, best_s = candidate, start_s
            -- Keep walking back: an earlier start that still ends at `target`
            -- packs more rows onto the page, and that is the real previous
            -- page. Only whole-row starts can extend it.
            if start_s ~= 0 then
                break
            end
            candidate = candidate - 1
        elseif next_a > target then
            -- Overshot: a page starting here would swallow `target`.
            break
        else
            break
        end
    end
    return best_a, best_s
end

-- ---------------------------------------------------------------------------
-- The page widget
-- ---------------------------------------------------------------------------

local RowPage = WidgetContainer:extend{
    width = 0,
    col_width = 0,
    items = nil,
    rules_enabled = true,
}

-- Paints each row's two cells at their own x, then the rule in the gutter
-- BELOW the row. Unlike the per-line rules this cannot clip a glyph: the band
-- it draws in is gutter space this file reserved.
function RowPage:paintTo(bb, x, y)
    local colour = ruleColour()
    local cy = y
    for _, item in ipairs(self.items or {}) do
        if item.kind == "basmala" then
            if item.ar then item.ar:paintTo(bb, x, cy) end
            if item.en then
                item.en:paintTo(bb, x, cy + (item.ar_h or 0))
            end
            cy = cy + item.height
        else
            local ar_x = x + self.col_width + Rows.COLUMN_GUTTER_PX
            if item.en then item.en:paintTo(bb, x, cy) end
            if item.ar then item.ar:paintTo(bb, ar_x, cy) end
            cy = cy + item.height
            if self.rules_enabled and colour then
                local ry = cy + math.floor(Rows.ROW_GAP_PX / 2) - Rows.RULE_THICKNESS_PX
                pcall(function()
                    bb:paintRect(x, ry, self.width, Rows.RULE_THICKNESS_PX, colour)
                end)
            end
            cy = cy + Rows.ROW_GAP_PX
        end
    end
end

-- Builds the widgets for a page description. Returns (widget, widgets_to_free)
-- or (nil, nil, err).
function Rows.layout(self, page)
    local made = {}

    local function box(text, face, width, line_height, rtl, height, top_line)
        local ok, w = pcall(function()
            return TextBoxWidget:new{
                text = text,
                face = face,
                width = width,
                height = height,
                line_height = line_height,
                top_line_num = top_line,
                alignment = rtl and "right" or "left",
                auto_para_direction = false,
                para_direction_rtl = rtl and true or false,
            }
        end)
        if not ok or not w then
            return nil
        end
        made[#made + 1] = w
        return w
    end

    for _, item in ipairs(page.items) do
        if item.kind == "basmala" then
            item.ar = box(self.basmala_ar, Rows.arabicFace(self), self.text_width,
                          self.arabic_line_height, true, nil, nil)
            item.ar_h = self.row_pitch_ar
            if self.basmala_en and self.basmala_en ~= "" then
                item.en = box(self.basmala_en, Rows.englishFace(self), self.text_width,
                              self.english_line_height, false, nil, nil)
            end
        else
            local ar, ar_err = Rows.arabicText(self, item.ayah)
            if not ar then
                return nil, made, ar_err
            end
            local en = Rows.englishText(self, item.ayah)
            local m = Rows.metrics(self, item.ayah)

            local first_ar = item.sub * self.lines_per_page_ar
            local first_en = item.sub * self.lines_per_page_en
            local take_ar = m.n_ar - first_ar
            local take_en = m.n_en - first_en
            local h_ar, h_en, top_ar, top_en

            if item.of > 1 then
                take_ar = math.max(0, math.min(take_ar, self.lines_per_page_ar))
                take_en = math.max(0, math.min(take_en, self.lines_per_page_en))
                h_ar = take_ar > 0 and take_ar * self.row_pitch_ar or nil
                h_en = take_en > 0 and take_en * self.row_pitch_en or nil
                top_ar = first_ar + 1
                top_en = first_en + 1
                item.height = math.max(h_ar or 0, h_en or 0)
            else
                h_ar, h_en, top_ar, top_en = nil, nil, nil, nil
                item.height = m.height
            end

            if take_ar > 0 then
                item.ar = box(ar, Rows.arabicFace(self), self.col_width,
                              self.arabic_line_height, true, h_ar, top_ar)
            end
            if en and take_en > 0 then
                item.en = box(en, Rows.englishFace(self), self.col_width,
                              self.english_line_height, false, h_en, top_en)
            end
        end
    end

    local widget = RowPage:new{
        width = self.text_width,
        col_width = self.col_width,
        items = page.items,
        rules_enabled = self.rules_enabled,
    }
    return widget, made, nil
end

Rows.RowPage = RowPage

return Rows
