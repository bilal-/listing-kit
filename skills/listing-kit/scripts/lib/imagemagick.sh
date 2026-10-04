# shellcheck shell=bash
# Resolve ImageMagick 7 (`magick …`) or 6 (`convert` / `compare` / `identify`).
# Source it, then call im_resolve; on success it sets three arrays:
#   IM          convert-style command (magick | convert)
#   IM_COMPARE  compare command        (magick compare | compare)
#   IM_IDENTIFY identify command       (magick identify | identify)
# Returns 1 when ImageMagick is absent, or when LK_NO_IMAGEMAGICK is set (tests,
# or to force a script's non-ImageMagick fallback).
im_resolve(){
  [ -z "${LK_NO_IMAGEMAGICK:-}" ] || return 1
  if command -v magick >/dev/null 2>&1; then
    IM=(magick); IM_COMPARE=(magick compare); IM_IDENTIFY=(magick identify)
  elif command -v convert >/dev/null 2>&1 || command -v compare >/dev/null 2>&1; then
    IM=(convert); IM_COMPARE=(compare); IM_IDENTIFY=(identify)
  else
    return 1
  fi
}
