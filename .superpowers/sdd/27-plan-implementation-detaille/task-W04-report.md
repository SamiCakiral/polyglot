# W04 - Rapport final

## Resultat

**ACCEPTE techniquement.** Le catalogue revisionne, son graphe de competences,
les lectures publiques et la fixture italienne hors reseau sont implementes.
La revue linguistique humaine reste explicitement `pending_human` et aucun
statut `P-LING` n'est revendique.

## Increments livres

- `W04-T01` : domaine revisionne, transitions et DAG `required` deterministe.
- `W04-T02` : migration `0003_catalogue`, contraintes PostgreSQL et droits en
  lecture seule pour le runtime.
- `W04-T03` : lectures paginees packs, cibles et lexique via `/api/v1`.
- `W04-T04` : fixture canonique italienne, empreinte, oracles et cas negatifs
  sans dependance reseau.

## Durcissements issus des revues

- immutabilite PostgreSQL des revisions publiees et de tous leurs enfants,
  y compris les reparentages controles sur `OLD` et `NEW` ;
- serialisation des mutations concurrentes du DAG et traversee bornee ;
- coherence forme, analyse, sens, unite, MWE, pack et variete ;
- curseur et `LIMIT` appliques dans la requete SQL lexicale ;
- fermeture des references, statuts et identifiants des fixtures ;
- validation des stable codes alignee entre domaine et PostgreSQL.

## Preuves

- suite W04 finale : `40 passed`, un avertissement Starlette/httpx existant ;
- suite backend integree sur clone exact : `212 passed` en `19.90s` ;
- Ruff et mypy : passes ;
- Alembic : round-trip `0003 -> 0002 -> 0003`, `check` sans operation et
  `0003_catalogue (head)` ;
- rerevue independante finale : `PASS`.

## Limite editoriale

Le corpus pilote italien reste une fixture technique synthetique. Sa qualite
linguistique devra etre approuvee separement avant toute publication de contenu
pedagogique destine a un utilisateur reel.
