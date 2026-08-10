# W08 phase B - Listes, imports et exports

## Statut

GREEN local intermediaire au commit `cd274f8`. W08 n'est pas accepte : la
quarantaine W15, les imports memoire/auteur et le profil SQL volumetrique restent
ouverts.

## Portee Prouvee

- listes manuelles, dynamiques et editoriales avec politiques de roles ;
- revisions, archivage, associations bornees et snapshots immuables ;
- AST dynamique allowlistee, preview pagine et snapshot au cutoff via port ;
- parseurs JSON/CSV bornes et inspection ZIP hostile sans extraction ;
- sept classes de conflit, preview sans mutation et decisions interactives ;
- lecture des candidats et mutations lexicales via frontieres W06 ;
- commit atomique, idempotent, manifeste signe et revert compensatoire ;
- verification du manifeste complet avant lecture ou revert ;
- consultation paginee des lignes et conflits d'import, owner scopee ;
- aucun format memoire/auteur/export ne peut muter le lexique par erreur ;
- export canonique avec scope ferme, expiration et port prive obligatoire ;
- aucun export `ready` sans attestation de chiffrement valide ;
- routes FastAPI, OpenAPI et client TypeScript regeneres ;
- `FX-IMPORTS` hors reseau, checksum verrouille et parse reel de 100 000 lignes.

## Correctifs De Robustesse

- suppression d'une fuite de connexion dans `get_list` ;
- distinction auditee entre references creees et reutilisees ;
- rollback total lorsqu'un port lexical echoue ;
- refus des manifests alteres avant toute compensation ;
- refus des chemins ambigus, doublons Unicode, executables, liens, types
  speciaux, archives imbriquees, binaires et types de fichier incoherents ;
- limites verrouillees : archive 50 Mio, 1 000 entrees, total 200 Mio, fichier
  20 Mio, ratio 20:1, JSON profondeur 32, chaine 32 Kio et 100 000 lignes ;
- refus explicite du reimport `polyglot.user.export/v1` ;
- mise en echec visible d'un export si le stockage ou le chiffrement manque.

## Preuves Locales Courantes

- matrice W08 avec performance 100 000 : `89 passed` ;
- non-regression ingestion/transactions W06 + W08 : `94 passed` avant le spike ;
- Ruff cible : PASS ;
- mypy strict sur W06/W08 et routes : PASS ;
- registre W00 : `contract registry valid` ;
- OpenAPI deterministe, Orval, ESLint et TypeScript : PASS ;
- parse 100 000 lignes, neuf runs : p50 `0.794789 s`, p95 `0.829307 s`,
  p99 `0.837981 s` ;
- preuve brute : `docs/evidence/W08/spk-import-100k-raw.json`.

## Gates Encore Ouvertes

- `PrivateArtifactPort.inspect_quarantined` et objet prive W15 : la route
  actuelle recoit encore un payload base64 en memoire ;
- historique observable de la machine `uploaded -> quarantined -> parsing ->
  preview`, y compris runs invalides et panne de scan ;
- selection partielle explicite des lignes valides et rapport d'erreurs borne a
  1 000 details ;
- `MemoryPromptImportPort` transactionnel W07 et handoff auteur sans publication ;
- adaptateurs reels pour listes dynamiques et associations aux modules/sessions ;
- resolution reelle de `sense_revision_id` dans les snapshots, pas seulement
  une reference de sens courante ;
- matrice hostile executable complete dans `FX-IMPORTS` (CRC, multi-disk,
  methode, hardlink/device/FIFO/socket, BOM et MIME) ;
- concurrence/adversarial et replay x100 ;
- insertion/commit PostgreSQL 100 000, profil SQL et budget p50/p95/p99 ;
- adaptateur cryptographique/stockage W15 reel et cycle de telechargement/expiry ;
- revue securite, revue produit et approbation humaine `P-LING`.

Aucun push et aucune acceptation W08 ne sont revendiques par ce rapport.
