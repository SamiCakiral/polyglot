# W06 - Rapport d'implementation

## Verdict

`PARTIAL` - implementation fonctionnelle et tests W06 cibles verts, mais le lot
ne peut pas etre accepte tant que le snapshot OpenAPI n'est pas regenere et que
les budgets PostgreSQL 100k n'ont pas ete mesures. `P-LING` reste
`pending_human`.

## Cycles TDD

| Increment | RED | GREEN |
|---|---|---|
| W06-T01 identite | `ab4870d` | `0bcf038` |
| W06-T02 persistance | `7f96a20`, `8fef088` | `af7e2d3` |
| W06-T03 ingestion | `062bf38`, `11c68f0`, `7513fc7` | `bdd5a98` |
| W06-T04 Word Bank | `ff399f9` | `3b58802` |

Corrections de cloture : `83d4729`, `ce4a686`, `a76a45a`.

## Preuves obtenues

- PostgreSQL 17.10 jetable sur `127.0.0.1:55440`.
- Migration reelle `0005 -> 0006 -> 0005 -> 0006` : passee.
- Matrice W06 executee depuis le clone `/tmp/polyglot-w06-head` :
  `26 passed in 1.57s`.
- Ruff cible avant les dernieres corrections : passe.
- Fixtures `FX-LEXICON` et `FX-WB` : `2 passed`; empreintes SHA-256
  validees et aucune dependance reseau.
- Tests PostgreSQL explicites : append-only, RLS forcee, IDOR deux
  utilisateurs, idempotence, conflit de payload, suppression du contexte prive.
- Pagination keyset et voisinage limites a deux sauts et 500 noeuds.
- Aucun objet de maitrise, dette, carte, prompt memoire ou liste n'est cree par
  la migration W06.

## Contrats livres

- Identites separees pour unite, forme, sens, mention, candidat et resolution.
- Homonymie, polysemie, syncretisme, formes flechies et expressions multi-mots.
- Rencontres et interpretations append-only; correction tardive sans mutation
  du fait brut.
- Suppression du contexte prive avec conservation de l'empreinte et de la
  provenance minimale.
- Treize commandes W06 montees sous `/api/v1` avec authentification,
  `Idempotency-Key`, et `If-Match`/`428` pour preferences et annotations.
- Lectures Word Bank, detail de sens, annotations et recherche partagee.
- Couverture uniquement possible sur un referentiel borne et versionne; aucun
  pourcentage absolu de langue.

## Limites et preuves manquantes

1. `contracts/openapi/v1.json` est stale. Le dernier controle a retourne :
   `OpenAPI is not current` apres alignement des noms de parametres du registre.
2. Le mypy strict final n'a pas ete relance apres les quatre corrections
   statiques issues de son dernier diagnostic. Le diagnostic precedent avait
   identifie quatre erreurs, toutes corrigees dans `ce4a686`.
3. Aucune valeur honnete de recherche p95 ou voisinage p95 sur 100 000 sens
   n'a ete produite. La preparation a ete interrompue avant execution SQL; aucun
   budget de performance n'est revendique.
4. Les donnees italiennes synthetiques n'ont pas ete validees par un linguiste :
   `P-LING = pending_human`.
5. Aucune matrice globale n'a ete lancee, conformement a la consigne de cloture.

## Conditions d'acceptation restantes

- Regenerer puis verifier `contracts/openapi/v1.json`.
- Relancer Ruff et mypy strict sur le write set W06 depuis `/tmp`.
- Charger reellement les 100 000 sens de `FX-WB`, publier les plans SQL et les
  p95 recherche/voisinage sans extrapolation.
- Faire realiser la revue independante W06 et conserver `P-LING` en attente
  tant qu'aucun linguiste n'a signe les donnees.
