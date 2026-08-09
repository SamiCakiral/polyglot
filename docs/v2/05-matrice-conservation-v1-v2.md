# Polyglot V2 - Matrice de conservation fonctionnelle

## 1. Usage

Les attributs `owner`, `lot`, `test` et `approbateur` sont normalisés dans
`docs/v2/23-tracabilite-execution.md`, donc non dupliqués ici.

Cette matrice empêche la reconstruction de supprimer silencieusement une idée
de la V1. Chaque ligne doit recevoir, pendant la planification :

- un lot d'implémentation ;
- un responsable ou une tâche ;
- un critère d'acceptation détaillé ;
- un test automatisé lorsque cela est possible ;
- une décision explicite si la capacité change ou disparaît.

Les statuts initiaux signifient :

- **Conserver** : comportement utile à reproduire ;
- **Refondre** : intention conservée, modèle ou interaction remplacé ;
- **Remplacer** : ancien comportement volontairement supprimé au profit d'une
  règle produit explicitement plus juste ;
- **Archiver** : données ou contenus gardés comme source, sans reproduire le
  fonctionnement ;
- **Différer** : contrat prévu, réalisation après le coeur du produit.

## 2. Identité et profil

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-ID-001 | Inscription, connexion, déconnexion | Identité | Conserver | Parcours navigateur et tests d'autorisation |
| V1-ID-002 | Modifier identifiant et mot de passe | Identité | Conserver | Validation, révocation et erreurs sûres |
| V1-ID-003 | Langue maternelle | Profil | Conserver | Toute langue cible est liée à une langue d'appui |
| V1-ID-004 | Langues connues, niveau et expérience | Profil | Refondre | Utilisées comme contexte, jamais comme preuve suffisante |
| V1-ID-005 | Objectifs et centres d'intérêt | Profil/Curriculum | Conserver | Influencent un module avec raison visible |
| V1-ID-006 | Préférence de correction | Profil/Correction | Conserver | Change le ton, pas la vérité du verdict |
| V1-ID-007 | Temps quotidien | Sprint | Étendre | Budget 10-60 minutes par pas de 5, ancres éditoriales 15/30/45/60 |
| V1-ID-008 | Préférence de voix | Médias | Conserver | Voix appliquée lorsque disponible |
| V1-ID-009 | Autosauvegarde du profil | API/UX | Conserver | Rechargement sans perte |

## 3. Tableau de bord et continuité

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-DASH-001 | Cartes nouvelles, dues et difficiles | Aujourd'hui/Vocabulaire | Conserver | Totaux explicables depuis les échéances |
| V1-DASH-002 | Recommandation de révision | Recommandations | Refondre | Chaque choix expose sa raison |
| V1-DASH-003 | Séries et activité du jour | Statistiques | Conserver | Fuseau horaire et jours manqués testés |
| V1-DASH-004 | Programmes actifs | Modules | Refondre | Module actuel et prochaine action visibles |
| V1-DASH-005 | Reprise de session | Sprint | Conserver | Reprise exacte au dernier état confirmé |
| V1-DASH-006 | Résumé par langue | Progression | Refondre | Quatre compétences et confiance séparées |

## 4. Paquets, cartes et listes

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-CARD-001 | Créer, modifier et supprimer un paquet | Listes/Vues de révision | Conserver | Cycle complet avec autorisations |
| V1-CARD-002 | Paquets personnels, publics et de programme | Listes/Partage | Refondre | Provenance et droits explicites |
| V1-CARD-003 | Importer un paquet public | Import | Conserver | Copie ou abonnement défini sans ambiguïté |
| V1-CARD-004 | Créer et modifier une carte | Mémoire | Conserver | Deux directions indépendantes |
| V1-CARD-005 | Supprimer ou archiver une carte | Mémoire | Conserver | Confirmation, historique et effet FSRS explicités |
| V1-CARD-006 | Création en masse | Import | Conserver | Rapport d'erreurs par ligne |
| V1-CARD-007 | Import JSON par fichier ou texte | Import | Conserver | Schéma versionné et aperçu avant validation |
| V1-CARD-008 | Compatibilité question/réponse | Import générique | Refondre | Format documenté sans dépendance aux données V1 |
| V1-CARD-009 | Détection de doublons | Lexique/Import | Refondre | Distingue même forme, sens distinct et vrai doublon |
| V1-CARD-010 | Catégories multiples | Listes/Étiquettes | Conserver | Filtres et statistiques corrects |
| V1-CARD-011 | Créer, renommer, colorer et supprimer une catégorie | Listes/Étiquettes | Conserver | Cycle CRUD et conséquences sur les cartes testés |
| V1-CARD-012 | Création automatique de catégories | Import | Conserver | Prévisualisation et confirmation |
| V1-CARD-013 | Mise à jour pendant un import | Import | Conserver | Stratégie de conflit explicite |
| V1-CARD-014 | Réinitialisation d'un paquet | Mémoire | Refondre | Confirmation et journal, sans effacer les faits bruts |
| V1-CARD-015 | Jeux de cartes historiques | Archives de contenu | Archiver | Réutilisation facultative après audit seulement |
| V1-CARD-016 | Mémoire de tous les mots rencontrés | Graphe lexical personnel | Conserver | Chaque rencontre a provenance sans créer une fausse maîtrise |
| V1-CARD-017 | État lexical par sens et modalité | Progression lexicale | Refondre | Reconnaissance, rappel et production restent séparés |
| V1-CARD-018 | Relations entre mots et expressions | Catalogue/Graphe lexical | Conserver | Arêtes typées, versionnées et sourcées |
| V1-CARD-019 | Vue générale des connaissances lexicales | Word Bank | Conserver | Couverture seulement sur référentiels bornés |
| V1-CARD-020 | Détection automatique des lacunes | Recommandations | Conserver | Écart explicable entre objectif et preuves utilisateur |

