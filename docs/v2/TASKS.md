# Polyglot V2 - Registre de fermeture de l'architecture

## 1. Objet de ce registre

Ce fichier suit le travail documentaire nécessaire avant l'implémentation. Il ne
contient aucune tâche de codage. Une case cochée signifie que le contrat ou plan
existe et a été relu au niveau architecture ; elle ne signifie jamais que le
code, la fixture exécutable, le pilote humain ou la preuve de release existe.

Statuts :

- `[ ]` non commencé ;
- `[-]` partiellement couvert par les spécifications actuelles ;
- `[x]` spécifié et relu au niveau architecture ;
- `[!]` bloqué par une décision produit.

Priorités : `P0` bloque toute planification, `P1` bloque le lot concerné, `P2`
peut être finalisé après le noyau conceptuel.

### [x] SCOPE-01 - Repartir avec une base vide

- Décision : aucun compte, profil, paquet, carte, révision, session, progression
  ou score de la V1 ne sera migré.
- Conséquence : la V1 reste une référence fonctionnelle et visuelle. Les contenus
  éditoriaux anciens ne sont réutilisables qu'après audit et conversion.
- Terminé : décision utilisateur explicite enregistrée.

## 2. Gate A - Périmètre et source de vérité

### [x] A00 - Établir une baseline versionnée (`P0`)

- Dépendances : aucune.
- Livrable : snapshot identifié de la V1, dossier V2 suivi par Git, règle de
  gouvernance documentaire et historique des validations.
- Terminé lorsque : les audits et plans citent une révision immuable et que les
  modifications futures de spécification sont visibles dans l'historique.
- Délégation : non ; opération de gouvernance centrale.

### [x] A01 - Consolider la source de vérité produit (`P0`)

- Dépendances : aucune.
- Livrable : index normatif indiquant quel document décide en cas de conflit.
- Travail : séparer exigences approuvées, propositions, décisions ouvertes et
  comportements seulement observés dans la V1.
- Terminé lorsque : chaque exigence possède un identifiant stable, une source,
  un statut et un propriétaire de décision.
- Délégation : préparation possible ; arbitrage final local avec l'utilisateur.

### [x] A02 - Fermer l'inventaire fonctionnel V1 (`P0`)

- Dépendances : A01.
- Livrable : matrice V1 exhaustive reliée aux routes, modèles, écrans et scripts.
- Travail : ajouter variantes, états vides, erreurs, autorisations, imports,
  réglages et comportements mobiles ; distinguer actif, partiel, dormant et mort.
  Couvrir explicitement suppression de carte, CRUD/couleur des catégories,
  réédition de programme, saut d'un bloc, reprise d'évaluation et inventaire des
  capacités TTS.
- Terminé lorsque : toutes les routes et tous les modèles V1 sont reliés à au
  moins une ligne, ou classés comme détail technique sans valeur produit.
- Délégation : audit en lecture seule, puis validation locale.

### [x] A03 - Écrire le glossaire métier normatif (`P0`)

- Dépendances : A01.
- Livrable : `06-glossaire-decisions.md`.
- Travail : définir langue maternelle, langue cible, profil linguistique,
  compétence, capacité, fonction, structure, moule, lexème, sens, forme, carte,
  liste, dette, module, journée, sprint, exercice, instance, tentative,
  observation, preuve, maîtrise, évaluation et contenu publié.
- Terminé lorsque : aucun terme central n'a deux sens dans les spécifications.
- Délégation : brouillon délégable ; arbitrage final local.

### [x] A04 - Construire le registre des décisions (`P0`)

- Dépendances : A01, A03.
- Livrable : décisions acceptées, rejetées et ouvertes avec conséquences.
- Travail : traiter les dix décisions ouvertes de la feuille de route, plus
  stack, dépôt, API, base, authentification, hébergement, confidentialité,
  imports génériques et politique de réutilisation des contenus V1.
- Terminé lorsque : aucune décision bloquante ne reste implicite avant le plan.
- Délégation : analyse des options délégable ; choix utilisateur requis.

### [x] A05 - Définir les exigences non fonctionnelles (`P0`)

- Dépendances : A04.
- Livrable : budget de performance, disponibilité, sauvegarde, accessibilité,
  navigateurs, mobile, sécurité, confidentialité, observabilité et volumétrie.
- Terminé lorsque : chaque exigence possède une métrique et une méthode de test.
- Délégation : proposition délégable ; validation locale.

### [x] A06 - Enrichir la matrice de traçabilité (`P0`)

- Dépendances : A02, A04, L01.
- Livrable : une ligne par capacité avec ID, décision, lot, owner, dépendances,
  critère d'acceptation, test, approbateur et état de livraison.
- Terminé lorsque : 100 % des capacités sont attribuées et aucune ligne
  `Refondre` ou `Remplacer` ne reste sans décision approuvée.
