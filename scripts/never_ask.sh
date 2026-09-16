#!/bin/sh
# Set Claude Code to never ask for permission on this machine.
#
# Merges into ~/.claude/settings.json (nothing already there is removed): the default
# permission mode becomes bypassPermissions, and explicit allow rules for the floor's deploys,
# scripts and git are added as a fallback. Takes effect in the next Claude Code session.
#
#     sh scripts/never_ask.sh
set -e
python3 - <<'EOF'
import json, os
path = os.path.expanduser("~/.claude/settings.json")
try:
    data = json.load(open(path))
except (OSError, ValueError):
    data = {}
perms = data.setdefault("permissions", {})
perms["defaultMode"] = "bypassPermissions"
allow = perms.setdefault("allow", [])
for rule in [
    "Bash(npx wrangler deploy*)",
    "Bash(cd * && npx wrangler deploy*)",
    "Bash(npm run build*)",
    "Bash(python3 scripts/*)",
    "Bash(timeout * .venv/bin/python scripts/*)",
    "Bash(.venv/bin/python scripts/*)",
    "Bash(git *)",
]:
    if rule not in allow:
        allow.append(rule)
os.makedirs(os.path.dirname(path), exist_ok=True)
json.dump(data, open(path, "w"), indent=2)
print("updated", path)
print(json.dumps(data["permissions"], indent=2))
EOF
