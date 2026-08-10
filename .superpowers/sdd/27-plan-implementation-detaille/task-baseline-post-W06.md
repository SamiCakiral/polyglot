# Baseline apres W06 et W11 phase A

Date : 2026-08-10  
Revision : `cd7e0f0`

## Collecte globale

- Environnement : Python 3.13.11, copie locale sous `/tmp`.
- Resultat : `613 tests collected in 1.31s`.
- Aucune collision de module ni erreur d'import.

## Matrice sans PostgreSQL

- Perimetre : `tests/unit`, `tests/property`, `tests/contract`.
- Exclusions explicites : contrats identity et commandes language profiles qui
  exigent les trois URL PostgreSQL de workload.
- Resultat final : `385 passed, 1 warning in 8.80s`.
- Warning connu : deprecation Starlette `httpx` vers `httpx2`.

## Defaut detecte et ferme

Le test catalogue figeait l'ancien cardinal `17` alors que la fixture publie
desormais 39 revisions. `cd7e0f0` remplace ce cardinal obsolete par la propriete
reelle : chaque revision presente doit avoir un checksum unique. Le test cible
et Ruff passent.

Les 24 contrats PostgreSQL non executes dans cette matrice ne sont pas annonces
comme verts. Ils restent couverts par les matrices PostgreSQL non privilegiees
des increments correspondants.