- Délégation : remplissage par domaines possible ; consolidation centrale.

## 3. Gate B - Parcours et règles pédagogiques

### [x] B01 - Décrire les personas et états d'entrée (`P0`)

- Dépendances : A03.
- Livrable : débutant absolu, faux débutant, intermédiaire, utilisateur
  reprenant après interruption et auteur pédagogique.
- Terminé lorsque : chaque profil possède données initiales, objectifs, risques
  et résultats attendus.
- Délégation : oui.

### [x] B02 - Spécifier les parcours de bout en bout (`P0`)

- Dépendances : B01.
- Livrable : scénarios Given/When/Then du compte jusqu'au bilan de module.
- Travail : onboarding, diagnostic, fondations, premier sprint, interruption,
  entraînement libre, listes de vocabulaire, progression et quatre évaluations.
- Terminé lorsque : chemins heureux, alternatifs, vides et erreurs sont couverts.
- Délégation : division par parcours possible.

### [x] B03 - Définir le modèle pédagogique de maîtrise (`P0`)

- Dépendances : A03, B02.
- Livrable : formule conceptuelle, états, transitions, seuils, décroissance,
  confiance, diversité de contexte et poids des aides.
- Terminé lorsque : les mêmes observations produisent un état reproductible et
  qu'aucune réussite isolée ne peut produire une maîtrise.
- Délégation : comparaison/relecture possible ; décision centrale locale.

### [x] B04 - Définir le diagnostic initial (`P0`)

- Dépendances : B03.
- Livrable : protocole adaptatif, micro-épreuves, conversation simulée, règles
  d'arrêt, confiance et orientation vers les fondations.
- Terminé lorsque : les profils débutant, faux débutant et intermédiaire ont des
  scénarios déterministes et des résultats explicables.
- Délégation : conception des cas de test possible.

### [x] B05 - Définir les fondations italiennes (`P1`)

- Dépendances : B04, C02.
- Livrable : programme fermé minimal, prérequis, exercices et gate de sortie.
- Terminé lorsque : un débutant absolu acquiert ce qui est nécessaire au premier
  module sans dépendre d'un niveau CECR déclaré.
- Délégation : audit linguistique séparé recommandé.

### [x] B06 - Définir les quatre évaluations (`P1`)

- Dépendances : B03, E01.
- Livrable : protocoles lecture, écoute, écriture et oral ; grilles, sécurité,
  nouveautés, reprises, confiance et agrégation.
- Terminé lorsque : chaque test peut fonctionner avec fixtures sans LLM et que
  l'expression orale possède un simulateur documenté.
- Délégation : un agent par modalité possible.

### [x] B07 - Cataloguer états vides et situations limites (`P0`)

- Dépendances : B02.
- Livrable : matrice par parcours couvrant aucune carte due, aucun paquet, aucune
  langue, liste vide, contenu invalide, média absent, fournisseur indisponible,
  correction ambiguë, réseau lent et génération échouée.
- Terminé lorsque : chaque état possède message, action de sortie, conservation
  des données et scénario d'acceptation.
- Délégation : oui, par parcours.

## 4. Gate C - Architecture backend

### [x] C01 - Verrouiller les contextes métier (`P0`)

- Dépendances : A03, B02.
- Livrable : carte des modules, responsabilités, dépendances autorisées et
  interfaces publiques.
- Terminé lorsque : aucune donnée centrale n'a deux propriétaires et aucun cycle
  de dépendance métier n'est nécessaire.
- Délégation : revue architecture possible.

### [x] C02 - Définir toutes les entités et valeurs (`P0`)

- Dépendances : C01.
- Livrable : dictionnaire de données conceptuel complet, identifiants, champs,
  cardinalités, contraintes et règles de suppression.
- Terminé lorsque : tous les parcours B02 peuvent être représentés sans blob
  métier opaque ni champ dont le sens reste implicite.
- Délégation : division par domaine possible.

### [x] C03 - Définir les invariants métier (`P0`)

- Dépendances : C02.
- Livrable : catalogue testable des invariants et violations attendues.
- Travail : propriété, langue, version publiée, tentative, échéance, dette,
  progression, association liste-session et suppression.
- Terminé lorsque : chaque mutation critique indique préconditions et effets.
- Délégation : oui, par domaine.

### [x] C04 - Définir les machines à états (`P0`)

- Dépendances : C02, C03.
- Livrable : Mermaid et tables de transitions pour contenu, module, sprint,
  exercice, tentative, dette, évaluation et tâche de génération.
- Terminé lorsque : transitions invalides et reprise après panne sont explicites.
- Délégation : oui, par machine indépendante.

### [x] C05 - Définir commandes, requêtes et événements (`P0`)

- Dépendances : C03, C04.
- Livrable : catalogue versionné avec entrée, sortie, erreurs, idempotence,
  autorisation et événements produits.
