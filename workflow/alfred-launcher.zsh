#!/bin/zsh -f
setopt NO_UNSET PIPE_FAIL
umask 077

readonly workflow_dir="${0:A:h}"
readonly cache_dir="${alfred_workflow_cache:-$HOME/Library/Caches/com.runningwithcrayons.Alfred/Workflow Data/com.nando.eject-photo-library}"
if (( $# != 1 )) || [[ -z "$1" ]]; then
  print -- 'Choose a mounted photo library image in Alfred and try again.'
  exit 0
fi
if ! /bin/mkdir -p "$cache_dir"; then
  print -- 'Could not create the eject log. Please check the workflow debugger.'
  exit 0
fi
readonly log_file="$cache_dir/last-run.log"
/bin/zsh -f "$workflow_dir/eject-photo-library.zsh" --image "$1" --no-pause > "$log_file" 2>&1
rc=$?
if (( rc == 0 )); then
  /usr/bin/tail -n 1 "$log_file"
else
  reason=$(/usr/bin/awk '/^Please finish work and quit / { print; exit }' "$log_file")
  [[ -n "$reason" ]] || reason=$(/usr/bin/tail -n 1 "$log_file")
  [[ -n "$reason" ]] || reason='See the workflow debugger for details.'
  print -r -- "Could not eject. $reason"
  /bin/cat "$log_file" >&2
fi
# Send both success and failure messages to Alfred's Post Notification object.
exit 0
