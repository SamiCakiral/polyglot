# Polyglot V2 - Traçabilité des exigences et preuves

## 1. Modèle de traçabilité

Ce document ferme `A01`, `A06`, `L01` et `L02` au niveau architecture. Il relie
les capacités unitaires de la matrice 05 aux lots et preuves sans dénormaliser
les mêmes informations dans chaque ligne.

```text
CapabilityId
  -> destination_family
  -> owner_module
  -> normative_contracts
  -> implementation_workstream
  -> canonical_fixtures
  -> required_proofs
  -> approver
  -> delivery_status
```

La matrice 05 possède une ligne et un ID par capacité historique. Les nouvelles
exigences portent un ID `REQ-*` dans leur document propriétaire. Toute PR cite
au moins un ID. Une capacité est livrée seulement lorsque sa décision, son
contrat, son test et sa preuve non automatisable éventuelle sont liés.

États distincts : `specified`, `planned`, `implemented`, `verified`, `accepted`,
`released`. Un document terminé ne signifie ni implémenté ni validé en usage.

## 2. Registre des familles de destination

| Famille | Module owner | Contrats | Lot | Dépendances | Fixtures | Preuves | Approbateur |
|---|---|---|---|---|---|---|---|
| identité/session | `identity` | 06, 08, 09, 16, 17 | `W02` | `W00-W01` | `FX-USERS`, `FX-AUTH` | unité, intégration, authz, E2E | sécurité + produit |
| profil/diagnostic/fondations | `language_profiles` | 08-10, 13, 21 | `W03` | `W02`, `W04` | `FX-PERSONAS`, `FX-IT-FOUND` | propriétés, parcours, revue pédagogique | pédagogie + produit |
| catalogue/pack/compétences | `catalogue` | 06, 08, 10, 13, 22 | `W04` | `W01` | `FX-CATALOGUE-IT` | schéma, DAG, linguistique | architecte + linguiste |
| contenu/publication | `content` | 08, 09, 15-17, 22 | `W05` | `W04` | `FX-CONTENT` | états, séparation rôles, historique | reviewer éditorial |
| Word Bank/catalogue lexical | `lexicon` | 03, 07-10, 16, 20, 22 | `W06` | `W03-W04` | `FX-LEXICON`, `FX-WB` | propriétés, Postgres, isolation, charge | architecture données + produit |
| cartes/mémoire/FSRS | `lexicon.memory` | 07-10, 22 | `W07` | `W06` | `FX-MEMORY` | propriétés calendrier, rejeu, reset | pédagogie + données |
| imports/exports/listes | `lexicon.exchange` | 07, 09, 16-17, 22 | `W08` | `W06-W07` | `FX-IMPORTS` | contrat, hostile, conflits, rollback | sécurité + produit |
| exercices/correction/aides | `exercises` | 02, 08-10, 12, 16, 20 | `W09` | `W04-W05` | `FX-PRIMITIVES` | contrats, propriétés, a11y, pédagogie | moteur + pédagogie |
| boîte grammaticale/Gym | `catalogue` + `exercises` | 02, 10, 12-13 | `W10` | `W04`, `W09` | `FX-GYM-IT` | cycles J0/J+1, linguistique | linguiste italien |
| curriculum/modules | `curriculum` | 08-11, 13, 22 | `W11` | `W04-W06`, `W09` | `FX-MODULE-IT` | déterminisme, contraintes | pédagogie + produit |
| sprint/entraînement libre | `sprints` | 08-13, 16, 20-21 | `W12` | `W07`, `W09-W11` | `FX-SPRINTS` | propriétés budget, reprise, E2E | produit + pédagogie |
| progression/dette/recommandations | `progress` | 03, 07-12, 14 | `W13` | `W06-W12` | `FX-EVIDENCE` | golden calcul, ordre, explication | pédagogie + data |
| évaluations | `assessments` | 08-10, 12, 14, 21 | `W14` | `W09`, `W13` | `FX-ASSESS` | modalité, minuteur, reprise, revue | pédagogie + produit |
| médias/TTS/STT/shadowing | `media` | 12-13, 16-18 | `W15` | `W02`, `W05` | `FX-MEDIA` | hostile, droits, absence, contrat | sécurité + accessibilité |
| génération/outils/LLM | `generation` | 02, 08-09, 15-17, 22 | `W16` | `W04-W05`, `W09-W12` | `FX-TOOLS` | runner hors réseau, schéma, quotas | architecture + reviewer |
| frontend apprenant | `frontend/features` | 16, 20-21 | `W17` | contrats des domaines | `FX-UI` | composant, E2E, a11y, visuel | produit + design |
| Atelier auteur | `frontend/authoring` | 16-17, 20, 22 | `W18` | `W05`, `W16-W17` | `FX-AUTHORING` | rôles, diff, publication, E2E | éditorial + sécurité |
| plateforme/ops | `platform` + `infra` | 06, 15, 17-19 | `W01`, `W19` | `W00` | `FX-OPS` | restauration, charge, canary, rollback | architecture + exploitation |

