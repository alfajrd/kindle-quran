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
  V41 DISPROVED ON DEVICE, 12 August 2026. `top_line_num` is IGNORED: two
      boxes over the same text, asked to start at lines 1 and 4, both reported
      virtual_line_num 1. Every sub-page of an oversized ayah rendered from
      line one, so a long ayah repeated its opening lines page after page.
      Oversized rows now scroll instead -- see Rows.sliceBox.

      Note what made this survive so long. The claim said it was "already
      relied on by the Arabic-only pager (V25)", which sounded like
      corroboration and was an assumption: V25 had never been exercised
      either, because the only surah read on device was Al-Fatiha and none of
      its ayat is long enough to need slicing. **Arabic-only mode has the same
      defect and it is not yet fixed** -- quranreader.lua's STEP P3 still
      passes top_line_num.
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

-- The Arabic leading used HERE, which is not the one Arabic-only mode uses.
--
-- arabic_line_height is 1.5 because the per-line rules need a gap wide enough
-- to sit in without clipping harakat. This layout has no per-line rules -- the
-- rule is in the gutter below a whole row -- so that leading buys nothing and
-- costs everything: measured on device, 34 px scales to a ~71 px face and 1.5
-- leading gives a 178 px line pitch, eight lines to a 1588 px column.
function Rows.arabicLeading(self)
    return self.rows_line_height or 0.3
end

function Rows.arabicFace(self)
    return Font:getFace(self.ARABIC_FONT, self.arabic_font_size)
end

-- Builds a text box showing one sub-page's worth of an oversized cell.
--
-- `top_line_num` DOES NOT WORK. Probed on device (Rows.diagnostics): two boxes
-- over the same text, asked to start at lines 1 and 4, both reported
-- virtual_line_num 1. Every sub-page rendered from the first line and was
-- clipped to the row height, so a long ayah showed its opening lines over and
-- over. It was believed to work because the Arabic-only pager "relied on" it
-- -- an assumption, never exercised, since the only surah read on device was
-- Al-Fatiha and none of its ayat need slicing.
--
-- `scrollDown()` is the method actually built for this: it advances by one
-- visible page and re-renders. Called `sub` times, it lands on sub-page `sub`.
--
-- Verified rather than trusted: after scrolling, virtual_line_num must have
-- moved. If it has not, the box is returned anyway -- showing the first lines
-- is wrong, but showing nothing is worse -- and the failure is recorded so
-- diagnostics can report it instead of the reader silently lying.
function Rows.sliceBox(self, opts)
    local ok, box = pcall(function()
        return TextBoxWidget:new{
            text = opts.text,
            face = opts.face,
            width = opts.width,
            height = opts.height,
            line_height = opts.line_height,
            alignment = opts.rtl and "right" or "left",
            auto_para_direction = false,
            para_direction_rtl = opts.rtl and true or false,
        }
    end)
    if not ok or not box then
        return nil
    end

    local sub = opts.sub or 0
    if sub > 0 then
        local before, after
        pcall(function() before = box.virtual_line_num end)
        pcall(function()
            for _ = 1, sub do
                box:scrollDown()
            end
        end)
        pcall(function() after = box.virtual_line_num end)
        if before and after and after > before then
            self.slice_mechanism = "scrollDown"
        else
            self.slice_mechanism = "FAILED (" .. tostring(before) .. " -> " ..
                tostring(after) .. ")"
        end
    end
    return box
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
                                   Rows.arabicLeading(self), true)
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
                          Rows.arabicLeading(self), true)
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

-- How an oversized row is split. -> { total, per_ar, per_en }.
--
-- The page count is set by whichever column needs more pages at full page
-- capacity. Each column's lines are then spread EVENLY across that shared
-- count, rather than each column taking its own maximum every page.
--
-- Taking the maximum was the first implementation and it is wrong on device.
-- Arabic wraps far more than English in a 562 px column, so on 2:282 the
-- Arabic needed four pages and the English three -- and the English, having
-- filled itself at full capacity, ran out. Page four rendered with a blank
-- left column: Arabic alone, translation gone, on the one ayah most in need
-- of it.
--
-- Dividing by `total` makes both columns finish on the last page. It cannot
-- overflow: total >= ceil(n / lines_per_page) for each column by construction,
-- so ceil(n / total) <= lines_per_page.
function Rows.splitPlan(self, ayah)
    local m = Rows.metrics(self, ayah)
    if m.height + Rows.ROW_GAP_PX <= self.text_height then
        return { total = 1, per_ar = m.n_ar, per_en = m.n_en }
    end
    local pages_ar = math.ceil(m.n_ar / self.lines_per_page_ar)
    local pages_en = math.ceil(m.n_en / self.lines_per_page_en)
    local total = math.max(1, pages_ar, pages_en)
    return {
        total = total,
        per_ar = math.max(1, math.ceil(m.n_ar / total)),
        per_en = math.max(1, math.ceil(m.n_en / total)),
    }
end

-- How many pages an oversized row needs. 1 when it fits.
function Rows.subPageCount(self, ayah)
    return Rows.splitPlan(self, ayah).total
end

-- ---------------------------------------------------------------------------
-- Diagnostics
-- ---------------------------------------------------------------------------

