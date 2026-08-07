--[[--
Qur'an, Milestone 1: reads the Uthmani text from a validated SQLite pack
(`data/quran.db`) instead of a hard-coded Lua literal, and proves on-device
that the displayed text genuinely came from the pack -- not from a
transcribed constant.

See kindle-quran/README.md for the manual on-device pass/fail checklist,
and d:\Nekoweb\dev\quran-spec-v1.md for the wider project this milestone
gates.

@module koplugin.Quran
--]]--

local Dispatcher = require("dispatcher")  -- luacheck:ignore
local Font = require("ui/font")
local InfoMessage = require("ui/widget/infomessage")
local UIManager = require("ui/uimanager")
local WidgetContainer = require("ui/widget/container/widgetcontainer")
local Screen = require("device").screen
local _ = require("gettext")
-- `require("db")` relies on KOReader's pluginloader adding this plugin's
-- own directory to package.path (the same convention other koplugins use
-- for same-directory submodules). Not independently re-verified here --
-- see the V11-V14 note above db.lua's DB.open for what could and could not
-- be checked on this machine.
-- pcall, not a bare require. A plugin that throws while loading is skipped by
-- KOReader without a word, which would produce the one symptom the README
-- calls hardest to debug ("the menu item isn't there") and would stop the
-- error InfoMessage below from ever being reached. Failing soft keeps the
-- plugin loadable so it can report why it is broken.
local ok_db, DB = pcall(require, "db")
if not ok_db then
    DB = nil
end

-- Reference of the verse shown. Latin, deliberately: orients the tester,
-- who reads it before the Arabic renders.
local AYAH_REF = "2:255"

-- Font override. nil = KOReader's default content font ("cfont") plus its
-- built-in Arabic fallback (NotoSansArabicUI-Regular.ttf). See D2: M0 must
-- not bundle a font. Set this to a font name already present on the device
-- (e.g. after manually dropping Amiri-Regular.ttf into KOReader's user font
-- directory) to test failure mode B without touching any other code.
-- Scheherazade New (SIL, OFL 1.1) — a Naskh face, shipped in fonts/.
-- KOReader resolves this by FILENAME out of its font directories, so this
-- must match the file copied to /mnt/us/koreader/fonts/ exactly. Set back
-- to nil to fall through to KOReader's default sans (Noto Sans Arabic).
local ARABIC_FONT = "ScheherazadeNew-Regular.ttf"

-- Starting point size (see d:\Nekoweb\dev\quran-spec-v1.md §9). Verified
-- against frontend/ui/font.lua: this is an "orig_size" scaled internally by
-- Screen:scaleBySize(), not a raw pixel count (MUST-VERIFY V5).
-- 34px, chosen by eye on a Paperwhite 11 against Scheherazade New after
-- comparing 26/30/34/38/44. At this size the harakat clear the line above,
-- which settles the line-height question the M0 checklist raised as
-- Fail Mode C. The comparison submenu that produced this number has been
-- removed; it was scaffolding.
local ARABIC_FONT_SIZE = 34

-- BEGIN VERBATIM TANZIL UTHMANI 2:255 -- DO NOT EDIT, DO NOT NORMALISE, DO NOT REFLOW
local PIN_2_255 = [==[ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ ۚ لَا تَأْخُذُهُۥ سِنَةٌۭ وَلَا نَوْمٌۭ ۚ لَّهُۥ مَا فِى ٱلسَّمَٰوَٰتِ وَمَا فِى ٱلْأَرْضِ ۗ مَن ذَا ٱلَّذِى يَشْفَعُ عِندَهُۥٓ إِلَّا بِإِذْنِهِۦ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَىْءٍۢ مِّنْ عِلْمِهِۦٓ إِلَّا بِمَا شَآءَ ۚ وَسِعَ كُرْسِيُّهُ ٱلسَّمَٰوَٰتِ وَٱلْأَرْضَ ۖ وَلَا يَـُٔودُهُۥ حِفْظُهُمَا ۚ وَهُوَ ٱلْعَلِىُّ ٱلْعَظِيمُ]==]
-- END VERBATIM
-- D5: PIN_2_255 is now a tripwire only. At runtime the plugin reads 2:255
-- from data/quran.db and displays THAT; PIN_2_255 is only ever compared
-- against it (see showTestAyah below). It must never be displayed itself,
-- and the pack must never be silently substituted with the pin on failure
-- -- a silent fallback would make the device test prove the opposite of
-- what it appears to prove.