## 5. Révision autonome

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-REV-001 | Recto-verso et verso-recto | Primitive carte | Conserver | Échéances et historique séparés |
| V1-REV-002 | Mélange des directions | Entraînement libre | Conserver | Distribution reproductible avec graine |
| V1-REV-003 | Retournement manuel | Lecteur d'exercice | Conserver | Tentative et auto-évaluation enregistrées |
| V1-REV-004 | Réponse écrite | Primitive rappel | Conserver | Normalisation et alternatives acceptables |
| V1-REV-005 | Navigation arrière/avant | Lecteur | Conserver | Aucune double comptabilisation |
| V1-REV-006 | Reprise et redémarrage | Exécution | Conserver | États interrompu et recommencé distincts |
| V1-REV-007 | Filtres de catégories ET/OU | Listes | Conserver | Tests combinatoires |
| V1-REV-008 | Catégories obligatoires | Sélecteur | Conserver | Chaque session respecte la contrainte |
| V1-REV-009 | Cartes non catégorisées | Sélecteur | Conserver | Inclusion explicite |
| V1-REV-010 | Filtre de maîtrise | Progression/Mémoire | Refondre | Utilise états V2 plutôt que lettres opaques |
| V1-REV-011 | Limite du nombre de cartes | Entraînement libre | Conserver | Limite stricte et estimation de durée |
| V1-REV-012 | Historique de réponses | Événements | Conserver | Historique immuable et consultable |
| V1-REV-013 | SM-2 historique | Migration | Archiver | Import sans usage comme moteur courant |
| V1-REV-014 | FSRS bidirectionnel | Mémoire | Conserver | Tests de propriétés sur fixtures V2 canoniques |
| V1-REV-015 | Notes A à F | Présentation | Refondre | État et confiance compréhensibles |

## 6. Création de programme et curriculum

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-CURR-001 | Assistant de création | Onboarding de module | Refondre | Produit un module cohérent et modifiable |
| V1-CURR-002 | Langue cible et langue d'explication | Profil/Pack | Conserver | Toutes les consignes respectent la paire |
| V1-CURR-003 | Niveau et expérience initiaux | Diagnostic | Refondre | Déclaration suivie de vérification |
| V1-CURR-004 | Objectifs et priorités | Curriculum | Conserver | Traçabilité vers objectifs du module |
| V1-CURR-005 | Sujets à favoriser ou éviter | Curriculum | Conserver | Contraintes respectées par contenus publiés |
| V1-CURR-006 | Style et contexte géographique | Contextes | Conserver | Variété sans stéréotypes forcés |
| V1-CURR-007 | Activer et ordonner des exercices | Sprint | Refondre | Le moteur protège les éléments indispensables |
| V1-CURR-008 | Durée de 10 à 60 minutes | Sprint | Conserver | Composition sous budget réel |
| V1-CURR-009 | Choix des mutations FSI | Gym libre | Conserver | Prérequis et niveau toujours appliqués |
| V1-CURR-010 | Ressources vidéo/podcast | Médias | Conserver | Disponibilité et remplacement contrôlés |
| V1-CURR-011 | Paquet dédié au programme | Listes de module | Refondre | Plusieurs listes avec rôles explicites |
| V1-CURR-012 | Génération initiale automatique | Atelier/Génération | Refondre | Brouillons validés avant publication |
| V1-CURR-013 | Activation et suppression | Modules | Conserver | Archivage et suppression testés |
| V1-CURR-014 | Rééditer et reconfigurer un programme | Modules | Conserver | Changements futurs sans réécrire les sessions passées |

