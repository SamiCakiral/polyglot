# Polyglot V2 - API et contrats frontend

## 1. Contrat de transport

L'API publique applicative est REST JSON sous `/api/v1`. L'OpenAPI 3.1 générée
par le backend est l'artefact normatif de transport. Le frontend ne redéclare
pas manuellement les payloads serveur.

Le registre exhaustif `commande -> route -> permission -> précondition ->
événement -> erreurs` est défini dans le document 25. Les tableaux ci-dessous
sont une vue par surface et ne peuvent introduire une route divergente.

Tâches couvertes : `C05`, `C06`, `J03` et contrat de dégradation de `J06`.

- MIME JSON : `application/json`; erreurs : `application/problem+json`.
- Noms de champs : `snake_case` dans l'API et le journal d'événements.
- Dates : RFC 3339 UTC ; durées : millisecondes entières ou ISO 8601 lorsque le
  champ le précise.
- Identifiants : chaînes UUID opaques.
- `request_id`, `traceparent` et `correlation_id` assurent la corrélation.
- Une réponse ne contient pas de champ conditionnel non documenté.
- Les listes utilisent un curseur opaque, `limit <= 100`, `next_cursor` et
  `has_more`; jamais de pagination par offset sur les historiques mouvants.

## 2. Commandes, lectures et erreurs

Les lectures sont des `GET`. Une création est un `POST`. Une mutation ciblée est
un `PATCH` avec `If-Match`. Une action métier qui n'est pas un CRUD utilise une
action suffixée par `:`, par exemple `POST /session-plans/{id}:prepare`.

Toute commande rejouable accepte `Idempotency-Key`. Les réponses de ressource
portent `ETag: "<version>"`. Une mutation sans précondition lorsqu'elle est
requise retourne `428 precondition_required`.

Format d'erreur :

```json
{
  "type": "https://polyglot.example/problems/version-conflict",
  "title": "La ressource a changé",
  "status": 409,
  "code": "version_conflict",
  "detail": "Rechargez la ressource avant de réessayer.",
  "instance": "/api/v1/vocabulary/lists/019...",
  "request_id": "019...",
  "retryable": false,
  "errors": []
}
```

`detail` est affichable, localisé selon `Accept-Language` et ne révèle aucune
donnée sensible. `code` est stable et pilote l'état frontend. Les familles
obligatoires sont : `validation_failed`, `unauthenticated`, `forbidden`,
`not_found`, `version_conflict`, `idempotency_conflict`, `rate_limited`,
`dependency_unavailable`, `media_not_ready` et `internal_error`.

## 3. Surface de la version 1 de l'API

### 3.1 Identité et profils

| Méthode et route | Contrat |
|---|---|
| `GET /session` | utilisateur courant, rôles, consentements et langues accessibles |
| `DELETE /session` | ferme la session courante |
| `GET /language-profiles` | profils linguistiques du compte |
| `POST /language-profiles` | crée une paire langue maternelle/cible |
| `GET /language-profiles/{id}` | état, capacités et actions disponibles |
| `DELETE /language-profiles/{id}` | lance l'effacement borné de cette langue |
| `GET /consents` / `PUT /consents/{purpose}` | consentements versionnés par finalité |

### 3.2 Catalogue, contenu et atelier

| Méthode et route | Contrat |
|---|---|
| `GET /language-packs` | packs publiés et capacités certifiées |
| `GET /catalogue/targets` | objectifs, structures, prérequis et versions |
| `GET /content/{content_id}/revisions/{revision}` | révision immuable autorisée |
| `POST /authoring/drafts` | crée un brouillon typé |
| `PATCH /authoring/drafts/{id}` | modifie sous contrôle `If-Match` |
| `POST /authoring/drafts/{id}:validate` | lance ou exécute les validateurs |
| `POST /authoring/drafts/{id}:approve` | enregistre l'approbation humaine |
| `POST /authoring/drafts/{id}:publish` | publication atomique autorisée |
| `POST /content/{content_id}/revisions/{revision_id}:retire` | retire sans casser l'historique |

### 3.3 Word Bank et mémoire

| Méthode et route | Contrat |
|---|---|
| `GET /language-profiles/{id}/word-bank` | projection paginée, filtres et raisons d'état |
| `GET /language-profiles/{id}/word-bank/senses/{sense_id}` | facettes, rencontres autorisées, échéances et relations |
| `POST /language-profiles/{id}/encounters` | ingestion idempotente d'une rencontre |
| `GET/POST /language-profiles/{id}/vocabulary-lists` | listes personnelles ou dynamiques |
| `GET/PATCH/DELETE /vocabulary-lists/{id}` | mutation versionnée et archivage logique |
| `POST /vocabulary-lists/{id}/members:batch` | ajout/retrait atomique avec rapport par membre |
| `POST /vocabulary-lists/{id}:snapshot` | fige une vue historique |
| `GET /language-profiles/{id}/learning-needs` | dette ouverte et justification |