- Terminé lorsque : chaque étape B02 correspond à une commande ou requête et que
  les statistiques peuvent être recalculées depuis les faits conservés.
- Délégation : oui, par contexte métier.

### [x] C06 - Définir contrats HTTP et temps réel (`P1`)

- Dépendances : C05, A04.
- Livrable : conventions API, pagination, erreurs, concurrence optimiste,
  uploads, streaming, reprise, versioning et compatibilité.
- Terminé lorsque : le frontend peut être planifié sans inventer un contrat.
- Délégation : oui.

### [x] C07 - Définir sécurité et confidentialité (`P0`)

- Dépendances : A05, C05.
- Livrable : matrice rôles/permissions, menaces, données sensibles, rétention,
  export, effacement, audit et limites des fournisseurs.
- Terminé lorsque : chaque commande possède une politique et chaque donnée une
  durée de vie approuvée.
- Délégation : audit sécurité possible.

### [x] C08 - Spécifier versionnement et publication du contenu (`P0`)

- Dépendances : C02, C03, C04.
- Livrable : identité stable, révision immuable, états draft/validated/approved/
  published/retired, publication atomique, remplacement et compatibilités.
- Terminé lorsque : édition concurrente, retrait, rollback et tentative utilisant
  une ancienne révision ont chacun une issue déterministe.
- Délégation : revue architecture possible.

### [x] C09 - Spécifier transactions, idempotence et concurrence (`P0`)

- Dépendances : C03, C05.
- Livrable : enveloppes commande/événement, clés d'idempotence, optimistic
  locking, outbox, ordre, corrélation, causalité et erreurs rejouables.
- Terminé lorsque : 100 rejeux n'ajoutent aucun effet et deux soumissions
  concurrentes ne créent qu'un résultat valide.
- Délégation : audit distribué possible ; contrat final central.

### [x] C10 - Définir l'évolution des schémas (`P1`)

- Dépendances : C06, C08, C09, K05.
- Livrable : compatibilités API/événements/packs, upcasters, fenêtre de support,
  migrations ascendantes et procédure de rollback.
- Terminé lorsque : une fixture de chaque version supportée reste lisible.
- Délégation : oui.

## 5. Gate D - Pack de langue italien

Les tâches `D02-D04` ferment le sous-ensemble normatif du pilote. Les tâches
suffixées `X` et `D05` produisent ensuite le catalogue éditorial complet et son
audit linguistique. Elles bloquent `GATE-IT-FULL`, la publication du pack italien
complet, pas la création du dépôt, `GATE-G0` ni le pilote de `GATE-G5`.

### [x] D01 - Spécifier le contrat `LanguagePack` (`P0`)

- Dépendances : A03, C01.
- Livrable : sections obligatoires, capacités optionnelles, versions,
  validateurs, compatibilité et certification d'un pack.
- Terminé lorsque : un futur pack japonais peut être décrit sans changer le
  moteur commun.
- Délégation : revue multilingue possible.

### [x] D02 - Spécifier la taxonomie italienne du pilote (`P1`)

- Dépendances : D01, B03.
- Livrable : graphe des compétences, fonctions, prérequis et niveaux de charge.
- Terminé lorsque : chaque cible du pilote italien possède un chemin de
  prérequis et des preuves possibles dans plusieurs primitives.
- Délégation : audit linguistique recommandé.

### [ ] D02X - Produire la taxonomie italienne exhaustive (`P1`, éditorial)

- Dépendances : D02 et implémentation de l'Atelier.
- Livrable : graphe complet, fréquences, domaines et revue linguistique signée.
- Bloque : pack italien complet et `GATE-IT-FULL`, pas l'architecture ni le pilote.

### [x] D03 - Normaliser la boîte grammaticale du pilote (`P1`)

- Dépendances : D02.
- Livrable : catalogue fonction -> moules, contraintes, contrastes, erreurs,
  registres, exemples et contre-exemples.
- Terminé lorsque : les 17 familles et les structures prioritaires ont une fiche
  exploitable par le moteur, sans règle absolue erronée.
- Délégation : familles disjointes possibles, revue finale unique.

### [ ] D03X - Enrichir la boîte grammaticale exhaustive (`P1`, éditorial)

- Dépendances : D02X, D03 et revue linguistique.
- Livrable : fiches publiables pour toutes les structures prioritaires au-delà
  des 30 moules et 17 familles structurées du pilote.
- Bloque : pack italien complet et `GATE-IT-FULL`.

### [x] D04 - Spécifier morphologie, conjugaison et prononciation du pilote (`P1`)

- Dépendances : D01.
- Livrable : capacités minimales du pilote, variantes, formes et validateurs.
- Terminé lorsque : cartes, dictées, conjugaison, Gym et TTS partagent les mêmes
  identifiants linguistiques.
