#!/bin/zsh -f
setopt NO_UNSET
readonly workflow_dir="${0:A:h}"
if ! result=$(/bin/zsh -f "$workflow_dir/eject-photo-library.zsh" --list); then
  print -r -- '{"items":[{"title":"Could not inspect mounted libraries","subtitle":"Try again, or check this workflow in Alfred’s debugger.","valid":false}]}'
else
  print -r -- "$result"
fi
