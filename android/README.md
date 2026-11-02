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
  serveur (`POST /api/relay/messages`, jeton par téléphone). Hors connexion,
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
   téléphone**, avec le nom exact du groupe.
2. Installer l'APK sur le téléphone :
   - par câble : `adb install android/dist/emb-relais-1.0.0.apk`
   - ou copier le fichier sur le téléphone et l'ouvrir (autoriser
     « Installer des applis inconnues » pour le gestionnaire de fichiers).
3. Sur le téléphone, ouvrir la page du site et toucher **Associer
   l'application** : l'app s'ouvre, enregistre le serveur, le jeton et le
   groupe, et teste la connexion.
4. Dans l'app : **Autoriser l'accès aux notifications** (activer « EMB
   Relais »), puis **Ignorer l'optimisation de batterie** (sinon certains
   téléphones — Xiaomi, Samsung, Huawei — coupent l'app en arrière-plan).
5. Vérifier : quand une ferme écrit, la ligne « Dernière discussion WhatsApp
   vue » affiche le groupe « (suivie) » et le message apparaît dans
   « Derniers messages » puis sur le site.

Si « non suivie » s'affiche pour le groupe des producteurs : corriger le nom
dans **Configuration** (un groupe par ligne, tel qu'affiché par WhatsApp).

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
| `Api.kt` | appels HTTPS au serveur |
| `MainActivity.kt` | état, association par lien `embrelais://pair?…`, configuration |
