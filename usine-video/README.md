# Usine à vidéos 🎬

Ton générateur de vidéos TikTok verticales (1080×1920) : tu écris les scènes, tu ajoutes des images, et l'appli sort une vidéo avec **voix off française**, **sous-titres animés**, **musique**, **effets** (zoom, flash, lignes de vitesse) et **barre de progression**.

- 2 styles : **Actu photo** (vraies photos, comme les vidéos lycéens/essence) et **Manga motion** (lignes de vitesse, trames, kanji, comme le Top 7 mangas)
- Recherche intégrée de **photos libres de droits** (Wikimedia Commons)
- Bouton **« Coller un script »** : une ligne = une scène
- Estimation de durée + alerte si la vidéo fait moins d'1 min (monétisation)
- Historique : retélécharge ou modifie une ancienne vidéo
- 100 % gratuit à l'usage : rien n'est envoyé à une API payante

---

## Installation sur ton serveur Hetzner (une seule fois)

### 1. Se connecter au serveur
```bash
ssh root@IP_DE_TON_SERVEUR
```

### 2. Installer Docker (si ce n'est pas déjà fait)
```bash
curl -fsSL https://get.docker.com | sh
```

### 3. Envoyer le dossier sur le serveur
Depuis ton PC (PowerShell), dans le dossier où est `usine-video.zip` :
```bash
scp usine-video.zip root@IP_DE_TON_SERVEUR:/root/
```
Puis sur le serveur :
```bash
apt install -y unzip && cd /root && unzip usine-video.zip && cd usine-video
```

### 4. Choisir ton mot de passe et lancer
```bash
echo "APP_PASSWORD=ChoisisUnMotDePasse" > .env
docker compose up -d --build
```
Le premier lancement prend ~5 min (téléchargement de la voix, ~350 Mo).

### 5. Ouvrir l'appli
Dans ton navigateur (PC ou téléphone) : **http://IP_DE_TON_SERVEUR:8000**
Identifiant : `hassen` · mot de passe : celui du `.env`.

---

## Utilisation rapide
1. Clique **Modèle Actu** ou **Modèle Top 7** pour partir d'un exemple.
2. Pour chaque scène : titre à l'écran (mets un mot entre `*étoiles*` pour le colorer), sous-titre, image.
3. Champ **Voix** : écris les chiffres en lettres pour une prononciation parfaite (« deux euros trente-six »).
4. **Générer la vidéo** → barre de progression → lecteur + bouton Télécharger.

Temps de rendu : environ 3 à 6 min pour une vidéo d'1 min (selon ton serveur).

## Commandes utiles
```bash
docker compose logs -f          # voir ce qui se passe
docker compose restart          # redémarrer
docker compose up -d --build    # après une mise à jour du code
```
Les vidéos et images sont gardées dans `usine-video/data/`.

## Bon à savoir
- Images : utilise tes propres images ou des photos libres de droits (le bouton 🔎 ne montre que des licences CC BY / BY-SA / domaine public). **Crédite les auteurs** dans « Sources » et dans ta description TikTok.
- Évite les couvertures/extraits de mangas, films, séries : TikTok coupe ou bloque souvent ces vidéos.
- Pour un accès en HTTPS avec un nom de domaine, on pourra ajouter Caddy plus tard.