- Délégation : oui, expert linguistique.

### [ ] D04X - Produire les paradigmes italiens exhaustifs (`P1`, éditorial)

- Dépendances : D04 et Atelier opérationnel.
- Livrable : conjugaisons, flexions, graphies, prononciations, variantes,
  exceptions, attestations et revue experte au-delà du pilote.
- Bloque : pack italien complet et `GATE-IT-FULL`.

### [ ] D05 - Auditer les contenus V1 (`P2`)

- Dépendances : D02X, D03X.
- Livrable : pour chaque fichier italien, réutilisable, à corriger ou à rejeter,
  avec justification pédagogique.
- Terminé lorsque : aucun JSON V1 n'est importé comme contenu fiable par défaut.
- Délégation : lots de fichiers parallèles possibles.

## 6. Gate E - Vocabulaire et mémoire

### [x] E01 - Spécifier lexèmes, sens et formes (`P0`)

- Dépendances : C02, D01.
- Livrable : identité lexicale, homonymie, polysémie, flexion, multi-mots,
  collocations, registre, fréquence, provenance et traductions.
- Terminé lorsque : les cas italiens ambigus et les imports génériques sont
  représentés.
- Délégation : oui.

### [x] E02 - Spécifier les listes de vocabulaire (`P0`)

- Dépendances : E01.
- Livrable : types, propriété, versioning, clonage, fusion, partage, import,
  archivage et rôles d'association aux modules/sessions/exercices.
- Terminé lorsque : préparation avant session, modification après session et
  réutilisation historique sont possibles sans altérer les tentatives passées.
- Délégation : oui.

### [x] E03 - Spécifier mémoire et FSRS (`P0`)

- Dépendances : E01, B03.
- Livrable : unité mémorisée, directions, événements, paramètres, échéances,
  suspension, reset et fusion des états.
- Terminé lorsque : toutes les opérations ont des propriétés testables et que
  l'historique reste immuable.
- Délégation : audit algorithmique possible.

### [x] E04 - Unifier la dette d'apprentissage (`P0`)

- Dépendances : E01, E03, B03.
- Livrable : types de dette, causes, priorités, échéances, déduplication,
  résolution, réouverture et conversion en activité.
- Terminé lorsque : SOS, révélation, erreur lexicale, grammaire et prononciation
  suivent le même cycle sans double stockage.
- Délégation : oui.

### [x] E05 - Définir imports, exports et conflits (`P1`)

- Dépendances : E01, E02, E03.
- Livrable : formats versionnés, aperçu, validation, stratégie de doublon,
  idempotence, rapport d'erreurs et rollback.
- Terminé lorsque : chaque format d'import officiellement supporté possède une
  fixture positive, partiellement invalide et conflictuelle.
- Délégation : oui.

### [x] E06 - Spécifier les gestes utilisateur sur le vocabulaire (`P0`)

- Dépendances : E01, E02, E04.
- Livrable : wireflows et effets métier pour créer, consulter, corriger un sens,
  déplacer, fusionner, cloner, partager, archiver, supprimer, restaurer et
  associer une liste avant/pendant/après une session.
- Terminé lorsque : chaque geste indique son effet sur lexème, sens, liste,
  carte, dette, FSRS et tentatives historiques.
- Délégation : préparation UX et métier parallélisable.

### [x] E07 - Spécifier le graphe lexical personnel (`P0`)

- Dépendances : E01, B03, C05.
- Livrable : objets occurrence, attention, production, preuve, facette
  personnelle, relation, annotation, prompt mémoire et besoin d'apprentissage.
- Terminé lorsque : polysémie, homonymie, formes syncrétiques, expressions
  multi-mots, traductions asymétriques et corrections tardives sont représentées
  sans propager artificiellement la maîtrise.
- Délégation : revue linguistique et revue données parallélisables.

### [x] E08 - Définir capture et désambiguïsation lexicales (`P0`)

- Dépendances : E01, E07, D04.
- Livrable : pipeline versionné segmentation, normalisation, analyse
  morphologique, candidats de sens, confirmation, ambiguïté et ingestion.
- Terminé lorsque : une même commande est idempotente, deux rencontres réelles
  restent distinctes et une analyse incertaine ne crée aucune preuve par sens.
- Délégation : spike linguistique et contrat d'ingestion séparables.

### [x] E09 - Définir l'overview et l'analyse des lacunes (`P0`)

- Dépendances : E02, E07, H02.
- Livrable : requêtes et projections rencontré/reconnu/utilisable/fiable, écarts
  écrit-oral, reconnaissance-production et couverture de référentiels bornés.
- Terminé lorsque : toute statistique est explicable et aucun pourcentage global
  de langue n'est affiché sans corpus nommé et versionné.
- Délégation : oui.

### [x] E10 - Définir contrats, requêtes et budgets du graphe lexical (`P0`)