local Quran = WidgetContainer:extend{
    name = "quran",
    is_doc_only = false,     -- MUST be false: KOReader boots into the File Manager on the
                              -- Kindle, and the tester needs the menu item there, with no
                              -- book open (see spec edge case 2).
}

function Quran:onDispatcherRegisterActions()
    Dispatcher:registerAction("quran_show_test_ayah", {
        category = "none",
        event = "QuranShowTestAyah",
        title = _("Qur'an — test ayah (2:255)"),
        general = true,
    })
    Dispatcher:registerAction("quran_show_pack_self_test", {
        category = "none",
        event = "QuranShowPackSelfTest",
        title = _("Qur'an — pack self-test"),
        general = true,
    })
end

function Quran:init()
    self:onDispatcherRegisterActions()
    self.ui.menu:registerToMainMenu(self)
end

function Quran:addToMainMenu(menu_items)
    menu_items.quran_test_ayah = {
        text = _("Qur'an — test ayah (2:255)"),
        sorting_hint = "more_tools",
        callback = function() self:showTestAyah() end,
    }
    menu_items.quran_pack_self_test = {
        text = _("Qur'an — pack self-test"),
        sorting_hint = "more_tools",
        callback = function() self:showPackSelfTest() end,
    }
end

-- MUST-VERIFY V3 note: the primary implementation described in the spec
-- (ui/widget/textviewer.TextViewer) does not, on inspection of the actual
-- KOReader source (frontend/ui/widget/textviewer.lua), accept a `text_face`
-- constructor key at all -- its internal font face is hardcoded to
-- "x_smallinfofont"/"smallinfont", and `text_font_size` is unconditionally
-- overwritten from the `text_type` presets on first init. There is no way
-- to plug ARABIC_FONT/ARABIC_FONT_SIZE into TextViewer through its public
-- keys. That is exactly the "widget unsuitable" case the spec anticipates,
-- so this uses the documented fallback, ui/widget/infomessage.InfoMessage,
-- instead. InfoMessage does accept `face` directly (frontend/ui/widget/
-- infomessage.lua), is dismissed by tapping anywhere (satisfies the
-- touch-only Close requirement), and -- when `height` is set -- uses
-- ScrollTextWidget internally, so overflow text scrolls.
--
-- MUST-VERIFY V4 note: frontend/ui/widget/textboxwidget.lua defaults
-- `use_xtext` to true (HarfBuzz+FriBiDi shaping, no flag needed -- V4
-- confirmed) but defaults `auto_para_direction` to *false*. Left at the
-- default, the Arabic paragraph would take the UI language's direction
-- (LTR for an English UI) instead of being detected as RTL. This is set
-- to true explicitly below; textboxwidget.lua auto-flips `alignment` from
-- "left" to "right" for a paragraph it detects as RTL (see the
-- `line.para_is_rtl` handling), so `alignment = "left"` is kept and lets
-- that auto-flip do the work.
--
-- MUST-VERIFY V14 note: could not read frontend/pluginloader.lua on this
-- machine (no KOReader checkout, no network -- see db.lua's header
-- comment for the same limitation applied to V11-V13). `packPath` below
-- tries `self.path` first, per the spec's stated claim that the plugin
-- loader sets it, and falls back to parsing `debug.getinfo(1, "S").source`
-- if `self.path` is absent. Whichever path is taken, the resolved
-- directory (or the failure) is what gets shown to the tester on a pack
-- error, per edge case 19 -- on a Kindle, that string is the only
-- debugging channel available.

-- Resolves the plugin's own directory. self.path is set by the plugin loader
-- (MUST-VERIFY V14); fall back to deriving it from debug.getinfo(1, "S").source.
-- Returns (dir, nil) or (nil, err).
function Quran:packPath()
    local dir = self.path
    if not dir or dir == "" then
        local info = debug.getinfo(1, "S")
        local source = info and info.source or ""
        if source:sub(1, 1) == "@" then
            dir = source:sub(2):match("^(.*)[/\\][^/\\]+$")
        end
    end
    if not dir or dir == "" then
        return nil, "could not resolve the plugin's own directory " ..
            "(self.path was unset, and debug.getinfo(1, \"S\").source fallback failed)"
    end
    return dir, nil
end

