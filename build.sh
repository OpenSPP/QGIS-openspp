#!/bin/bash
# Build OpenSPP QGIS plugin for distribution

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$SCRIPT_DIR/openspp_qgis"
OUTPUT_FILE="$SCRIPT_DIR/openspp_qgis.zip"

echo "Building OpenSPP QGIS Plugin..."

# Check plugin directory exists
if [ ! -d "$PLUGIN_DIR" ]; then
    echo "Error: Plugin directory not found: $PLUGIN_DIR"
    exit 1
fi

# Check metadata.txt exists
if [ ! -f "$PLUGIN_DIR/metadata.txt" ]; then
    echo "Error: metadata.txt not found"
    exit 1
fi

# Remove old build
if [ -f "$OUTPUT_FILE" ]; then
    rm "$OUTPUT_FILE"
    echo "Removed old build"
fi

# Clean up Python cache
find "$PLUGIN_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$PLUGIN_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

# Validate Python syntax
echo "Validating Python syntax..."
for pyfile in $(find "$PLUGIN_DIR" -name "*.py"); do
    python3 -m py_compile "$pyfile" || {
        echo "Syntax error in: $pyfile"
        exit 1
    }
done
echo "All Python files valid"

# Create ZIP
cd "$SCRIPT_DIR"
zip -r "$OUTPUT_FILE" openspp_qgis \
    -x "*.pyc" \
    -x "*__pycache__*" \
    -x "*.git*" \
    -x "*.DS_Store"

# Show result
echo ""
echo "Build complete!"
echo "Output: $OUTPUT_FILE"
echo "Size: $(du -h "$OUTPUT_FILE" | cut -f1)"
echo ""
echo "To install in QGIS:"
echo "  1. Plugins → Manage and Install Plugins"
echo "  2. Install from ZIP"
echo "  3. Select: $OUTPUT_FILE"
