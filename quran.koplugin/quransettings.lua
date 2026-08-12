--[[--
Qur'an, Milestone 2: `LuaSettings` wrapper -- typography values, per-surah
position memory, validation on read, and flush policy.

Persists through KOReader's own `LuaSettings`, in KOReader's own settings
directory (`DataStorage:getSettingsDir() .. "/quran.lua"`), never inside
`quran.koplugin/` -- that directory holds the pack, may be on a read-only
mount, and is replaced wholesale on upgrade. See `.pipeline/spec.md` D3.

MUST-VERIFY V30-V32 -- read this before touching anything in this file.
------------------------------------------------------------------------
This machine has no KOReader checkout and no network access, so none of the
following could be confirmed by reading source -- only implemented as the
spec's own best-effort claim and flagged here. See `docs/VERIFY-M2.md`.

  MUST-VERIFY V30 (LuaSettings API surface): implemented as
      `require("luasettings")` returning a module with `LuaSettings:open(path)`
      -> an instance with `:readSetting(k)`, `:saveSetting(k, v)`, `:flush()`,
      `:close()`. Every call into it is wrapped in `pcall`; a mismatch here
      surfaces as a normal `(store, err_string)` pair from `Settings.open`,
      never an uncaught Lua error.
  MUST-VERIFY V31 (settings directory): implemented as
      `require("datastorage")`, `DataStorage:getSettingsDir()` returning a
      writable directory. If either require or the call fails, persistence
      is disabled: `store.ls == nil`, every getter falls back to
      `Settings.DEFAULTS`, every setter is an in-memory no-op, and the
      reader still opens and reads.
  MUST-VERIFY V32 (nested-table round-trip): `positions` is a Lua table,
      keyed by surah number **as a string** (`"2"`, not `2`) -- Lua
      serialisers handle string keys unambiguously and integer keys less
      so -- saved and read back through a single `saveSetting`/`readSetting`
      call. Not independently verified on this machine that `LuaSettings`
      round-trips a nested table faithfully; if it does not, the failure
      mode is `Settings.getPosition` returning its own default (1, 0)
      rather than a corrupted position, because every read is validated
      (see below) before it is trusted.

If any of V30-V32 turn out wrong on-device, the failure mode is: persistence
silently degrades to "off" (defaults every session), never a crash, never a
half-written settings file, never a value invented instead of a default.

@module koplugin.Quran.settings
--]]--

local Settings = {}

Settings.SETTINGS_VERSION = 1

-- Defaults and limits, from `.pipeline/spec.md` SPEC-v1 §9 / §6.6.
--
-- `arabic_line_height` is `TextBoxWidget`'s `line_height` key: extra
-- leading in EM, default 0.3 upstream (MUST-VERIFY V21). SPEC-v1 §9's
-- "1.9 x line height" therefore maps to `line_height = 0.9`, and the 1.7x
-- floor to `0.7`. Do not "correct" this back to 1.9 -- that would be the
-- raw multiplier, not the extra-leading value TextBoxWidget actually wants.
-- Milestone 3 adds the English pair and the display mode.
--
-- English defaults are SPEC-v1 §9's (22 px, 1.5x leading -> line_height 0.5).
-- They are separate keys, not a ratio of the Arabic ones, because a reader
-- wanting large Arabic rarely wants equally large English -- which is exactly
-- what the interleaved layout makes visible, since both appear at once.
--
-- Note the Arabic default was chosen on device at FULL width. Interleaved mode
-- gives it a ~562 px column on a PW11, where it wraps roughly twice as often.
-- If 34 proves too large there, lower it in the reader rather than changing
-- this default, which Arabic-only mode still depends on.
Settings.DEFAULTS = { arabic_font_size = 34, arabic_line_height = 1.5,
                      english_font_size = 22, english_line_height = 0.5,
                      rules_enabled = true, display_mode = "arabic" }
Settings.LIMITS   = { arabic_font_size    = { min = 26, max = 60,  step = 2   },
                      arabic_line_height  = { min = 0.7, max = 2.0, step = 0.1 },
                      english_font_size   = { min = 16, max = 40,  step = 2   },
                      english_line_height = { min = 0.3, max = 1.2, step = 0.1 } }

-- The two pagination models (docs/BACKLOG.md B1). Anything else read from the
-- settings file falls back to the default rather than being passed through --
-- an unknown mode string would reach the reader as neither model.
Settings.DISPLAY_MODES = { arabic = true, interleaved = true }

local function clamp(value, lim)
    if value < lim.min then
        return lim.min
    elseif value > lim.max then
        return lim.max
    end
    return value
end

-- Safe wrappers: `store.ls` may be nil (persistence off), and any call into
-- LuaSettings itself is pcall-guarded per V30.
local function ls_read(store, key)
    if not store.ls then
        return nil
    end
    local ok, value = pcall(function() return store.ls:readSetting(key) end)
    if not ok then
        return nil
    end
    return value
end