-- Reports the real numbers behind a split, plus a direct probe of whether
-- TextBoxWidget honours `top_line_num`.
--
-- This exists because a device report -- "the Arabic repeated three times
-- while the English ran out" -- had two possible causes and guessing between
-- them would have cost another trip. Identical Arabic on every sub-page is
-- what you get if `top_line_num` is ignored: each one renders from line 1 and
-- is clipped to the row height. The probe below settles it rather than
-- inferring it.
--
-- `virtual_line_num` is TextBoxWidget's own record of which line it starts
-- from; upstream sets it from `top_line_num` at init. If it comes back as 1
-- when 4 was asked for, the key is not honoured and every mid-ayah slice in
-- this project is rendering the wrong lines.
function Rows.diagnostics(self, ayah)
    local out = {}
    local function add(s) out[#out + 1] = s end

    add("geometry")
    add("  text " .. tostring(self.text_width) .. " x " .. tostring(self.text_height))
    add("  col " .. tostring(self.col_width) ..
        "  pitch ar " .. tostring(self.row_pitch_ar) ..
        "  en " .. tostring(self.row_pitch_en))
    add("  per page  ar " .. tostring(self.lines_per_page_ar) ..
        "  en " .. tostring(self.lines_per_page_en))

    local ok_m, m = pcall(function() return Rows.metrics(self, ayah) end)
    local ok_p, plan = pcall(function() return Rows.splitPlan(self, ayah) end)
    add("")
    add("ayah " .. tostring(self.surah) .. ":" .. tostring(ayah))
    if ok_m and m then
        add("  lines  ar " .. tostring(m.n_ar) .. "  en " .. tostring(m.n_en))
        add("  row height " .. tostring(m.height))
    else
        add("  metrics FAILED: " .. tostring(m))
    end
    if ok_p and plan then
        add("  split  " .. tostring(plan.total) .. " page(s)" ..
            "  ar " .. tostring(plan.per_ar) .. "/page" ..
            "  en " .. tostring(plan.per_en) .. "/page")
    else
        add("  splitPlan FAILED: " .. tostring(plan))
    end
    add("  now on part " .. tostring((self.top_line or 0) + 1))
    add("  leading " .. tostring(Rows.arabicLeading(self)) ..
        " (arabic-only uses " .. tostring(self.arabic_line_height) .. ")")
    add("  slicing: " .. tostring(self.slice_mechanism or "not used on part 1"))

    -- The probe. Two boxes over the same text, asking to start at different
    -- lines. If they agree, the key is being ignored.
    add("")
    add("top_line_num probe")
    local text = Rows.arabicText(self, ayah)
    if not text then
        add("  could not read the ayah")
        return table.concat(out, "\n")
    end
    local function probe(n)
        local ok, box = pcall(function()
            return TextBoxWidget:new{
                text = text,
                face = Rows.arabicFace(self),
                width = self.col_width,
                height = 3 * (self.row_pitch_ar or 40),
                line_height = Rows.arabicLeading(self),
                top_line_num = n,
                alignment = "right",
                auto_para_direction = false,
                para_direction_rtl = true,
            }
        end)
        if not ok or not box then
            return nil, "construction failed: " .. tostring(box)
        end
        local vln
        pcall(function() vln = box.virtual_line_num end)
        pcall(function() box:free() end)
        return vln, nil
    end
    local a, err_a = probe(1)
    local b, err_b = probe(4)
    add("  asked 1 -> virtual_line_num " .. tostring(a) .. (err_a and (" (" .. err_a .. ")") or ""))
    add("  asked 4 -> virtual_line_num " .. tostring(b) .. (err_b and (" (" .. err_b .. ")") or ""))
    if a == nil or b == nil then
        add("  VERDICT: virtual_line_num not exposed -- inconclusive")
    elseif a == b then
        add("  VERDICT: IGNORED. Every sub-page renders from the same line.")
    else
        add("  VERDICT: honoured (" .. tostring(a) .. " vs " .. tostring(b) .. ")")
    end

    return table.concat(out, "\n")
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

    -- `sub` is the sub-page to show, NOT a top_line_num: that key is ignored
    -- by this KOReader build (proved by the probe in Rows.diagnostics), and
    -- passing it produced an ayah that repeated its opening lines on every
    -- page. Rows.sliceBox scrolls instead, and verifies that it moved.
    local function box(text, face, width, line_height, rtl, height, sub)
        local w = Rows.sliceBox(self, {
            text = text,
            face = face,
            width = width,
            height = height,
            line_height = line_height,
            rtl = rtl,
            sub = sub,
        })
        if not w then
            return nil
        end
        made[#made + 1] = w
        return w
    end

    for _, item in ipairs(page.items) do
        if item.kind == "basmala" then
            item.ar = box(self.basmala_ar, Rows.arabicFace(self), self.text_width,
                          Rows.arabicLeading(self), true, nil, nil)
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

            -- Both columns advance by their SHARE of the split, not by their
            -- own page capacity, so neither runs out before the other and no
            -- trailing page renders a blank column. See Rows.splitPlan.
            local plan = Rows.splitPlan(self, item.ayah)
            local first_ar = item.sub * plan.per_ar
            local first_en = item.sub * plan.per_en
            local take_ar = m.n_ar - first_ar
            local take_en = m.n_en - first_en
            local h_ar, h_en, top_ar, top_en

            if item.of > 1 then
                take_ar = math.max(0, math.min(take_ar, plan.per_ar))
                take_en = math.max(0, math.min(take_en, plan.per_en))
                h_ar = take_ar > 0 and take_ar * self.row_pitch_ar or nil
                h_en = take_en > 0 and take_en * self.row_pitch_en or nil
                -- The sub-page index, scrolled to. Not a line ordinal: see
                -- the note on `box` above and Rows.sliceBox.
                top_ar = item.sub
                top_en = item.sub
                item.height = math.max(h_ar or 0, h_en or 0)
            else
                h_ar, h_en, top_ar, top_en = nil, nil, nil, nil
                item.height = m.height
            end

            if take_ar > 0 then
                item.ar = box(ar, Rows.arabicFace(self), self.col_width,
                              Rows.arabicLeading(self), true, h_ar, top_ar)
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
