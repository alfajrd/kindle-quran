--[[--
Qur'an, Milestone 4: the navigator -- surah list, juz list, reference jump.

This is the milestone that makes the plugin worth using over an EPUB. Until
now "navigation" was four hard-coded menu entries, which is how a checklist
step came to name a surah the reader could not reach.

Three ways in, all landing in the same place:

  * by surah  -- 1..114, with transliteration, meaning, ayah count, and where
                 it was revealed
  * by juz    -- 1..30, showing the ayah each begins at
  * by reference -- type "2:255" and land there

Everything here reads data already in the pack. No new sources, no licensing
questions.

MUST-VERIFY (device)
--------------------
  V50 `Menu:new{}` accepts `title`, `item_table`, `width`, `height` and calls
      `onMenuSelect(item)` on tap. KOReader's default `onMenuSelect` has
      differed across versions in whether it invokes `item.callback`, so this
      file supplies its OWN `onMenuSelect` and does not rely on the default.
      Each item still carries `callback`, so if a version routes through the
      default instead, both paths reach the same function.
  V51 `InputDialog:new{}` accepts `title`, `input`, `input_hint`, `buttons`,
      and exposes `getInputText()`. A failure to build it is reported and the
      other two navigation routes keep working.
  V52 `dialog:onShowKeyboard()` exists and raises the on-screen keyboard. If
      it does not, the field is still editable by other means, so this is
      called through pcall and its absence is not an error.

Nothing here throws: every widget call is pcall-guarded and every failure
becomes an InfoMessage naming what could not be built. A navigator that
crashes takes the reader with it.

@module koplugin.Quran.navigator
--]]--

local UIManager = require("ui/uimanager")
local InfoMessage = require("ui/widget/infomessage")
local Screen = require("device").screen

local Nav = {}

-- ---------------------------------------------------------------------------
-- Reference parsing
-- ---------------------------------------------------------------------------

-- Parses a reference string. -> (surah, ayah, nil) | (nil, nil, err_string).
--
-- Pure: no widgets, no database, no globals. That is deliberate -- it is the
-- only part of M4 with real logic, and keeping it free of dependencies means
-- it can be reasoned about (and later tested) on its own.
--
-- Accepted, all with any surrounding or internal whitespace:
--
--     "2:255"   "2 255"   "2.255"   "2-255"     -> surah 2, ayah 255
--     "2"                                       -> surah 2, ayah 1
--
-- Rejected: anything else, including empty input, negative or zero numbers,
-- three-part references, and trailing junk ("2:255x"). Range checking against
-- the pack is the CALLER's job -- this function knows the grammar, not the
-- Qur'an, and cannot tell that 2:300 does not exist.
function Nav.parseReference(text)
    if type(text) ~= "string" then
        return nil, nil, "no reference given"
    end
    -- Trim the ends only. Stripping ALL whitespace looks equivalent and is
    -- not: it turns "2 255" into "2255", which then parses as surah 2255 and
    -- fails as out of range rather than as the reference it obviously is.
    -- Internal whitespace is a SEPARATOR here, so it has to survive to be
    -- matched against.
    local s = text:gsub("^%s+", ""):gsub("%s+$", "")
    if s == "" then
        return nil, nil, "no reference given"
    end

    -- Every pattern is anchored so trailing junk cannot be silently ignored:
    -- "2:255x" must be an error, not a jump to 2:255.
    local surah, ayah = s:match("^(%d+)%s*[:%.%-]%s*(%d+)$")
    if not surah then
        -- Whitespace alone as the separator: "2 255".
        surah, ayah = s:match("^(%d+)%s+(%d+)$")
    end
    if surah then
        surah, ayah = tonumber(surah), tonumber(ayah)
        if surah < 1 or surah > 114 then
            return nil, nil, "surah must be between 1 and 114 (got " .. surah .. ")"
        end
        if ayah < 1 then
            return nil, nil, "ayah must be 1 or more"
        end
        return surah, ayah, nil
    end

    local only = s:match("^(%d+)$")
    if only then
        only = tonumber(only)
        if only < 1 or only > 114 then
            return nil, nil, "surah must be between 1 and 114 (got " .. only .. ")"
        end
        return only, 1, nil
    end

    return nil, nil, "could not read \"" .. text .. "\" as a reference. Try 2:255"
