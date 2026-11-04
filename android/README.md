# EMB Relais — application Android

Transmet au site Etic'Monts les messages du groupe WhatsApp des producteurs,
pour que les listes de chaque ferme arrivent toutes seules dans
**WhatsApp → Listes reçues** (module `whatsapp`).

## Principe

- L'application tourne sur un téléphone Android **membre du groupe**
  (celui du coordinateur, ou un téléphone dédié).
- Elle a l'**accès aux notifications** (permission Android standard) et lit
  les notifications WhatsApp que le téléphone reçoit déjà. WhatsApp n'est pas
  modifié, aucun compte n'est automatisé : pas de risque de bannissement.
- Seuls les messages des **groupes listés** dans l'application quittent le
  téléphone. Les autres notifications sont ignorées et jamais enregistrées.
- Les messages sont mis en file sur le téléphone puis envoyés en HTTPS au
  serveur (`POST /api/relay/messages`, signés par une clé matérielle propre au
  téléphone — voir *Sécurité*). Hors connexion,
  ils partent automatiquement au retour du réseau.

### Limites (inhérentes aux notifications)

- Le groupe **ne doit pas être en sourdine** sur ce téléphone.
- Un message reçu pendant que la discussion est **ouverte à l'écran** n'est
  pas notifié par WhatsApp, donc pas transmis : laisser le téléphone en veille
  ou sur une autre application.
- Texte uniquement (photos, vocaux : seul leur libellé « 📷 Photo » passe).
- Les messages déjà lus avant l'installation ne sont pas récupérés.

## Installation (une fois)

1. Sur le site (compte admin) : **WhatsApp → Téléphone relais → Nouveau
   téléphone** (le nom du groupe est facultatif).
2. Installer l'APK sur le téléphone :
   - par câble : `adb install android/dist/emb-relais-1.2.0.apk`
   - ou copier le fichier sur le téléphone et l'ouvrir. Si **Google Play
     Protect** bloque (app hors Play Store demandant l'accès aux
     notifications) : *Plus de détails → Installer quand même*, ou couper
     temporairement l'analyse Play Protect le temps de l'installation. L'accès
     aux notifications sera ensuite « paramètre restreint » : *Paramètres →
     Applications → EMB Relais → ⋮ → Autoriser les paramètres restreints*.
3. Sur le téléphone, ouvrir la page du site et toucher **Associer
   l'application** (dans les 24 h) : l'app s'ouvre, crée sa clé de sécurité,
   s'enregistre auprès du serveur avec le code à usage unique et retient le
   groupe (« Associée à … — clé : puce sécurisée » confirme le tout).
4. Dans l'app : **Autoriser l'accès aux notifications** (activer « EMB
   Relais »), puis **Ignorer l'optimisation de batterie** (sinon certains
   téléphones — Xiaomi, Samsung, Huawei — coupent l'app en arrière-plan).
5. **Choisir les groupes** : dès qu'un groupe reçoit un message, il apparaît
   dans la carte **Discussions de groupe vues** de l'app, avec son nom exact.
   Toucher **Suivre** pour chaque groupe à transmettre. Les messages arrivent
   alors dans « Derniers messages » puis sur le site.

**Communauté WhatsApp** : chaque groupe d'une communauté a son propre nom
dans les notifications ; le nom de la communauté ne désigne que son groupe
d'annonces. Suivre donc chacun des groupes voulus (carte « Discussions de
groupe vues », ou un nom par ligne dans **Configuration**). Les messages
reçus avant de suivre un groupe ne sont pas transmis (l'app n'en garde pas le
contenu).

## Sécurité

**Seul le téléphone associé peut envoyer des messages.**

1. **Association** : la page *Téléphone relais* donne un code **à usage
   unique, valable 24 h**. L'app crée alors une paire de clés EC P-256 **dans
   la puce de sécurité du téléphone** (Android Keystore : StrongBox ou TEE) et
   n'envoie au serveur que la **clé publique**. Le code est aussitôt brûlé.
2. **Chaque requête est signée** par cette clé (ECDSA-SHA256 sur méthode,
   chemin, horodatage, nonce et empreinte SHA-256 du corps). Le serveur
   refuse : signature absente ou fausse, corps modifié, horodatage décalé de
   plus de 5 min, nonce déjà vu (rejeu), téléphone révoqué.
3. La clé privée **ne sort jamais de la puce** — même l'app ne peut pas la
   lire. Copier les données de l'app, intercepter une requête ou voler le
   code après usage ne permet pas d'envoyer des messages.
4. Le serveur ne stocke que des **clés publiques** et l'empreinte des codes :
   une fuite de la base ne permet pas de se faire passer pour le téléphone.
5. Réinstallation / nouveau téléphone : **Nouveau lien** sur le site (l'ancienne
   clé cesse immédiatement de fonctionner). Perte / vol : **Révoquer**.

**Anti-abus** (personne ne peut saturer le serveur par cette porte) :

| Couche | Limite |
|---|---|
| nginx (par IP) | 30 req/min sur `/api/relay/` (rafale 20), 10 connexions, corps ≤ 512 Ko, 10 s pour l'envoyer → `429`/`413` avant Flask |
| application, avant toute requête SQL | en-têtes de signature mal formés, horodatage hors délai, corps > 512 Ko ou sans `Content-Length` |
| par téléphone | `RELAY_RATE_PER_MIN` (30) requêtes/min, `RELAY_DAILY_CAP` (3 000) messages/24 h, ≤ 200 messages par envoi |

Limites connues : le niveau de la clé (StrongBox/TEE) est déclaré par le
téléphone, pas prouvé par attestation ; sur un téléphone *rooté*, un logiciel
malveillant pourrait faire signer des requêtes par l'app (sans pouvoir
extraire la clé). Révoquer le téléphone coupe tout accès.

## Développement

```bash
scripts/build-android.sh        # APK signé → android/dist/emb-relais-<version>.apk
cd android && ./gradlew :app:testDebugUnitTest :app:assembleDebug
```

- JDK 17 + Android SDK (`ANDROID_HOME`, défaut `~/Android/Sdk`).
- Clé de signature : `~/.android/emb-relais.jks` (créée au premier build,
  **hors dépôt, à sauvegarder**). Une mise à jour signée avec une autre clé
  ne s'installe pas par-dessus : il faudrait désinstaller et réassocier.
- Nouvelle version : augmenter `versionCode` et `versionName` dans
  `app/build.gradle.kts`.
- La version *debug* (`eu.boblabs.emb.relais.debug`) accepte le HTTP clair
  et a un bouton « Simuler un message WhatsApp » pour tester sur émulateur
  (le serveur local est joignable en `http://10.0.2.2:<port>`).

| Fichier | Rôle |
|---|---|
| `NotificationParser.kt` | lecture d'une notification (MessagingStyle et anciens formats), filtre de groupes — testé sans Android |
| `WhatsAppListener.kt` | `NotificationListenerService` : filtre, met en file |
| `Store.kt` | file SQLite locale (dédoublonnage par la même clé que le serveur) |
| `UploadWorker.kt` | envoi par WorkManager, reprise automatique |
| `Api.kt` | appels HTTPS au serveur (association, requêtes signées, correction d'horloge) |
| `DeviceKey.kt` | clé EC P-256 dans l'Android Keystore (StrongBox/TEE), signature |
| `RequestSigner.kt` | chaîne signée — identique au serveur (`eticmonts/relay_auth.py`), testée |
| `MainActivity.kt` | état, association par lien `embrelais://pair?…`, configuration |