## 7. Sprint quotidien

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-SPRINT-001 | Vocabulaire thématique nouveau | Sélection du jour | Conserver | Relié au module et aux exercices |
| V1-SPRINT-002 | Révisions dues | Mémoire/Sprint | Conserver | Priorité sur nouveauté selon politique |
| V1-SPRINT-003 | Dette lexicale | Dette unifiée | Refondre | Cause, échéance et résolution explicites |
| V1-SPRINT-004 | Version cible vers maternelle | Primitive compréhension/traduction | Conserver | Texte, réponse et correction versionnés |
| V1-SPRINT-005 | Assistant de traduction | Aides | Refondre | Aide minimale, coût et observation enregistrés |
| V1-SPRINT-006 | Conservation du texte pour J+1 | Rappel différé | Conserver | Utilise une source corrigée et figée |
| V1-SPRINT-007 | Explication de structure | Boîte grammaticale | Refondre | Fonction, contraste, piège et exemples |
| V1-SPRINT-008 | Construction guidée | Primitive production | Conserver | Cible et aides déclarées |
| V1-SPRINT-009 | Transformations FSI | Gym | Refondre | Transformations choisies par compétence due |
| V1-SPRINT-010 | Traduction avec structure cible | Gym/Transfert | Conserver | Vérifie réellement la structure |
| V1-SPRINT-011 | Shadowing vidéo | Primitive orale | Conserver | Segment et auto-évaluation tracés |
| V1-SPRINT-012 | Shadowing TTS | Médias/Primitive orale | Conserver | Texte, voix et vitesse versionnés |
| V1-SPRINT-013 | Reconstruction J+1 | Rappel différé | Conserver | Comparaison et erreurs structurées |
| V1-SPRINT-014 | Écriture avec mission | Primitive production | Conserver | Grille, mots et structures cibles |
| V1-SPRINT-015 | Mots imposés | Liaison session-liste | Conserver | Usage mesuré sans exiger artificiellement tous les mots |
| V1-SPRINT-016 | Bilan de sprint | Aujourd'hui/Progression | Refondre | Activité, acquis provisoires et suite séparés |

## 8. Outils pendant les exercices

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-TOOL-001 | Barre de vocabulaire | Lecteur/Listes | Conserver | Disponible sans masquer l'exercice |
| V1-TOOL-002 | Révéler une traduction | Aides | Refondre | Ne modifie pas arbitrairement FSRS |
| V1-TOOL-003 | Ajouter un mot contextuellement | Lexique personnel | Conserver | Sens et contexte confirmés avant ajout |
| V1-TOOL-004 | SOS de traduction | Aides/Dette | Conserver | Quota configurable et dette ciblée |
| V1-TOOL-005 | Jetons quotidiens | Politique d'aide | Refondre | Option pédagogique, pas monnaie artificielle obligatoire |
| V1-TOOL-006 | État persistant par module | Exécution | Refondre | Modèle relationnel et événements |
| V1-TOOL-007 | Résultats par module | Observations | Refondre | Résultats typés par primitive |
| V1-TOOL-008 | Arrêt anticipé | Exécution | Conserver | Travail confirmé sauvegardé |
| V1-TOOL-009 | Passer volontairement un bloc | Exécution | Conserver | Distinct d'un abandon, d'une panne et d'une interruption |
| V1-TOOL-010 | Thème hebdomadaire/journalier | Curriculum | Refondre | Module de durée variable et plan versionné |

## 9. Cours, progression et tuteur

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-LEARN-001 | Onboarding par langue | Diagnostic | Refondre | Placement, confiance et fondations |
| V1-LEARN-002 | Langue-pont | Profil | Conserver | Explications adaptées à la langue connue |
| V1-LEARN-003 | Validation automatique des niveaux inférieurs | Progression | Remplacer | Aucune maîtrise sans preuve ; diagnostic peut dispenser |
| V1-LEARN-004 | Prérequis et déblocage | Graphe de compétences | Conserver | Déblocage explicable et testable |
| V1-LEARN-005 | Leçons, cartes et exercices | Catalogue/Modules | Refondre | Contenu découplé de la page progression |
| V1-LEARN-006 | Chat professeur contextuel | Tuteur futur | Différer | Outils bornés et contexte minimal |
| V1-LEARN-007 | Explications et mnémotechniques | Micro-explications | Conserver | Contenus révisables et versionnés |
| V1-LEARN-008 | Maîtrise par pilier | États de compétences | Remplacer | Preuves multiples, délai et confiance |
| V1-LEARN-009 | Suppression d'une langue | Profil/Données | Conserver | Portée claire et export préalable possible |
| V1-LEARN-010 | 44 cours italiens | Archive et matière éditoriale | Archiver | Audit avant réutilisation |
| V1-LEARN-011 | 37 cours japonais | Archive et futur pack | Archiver | Aucun engagement de qualité implicite |
| V1-LEARN-012 | 38 cours turcs | Archive et futur pack | Archiver | Aucun engagement de qualité implicite |