end

-- ---------------------------------------------------------------------------
-- Presentation helpers
-- ---------------------------------------------------------------------------

local function titleCase(word)
    if type(word) ~= "string" or word == "" then
        return word
    end
    return word:sub(1, 1):upper() .. word:sub(2)
end

-- "2. Al-Baqara - The Cow (286 ayat, Medinan)"
function Nav.surahLabel(s)
    local parts = tostring(s.id) .. ". " .. tostring(s.name_tr)
    if s.name_en and s.name_en ~= "" then
        parts = parts .. " - " .. s.name_en
    end
    local count = tostring(s.ayah_count) .. (s.ayah_count == 1 and " ayah" or " ayat")
    return parts .. "  (" .. count .. ", " .. titleCase(tostring(s.revelation)) .. ")"
end

function Nav.juzLabel(j)
    return "Juz " .. tostring(j.juz) .. "  -- begins at " ..
        tostring(j.surah) .. ":" .. tostring(j.ayah)
end

local function showError(message)
    UIManager:show(InfoMessage:new{
        text = "Qur'an: " .. tostring(message),
        show_icon = false,
        dismissable = true,
    })
end

Nav.showError = showError

-- ---------------------------------------------------------------------------
-- Menus
-- ---------------------------------------------------------------------------

-- Builds and shows a full-screen menu. `items` is an array of
-- { text = ..., on_select = function() end }.
--
-- Supplies its own onMenuSelect rather than trusting the default (V50), and
-- closes the menu BEFORE running the selection so the reader is not opened
-- underneath a menu that is still on screen.
local function showMenu(title, items)
    local ok_menu, Menu = pcall(require, "ui/widget/menu")
    if not ok_menu or not Menu then
        showError("the menu widget is unavailable (ui/widget/menu failed to load)")
        return
    end

    local menu
    local item_table = {}
    for _, item in ipairs(items) do
        local run = item.on_select
        item_table[#item_table + 1] = {
            text = item.text,
            callback = function()
                pcall(function() UIManager:close(menu) end)
                if run then run() end
            end,
        }
    end

    local ok_new, built = pcall(function()
        return Menu:new{
            title = title,
            item_table = item_table,
            is_popout = false,
            is_borderless = true,
            width = Screen:getWidth(),
            height = Screen:getHeight(),
            onMenuSelect = function(_, item)
                if item and item.callback then
                    item.callback()
                end
                return true
            end,
            close_callback = function()
                menu = nil
            end,
        }
    end)
    if not ok_new or not built then
        showError("could not build the list (" .. tostring(built) .. ")")
        return
    end
    menu = built

    if not pcall(function() UIManager:show(menu) end) then
        showError("could not show the list")
    end
end

Nav.showMenu = showMenu

-- Reads everything the navigator needs in one go. -> (data, nil) | (nil, err).
--
-- The three show* functions below take DATA, not a connection. That is not
-- tidiness: a menu waits indefinitely for a tap and may be dismissed without
-- choosing anything, so a connection held across it is a connection nobody
-- closes. Reading up front lets the caller close immediately and lets the
-- reference dialog validate without touching the database at all.
--
-- `ayah_counts` is derived from the surah list rather than queried per lookup,
-- so a reference typed into the dialog is checked against the same numbers the
-- surah list displays.
function Nav.loadData(DB, conn)
    local surahs, err = DB.listSurahs(conn)
    if not surahs then
        return nil, "could not read the surah list.\n\n" .. tostring(err)
    end
    local juz, juz_err = DB.listJuz(conn)
    if not juz then
        return nil, "could not read the juz list.\n\n" .. tostring(juz_err)
    end
    local counts = {}
    for _, s in ipairs(surahs) do
        counts[s.id] = s.ayah_count
    end
    return { surahs = surahs, juz = juz, ayah_counts = counts }, nil
end

