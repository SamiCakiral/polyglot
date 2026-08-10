# W05 - Rapport du sous-lot rejet éditorial

Date : 2026-08-10
Révision GREEN vérifiée : `8970f093110518c4f424f027f0b3eefb6219b75d`

## Verdict

**PASS technique.** Le blocage W00 est levé par `8f1c70c` et `ae0bfc7`.
Le sous-lot W05 implémente désormais le rejet éditorial de bout en bout sans
modifier W00 ni W04F. La revue finale indépendante en cours s'arrête à
`5d129fd` et devra donc auditer séparément les commits de ce sous-lot.

`P-LING` reste `pending_human`.

## Contrat et domaine

`ApproveContentRevision` porte une décision explicite et fermée
`approved|rejected`. La décision participe à l'empreinte d'idempotence. Toute
autre valeur produit une validation 422 structurée.

Le service exige un rôle reviewer, une révision `validated` et un reviewer
distinct de l'auteur. Une approbation produit `approved`; un rejet produit le
statut terminal `rejected`. La reprise impose `ReviseContentDraft`, qui crée une
nouvelle révision `draft` avec `supersedes_revision_id` ; la révision rejetée ne
peut pas être publiée.

## Transaction et PostgreSQL

La décision utilise le chemin W05 existant : `SqlCommandReceiptStore`, version
attendue, verrou d'agrégat, UoW, contexte SQL de commande et receipt terminal.
Dans la même transaction :

- une décision append-only unique par révision est insérée ;
- la révision passe de `validated` à `approved` ou `rejected` ;
- `content_approved` ou `content_rejected` est écrit ;
- exactement une outbox est associée à l'événement ;
- le receipt conserve le résultat rejouable.

Le trigger SQL interdit un rejet sans décision `rejected`, une décision du même
acteur et plusieurs décisions pour la même révision. Les contraintes W05
antérieures contre les mutations SQL hors commande restent actives.

## Idempotence et erreurs

- même clé et même rejet : résultat identique, sans seconde décision ni second
  événement ;
- même clé avec décision différente : `idempotency_conflict` ;
- publication d'une révision rejetée : `invalid_transition` ;
- auto-rejet : `self_approval_forbidden` ;
- décision hors enum : Problem Details 422 `validation_failed`.

## API, OpenAPI et fixture

`POST /api/v1/authoring/drafts/{draft_id}:approve` accepte désormais
`decision` et `reason_code`. Le schéma OpenAPI est fermé, requiert les deux
champs et publie l'enum exacte.

`FX-CONTENT` contient des décisions synthétiques `approved` et `rejected`, avec
auteur et reviewer distincts. Le parcours base vide couvre validation échouée,
correction, validation verte, rejet, nouvelle révision, approbation,
publication, remplacement, retrait et lecture historique.

## TDD et preuves

- RED : `66a8cf5` avec cinq familles d'échecs ciblés ;
- GREEN : `8970f09`.

Base isolée neuve : `polyglot_w05_rejection_final`, PostgreSQL 17 local.
Aucun DSN ni secret n'est versionné.

- W05 complet : `39 passed` ;
- migration base vide jusqu'à `0005_content` : PASS ;
- cycle `0005 -> 0004_language_profiles -> 0005` : PASS ;
- `alembic check` : aucune opération nouvelle ;
- Ruff `src tests` : PASS ;
- mypy `src` : PASS, 56 fichiers ;
- OpenAPI `--check` : PASS ;
- registre W00 : `contract registry valid` ;
- `git diff --check` : PASS.

Versions : Python 3.13.11, pytest 9.1.1.

## Restes

- étendre la revue finale indépendante aux commits `66a8cf5` et `8970f09` ;
- conserver la revue linguistique italienne comme validation humaine séparée.

Aucun push n'a été effectué.