## 10. Exercices libres et adaptation

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-FREE-001 | Choisir langue, type et difficulté | Entraînement libre | Conserver | Prérequis toujours appliqués |
| V1-FREE-002 | Génération d'exercices | Atelier/Génération | Refondre | Préparation, validation et publication |
| V1-FREE-003 | Correction en temps réel | Correcteurs | Refondre | Confiance et panne explicites |
| V1-FREE-004 | Difficulté de 1 à 5 | Difficulté multidimensionnelle | Remplacer | Lexique, structure, tâche et aide séparés |
| V1-FREE-005 | Ajustement automatique | Recommandations | Refondre | Politique déterministe et raison visible |
| V1-FREE-006 | Historique | Événements | Conserver | Recalcul des agrégats possible |
| V1-FREE-007 | Profil de faiblesses | Progression | Refondre | Fondé sur observations typées |
| V1-FREE-008 | Exercice suivant conseillé | Recommandations | Conserver | Explication et possibilité de refus |
| V1-FREE-009 | Conseil de saut | Diagnostic/Dispense | Refondre | Nécessite une preuve suffisante |
| V1-FREE-010 | Préparation au niveau suivant | Évaluation | Refondre | Quatre compétences séparées |

## 11. Évaluations et médias

| ID | Capacité V1 | Destination V2 | Statut | Preuve minimale attendue |
|---|---|---|---:|---|
| V1-ASSESS-001 | Grammaire et vocabulaire isolés | Diagnostic ciblé | Refondre | Utilisés comme indices, pas niveau global |
| V1-ASSESS-002 | Compréhension écrite | Évaluation dédiée | Conserver | Formes connues et transfert nouveau |
| V1-ASSESS-003 | Compréhension orale | Évaluation dédiée | Conserver | Audio contrôlé et rejouages tracés |
| V1-ASSESS-004 | Expression écrite | Évaluation dédiée | Conserver | Grille et preuves consultables |
| V1-ASSESS-005 | Dialogue textuel | Interaction | Conserver | Peut précéder l'expression orale temps réel |
| V1-ASSESS-006 | Expression orale | Évaluation dédiée | Différer partiellement | Protocole simulé avant STT/Live |
| V1-ASSESS-007 | Minuteur | Protocole d'évaluation | Conserver | Configurable et accessible |
| V1-ASSESS-008 | Historique et résultats | Progression | Conserver | Comparaison sans écraser les essais précédents |
| V1-ASSESS-009 | Reprendre une évaluation en cours | Évaluation | Conserver | Section, réponses et minuteur restaurés selon le protocole |
| V1-ASSESS-010 | Consulter correction et explication après réponse | Correction | Conserver | Feedback révélé au bon moment et réévaluable |
| V1-ASSESS-011 | Validation automatique de cours | Progression | Remplacer | Met à jour des preuves, pas un bloc entier arbitraire |
| V1-ASSESS-012 | TTS multilingue et voix | Adaptateur TTS | Conserver | Contrat fournisseur neutre |
| V1-ASSESS-013 | Découvrir disponibilité, langues et voix TTS | Adaptateur TTS | Conserver | États indisponible et voix retirée explicitement gérés |
| V1-ASSESS-014 | YouTube et podcasts | Adaptateur média | Conserver | Source, segment, disponibilité et droits |
| V1-ASSESS-015 | STT | Adaptateur oral | Différer | Port et simulateur présents avant fournisseur |
| V1-ASSESS-016 | LLM local | Adaptateur de génération | Différer | Aucun besoin pour faire fonctionner le coeur |

## 12. Condition de clôture de la transition fonctionnelle

La transition fonctionnelle n'est complète que lorsque :

1. chaque ligne possède un lot et un test ou une justification ;
2. aucun comportement marqué `Conserver` n'est absent du produit cible ;
3. chaque élément `Refondre` possède une comparaison explicite V1/V2 ;
4. chaque élément `Remplacer` a reçu une validation produit ;
5. les archives sont exportables et leur provenance est conservée ;
6. un nouvel utilisateur termine le parcours V2 de bout en bout ;
7. un utilisateur neuf peut construire cartes, listes, échéances et historique
   dans la V2 sans dépendre de la base V1.
