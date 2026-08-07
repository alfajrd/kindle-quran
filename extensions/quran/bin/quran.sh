#!/bin/sh
# Launches KOReader. The Qur'an plugin is then opened from KOReader's own
# menu (see D4 in .pipeline/spec.md) -- this script does not deep-link into
# the plugin.
#
# MUST-VERIFY V6: the spec's assumed launcher path,
# /mnt/us/extensions/koreader/bin/koreader.sh, does not match KOReader's own
# published Kindle KUAL entry (platform/kindle/extensions/koreader/menu.json
# in the koreader/koreader source tree), which launches
# /mnt/us/koreader/koreader.sh. That verified path is tried first; the
# spec's originally assumed path is tried as a fallback in case of an
# unusual install layout. If neither exists, fail loudly instead of
# silently, per spec edge case 10.

PRIMARY=/mnt/us/koreader/koreader.sh
FALLBACK=/mnt/us/extensions/koreader/bin/koreader.sh

if [ -x "$PRIMARY" ]; then
    exec "$PRIMARY"
elif [ -x "$FALLBACK" ]; then
    exec "$FALLBACK"
else
    echo "quran.sh: could not find KOReader's launcher at $PRIMARY or $FALLBACK -- is KOReader installed?" 1>&2
    exit 1
fi
