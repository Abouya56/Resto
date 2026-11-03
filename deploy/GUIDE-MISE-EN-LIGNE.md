# Mettre Resto en ligne, gratuitement (Oracle Cloud)

Ce guide installe le site sur un petit serveur gratuit, toujours allumé, avec une adresse en https.
Il marche aussi sur n'importe quel autre serveur Linux plus tard, sans rien changer.

> Les fichiers de ce dossier n'ont pas encore été essayés sur un vrai serveur : le premier lancement servira de test.
> Les offres gratuites changent : vérifiez ce que propose Oracle au moment de vous inscrire.

## Ce qu'il faut avoir
- Une adresse e-mail et une carte bancaire (Oracle la demande seulement pour vérifier votre identité).
- 1 heure de temps pour la première installation.

## Étape 1 : une adresse gratuite
Créez un nom gratuit sur **duckdns.org** (exemple : `monresto.duckdns.org`). Gardez-le, vous le donnerez à l'étape 4.
Vous le relierez à l'adresse du serveur (étape 3).

## Étape 2 : le serveur gratuit
1. Créez un compte sur **oracle.com/cloud/free**.
2. Créez une machine (« Instance ») **Ubuntu**, de type « Always Free ». Si Oracle répond « out of capacity » (plus de place), réessayez plus tard : c'est courant.
3. Notez l'**adresse IP publique** de la machine et téléchargez la **clé de connexion** (fichier `.key`) : gardez-la précieusement.
4. Dans Oracle, ouvrez les ports **80** et **443** (réseau de la machine, « règles d'entrée »).
5. Sur duckdns.org, collez cette adresse IP en face de votre nom : `monresto.duckdns.org` pointe maintenant vers votre serveur.

## Étape 3 : installer Docker sur le serveur
Connectez-vous à la machine (`ssh -i votre-cle.key ubuntu@ADRESSE_IP`), puis :

```
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
```
Déconnectez-vous puis reconnectez-vous.

## Étape 4 : mettre le site sur le serveur
Copiez le dossier du projet sur le serveur (par exemple avec Git depuis un dépôt privé), puis :

```
cd resto
cp deploy/.env.production.example .env
nano .env
```
Dans `.env`, remplacez chaque `CHANGEZ` :
- l'adresse du site (`monresto.duckdns.org`) aux endroits indiqués ;
- `DJANGO_SECRET_KEY` : générez-en une avec `openssl rand -base64 48` ;
- `POSTGRES_PASSWORD` : un long mot de passe (la base n'est pas visible depuis Internet).

## Étape 5 : démarrer
```
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```
Au premier lancement, la préparation prend quelques minutes. Ensuite le site répond sur `https://monresto.duckdns.org`.

## Étape 6 : créer votre compte super admin
```
docker compose -f deploy/docker-compose.prod.yml --env-file .env exec web \
  python manage.py create_platform_admin --email vous@exemple.com --first-name Prénom --last-name Nom
```
Le mot de passe est demandé au clavier. Choisissez-en un solide, différent de celui de démonstration.
Le site démarre **vide** : aucun faux restaurant, aucune fausse commande.

## Étape 7 : les sauvegardes (indispensable)
```
chmod +x deploy/backup.sh
crontab -e
```
Ajoutez la ligne (une sauvegarde chaque nuit à 3 h) :
```
0 3 * * * /home/ubuntu/resto/deploy/backup.sh >> /home/ubuntu/resto/backups/sauvegarde.log 2>&1
```
Les sauvegardes sont dans le dossier `backups`. **Copiez-les régulièrement sur votre PC** : si le serveur disparaît, ses sauvegardes disparaissent avec lui.

## Mettre à jour le site plus tard
```
cd resto
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file .env up -d --build
```

## Les limites du gratuit
- Pas d'envoi d'e-mails (les reçus par e-mail ne partent pas).
- Un seul petit serveur : suffisant pour quelques restaurants, à agrandir si le site grandit.
- Les offres gratuites peuvent changer : gardez une sauvegarde à jour pour pouvoir déménager.
