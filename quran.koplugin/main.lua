--[[--
Qur'an, Milestone 0: renders one hard-coded, verbatim Tanzil Uthmani ayah
(2:255, Ayat al-Kursi) full-screen, to answer one question: does Arabic
shaping, joining and harakat work on this KOReader/Kindle build?

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
local AYAH_TEXT = [==[ٱللَّهُ لَآ إِلَٰهَ إِلَّا هُوَ ٱلْحَىُّ ٱلْقَيُّومُ ۚ لَا تَأْخُذُهُۥ سِنَةٌۭ وَلَا نَوْمٌۭ ۚ لَّهُۥ مَا فِى ٱلسَّمَٰوَٰتِ وَمَا فِى ٱلْأَرْضِ ۗ مَن ذَا ٱلَّذِى يَشْفَعُ عِندَهُۥٓ إِلَّا بِإِذْنِهِۦ ۚ يَعْلَمُ مَا بَيْنَ أَيْدِيهِمْ وَمَا خَلْفَهُمْ ۖ وَلَا يُحِيطُونَ بِشَىْءٍۢ مِّنْ عِلْمِهِۦٓ إِلَّا بِمَا شَآءَ ۚ وَسِعَ كُرْسِيُّهُ ٱلسَّمَٰوَٰتِ وَٱلْأَرْضَ ۖ وَلَا يَـُٔودُهُۥ حِفْظُهُمَا ۚ وَهُوَ ٱلْعَلِىُّ ٱلْعَظِيمُ]==]
-- END VERBATIM

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
function Quran:showTestAyah()
    UIManager:show(InfoMessage:new{
        text = "Qur'an " .. AYAH_REF .. "\n\n" .. AYAH_TEXT,
        face = Font:getFace(ARABIC_FONT or "cfont", ARABIC_FONT_SIZE),
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

return Quran
