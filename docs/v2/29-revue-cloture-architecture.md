# Polyglot V2 - Revue de clôture de l'architecture

## 1. Conclusion exacte

L'architecture V2 est fermée au statut `specified` : zéro décision documentaire
P0 reste ouverte, chaque capacité V1 est inventoriée et orientée, les contrats
métier ont un propriétaire, et W00-W19 disposent de dépendances, write sets,
migrations, fixtures, preuves et incréments red/green. Cette conclusion ne vaut
ni implémentation, ni validation linguistique, ni preuve de release.

Baseline V1 auditée : commit
`1eaaf086b6c88e77281625837c043aa4c5abe165`. La baseline d'architecture est le
commit Git qui introduit le dossier `docs/v2`; toute évolution ultérieure exige
une modification versionnée des contrats propriétaires et de leurs dépendants.

## 2. Périmètre fermé

- vision, frontières produit, glossaire, NFR et décisions ;
- inventaire des 119 routes, modèles, contenus, tests et écrans V1 ;
- modèle multilingue générique, fondations et pilote italien de trois jours ;
- Word Bank personnelle exhaustive par rencontre/sens et listes associables ;
- mémoire FSRS, cartes existantes remodelées, dette et rappel différé ;
- primitives d'exercices, Gym grammaticale, correction hors LLM et shadowing ;
- sprint 10-60 minutes, thème, vocabulaire, version, inversion J+1 et pratique libre ;
- progression distincte en lecture, écoute, écriture et oral, sans score global ;
- quatre évaluations, formes parallèles, reprise et revue humaine ;
- dictionnaire de données, ownership, états, commandes, API, outils et sécurité ;
- UX desktop/mobile, lecteur universel, Atelier, exploitation et release ;
- plan W00-W19 et registre d'incréments testables.

## 3. Revues contradictoires

Trois relectures indépendantes ont été rejouées après correction :

| Axe | Défauts initiaux principaux | Résolution | Revue finale |
|---|---|---|---|
| cohérence normative | autorité, enums, états MemoryPrompt/Attempt, double pondération, defaults | documents 06/09/10/12/24/25/26 alignés | `RESOLVED` |
| complétude produit | correction hors IA, quatre modalités, sélection d'évaluation, J+1, lacune lexicale, libre, fondations, gestes WB, outils | contrats ajoutés dans 07/10-15/25/26/30 | `RESOLVED` |
| exécutabilité | ordre migrations, FKs avales, ownership, spikes, artefacts générés, Gym, API, granularité | plan 27 corrigé et incréments 31 ajoutés | `RESOLVED` |

Les dernières divergences sur l'autorité des transitions, le partage de listes et
la séparation pilote/catalogue italien exhaustif ont elles aussi été rejouées et
retournent `RESOLVED`.

## 4. Vérifications mécaniques du dossier

Exécutées le 2026-08-09 sur le workspace local :

| Contrôle | Résultat |
|---|---|
| liens Markdown locaux | 0 cible manquante |
| blocs de code | 0 clôture déséquilibrée |
| tables Markdown hors wireframes | 0 erreur de forme |
| commandes/routes publiques du registre 25 | 95 commandes, 0 doublon de nom ou route |
| diagrammes Mermaid | 40 extraits, 40 rendus, 0 échec |
| captures V1 | 24 fichiers, 24 PNG valides |
| whitespace Git | `git diff --check` sans erreur |
| non-régression V1 disponible | 11 tests `unittest`, 11 réussites |

Les tests V1 émettent encore des avertissements de dépréciation SQLAlchemy,
`datetime.utcnow()` et de connexions SQLite non fermées. Ils ne bloquent pas la
spécification V2 et ne sont pas présentés comme preuve G1-G7.

## 5. Restes volontairement hors clôture

| Travail | Statut | Gate concernée |
|---|---|---|
| D02X-D04X : catalogue italien exhaustif au-delà du pilote | éditorial non produit | `GATE-IT-FULL` |
| D05 : tri détaillé des contenus italiens V1 | audit éditorial non exécuté | réutilisation de contenu uniquement |
| L03A : huit spikes adopter/rejeter | preuve d'implémentation non exécutée | lot de production concerné |
| schémas, migrations, fixtures, backend, frontend et runner | `not_implemented` | G1-G6 |
| revues linguistique, pédagogique, a11y et visuelle | `not_verified` | G4-G5 |
| restauration, charge, staging, canary et rollback | `not_verified` | G3/G7 |

Ces éléments ne sont pas des trous d'architecture. Leurs contrats, owners,
entrées, sorties et critères de preuve sont définis ; leurs artefacts réels
doivent être produits pendant l'exécution.

## 6. Décision de passage

Le dossier est candidat à l'approbation `GATE-G0 Spec-ready`. Après approbation
produit, le premier travail autorisé est W00 : créer le dépôt V2, encoder les
registres machine-readable et exécuter le validateur sans dépendance. Aucun lot
W01+ ne démarre avant le commit de baseline W00 et les ADR approuvées.
