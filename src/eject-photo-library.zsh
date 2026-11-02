#!/bin/zsh -f
# Find and eject mounted disk images held open by Photos libraries.
# No force unmounts, SIGKILL, sudo, or permanent service/indexing changes.
setopt NO_UNSET PIPE_FAIL
umask 077

typeset IMAGE_PATH=''
readonly PB=/usr/libexec/PlistBuddy
typeset scratch='' disk='' mode=eject
typeset -a mounts blocker_pids stop_pids candidate_images candidate_labels
typeset -A blocker_names
typeset -i pause_at_end=1 has_photo_library=0

cleanup() {
  [[ -n "$scratch" ]] && /bin/rm -rf -- "$scratch"
  return 0
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

usage() {
  print -r -- "Usage: ${0:t} [--list | --diagnose] [--image PATH] [--no-pause]"
  print -r -- 'Finds mounted disk images with a Photos library open in Photos or its background services.'
}

# Return 10 when this exact image is not attached; 1 on uncertain/invalid state.
# Resolve the device afresh each time: disk numbers can change between mounts.
discover_image() {
  disk=''
  mounts=()
  /usr/bin/hdiutil info -plist > "$scratch/images.plist" || return 1
  "$PB" -c 'Print :images' "$scratch/images.plist" >/dev/null 2>&1 || {
    print -u2 -- 'Cannot read the attached-image list.'
    return 1
  }
  local image_path entity dev mount_point
  local -i i=0 j=0 matches=0
  while "$PB" -c "Print :images:${i}" "$scratch/images.plist" >/dev/null 2>&1; do
    image_path=$("$PB" -c "Print :images:${i}:image-path" "$scratch/images.plist" 2>/dev/null) || return 1
    if [[ "$image_path" == "$IMAGE_PATH" ]]; then
      (( matches += 1 ))
      j=0
      while "$PB" -c "Print :images:${i}:system-entities:${j}" "$scratch/images.plist" >/dev/null 2>&1; do
        entity=":images:${i}:system-entities:${j}"
        dev=$("$PB" -c "Print ${entity}:dev-entry" "$scratch/images.plist" 2>/dev/null) || return 1
        # The image's physical disk precedes any synthesized APFS disks.
        [[ -z "$disk" && "$dev" == /dev/disk<-> ]] && disk="$dev"
        mount_point=$("$PB" -c "Print ${entity}:mount-point" "$scratch/images.plist" 2>/dev/null) || mount_point=''
        [[ -n "$mount_point" ]] && mounts+=("$mount_point")
        (( j += 1 ))
      done
    fi
    (( i += 1 ))
  done
  (( matches == 0 )) && return 10
  if (( matches != 1 )) || [[ "$disk" != /dev/disk<-> ]]; then
    print -u2 -- 'Cannot identify one unambiguous image device. Stopping.'
    return 1
  fi
  return 0
}

collect_blockers() {
  blocker_pids=()
  blocker_names=()
  has_photo_library=0
  (( ${#mounts} == 0 )) && return 0
  local line pid='' rc
  /usr/sbin/lsof -nP -F pcn +f -- "${mounts[@]}" > "$scratch/blockers" 2> "$scratch/lsof-error"
  rc=$?
  if (( rc > 1 )) || [[ -s "$scratch/lsof-error" ]]; then
    print -u2 -- 'Cannot reliably inspect open files. Stopping without stopping services.'
    /bin/cat "$scratch/lsof-error" >&2
    return 1
  fi
  while IFS= read -r line; do
    case "$line" in
      p<->)
        pid=${line#p}
        (( pid > 1 )) || return 1
        blocker_pids+=("$pid")
        blocker_names[$pid]='unknown process'
        ;;
      c*) [[ -n "$pid" ]] && blocker_names[$pid]=${line#c} ;;
      n*)
        if [[ -n "$pid" && "${(L)line}" == *.photoslibrary(/*|) ]]; then
          case "${blocker_names[$pid]}" in
            Photos|photolibraryd|photoanalysisd|mediaanalysisd|managedcorespotlightd)
              has_photo_library=1 ;;
          esac
        fi
        ;;
    esac
  done < "$scratch/blockers"
  # A nonzero result is normal only when no open files were found.
  (( rc == 0 || ${#blocker_pids} == 0 ))
}

# Read only open-file metadata. Do not scan photo folders or open photo contents.
find_candidates() {
  candidate_images=()
  candidate_labels=()
  /usr/bin/hdiutil info -plist > "$scratch/candidates.plist" || return 1
  "$PB" -c 'Print :images' "$scratch/candidates.plist" >/dev/null 2>&1 || return 1
  local -i i=0
  while "$PB" -c "Print :images:${i}" "$scratch/candidates.plist" >/dev/null 2>&1; do
    IMAGE_PATH=$("$PB" -c "Print :images:${i}:image-path" "$scratch/candidates.plist" 2>/dev/null) || return 1
    discover_image || return 1
    collect_blockers || return 1
    if (( has_photo_library )); then
      candidate_images+=("$IMAGE_PATH")
      candidate_labels+=("${mounts[1]:t}")
    fi
    (( i += 1 ))
  done
  IMAGE_PATH=''
  return 0
}

json_string() {
  local value=$1 char escaped='' piece
  local -i i code
  for (( i=1; i<=${#value}; i++ )); do
    char=${value[i]}
    case "$char" in
      '"') escaped+='\"' ;;
      '\') escaped+='\\' ;;
      [[:cntrl:]])
        printf -v code '%d' "'$char"
        printf -v piece '\\u%04x' "$code"
        escaped+=$piece
        ;;
      *) escaped+=$char ;;
    esac
  done
  print -nr -- "\"$escaped\""
}

list_candidates() {
  local -i i
  local subtitle
  if (( ${#candidate_images} == 0 )); then
    print -r -- '{"items":[{"title":"No photo library image to eject","subtitle":"No mounted disk image is currently held open by a Photos library.","valid":false}]}'
    return 0
  fi
  print -nr -- '{"items":['
  for (( i=1; i<=${#candidate_images}; i++ )); do
    (( i > 1 )) && print -nr -- ','
    subtitle='Safely release background services and eject the disk image'
    # Names are needed only to distinguish several images; never show library paths.
    (( ${#candidate_images} > 1 )) && subtitle="Choose mounted image: ${candidate_labels[i]}"
    print -nr -- '{"title":"Eject photo library","subtitle":'
    json_string "$subtitle"
    print -nr -- ',"arg":'
    json_string "${candidate_images[i]}"
    print -nr -- ',"text":{"copy":"Eject photo library","largetype":"Eject photo library"},"valid":true}'
  done
  print -r -- ']}'
}

show_blockers() {
  local pid
  if (( ${#blocker_pids} == 0 )); then
    print -- 'No open-file blockers were visible to this account.'
  else
    print -- 'Processes holding this image open:'
    for pid in "${blocker_pids[@]}"; do
      print -r -- "  ${blocker_names[$pid]} (PID $pid)"
    done
  fi
}

# Only our own, known Apple helpers are eligible for a graceful SIGTERM.
# Never quit Photos, Finder, editors, terminals, or unknown processes.
prepare_services() {
  stop_pids=()
  local pid owner executable
  local -i blocked=0
  for pid in "${blocker_pids[@]}"; do
    if ! owner=$(/bin/ps -p "$pid" -o uid=); then
      print -u2 -- "Process $pid changed or cannot be inspected. Please rerun."
      return 1
    fi
    owner=${owner//[[:space:]]/}
    executable=$(/bin/ps -p "$pid" -o comm=) || return 1
    if [[ "$owner" != "$EUID" ]]; then
      blocked=1
    else
      case "$executable" in
        /System/Library/PrivateFrameworks/PhotoLibraryServices.framework/Versions/A/Support/photolibraryd|\
        /System/Library/PrivateFrameworks/PhotoAnalysis.framework/Versions/A/Support/photoanalysisd|\
        /System/Library/PrivateFrameworks/MediaAnalysis.framework/Versions/A/mediaanalysisd|\
        /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/Metadata.framework/Versions/A/Support/managedcorespotlightd)
          stop_pids+=("$pid")
          continue
          ;;
      esac
      blocked=1
    fi
    print -r -u2 -- "Please finish work and quit ${blocker_names[$pid]} (PID $pid), then run this again."
  done
  (( blocked == 0 ))
}

try_eject() {
  local rc
  discover_image
  rc=$?
  (( rc == 10 )) && return 0
  (( rc == 0 )) || return 1
  print -r -- "Trying a normal eject of $disk..."
  /usr/sbin/diskutil eject "$disk" || return 1
  discover_image
  rc=$?
  if (( rc == 10 )); then
    return 0
  fi
  print -u2 -- 'The image is still attached, or its state could not be verified.'
  return 1
}

main() {
  local rc pid
  local -i attempt
  while (( $# )); do
    case "$1" in
      --list) mode=list; pause_at_end=0 ;;
      --diagnose) mode=diagnose ;;
      --image)
        (( $# >= 2 )) || { usage >&2; return 2; }
        IMAGE_PATH=$2
        shift
        ;;
      --no-pause) pause_at_end=0 ;;
      --help|-h) usage; return 0 ;;
      *) usage >&2; return 2 ;;
    esac
    shift
  done
  if (( EUID == 0 )); then
    print -u2 -- 'Run this as your normal Mac account, without sudo.'
    return 1
  fi
  # Do not let this script's own working directory keep the volume busy.
  builtin cd / || return 1
  scratch=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/eject-photo-library.XXXXXXXX") || return 1
  if [[ -z "$IMAGE_PATH" || "$mode" == list ]]; then
    find_candidates || return 1
    if [[ "$mode" == list ]]; then
      list_candidates
      return 0
    fi
    if (( ${#candidate_images} == 0 )); then
      print -- 'No mounted photo library image needs ejecting.'
      return 0
    fi
    if (( ${#candidate_images} > 1 )); then
      print -u2 -- 'Several photo library images are mounted. Choose one in Alfred, or use --image PATH.'
      return 1
    fi
    IMAGE_PATH=${candidate_images[1]}
  fi
  discover_image
  rc=$?
  if (( rc == 10 )); then
    print -- 'Photo library image is already ejected.'
    return 0
  fi
  (( rc == 0 )) || return 1
  if [[ "$mode" == diagnose ]]; then
    collect_blockers || return 1
    show_blockers
    return 0
  fi
  if try_eject; then
    print -- 'Photo library image safely ejected.'
    return 0
  fi
  for attempt in 1 2 3; do
    discover_image
    rc=$?
    if (( rc == 10 )); then
      print -- 'Photo library image safely ejected.'
      return 0
    fi
    (( rc == 0 )) || return 1
    collect_blockers || return 1
    show_blockers
    prepare_services || return 1
    for pid in "${stop_pids[@]}"; do
      print -r -- "Asking ${blocker_names[$pid]} (PID $pid) to stop gracefully..."
      /bin/kill -TERM "$pid" || {
        print -u2 -- 'A service changed or could not be stopped. Please rerun.'
        return 1
      }
    done
    if try_eject; then
      print -- 'Photo library image safely ejected.'
      return 0
    fi
    (( attempt < 3 )) && /bin/sleep 1
  done
  print -u2 -- 'Still busy after three retries. No force eject was used.'
  print -u2 -- 'Finish any photo work, then rerun. If it persists, log out or restart your Mac.'
  return 1
}

main "$@"
result=$?
if (( pause_at_end )) && [[ -t 0 && -t 1 ]]; then
  read -r '?Press Return to close this window. '
fi
exit "$result"
