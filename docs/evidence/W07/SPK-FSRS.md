# SPK-FSRS - décision de fournisseur W07

- Date : 2026-08-10
- Python : 3.13.11
- Fournisseur : paquet officiel `fsrs==6.3.1`
- Politique : 21 paramètres par défaut 6.3.1, rétention `0.90`, fuzz activé
- Horloge : `2026-01-05T09:00:00Z`
- Seed de base : `4242`
- Réseau : utilisé uniquement pour résoudre la roue exacte ; exécutions rejouées hors réseau
- Hash SHA-256 `uv.lock` : `fc227db2f7afe96473da3107744394c2fbbb338a4b7b7774d1c2606edfbb38fe`
- Preuve brute : `spk-fsrs-raw.json`

## Histoires comparées

Le harness couvre un prompt neuf, deux directions indépendantes, la suite
`again/good/good/easy`, deux reviews le même jour, une review anticipée, une
review tardive, un reset par nouvelle carte, une fusion compatible par rejeu
trié et un changement de fuseau normalisé en UTC.

Les deux directions terminent avec les mêmes valeurs de calendrier mais des
identités distinctes. Le rejeu trié est stable. Une date naïve est refusée par
la bibliothèque. Le reset ne reprend ni difficulté, ni stabilité, ni historique.

Les cas temporels sont exécutés dans `test_spk_fsrs_temporal.py` et comparés à
des constantes du JSON brut :

| Cas | Review | Due golden | Stabilité golden |
|---|---|---|---|
| anticipée | `2026-01-06T09:10:00Z`, avant due initiale | `2026-01-12T09:10:00Z` | `7.319186097840142` |
| retardée | `2026-01-25T09:10:00Z`, après due initiale | `2026-02-25T09:10:00Z` | `32.80902069289039` |
| Europe/Rome | `2026-03-29T09:00:00+02:00` | normalisée `2026-03-29T07:10:00Z` | `2.3065` |

Le harness prouve aussi que le fournisseur refuse directement la date Rome ;
seule sa normalisation explicite en UTC est acceptée.

## Décision

`adopt`

La version 6.3.1 satisfait le contrat nécessaire sans formule FSRS locale. Elle
sera encapsulée derrière `MemorySchedulerPort`. Toute exception devient
`dependency_unavailable` sans transition ni fallback. Le hash du lockfile et la
preuve d'installation hors réseau sont consignés dans le rapport final W07.
