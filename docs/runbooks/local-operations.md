# Exploitation locale Polyglot V2

## États observables

`GET /api/v1/health/live` prouve que le processus répond. `GET
/api/v1/health/ready` vérifie PostgreSQL et le stockage objet. LM Studio et TTS
sont des capacités facultatives : leur panne ne rend pas l'apprentissage
indisponible et ne doit jamais être transformée en réussite.

Les journaux backend sont des objets JSON contenant uniquement l'heure, le
niveau, l'événement, les identifiants de requête/corrélation, la méthode, la
route, le statut et la durée. Ils n'enregistrent ni corps HTTP, ni cookie, ni
jeton, ni mot de passe, ni production d'apprenant.

## Diagnostic

1. Exécuter `./scripts/local-status.sh`.
2. Si la readiness échoue, lire `docker compose ps` puis les journaux du service
   en échec avec `docker compose logs --tail 200 SERVICE`.
3. Conserver `X-Request-ID` et `X-Correlation-ID` affichés par l'API pour relier
   la requête aux journaux.
4. Ne jamais coller `.local/runtime.env` dans un ticket ou un rapport.

## Pannes connues

| Signal | État attendu | Action locale |
|---|---|---|
| PostgreSQL indisponible | readiness `503` | arrêter les écritures, vérifier le volume, restaurer seulement selon le runbook |
| Stockage objet absent | readiness `503` | vérifier le volume monté et ses permissions |
| LM Studio indisponible | job auteur `failed/provider_unavailable` | démarrer le modèle exact puis créer un nouveau job manuellement |
| TTS Alice indisponible | audio marqué indisponible | poursuivre sans audio ; ne pas substituer une autre voix |
| Job de génération bloqué | état visible, aucun retry | inspecter le job et annuler si encore annulable |
| Projection retardée | données sources conservées | relancer le dispatcher puis reconstruire la projection |

## Arrêt et reprise

`./scripts/local-down.sh` arrête les services sans supprimer les volumes. Ne pas
utiliser `docker compose down -v` hors environnement jetable. Après reprise,
vérifier la readiness, une session interrompue et les tâches en attente avant de
continuer.

## Sauvegarde

La procédure et ses garde-fous sont dans `local-backup-restore.md`. Une
restauration est toujours réalisée vers une base et un dossier objet vides et
isolés. Un rapport autre que `PASS` bloque la release locale.
