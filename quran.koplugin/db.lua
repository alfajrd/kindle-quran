--[[--
Qur'an, Milestone 1: read-only SQLite access layer for `data/quran.db`.

No caching, no preloading, no "load the whole Qur'an into a table" (see
`.pipeline/spec.md` §10: don't). Every function below returns an error
string rather than throwing; the caller decides how loud to be.

MUST-VERIFY V11-V14 -- read this before touching anything in this file.
------------------------------------------------------------------------
This machine has no KOReader/koreader-base checkout and no network access,
so none of the following could be settled by reading source, only by
implementing the spec's own best-effort claim as the conservative option
and flagging it here, per instruction. All four are on the "what only the
device can settle" list in `.pipeline/spec.md` -- the spec itself expects
these to be confirmed on a real Kindle, not on this machine.

  V11 (binding module path): implemented as `require("lua-ljsqlite3/init")`,
      exactly as spec.md states. UNVERIFIED -- could not grep a KOReader
      tree for `ljsqlite3` on this machine.
  V12 (binding API surface): implemented as `SQ3.open(path)` -> conn,
      `conn:exec(sql)` for the read-only pragma, and `conn:rowexec(sql,
      ...params)` -> the first row's column(s) as return value(s) for the
      two single-row queries this module needs (`getAyah`, `getMeta`,
      `counts`). UNVERIFIED against `koreader-base/thirdparty/
      lua-ljsqlite3/init.lua` -- could not read that file on this machine.
      Every call into the binding is wrapped in `pcall`, and any failure
      (wrong method name, wrong argument shape, wrong return shape) is
      surfaced as a normal `(nil, err_string)` return from this module
      rather than an uncaught Lua error, so a mismatch here fails loudly
      and specifically on the device instead of crashing plugin load.
  V13 (read-only open): no verified open-flags argument for `SQ3.open`, so
      this uses the fallback spec.md itself names for exactly this case:
      `PRAGMA query_only = 1` immediately after opening. This does not
      stop SQLite from creating a `-wal`/`-journal` file if the pragma
      itself fails to apply before any other statement runs -- `DB.open`
      aborts and closes the connection if setting the pragma fails, rather
      than proceeding without it.
  V14 (plugin resolves its own directory via `self.path`): not exercised in
      this file -- `main.lua:packPath()` owns that logic. See its header
      comment for the V14 finding.

If any of V11-V13 turn out wrong on-device, the failure mode is a clear,
specific `(nil, err_string)` from `DB.open`/`DB.getAyah`, surfaced by
`main.lua` as an InfoMessage naming the attempted path and the underlying
Lua error -- never a silent fallback, never a crash at plugin load.

@module koplugin.Quran.db
--]]--

local SQ3ok, SQ3 = pcall(require, "lua-ljsqlite3/init")

local DB = {}

-- Opens the pack READ-ONLY. Returns (conn, nil) or (nil, err_string).
-- Must not create -wal/-journal files: /mnt/us may be mounted read-only.
function DB.open(path)
    if not SQ3ok then
        return nil, "lua-ljsqlite3/init could not be loaded: " .. tostring(SQ3)
    end
    local ok, conn = pcall(SQ3.open, path)
    if not ok or not conn then
        return nil, "could not open pack: " .. tostring(conn)
    end
    local qok, qerr = pcall(function()
        conn:exec("PRAGMA query_only = 1;")
    end)
    if not qok then
        pcall(function() conn:close() end)
        return nil, "could not set PRAGMA query_only: " .. tostring(qerr)
    end
    return conn, nil
end

-- Returns (text, nil) or (nil, err_string). err_string when the row is absent.
function DB.getAyah(conn, surah, ayah)
    if not conn then
        return nil, "DB.getAyah: no connection"
    end
    local ok, text = pcall(function()
        return conn:rowexec("SELECT text FROM ayah WHERE surah = ? AND ayah = ?;", surah, ayah)
    end)
    if not ok then
        return nil, "DB.getAyah(" .. tostring(surah) .. ":" .. tostring(ayah) .. "): " .. tostring(text)
    end
    if text == nil then
        return nil, "DB.getAyah: no row for " .. tostring(surah) .. ":" .. tostring(ayah)
    end
    return text, nil
end

-- Returns value string, or nil if the key is absent.
function DB.getMeta(conn, key)
    if not conn then
        return nil
    end
    local ok, value = pcall(function()
        return conn:rowexec("SELECT value FROM meta WHERE key = ?;", key)
    end)
    if not ok then
        return nil
    end
    return value
end

-- Returns (surah_count, ayah_count) as integers, counted from the tables.
function DB.counts(conn)
    if not conn then
        return 0, 0
    end
    local ok1, surah_count = pcall(function()
        return conn:rowexec("SELECT COUNT(*) FROM surah;")
    end)
    local ok2, ayah_count = pcall(function()
        return conn:rowexec("SELECT COUNT(*) FROM ayah;")
    end)
    return (ok1 and tonumber(surah_count)) or 0, (ok2 and tonumber(ayah_count)) or 0
end

-- Returns (count, nil) or (nil, err_string).
function DB.getSurahAyahCount(conn, surah)
    if not conn then
        return nil, "DB.getSurahAyahCount: no connection"
    end
    local ok, count = pcall(function()
        return conn:rowexec("SELECT ayah_count FROM surah WHERE id = ?;", surah)
    end)
    if not ok then
        return nil, "DB.getSurahAyahCount(" .. tostring(surah) .. "): " .. tostring(count)
    end
    if count == nil then
        return nil, "DB.getSurahAyahCount: no row for surah " .. tostring(surah)
    end
    return count, nil
end

-- `which` is one of "name_ar" | "name_en" | "name_tr"; anything else is an
-- error return, never interpolated into SQL. Returns (value, nil) or (nil, err).
function DB.getSurahName(conn, surah, which)
    if not conn then
        return nil, "DB.getSurahName: no connection"
    end
    local column
    if which == "name_ar" then
        column = "name_ar"
    elseif which == "name_en" then
        column = "name_en"
    elseif which == "name_tr" then
        column = "name_tr"
    else
        return nil, "DB.getSurahName: invalid `which`: " .. tostring(which)
    end
    local sql
    if column == "name_ar" then
        sql = "SELECT name_ar FROM surah WHERE id = ?;"
    elseif column == "name_en" then
        sql = "SELECT name_en FROM surah WHERE id = ?;"
    else
        sql = "SELECT name_tr FROM surah WHERE id = ?;"
    end
    local ok, value = pcall(function()
        return conn:rowexec(sql, surah)
    end)
    if not ok then
        return nil, "DB.getSurahName(" .. tostring(surah) .. ", " .. tostring(which) .. "): " .. tostring(value)
    end
    if value == nil then
        return nil, "DB.getSurahName: no row for surah " .. tostring(surah)
    end
    return value, nil
end

function DB.close(conn)
    if conn then
        pcall(function() conn:close() end)
    end
end

return DB
