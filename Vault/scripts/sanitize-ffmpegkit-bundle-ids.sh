#!/bin/bash
set -euo pipefail

sanitize_plist() {
    local plist="$1"
    local identifier

    identifier=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$plist" 2>/dev/null || true)
    if [[ "$identifier" == *_* ]]; then
        /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier ${identifier//_/-}" "$plist"
        return 0
    fi

    return 1
}

roots=(
    "${PROJECT_DIR:-}/../FFmpegKit/Sources"
    "${SOURCE_ROOT:-}/FFmpegKit/Sources"
    "${BUILD_DIR:-}/../../SourcePackages/checkouts/FFmpegKit/Sources"
    "${TARGET_BUILD_DIR:-}/${FRAMEWORKS_FOLDER_PATH:-}"
)

for root in "${roots[@]}"; do
    [[ -d "$root" ]] || continue
    while IFS= read -r -d '' plist; do
        if sanitize_plist "$plist"; then
            framework_dir="${plist%/Info.plist}"
            if [[ "$framework_dir" == "${TARGET_BUILD_DIR:-}"* ]] &&
               [[ "${CODE_SIGNING_ALLOWED:-YES}" != "NO" ]] &&
               [[ -n "${EXPANDED_CODE_SIGN_IDENTITY:-}" ]]; then
                /usr/bin/codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" "$framework_dir"
            fi
        fi
    done < <(find "$root" -path "*.framework/Info.plist" -print0)
done
