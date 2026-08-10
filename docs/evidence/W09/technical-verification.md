# W09 - Preuve technique

Date : 2026-08-10

## Statut

Le moteur d'exercices W09 est techniquement implémenté. Le gate pédagogique
`P-LING` reste `pending_human` et interdit de présenter W09 comme validé
linguistiquement.

## Livrables vérifiés

- domaine commun pour les 22 primitives core ;
- stratégies exactes, ensemble accepté, morphologie, contraintes, traduction
  bornée, grilles, auto-évaluation et comparaison avant/après ;
- migration PostgreSQL `0009_exercises`, RLS propriétaire/opérateur,
  réponses brutes immuables et corrections versionnées ;
- commandes transactionnelles d'ouverture, brouillon, aide, soumission,
  correction, lecture, contestation et revue ;
- rejeu exact par `Idempotency-Key`, version attendue et verrou concurrent ;
- événements/outbox et client TypeScript généré depuis OpenAPI ;
- fixture hors réseau `FX-PRIMITIVES`, seed figée, H0-H4, accessibilité,
  positif, négatif, ambigu et indisponible.

## Vérifications

- `41 passed` sur les tests unitaires, propriétés, intégration PostgreSQL et
  contrats W09 ;
- migration `0008_exchange -> 0009_exercises -> 0008_exchange -> 0009_exercises` ;
- Ruff : aucun constat ;
- mypy ciblé : aucun constat ;
- OpenAPI et registre de contrats : valides ;
- génération Orval, lint et typecheck frontend : valides ;
- Node local `24.14.0` utilisé avec avertissement, version épinglée attendue
  `22.18.0`.

## Limites ouvertes

- revue linguistique humaine italienne non réalisée ;
- actions `SkipExerciseBlock` et `AbandonExerciseBlock` branchées en W12,
  avec les vrais `SprintRun`, plutôt que sur une API orpheline ;
- le contrôle global des artefacts privés signale d'anciens rapports ignorés
  sous `.superpowers/sdd`; aucun de ces fichiers n'est suivi ou poussé.