- Dépendances : E07, E08, C05, A05.
- Livrable : contrats WB-01 à WB-12, commandes d'analyse/résolution/relation,
  requêtes de recherche/voisinage/explication/export et limites de traversée.
- Travail : fixer corpus volumétrique, index, profondeur, pagination, p95 de
  recherche, file due et voisinage ; tester isolation et suppression de contexte.
- Terminé lorsque : les requêtes critiques passent sur un corpus synthétique
  approuvé et qu'une projection graphe éventuelle reste reconstruisible.
- Délégation : spike performance et revue de contrats parallélisables.

## 7. Gate F - Moteur d'exercices

### [x] F01 - Fermer le registre des primitives (`P0`)

- Dépendances : B03, D01.
- Livrable : liste normative, responsabilités, entrées, réponses, correction,
  aides et observations pour chaque primitive.
- Terminé lorsque : les doublons sont fusionnés et chaque besoin du sprint ou
  des évaluations est couvert.
- Délégation : audit par famille possible.

### [x] F02 - Définir le contrat d'exercice (`P0`)

- Dépendances : F01, C02.
- Livrable : schémas conceptuels Definition, Instance, Attempt, Answer,
  Correction, Hint et Observation.
- Terminé lorsque : toutes les primitives prioritaires utilisent le contrat sans
  champ spécial non documenté.
- Délégation : revue contrat possible.

### [x] F03 - Définir les stratégies de correction (`P0`)

- Dépendances : F02, D04.
- Livrable : exact, ensemble accepté, morphologique, traduction, grille,
  sémantique bornée, humaine et future LLM ; confiance et contestation.
- Terminé lorsque : pannes, ambiguïtés et désaccords ne deviennent jamais des
  réussites silencieuses.
- Délégation : un audit par stratégie possible.

### [x] F04 - Spécifier aides et accessibilité (`P1`)

- Dépendances : F02, B03.
- Livrable : indices progressifs, révélation, SOS, coût pédagogique, clavier,
  lecteur d'écran, audio, transcription et alternatives.
- Terminé lorsque : chaque primitive possède au moins un parcours accessible et
  que toute aide produit une observation explicite.
- Délégation : audit accessibilité recommandé.

### [x] F05 - Définir la nouvelle Gym (`P1`)

- Dépendances : D03, F01, F03.
- Livrable : cycles J0/J+1/espacé, transformations, sélection par prérequis,
  conjugaison et transfert.
- Terminé lorsque : une structure prioritaire peut parcourir tout le cycle avec
  fixtures et critères de maîtrise.
- Délégation : conception des transformations par familles possible.

### [x] F06 - Définir shadowing et oral simulé (`P1`)

- Dépendances : F01, D04.
- Livrable : vidéo, TTS, segmentation, vitesse, répétition, auto-évaluation,
  lecture et future mesure STT.
- Terminé lorsque : indisponibilité du média et mode sans fournisseur ont un
  comportement déterministe.
- Délégation : oui.

### [x] F07 - Spécifier saut, abandon et correction après exercice (`P0`)

- Dépendances : F02, F03, C04.
- Livrable : transitions et UX pour répondu, corrigé, explication consultée,
  contesté, passé volontairement, abandonné, indisponible et repris.
- Terminé lorsque : chaque état a des effets distincts sur progression, dette,
  minuteur et prochaine activité, sans double comptabilisation.
- Délégation : oui.

## 8. Gate G - Curriculum et sprint

### [x] G01 - Spécifier module, arc et journée (`P0`)

- Dépendances : B02, D02, E02, F01.
- Livrable : objectifs, contextes, scènes, vocabulaire, structures, quatre
  compétences, progression, mission finale et versions.
- Terminé lorsque : modules de 3 à 30 jours sont représentables et modifiables.
- Délégation : oui.

### [x] G02 - Définir le planificateur de module (`P0`)

- Dépendances : G01, B03.
- Livrable : contraintes, quotas, couverture, prérequis, variété, dette et règles
  de régénération partielle.
- Terminé lorsque : une même entrée et une même graine produisent le même plan.
- Délégation : audit algorithmique possible.

### [x] G03 - Définir le compositeur de sprint (`P0`)

- Dépendances : G02, E03, E04, F02.
- Livrable : budgets 10-60 par pas de 5, ancres 15/30/45/60, obligatoires, options, ordre, estimation,
  remplacement et justification de chaque bloc.
- Terminé lorsque : les scénarios de temps, dette et absence de contenu ont une
  composition déterministe conforme aux priorités.
- Délégation : matrice de scénarios possible.

### [x] G04 - Définir J-1/J+1 et répétition espacée inter-domaines (`P0`)

- Dépendances : G03, B03.
- Livrable : règles distinctes pour textes, vocabulaire, structures, erreurs et
  productions ; source corrigée et version figée.
