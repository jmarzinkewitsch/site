#!/bin/sh
set -eu

derived_data_root="${1:-${HOME}/Library/Developer/Xcode/DerivedData}"
old_identifier="com.kintan.ksplayer.libshaderc_combined"
new_identifier="com.kintan.ksplayer.libshaderc-combined"

patch_plist() {
    plist="$1"
    current=$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" "$plist" 2>/dev/null || true)
    if [ "$current" = "$old_identifier" ]; then
        /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $new_identifier" "$plist"
        echo "Patched $plist"
    fi
}

find "$derived_data_root" \
    -path "*/SourcePackages/checkouts/FFmpegKit/Sources/libshaderc_combined.xcframework/*/libshaderc_combined.framework/Info.plist" \
    -print | while IFS= read -r plist; do
        patch_plist "$plist"
    done

find "$derived_data_root" \
    -path "*/Build/Products/*/*.app/Frameworks/libshaderc_combined.framework/Info.plist" \
    -print | while IFS= read -r plist; do
        patch_plist "$plist"

        framework_dir=$(dirname "$plist")
        app_dir=${framework_dir%/Frameworks/libshaderc_combined.framework}
        identity=$(codesign -dv --verbose=4 "$app_dir" 2>&1 | awk -F= '/^Authority=Apple Development/{print $2; exit}')

        if [ -n "$identity" ]; then
            codesign --force --sign "$identity" "$framework_dir"
            codesign --force --sign "$identity" --preserve-metadata=entitlements,requirements,flags "$app_dir"
            echo "Re-signed $framework_dir and $app_dir"
        else
            echo "Skipped re-signing $framework_dir: could not infer Apple Development identity from $app_dir" >&2
        fi
    done
