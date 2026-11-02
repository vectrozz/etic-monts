#!/usr/bin/env bash
# Install a pre-push hook that runs the local CI (scripts/ci.sh) before every push.
# Skip it once with `git push --no-verify`.
set -euo pipefail
cd "$(dirname "$0")/.."
hook="$(git rev-parse --git-path hooks)/pre-push"
mkdir -p "$(dirname "$hook")"
cat > "$hook" <<'EOF'
#!/usr/bin/env bash
# Installed by scripts/install-git-hooks.sh — local CI before every push.
# Skip once: git push --no-verify
exec "$(git rev-parse --show-toplevel)/scripts/ci.sh"
EOF
chmod +x "$hook"
echo "pre-push hook installed: $hook"
