# W07-T02 - Rerevue indépendante après correction

## Révision relue

- Checkout exact : `54532b34b0fcf9997607b1c61e95490a9f897764`.
- Inspection commit par commit des six commits W07-T02 uniquement.
- Aucun range ancestral et aucun fichier W11 inspecté comme changement W07.
- Revue read-only ; aucun fichier modifié.

## Findings

1. `P1` : le rebuild vérifie une transition persistée depuis son propre
   `state_before`, mais ne prouve pas que cet état est celui obtenu au checkpoint
   causal précédent. Une transition isolément valide mais déconnectée peut être
   acceptée.
2. `P1` : une chaîne source de fusion utilise `earliest_at=None`; un fait source
   antérieur à la création de son prompt peut donc être rejoué.
3. `P2` : aucune propriété adversariale ne génère ces deux corruptions.

## Vérifications

- Pytest T02 : `43 passed`.
- mypy strict : passé sur 8 fichiers source.
- Ruff : échec sur l'ordre des imports du test unitaire, correction mécanique
  non encore incluse dans le commit relu.
- Certification épinglée, résolveur fail-closed, faits resume/restore,
  checkpoints, conservation des faits et déduplication : présents.
- Aucun fallback FSRS ou calcul de maîtrise pédagogique relevé.

## Verdict

`FAIL` technique. W07-T03 reste bloqué.
