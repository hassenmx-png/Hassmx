#!/usr/bin/env bash
# Installation automatique de l'Usine à vidéos sur un serveur Linux (Ubuntu/Debian).
# Usage :  curl -fsSL <url>/install.sh | bash -s MOT_DE_PASSE
set -e
PASS="${1:-}"
if [ -z "$PASS" ]; then PASS=$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 10); fi
BRANCH_URL="https://codeload.github.com/hassenmx-png/Hassmx/tar.gz/refs/heads/usine-video"
DIR=/opt/usine-video

echo "🎬 Installation de l'Usine à vidéos…"
if ! command -v docker >/dev/null 2>&1; then
  echo "→ Installation de Docker (1-2 min)…"
  curl -fsSL https://get.docker.com | sh >/dev/null
fi
mkdir -p "$DIR" && cd "$DIR"
echo "→ Téléchargement du logiciel…"
curl -fsSL "$BRANCH_URL" | tar xz --strip-components=2 --wildcards '*/usine-video/*'
echo "APP_PASSWORD=$PASS" > .env
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q active; then ufw allow 8000/tcp >/dev/null; fi
echo "→ Construction et lancement (5 min la première fois)…"
docker compose up -d --build
IP=$(curl -fsSL https://api.ipify.org || hostname -I | awk '{print $1}')
echo ""
echo "✅ C'est prêt !"
echo "👉 Ouvre : http://$IP:8000"
echo "   Identifiant : hassen   ·   Mot de passe : $PASS"
echo "   (note-le ! il est aussi dans /opt/usine-video/.env)"
