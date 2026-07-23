#!/bin/bash
set -e
cd "$(dirname "$0")"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   DataBroker229 — Redesign Complet 🎨    ║"
echo "╚══════════════════════════════════════════╝"
echo ""

FILES=(
  "app/templates/base.html"
  "app/templates/index.html"
  "app/templates/login.html"
  "app/templates/register.html"
  "app/templates/agent_dashboard.html"
  "app/templates/agent_submit.html"
  "app/templates/client_dashboard.html"
  "app/templates/admin_dashboard.html"
  "app/templates/admin_review.html"
)

echo "📂 Copie des fichiers redesignés..."
for f in "${FILES[@]}"; do
  src="/home/claude/databroker229_fixed/$f"
  dst="$f"
  if [ -f "$src" ]; then
    cp "$src" "$dst"
    echo "  ✅ $f"
  else
    echo "  ⚠️  MANQUANT : $src"
  fi
done

echo ""
echo "🚀 Envoi sur GitHub..."
git add "${FILES[@]}"
git commit -m "redesign: nouveau design sombre moderne (style dark/amber) sur toutes les pages"
git push

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  ✅  Redesign terminé — projet sur GitHub ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "➡  Va sur Render et lance un nouveau déploiement !"