- Terminé lorsque : interruption, jour manqué et fuseau horaire sont définis.
- Délégation : oui.

### [x] G05 - Spécifier le pilote italien de trois jours (`P0`)

- Dépendances : B05, D03, E02, F05, G03.
- Livrable : contenu humain complet, fixtures, plans 15/30/60 et résultats
  attendus pour plusieurs profils.
- Terminé lorsque : il peut servir de test end-to-end sans LLM.
- Délégation : contenus et scénarios peuvent être préparés séparément.

## 9. Gate H - Progression, statistiques et évaluations

### [x] H01 - Définir le calcul des observations (`P0`)

- Dépendances : B03, F02.
- Livrable : mapping tentative -> observations, poids, confiance et invalidation.
- Terminé lorsque : chaque primitive a des exemples chiffrés reproductibles.
- Délégation : division par primitive possible.

### [x] H02 - Définir agrégats et recommandations (`P0`)

- Dépendances : H01, E03.
- Livrable : projections par compétence, lexique, structure et modalité ; oubli,
  fraîcheur, diversité et raisons des recommandations.
- Terminé lorsque : tout chiffre visible peut être expliqué par des preuves.
- Délégation : audit statistique possible.

### [x] H03 - Définir les tableaux de bord (`P1`)

- Dépendances : H02, B06.
- Livrable : métriques visibles, métriques internes, libellés, états vides et
  comparaisons temporelles.
- Terminé lorsque : aucune métrique d'activité n'est présentée comme maîtrise.
- Délégation : oui, avec revue UX.

### [x] H04 - Définir protocoles et résultats d'évaluation (`P1`)

- Dépendances : B06, H01.
- Livrable : sélection d'épreuves, sécurité, reprise, score, confiance,
  historique, preuves et effet sur le profil.
- Terminé lorsque : réussite ou échec ne déverrouille aucune compétence sans
  preuve correspondante.
- Délégation : par modalité possible.

### [x] H05 - Spécifier orchestration et reprise des évaluations (`P0`)

- Dépendances : B06, C04, H04.
- Livrable : disponibilité, ordre, fréquence, tentatives, minuteur, sauvegarde,
  reprise à la section exacte, expiration et agrégation des quatre modalités.
- Terminé lorsque : fermeture navigateur, expiration et double soumission ont des
  résultats déterministes testables.
- Délégation : oui.

## 10. Gate I - Génération, outils et fournisseurs

### [x] I01 - Définir le cycle éditorial (`P0`)

- Dépendances : C04, D01, F02, G01.
- Livrable : brouillon, validation, revue, publication, retrait, remplacement,
  provenance et compatibilité de version.
- Terminé lorsque : une tentative historique reste interprétable après édition.
- Délégation : oui.

### [x] I02 - Définir la façade d'outils du LLM (`P0`)

- Dépendances : C05, I01.
- Livrable : outil par opération, schéma, permissions, idempotence, limites,
  erreurs, audit et exemples positifs/négatifs.
- Contrat : `30-contrats-outils-auteur.md` pour les onze outils.
- Terminé lorsque : un runner déterministe peut simuler tous les appels sans LLM.
- Délégation : outils par domaine possibles.

### [x] I03 - Définir les validateurs pédagogiques (`P0`)

- Dépendances : D03, F02, G01.
- Livrable : schéma, naturalité, niveau, prérequis, alignement, couverture,
  sécurité, biais et règles spécifiques à la langue.
- Terminé lorsque : les défauts connus de la V1 sont des fixtures rejetées.
- Délégation : validateurs par catégorie possibles.

### [x] I04 - Définir les adaptateurs fournisseurs (`P1`)

- Dépendances : A04, C06.
- Livrable : ports LLM/TTS/STT/média, capacités, timeouts, erreurs, retries
  autorisés, cache, quotas et absence de fallback silencieux.
- Terminé lorsque : chaque adaptateur possède un faux local contractuel.
- Délégation : un agent par adaptateur possible.

### [x] I05 - Définir l'évaluation future du LLM (`P1`)

- Dépendances : I02, I03, G05.
- Livrable : corpus, rubriques, répétitions, seuils, revue humaine, coût et
  comparaison aux contenus de référence.
- Terminé lorsque : brancher LLM Studio ne peut pas changer les règles métier.
- Délégation : oui.

### [x] I06 - Spécifier tâches et tentatives de génération (`P0`)

- Dépendances : I01, I02, C09.
- Livrable : `GenerationJob` et `GenerationAttempt` avec fournisseur, modèle,
  paramètres, versions prompt/outils, empreinte d'entrée, statut, coût, timeout,
  retries autorisés et résultat.
- Terminé lorsque : timeout, rejeu, correction et abandon ne créent aucun
  brouillon dupliqué ni publication directe.
- Délégation : oui.

## 11. Gate J - UX et frontend

