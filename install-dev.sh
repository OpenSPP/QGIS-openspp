#!/bin/bash
# Install OpenSPP QGIS plugin for development (symlink)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_DIR="$SCRIPT_DIR/openspp_qgis"

# Detect QGIS plugins directory
if [ -d "$HOME/.local/share/QGIS/QGIS3/profiles/default/python/plugins" ]; then
    # Linux
    QGIS_PLUGINS="$HOME/.local/share/QGIS/QGIS3/profiles/default/python/plugins"
elif [ -d "$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins" ]; then
    # macOS
    QGIS_PLUGINS="$HOME/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins"
else
    echo "Could not detect QGIS plugins directory."
    echo ""
    echo "Please create it manually and run:"
    echo "  ln -sf \"$PLUGIN_DIR\" /path/to/qgis/plugins/"
    exit 1
fi

# Create plugins directory if needed
mkdir -p "$QGIS_PLUGINS"

# Remove existing installation
if [ -L "$QGIS_PLUGINS/openspp_qgis" ]; then
    rm "$QGIS_PLUGINS/openspp_qgis"
    echo "Removed existing symlink"
elif [ -d "$QGIS_PLUGINS/openspp_qgis" ]; then
    echo "Warning: Existing directory found (not a symlink)"
    echo "Please remove manually: $QGIS_PLUGINS/openspp_qgis"
    exit 1
fi

# Create symlink
ln -sf "$PLUGIN_DIR" "$QGIS_PLUGINS/openspp_qgis"

echo ""
echo "Plugin installed for development!"
echo ""
echo "Symlink created:"
echo "  $QGIS_PLUGINS/openspp_qgis -> $PLUGIN_DIR"
echo ""
echo "Next steps:"
echo "  1. Open QGIS"
echo "  2. Plugins → Manage and Install Plugins"
echo "  3. Go to 'Installed' tab"
echo "  4. Enable 'OpenSPP GIS'"
echo ""
echo "To reload after changes:"
echo "  - Install 'Plugin Reloader' plugin, or"
echo "  - Restart QGIS"
