#!/usr/bin/env bash
# One-time setup for the Shadow Mirror MCP server bundled with this plugin.
#
# Builds a dedicated virtualenv and installs `shadow-mirror[mcp,engine]` FROM THE
# GIT REPOSITORY — no PyPI publication required. Because the repo is PRIVATE, you
# need git access (an SSH key or a token in your git credential helper) for the
# install to succeed. The MCP tools run the engine, so [mcp] and [engine] are
# installed together.
#
# After running this, reconnect the server in Claude Code with `/reload-plugins`
# (or restart) and confirm it under `/mcp`. The matching server config is in the
# sibling `.mcp.json`, which points `command` at this venv's python.
set -euo pipefail

# Persistent per-plugin data dir (survives plugin updates); fall back for a plain
# shell run outside the plugin runtime.
DATA="${CLAUDE_PLUGIN_DATA:-${XDG_CACHE_HOME:-$HOME/.cache}/shadow-mirror-plugin}"
VENV="$DATA/mcp-venv"
# Override to pin a ref/fork, or point at a local checkout for development, e.g.
#   SHADOW_MIRROR_PIP="shadow-mirror[mcp,engine] @ git+https://github.com/acidblock/shadow-mirror.git@v0.2.1"
PIP_SPEC="${SHADOW_MIRROR_PIP:-shadow-mirror[mcp,engine] @ git+https://github.com/acidblock/shadow-mirror.git}"

mkdir -p "$DATA"
if [ -x "$VENV/bin/python" ]; then
  echo "Reusing existing MCP venv: $VENV"
else
  echo "Creating MCP venv: $VENV"
  python3 -m venv "$VENV"
fi

"$VENV/bin/python" -m pip install --quiet --upgrade pip
echo "Installing $PIP_SPEC ..."
"$VENV/bin/python" -m pip install --quiet "$PIP_SPEC"

# Fail loudly if the server can't even import — better here than as a silent
# not-connected server in /mcp.
"$VENV/bin/python" -c "import shadow_mirror.mcp_server; print('shadow-mirror MCP server: import OK')"
echo "Done. Run /reload-plugins in Claude Code, then check /mcp."