### [x] J01 - Capturer la V1 (`P0`)

- Dépendances : A02.
- Livrable : inventaire des écrans, captures desktop/mobile, interactions,
  textes, états vides, erreurs et éléments à préserver/rejeter.
- Terminé lorsque : refaire le frontend ne nécessite plus de relire les templates.
- Délégation : parcours indépendants possibles via navigateur.

### [x] J02 - Définir l'architecture d'information (`P0`)

- Dépendances : B02, J01.
- Livrable : navigation, hiérarchie, objets accessibles et permissions.
- Terminé lorsque : chaque parcours B02 possède un chemin court et réversible.
- Délégation : proposition UX possible ; validation utilisateur requise.

### [x] J03 - Définir le contrat du lecteur d'exercice (`P0`)

- Dépendances : F02, F04, C06.
- Livrable : shell, composants par primitive, progression, sauvegarde, aides,
  correction, contestation, audio et interruption.
- Terminé lorsque : chaque primitive prioritaire a états loading/ready/answered/
  error/resumed documentés sans déplacement incohérent de mise en page.
- Délégation : composants par famille possibles.

### [x] J04 - Concevoir les écrans structurants (`P1`)

- Dépendances : J02, H03, E02, G03.
- Livrable : wireframes et spécifications Aujourd'hui, Apprendre, S'entraîner,
  Vocabulaire, Progression, Évaluer, Profil et Atelier.
- Terminé lorsque : desktop/mobile et contenus extrêmes ont été revus visuellement.
- Délégation : écrans indépendants possibles ; direction finale unique.

### [x] J05 - Définir design system et accessibilité (`P1`)

- Dépendances : J03, J04, A05.
- Livrable : tokens, typographie, couleurs, densité, composants, états, clavier,
  focus, contrastes, audio/transcriptions et responsive.
- Terminé lorsque : règles testables et composants limites sont documentés.
- Délégation : audit accessibilité et inventaire visuel parallèles possibles.

### [x] J06 - Spécifier découverte et dégradation TTS (`P1`)

- Dépendances : I04, J03.
- Livrable : disponibilité, langues, voix, préférence, voix supprimée, solution
  de remplacement explicite et comportement sans audio.
- Terminé lorsque : chaque changement de capacité fournisseur possède un état UX
  et un test de contrat.
- Délégation : oui.

## 12. Gate K - Exploitation et cycle de vie des données

### [x] K03 - Définir sauvegarde, restauration et suppression (`P0`)

- Dépendances : C02, C07.
- Livrable : RPO/RTO, sauvegardes, restauration testée, export utilisateur,
  suppression partielle/totale et rétention.
- Terminé lorsque : chaque scénario possède procédure et test.
- Délégation : oui.

### [x] K04 - Définir observabilité et support (`P1`)

- Dépendances : C05, A05.
- Livrable : logs structurés, métriques, traces, corrélation, alertes, audit et
  diagnostic sans exposer les réponses privées.
- Terminé lorsque : les pannes majeures ont signal, contexte et procédure.
- Délégation : oui.

### [x] K05 - Définir environnements et livraison (`P0`)

- Dépendances : A04, A05.
- Livrable : local, test, preview, production, secrets, migrations, déploiement,
  rollback, feature flags et données de démonstration.
- Terminé lorsque : un lot peut être livré indépendamment et désactivé.
- Délégation : proposition DevOps possible.

## 13. Gate L - Stratégie de tests et plans exécutables

### [x] L01 - Construire la matrice de tests globale (`P0`)

- Dépendances : B02, C03, F01, A05.
- Livrable : exigences -> unités, propriétés, intégration, contrats, E2E,
  sécurité, accessibilité, visuel, imports et pilote pédagogique.
- Terminé lorsque : chaque exigence normative a au moins une preuve prévue.
- Délégation : matrices par domaine possibles.

### [x] L02 - Définir les fixtures canoniques (`P0`)

- Dépendances : B01, G05, E07.
- Livrable : utilisateurs, lexique, listes, structures, modules, médias simulés,
  tentatives, contenus invalides connus et résultats attendus.
- Terminé lorsque : tout le produit sans LLM peut être démontré hors réseau.
- Délégation : jeux de fixtures par domaine possibles.

### [x] L03 - Définir les gates de qualité (`P0`)

- Dépendances : L01, A05.
- Livrable : critères bloquants par lot, couverture utile, budgets, revues,
  captures et pilote humain.
- Terminé lorsque : aucun lot ne peut être déclaré terminé sur ses seuls tests
  unitaires.
- Délégation : proposition possible ; validation locale.

### [ ] L03A - Exécuter les spikes avant le lot de production concerné (`P1`, preuve d'implémentation)