-- Opens the pack, reads (surah, ayah), closes. Returns (text, nil) or (nil, err).
function Quran:readAyah(surah, ayah)
    local dir, path_err = self:packPath()
    if not dir then
        return nil, path_err
    end
    if not DB then
        return nil, "db.lua failed to load (see crash.log)"
    end
    local db_path = dir .. "/data/quran.db"
    local conn, open_err = DB.open(db_path)
    if not conn then
        return nil, open_err
    end
    local text, get_err = DB.getAyah(conn, surah, ayah)
    DB.close(conn)
    if not text then
        return nil, get_err
    end
    return text, nil
end

-- Existing entry point, rewritten: reads 2:255 from the pack, compares it
-- against PIN_2_255, and only ever displays the text that came from the
-- database. Never falls back to the pin (D5, edge case 22).
function Quran:showTestAyah(size)
    local dir, path_err = self:packPath()
    local attempted_path
    if dir then
        attempted_path = dir .. "/data/quran.db"
    else
        attempted_path = "<unresolved: " .. tostring(path_err) .. ">"
    end

    local text, err = self:readAyah(2, 255)
    if not text then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: pack error\n\n" .. tostring(err) .. "\n\nPath: " .. attempted_path,
            show_icon = false,
            dismissable = true,
        })
        return
    end

    if text ~= PIN_2_255 then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: PACK MISMATCH — the text in quran.db does not match the " ..
                "pinned 2:255. Do not trust this pack." ..
                "\n\npack text length: " .. #text .. " bytes" ..
                "\npinned text length: " .. #PIN_2_255 .. " bytes",
            show_icon = false,
            dismissable = true,
        })
        return
    end

    UIManager:show(InfoMessage:new{
        text = "Qur'an " .. AYAH_REF .. "\n\n" .. text,
        face = Font:getFace(ARABIC_FONT or "cfont", size or ARABIC_FONT_SIZE),
        show_icon = false,
        width = Screen:getWidth() - Screen:scaleBySize(30),
        height = Screen:getHeight() - Screen:scaleBySize(30),
        alignment = "left",
        auto_para_direction = true,
        dismissable = true,
    })
end

function Quran:onQuranShowTestAyah()
    self:showTestAyah()
end

-- New menu entry: reports pack facts read from the db. Latin-only, so it
-- is readable at arm's length regardless of Arabic font coverage -- this
-- is the device-side acceptance evidence for Milestone 1.
function Quran:showPackSelfTest()
    local dir, path_err = self:packPath()
    if not dir then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: pack self-test error\n\n" .. tostring(path_err),
            show_icon = false,
            dismissable = true,
        })
        return
    end

    if not DB then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: db.lua failed to load.

See /mnt/us/koreader/crash.log",
            show_icon = false,
            dismissable = true,
        })
        return
    end

    local db_path = dir .. "/data/quran.db"
    local conn, open_err = DB.open(db_path)
    if not conn then
        UIManager:show(InfoMessage:new{
            text = "Qur'an: pack self-test error\n\n" .. tostring(open_err) .. "\n\nPath: " .. db_path,
            show_icon = false,
            dismissable = true,
        })
        return
    end

    local pack_id = DB.getMeta(conn, "pack_id") or "<missing>"
    local build_date = DB.getMeta(conn, "build_date") or "<missing>"
    local checksum = DB.getMeta(conn, "checksum") or "<missing>"
    local surah_count, ayah_count = DB.counts(conn)

    local pin_text, pin_err = DB.getAyah(conn, 2, 255)
    local pin_status
    if not pin_text then
        pin_status = "ERROR (" .. tostring(pin_err) .. ")"
    elseif pin_text == PIN_2_255 then
        pin_status = "MATCH"
    else
        pin_status = "MISMATCH"
    end

    DB.close(conn)

    local lines = {
        "Qur'an — pack self-test",
        "",
        "pack_id: " .. pack_id,
        "build_date: " .. build_date,
        "surah_count: " .. tostring(surah_count),
        "ayah_count: " .. tostring(ayah_count),
        "checksum: " .. checksum,
        "2:255 pin: " .. pin_status,
    }
    UIManager:show(InfoMessage:new{
        text = table.concat(lines, "\n"),
        show_icon = false,
        dismissable = true,
    })
end

function Quran:onQuranShowPackSelfTest()
    self:showPackSelfTest()
end

return Quran