### 3.4 Curriculum, sprints et exercices

| Méthode et route | Contrat |
|---|---|
| `GET /language-profiles/{id}/module-enrollments` | modules accessibles et inscription courante |
| `POST /language-profiles/{id}/module-enrollments` | inscrit à une révision publiée |
| `POST /language-profiles/{id}/daily-plans` | compose le plan quotidien avec budget et clé d'idempotence |
| `GET /session-plans/{id}` | snapshot et état de préparation |
| `POST /session-plans/{id}:prepare` | résout puis fige les instances et médias |
| `POST /session-plans/{id}/runs` | démarre un sprint prêt |
| `GET /sprint-runs/{id}` | blocs, position et reprise |
| `POST /sprint-runs/{id}:interrupt` / `resume` / `stop` / `complete` | transitions explicites |
| `GET /exercise-instances/{id}` | stimulus prêt pour le lecteur |
| `POST /exercise-instances/{id}/attempts` | ouvre une tentative brouillon unique |
| `PATCH /attempts/{id}/draft` / `POST /attempts/{id}:submit` | sauvegarde puis soumission idempotente |
| `POST /attempts/{id}/correction-case` | contestation append-only |
| `POST /sprint-runs/{run_id}/blocks/{block_id}:skip` | saut du bloc avec raison |

### 3.5 Progression et évaluations

| Méthode et route | Contrat |
|---|---|
| `GET /language-profiles/{id}/progress` | projections explicables par compétence/modalité |
| `GET /language-profiles/{id}/recommendations` | cible, raison, preuve manquante et action |
| `GET /recommendations/{id}/explanation` | chaîne de preuves autorisée |
| `POST /language-profiles/{id}/assessments` | crée une session d'évaluation |
| `GET /assessments/{id}` | section courante, expiration et reprise |
| `PATCH /assessments/{id}/responses/{item_id}` | sauvegarde versionnée d'une réponse |
| `POST /assessments/{id}:submit` | fige les réponses pour notation |

### 3.6 Jobs, outils et médias

| Méthode et route | Contrat |
|---|---|
| `GET /jobs/{id}` | état, progression bornée, erreur publique et résultat autorisé |
| `GET /jobs/{id}/events` | SSE reprenable par `Last-Event-ID` |
| `POST /tools/{tool_name}:invoke` | atelier uniquement ; schéma et permission de l'outil |
| `POST /media/uploads` | réserve un upload et retourne une URL signée courte |
| `POST /media/uploads/{id}:complete` | vérifie empreinte, taille et type puis lance le scan |
| `GET /media/{id}` | métadonnées et URL de lecture signée si disponible |
| `DELETE /media/{id}` | suppression logique puis purge asynchrone |

L'invocation HTTP des outils n'est jamais accessible au rôle `learner`. Le
runner déterministe appelle directement le même registre d'outils en test.

## 4. Streaming et reprise

Le périmètre initial du temps réel se limite aux événements de jobs et à la
progression d'uploads.
Le protocole est SSE, pas WebSocket. Chaque événement contient :

```json
{
  "event_id": "019...",
  "job_id": "019...",
  "sequence": 12,
  "type": "validation.completed",
  "occurred_at": "2026-08-09T10:15:00Z",
  "progress": {"completed": 4, "total": 4},
  "data": {"report_id": "019..."}
}
```

La séquence est strictement croissante par job. Le serveur conserve un journal
reprenable au moins 24 heures après la fin. Le client se reconnecte avec
`Last-Event-ID`, puis bascule vers `GET /jobs/{id}` après trois échecs. Aucun
token ou texte privé ne passe dans le nom d'événement.

## 5. Contrat frontend

### 5.1 Organisation

```text
frontend/src/
  app/                 # router, providers, session, error boundary
  features/
    today/
    learn/
    practice/
    vocabulary/
    progress/
    assessments/
    authoring/
  components/          # composants partagés sans règle métier
  generated/           # client OpenAPI généré
  lib/                 # transport, formatage, télémétrie
```

Une feature ne lit pas l'état interne d'une autre. Les échanges passent par les
routes, le cache de requêtes typé ou un contrat public de composant.

### 5.2 Sources d'état

- État serveur : TanStack Query, indexé par identifiant et version.
- État de route : paramètres et recherche validés.
- État de formulaire : React Hook Form ; brouillon local explicitement nommé.
- État du lecteur : reducer/machine déterministe, sérialisable et testé.
- État visuel local : composant ; aucun store global pour recopier une ressource.

Le frontend ne calcule ni maîtrise, ni dette, ni prochaine activité. Il affiche
les projections et explications du backend. Les mutations optimistes sont
limitées aux préférences et gestes réversibles ; jamais aux tentatives,
publications, évaluations ou suppressions.