Une destination composée utilise la famille la plus spécifique. Par exemple
« Listes/Partage » relève de `imports/exports/listes`; « Gym/Transfert » relève
de `boîte grammaticale/Gym`. Une ambiguïté est arbitrée dans cette table avant
implémentation, pas dans une PR.

## 3. Exigences transversales nouvelles

| ID | Exigence | Propriétaire | Contrat | Preuve bloquante |
|---|---|---|---|---|
| `REQ-DET-001` | tout parcours coeur fonctionne sans fournisseur | architecture | 06, 15, 19 | runner + E2E hors réseau |
| `REQ-DET-002` | même snapshot/politique/graine donne le même plan | `sprints` | 11 | test de propriété/rejeu |
| `REQ-EVD-001` | une réussite isolée ne produit pas `reliable` | `progress` | 10 | golden evidence |
| `REQ-EVD-002` | aucune modalité non mesurée n'est créditée | `progress` | 10, 12, 14 | matrice inter-modalités |
| `REQ-WB-001` | toute rencontre ciblée garde sa provenance | `lexicon` | 07 | intégration et export |
| `REQ-WB-002` | aucune couverture sans référentiel borné | `lexicon` | 06, 07 | contrat API/UI |
| `REQ-SPR-001` | le sprint respecte 10-60 min par pas de 5 | `sprints` | 06, 11 | propriété sur tous budgets |
| `REQ-SPR-002` | J+1 prioritaire et jour manqué sans avance | `sprints` | 11 | horloge simulée |
| `REQ-EX-001` | panne/ambiguïté n'est jamais une réussite | `exercises` | 09, 12 | erreurs et correcteurs |
| `REQ-EX-002` | adaptations a11y ne réduisent pas la preuve | `exercises` | 12 | contrats et revue a11y |
| `REQ-CNT-001` | publication humaine séparée de génération | `content` | 09, 17, 22 | authz E2E |
| `REQ-DAT-001` | réponses/faits bruts append-only | plateforme | 08-09, 15 | intégration/reprojection |
| `REQ-SEC-001` | isolation ressource et RLS | `identity`/plateforme | 17 | tests croisés |
| `REQ-SEC-002` | aucun fallback ou appel payé implicite | adaptateurs | 06, 15, 17 | doubles et quotas |
| `REQ-OPS-001` | suppression survit à une restauration | plateforme | 17-19 | exercice tombstone |
| `REQ-UX-001` | aucune activité affichée comme maîtrise | frontend | 20 | contenu/UI review |
| `REQ-UX-002` | reprise au dernier accusé sans doublon | frontend/API | 09, 16, 20 | E2E crash/reload |

## 4. Fixtures canoniques