-- opts = { data = <from Nav.loadData>, on_pick = function(surah) end }
function Nav.showSurahList(opts)
    local surahs = opts.data and opts.data.surahs
    if not surahs then
        showError("the surah list is unavailable")
        return
    end
    local items = {}
    for _, s in ipairs(surahs) do
        items[#items + 1] = {
            text = Nav.surahLabel(s),
            on_select = function() opts.on_pick(s.id) end,
        }
    end
    showMenu("Surahs", items)
end

-- opts = { data, on_pick = function(surah, ayah) end }
function Nav.showJuzList(opts)
    local juz = opts.data and opts.data.juz
    if not juz then
        showError("the juz list is unavailable")
        return
    end
    local items = {}
    for _, j in ipairs(juz) do
        items[#items + 1] = {
            text = Nav.juzLabel(j),
            on_select = function() opts.on_pick(j.surah, j.ayah) end,
        }
    end
    showMenu("Juz", items)
end

-- opts = { bookmarks = <array>, surahs = <array|nil>, on_pick, on_delete }
--
-- Shows the surah's transliterated name beside the reference when the surah
-- list is available, because "Al-Baqara 2:255" is a bookmark and "2:255" is a
-- coordinate. Falls back to the bare reference rather than refusing to list.
function Nav.showBookmarkList(opts)
    local list = opts.bookmarks or {}
    if #list == 0 then
        showError("no bookmarks yet.\n\nAdd one from the reader: tap the top " ..
                  "centre of the screen, then \"Bookmark\".")
        return
    end

    local names = {}
    for _, s in ipairs((opts.data and opts.data.surahs) or {}) do
        names[s.id] = s.name_tr
    end

    local items = {}
    for _, b in ipairs(list) do
        local label = tostring(b.surah) .. ":" .. tostring(b.ayah)
        if names[b.surah] then
            label = names[b.surah] .. "  " .. label
        end
        if b.note and b.note ~= "" then
            label = label .. "  -  " .. b.note
        end
        items[#items + 1] = {
            text = label,
            on_select = function() opts.on_pick(b.surah, b.ayah) end,
        }
    end
    showMenu("Bookmarks", items)
end

-- opts = { data, initial = "2:255", on_pick = function(surah, ayah) end }
--
-- Validates against the PACK's real ayah counts, not just the grammar: 2:300
-- parses fine and does not exist, and the error says so with the surah's
-- actual length rather than a generic refusal.
function Nav.showReferenceInput(opts)
    local ok_dlg, InputDialog = pcall(require, "ui/widget/inputdialog")
    if not ok_dlg or not InputDialog then
        showError("the input dialog is unavailable (ui/widget/inputdialog failed to load)")
        return
    end

    local dialog

    local function submit()
        local text
        pcall(function() text = dialog:getInputText() end)
        local surah, ayah, err = Nav.parseReference(text)
        if not surah then
            showError(err)
            return
        end
        local count = opts.data and opts.data.ayah_counts and opts.data.ayah_counts[surah]
        if not count then
            showError("surah " .. surah .. " is not in this pack.")
            return
        end
        if ayah > count then
            showError("surah " .. surah .. " has " .. count ..
                (count == 1 and " ayah" or " ayat") .. "; there is no ayah " .. ayah .. ".")
            return
        end
        pcall(function() UIManager:close(dialog) end)
        opts.on_pick(surah, ayah)
    end

    local ok_new, built = pcall(function()
        return InputDialog:new{
            title = "Go to reference",
            input = opts.initial or "",
            input_hint = "surah:ayah  (e.g. 2:255)",
            buttons = {
                {
                    { text = "Cancel", callback = function()
                        pcall(function() UIManager:close(dialog) end)
                    end },
                    { text = "Go", is_enter_default = true, callback = submit },
                },
            },
        }
    end)
    if not ok_new or not built then
        showError("could not build the reference dialog (" .. tostring(built) .. ")")
        return
    end
    dialog = built

    if not pcall(function() UIManager:show(dialog) end) then
        showError("could not show the reference dialog")
        return
    end
    -- V52: absence of the keyboard call is not an error.
    pcall(function() dialog:onShowKeyboard() end)
end

return Nav
