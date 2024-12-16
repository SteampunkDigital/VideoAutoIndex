#!/bin/bash

# Build the app
swift build -c release

# Create app bundle structure
APP_NAME="VideoAutoIndexApp"
BUNDLE_DIR="/Applications/$APP_NAME.app"
CONTENTS_DIR="$BUNDLE_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

# Create directories
mkdir -p "$MACOS_DIR" "$RESOURCES_DIR"

# Copy binary
cp .build/release/VideoAutoIndexApp "$MACOS_DIR/"

# Create Info.plist in Contents directory
cat > "$CONTENTS_DIR/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>VideoAutoIndexApp</string>
    <key>CFBundleIdentifier</key>
    <string>com.steampunkdigital.videoautoindex</string>
    <key>CFBundleName</key>
    <string>VideoAutoIndexApp</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>CFBundleSupportedPlatforms</key>
    <array>
        <string>MacOSX</string>
    </array>
</dict>
</plist>
EOF

echo "App bundle created at $BUNDLE_DIR"