| ID | Contenu et oracle |
|---|---|
| `FX-USERS` | six rôles, deux comptes, profils croisés, consentements et sessions |
| `FX-AUTH` | mot de passe local, faux OIDC, session expirée, CSRF, changement de rôle |
| `FX-PERSONAS` | `P-ABS`, `P-FAUX`, `P-INT`, `P-RETOUR`, `P-A11Y`, `P-AUTEUR` |
| `FX-CATALOGUE-IT` | variété it-IT, DAG, fonctions, structures, formes, erreurs connues |
| `FX-IT-FOUND` | F1-F5, gate immédiate et différée, cas non évaluable |
| `FX-LEXICON` | `piano`, `sono`, homonymes, polysémie, syncrétisme, expressions multi-mots |
| `FX-WB` | 0, 10, 100k sens personnels, rencontres, ambiguïtés et contextes supprimés |
| `FX-MEMORY` | deux directions, due, suspendu, reset, fusion, historique importé |
| `FX-IMPORTS` | JSON/CSV valides, partiels, conflictuels, hostiles et obsolètes |
| `FX-CONTENT` | draft, validated, approved, published, retired, superseded, conflit |
| `FX-PRIMITIVES` | positif, négatif, ambigu, aide H0-H4 et alternative a11y par primitive core |
| `FX-GYM-IT` | explication, production, transformation, J+1, espacé et transfert |
| `FX-MODULE-IT` | pilote humain trois jours, dialogues, listes et mission |
| `FX-SPRINTS` | chaque budget, dette vide/saturée, média absent, jour manqué, reprise |
| `FX-EVIDENCE` | faits ordonnés/désordonnés, doublons, correction révisée, oubli |
| `FX-ASSESS` | quatre protocoles, expiration, pause, double soumission, oral simulé |
| `FX-MEDIA` | audio fixe, transcript, voix retirée, MIME trompeur, archive hostile |
| `FX-TOOLS` | appels valides/invalides, permission, timeout, quota, rejeu, sortie hostile |
| `FX-UI` | états vide/long/lent/hors-ligne/conflit aux largeurs de référence |
| `FX-AUTHORING` | auteur/reviewer distincts, validateurs, diff, retrait, historique |
| `FX-OPS` | charge synthétique, outbox bloquée, backup, tombstones et version N-1 |

Chaque fixture possède `fixture_id`, `schema_version`, horloge, graine, manifeste,
empreintes et oracles. Les données réelles sont interdites.

## 5. Catalogue de preuves

| Code | Preuve | Quand elle est indispensable |
|---|---|---|
| `P-UNIT` | tests unitaires | valeurs, politiques, transitions |
| `P-PROP` | tests de propriétés | invariants, ordre, idempotence, bornes |
| `P-PG` | intégration PostgreSQL réel | transactions, RLS, migrations, requêtes |
| `P-CONTRACT` | OpenAPI/JSON Schema/client | API, événements, outils, médias |
| `P-COMP` | tests composants | renderers, formulaires, états |
| `P-E2E` | navigateur réel | parcours et reprise |
| `P-A11Y` | axe, clavier, lecteur d'écran manuel | tout écran/primitive core |
| `P-VISUAL` | captures et revue humaine | écran structurant desktop/mobile |
| `P-SEC` | SAST/SCA/DAST/authz | identité, import, Atelier, suppression |
| `P-PERF` | charge et profils SQL | budgets NFR/Word Bank/compositeur |
| `P-RESTORE` | restauration chronométrée | données, backup, tombstones |
| `P-LING` | revue linguistique | pack, structure, dialogue, correction |
| `P-PED` | pilote humain | maîtrise, sprint, évaluation |
| `P-CANARY` | staging/production | release uniquement |

## 6. Couverture et statut

Les documents 00 à 31 fixent l'inventaire, les décisions, contrats, dictionnaire,
wireframes et plans : état `specified`. Les captures V1 sous `assets/v1` sont des
preuves historiques, pas des preuves V2. Les fixtures, schémas exécutables,
tests, captures V2, spikes et rapports n'existent qu'après implémentation : ils
ne peuvent pas être marqués `verified` par la seule présence de cette architecture.

Le tableau de livraison sera généré depuis les IDs de la matrice 05 et de la
section 3. Une ligne sans famille, owner, lot, fixture, preuve ou approbateur
échoue `G0`. Une ligne dont une preuve obligatoire manque reste `PARTIAL`, même
si tous ses tests unitaires sont verts.