## 6. Lecteur d'exercice

États normatifs : `loading`, `ready`, `answering`, `submitting`, `corrected`,
`contested`, `skipped`, `unavailable`, `paused`, `resuming`, `completed`,
`recoverable_error` et `fatal_error`.

| État | Actions permises | Persistance |
|---|---|---|
| `ready` / `answering` | saisir, écouter, demander une aide, pause | brouillon local sans preuve |
| `submitting` | aucune seconde soumission ; annulation visuelle interdite | commande idempotente en vol |
| `corrected` | lire, contester, continuer | tentative et correction serveur |
| `skipped` | continuer, voir l'explication si autorisée | événement de saut distinct |
| `unavailable` | remplacer ou quitter | aucune preuve de réussite/échec |
| `resuming` | attendre le snapshot serveur | aucun calcul local de progression |
| `recoverable_error` | réessayer la même clé ou revenir | brouillon conservé |

La réponse est sauvegardée avant de passer au bloc suivant. Fermer le navigateur
après accusé de réception ne peut pas perdre la tentative. Le minuteur utilise le
temps serveur pour les évaluations et un temps actif distinct pour l'entraînement.

### 6.1 Contrat des adaptateurs de primitive

Chaque primitive implémente `renderStimulus`, `renderResponse`, `serializeDraft`,
`validateLocalShape`, `renderCorrection` et `focusFirstAction`. Elle reçoit une
instance immuable et émet seulement des intentions vers le shell.

| Famille | Réponse | États/a11y spécifiques |
|---|---|---|
| choix/discrimination | identifiant(s) d'option | groupe annoncé, sélection clavier, aucun résultat par couleur seule |
| texte/trou/dictée | texte brut et langue | label, direction d'écriture, accents accessibles, erreur non destructive |
| ordre/recomposition | suite d'identifiants | alternative clavier aux gestes de déplacement, annonce de position |
| transformation/conjugaison | champs structurés | consigne et cible persistantes, comparaison champ par champ |
| compréhension | réponses + segments cités | transcription selon règle, navigation structurée du support |
| audio/prononciation | référence média + auto-évaluation bornée | lecture clavier, transcript, vitesse, état sans audio |
| oral/production libre | artefact ou texte, consentement | enregistrement explicite, durée, suppression, correction incertaine |
| métacognition/réparation | choix d'aide, contestation ou explication | aucune aide comptée comme rappel autonome |

Le shell, et non l'adaptateur, possède soumission, idempotence, minuteur,
progression, reprise, erreurs et télémétrie. Une primitive non reconnue rend
`fatal_error` avec sortie sûre ; elle n'affiche jamais un formulaire générique.

### 6.2 Contrat de capacité TTS

`GET /media/tts/capabilities?language=<tag>` retourne la version du catalogue,
les voix, langues, formats, limites et disponibilité. La préférence utilisateur
référence un `voice_id` opaque et une version de catalogue.

- `available` : lecture et génération permises ;
- `temporarily_unavailable` : état visible et nouvel essai manuel seulement ;
- `retired` : préférence conservée mais voix non utilisée ;
- `unsupported` : parcours texte/transcription, sans appel fournisseur.

Une voix retirée ne bascule pas vers une autre. L'utilisateur choisit une voix
disponible ou continue sans audio. Les tests utilisent un catalogue et des
fichiers fixes ; aucun fournisseur n'est requis.

## 7. Gestion des contrats

1. Le pipeline exporte `contracts/openapi/v1.json` depuis l'application.
2. Un diff OpenAPI bloque toute rupture non annoncée.
3. Le client TypeScript est régénéré et son diff est versionné.
4. Les exemples OpenAPI sont exécutés comme tests de contrat.
5. Les réponses réelles sont validées contre le schéma en test et en preview.
6. Un ajout optionnel reste compatible dans `/v1`. Renommer, supprimer, changer
   le type ou durcir une contrainte exige `/v2` ou une période de coexistence.
7. Une version d'événement n'est pas la version de l'API ; les consommateurs
   acceptent la version courante et la précédente pendant la fenêtre publiée.

## 8. États globaux obligatoires

Chaque écran documente et teste : chargement, vide, contenu, permission refusée,
session expirée, réseau lent, hors ligne, erreur récupérable, erreur définitive
et contenu extrême. Le mode hors ligne initial est consultatif : les assets déjà
chargés peuvent rester visibles, mais aucune file de mutations locale n'est
inventée. La reprise se fait depuis l'état serveur.

Le frontend doit rester utilisable au clavier, à 200 % de zoom et avec une
largeur CSS de 320 px. Les composants audio possèdent transcription et état sans
audio ; une voix indisponible est affichée et ne déclenche aucun remplacement
silencieux.
