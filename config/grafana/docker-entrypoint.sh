#!/bin/sh
set -e

# Install gcompat packages if not present
if ! apk list --installed 2>/dev/null | grep -q gcompat; then
  apk add --no-cache gcompat libstdc++ libc6-compat 2>/dev/null || true
fi

# Install grafana-image-renderer plugin if not present
PLUGIN_DIR="/var/lib/grafana/plugins/grafana-image-renderer"
if [ ! -d "$PLUGIN_DIR" ]; then
  echo "Installing grafana-image-renderer plugin..."
  grafana cli plugins install grafana-image-renderer 4.1.5
fi

# Apply gcompat wrapper to the plugin binary
if [ -f "$PLUGIN_DIR/plugin_start_linux_amd64" ] && [ ! -f "$PLUGIN_DIR/plugin_start_linux_amd64.bin" ]; then
  echo "Applying gcompat wrapper to renderer plugin..."
  cp "$PLUGIN_DIR/plugin_start_linux_amd64" "$PLUGIN_DIR/plugin_start_linux_amd64.bin"
  cat > "$PLUGIN_DIR/plugin_start_linux_amd64" << 'WRAPPER'
#!/bin/sh
exec /usr/glibc-compat/lib/ld-linux-x86-64.so.2 \
  --library-path /usr/glibc-compat/lib:/usr/lib:/lib \
  /var/lib/grafana/plugins/grafana-image-renderer/plugin_start_linux_amd64.bin \
  "$@"
WRAPPER
  chmod +x "$PLUGIN_DIR/plugin_start_linux_amd64"
fi

# Update plugin.json to use wrapper
if [ -f "$PLUGIN_DIR/plugin.json" ]; then
  python3 -c "
import json
with open('$PLUGIN_DIR/plugin.json', 'r') as f:
    data = json.load(f)
data['server'] = {'command': '$PLUGIN_DIR/plugin_start_linux_amd64'}
with open('$PLUGIN_DIR/plugin.json', 'w') as f:
    json.dump(data, f, indent=2)
" 2>/dev/null || true
fi

echo "Starting Grafana..."
exec grafana server "$@"