- Dépendances : architecture spécifiée, puis fixture exécutable du lot concerné.
- Livrable : rapports jetables `adopter/rejeter` pour parité FSRS, compositeur
  sous contraintes, correction sans LLM, reprise après crash, import volumique,
  oral simulé, cycle publication/retrait et cache audio.
- Cette tâche ne bloque pas la fermeture documentaire `GATE-G0`. Elle bloque la
  conception de production du mécanisme qu'elle mesure et sa gate ultérieure.
- Terminé lorsque : chaque spike possède hypothèse, fixture, mesure, résultat,
  limites et décision enregistrée ; aucun code de spike n'entre en production.
- Délégation : pistes indépendantes en parallèle.

### [x] L04 - Découper les plans d'implémentation (`P0`)

- Dépendances : toutes les tâches P0 précédentes.
- Livrable : un plan autonome par sous-projet, avec arborescence exacte,
  interfaces, incréments red/green indépendamment vérifiables, commandes,
  résultats et commits. Aucune durée artificielle n'est imposée à un incrément.
- Contrats : documents 27 (workstreams, dépendances, write sets) et 31 (tests,
  changements bornés et résultats attendus par incrément).
- Terminé lorsque : un agent sans contexte peut exécuter une tâche sans inventer
  de décision et qu'un reviewer peut accepter chaque lot indépendamment.
- Délégation : rédaction par plan possible après verrouillage des interfaces.

### [x] L05 - Construire le graphe de délégation (`P0`)

- Dépendances : L04.
- Livrable : tâches parallèles, chemin critique, write sets disjoints, gates de
  revue et ordre d'intégration.
- Terminé lorsque : aucune délégation parallèle ne modifie les mêmes contrats ou
  fichiers sans coordination explicite.
- Délégation : synthèse centrale uniquement.

## 14. Vagues de délégation prévues

### Vague 1 - Audits indépendants

- exhaustivité fonctionnelle et pédagogique ;
- architecture, données et cycle de vie ;
- exécution, tests et délégation ;
- résultat intégré dans ce registre avant toute décision technique.

### Vague 2 - Spécifications par domaine

- profil/diagnostic ;
- vocabulaire/mémoire ;
- langue italienne/boîte grammaticale ;
- exercices/correction ;
- curriculum/sprint ;
- progression/évaluations ;
- génération/outils ;
- UX/accessibilité ;
- exploitation et imports.

Les agents produisent des propositions dans des fichiers séparés. Les contrats
transversaux restent sous responsabilité de la synthèse centrale.

### Vague 3 - Relectures contradictoires

- revue de cohérence métier ;
- revue linguistique ;
- revue sécurité/confidentialité ;
- revue testabilité ;
- revue UX ;
- revue de conservation V1.

### Vague 4 - Plans d'implémentation

Un plan par sous-projet seulement après fermeture des gates A à L03.

## 15. Gate finale avant retour avec découpage ultra-précis

Le découpage d'implémentation ne doit être présenté comme prêt que si :

- [x] toutes les tâches documentaires `P0` sont terminées ;
- [x] aucune décision produit `P0` ne reste ouverte ;
- [x] la matrice V1 couvre routes, modèles, écrans et données ;
- [x] les contrats de domaines ont passé les revues contradictoires ;
- [x] le pilote italien de trois jours possède une fixture normative spécifiée ;
- [x] les onze outils et les scénarios du runner déterministe sont spécifiés ;
- [x] la matrice de tests couvre chaque exigence ;
- [x] imports et opérations destructrices ont fixtures et rollback spécifiés ;
- [x] les parcours UX ont été capturés puis redessinés ;
- [x] le graphe de délégation possède des write sets disjoints ;
- [x] chaque plan et incrément peut être exécuté sans décision P0 improvisée.

Cette checklist atteste `specified`, pas `implemented` ni `verified`. Les spikes,
fixtures exécutables, runner, revues humaines et preuves G1-G7 restent à produire
pendant l'implémentation.

## 16. Gates de passage normatives

- **G0 Spec-ready** : 100 % des capacités tracées et zéro décision `P0` ouverte.
- **G1 Contract-ready** : schémas validables, machines à états, erreurs,
  idempotence et compatibilité définis.
- **G2 Core-ready** : suites déterministes rejouables ; différences autorisées
  d'horodatage et d'identifiant explicitement normalisées.
- **G3 Data-lifecycle-ready** : imports idempotents, sauvegarde restaurée,
  suppressions vérifiées et rollback chronométré.
- **G4 UX-ready** : parcours critiques desktop, mobile, clavier, zoom 200 % et
  cible WCAG approuvée, puis revue humaine sans défaut bloquant.
- **G5 Pedagogy-ready** : pilote italien revu linguistiquement et réussi par les
  scénarios débutant, faux débutant et intermédiaire.
- **G6 AI-ready** : le produit complet et la façade d'outils sont démontrés hors
  réseau, sans fournisseur et avec artefacts de preuve.