local function ls_save(store, key, value)
    if not store.ls then
        return
    end
    local ok = pcall(function() store.ls:saveSetting(key, value) end)
    if ok then
        store.dirty = true
    end
end

-- Returns (store, nil) | (nil, err_string). `store` is always usable, even
-- on failure -- see D3: the reader must work without a settings file.
function Settings.open()
    local ok_ds, DataStorage = pcall(require, "datastorage")
    local ok_ls, LuaSettingsMod = pcall(require, "luasettings")
    if not ok_ds or not ok_ls then
        local store = { ls = nil, dirty = false }
        return store, "settings persistence unavailable: require(\"datastorage\")=" ..
            tostring(ok_ds) .. " require(\"luasettings\")=" .. tostring(ok_ls)
    end

    local ok_dir, dir = pcall(function() return DataStorage:getSettingsDir() end)
    if not ok_dir or not dir or dir == "" then
        local store = { ls = nil, dirty = false }
        return store, "DataStorage:getSettingsDir() failed: " .. tostring(dir)
    end

    local path = dir .. "/quran.lua"
    local ok_open, ls = pcall(function() return LuaSettingsMod:open(path) end)
    if not ok_open or not ls then
        local store = { ls = nil, dirty = false }
        return store, "LuaSettings:open(" .. path .. ") failed: " .. tostring(ls)
    end

    local store = { ls = ls, dirty = false }

    -- settings_version mismatch: keep positions if they validate (reads are
    -- validated on every access anyway), reset typography to defaults,
    -- never delete the user's file.
    local version = ls_read(store, "settings_version")
    if version ~= Settings.SETTINGS_VERSION then
        for key, value in pairs(Settings.DEFAULTS) do
            ls_save(store, key, value)
        end
        ls_save(store, "settings_version", Settings.SETTINGS_VERSION)
    end

    return store, nil
end

-- Never nil; falls back to DEFAULTS on a missing/corrupt/wrong-type value.
function Settings.get(store, key)
    local default = Settings.DEFAULTS[key]
    local raw = ls_read(store, key)
    if raw == nil or type(raw) ~= type(default) then
        return default
    end
    -- An unrecognised display_mode is treated as absent. It cannot be clamped
    -- into range like a number, and passing it through would leave the reader
    -- in neither pagination model.
    if key == "display_mode" and not Settings.DISPLAY_MODES[raw] then
        return default
    end
    local lim = Settings.LIMITS[key]
    if lim and type(raw) == "number" then
        return clamp(raw, lim)
    end
    return raw
end

-- Clamps to LIMITS (when the key has limits); marks dirty. In-memory no-op
-- when persistence is unavailable.
function Settings.set(store, key, value)
    local lim = Settings.LIMITS[key]
    if lim and type(value) == "number" then
        value = clamp(value, lim)
    end
    ls_save(store, key, value)
end

-- -> (ayah, line), default (1, 0). Validated: `ayah` outside 1..huge or not
-- a positive integer falls back to 1; `line` < 0 or non-integer falls back
-- to 0. Clamping against the surah's *current* ayah/line count is the
-- caller's job (it alone knows the current ayah_count / line count).
function Settings.getPosition(store, surah)
    if type(surah) ~= "number" or surah < 1 or surah > 114 then
        return 1, 0
    end
    local positions = ls_read(store, "positions")
    if type(positions) ~= "table" then
        return 1, 0
    end
    local entry = positions[tostring(surah)]
    if type(entry) ~= "table" then
        return 1, 0
    end
    local ayah = entry.ayah
    local line = entry.line
    if type(ayah) ~= "number" or ayah ~= math.floor(ayah) or ayah < 1 then
        ayah = 1
    end
    if type(line) ~= "number" or line ~= math.floor(line) or line < 0 then
        line = 0
    end
    return ayah, line
end

function Settings.setPosition(store, surah, ayah, line)
    if type(surah) ~= "number" or surah < 1 or surah > 114 then
        return
    end
    if not store.ls then
        return
    end
    local positions = ls_read(store, "positions")
    if type(positions) ~= "table" then
        positions = {}
    end
    positions[tostring(surah)] = { ayah = ayah, line = line }
    ls_save(store, "positions", positions)
end

-- -> integer | nil. Outside 1..114 or the wrong type is treated as absent.
function Settings.getLastSurah(store)
    local value = ls_read(store, "last_surah")
    if type(value) ~= "number" or value ~= math.floor(value) or value < 1 or value > 114 then
        return nil
    end
    return value
end

function Settings.setLastSurah(store, surah)
    if type(surah) ~= "number" or surah < 1 or surah > 114 then
        return
    end
    if not store.ls then
        return
    end
    ls_save(store, "last_surah", surah)
end

-- No-op unless dirty.
function Settings.flush(store)
    if store.dirty and store.ls then
        local ok = pcall(function() store.ls:flush() end)
        if ok then
            store.dirty = false
        end
    end
end

function Settings.close(store)
    Settings.flush(store)
    if store.ls then
        pcall(function() store.ls:close() end)
    end
end

return Settings
