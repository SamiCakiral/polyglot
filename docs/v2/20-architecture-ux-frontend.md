# Polyglot V2 - Architecture UX et frontend

## 1. Principes

- L'écran principal est l'expérience, pas une page marketing.
- L'interface répond toujours à : quoi faire, pourquoi, et où en suis-je.
- Une activité ne doit jamais être présentée comme une maîtrise.
- La correction apparaît avant la suite, sans humilier ni masquer l'incertitude.
- La reprise est un comportement central.
- Les données avancées existent sans encombrer l'action quotidienne.
- Mobile, clavier, audio et zoom sont conçus dès le contrat.
- Le frontend ne décide jamais de la pédagogie.

## 2. Navigation

Navigation principale :

1. **Aujourd'hui** ;
2. **Apprendre** ;
3. **S'entraîner** ;
4. **Vocabulaire** ;
5. **Progression** ;
6. **Évaluer**.

Navigation secondaire : profil de langue, préférences, aide et Atelier selon rôle.

Sur mobile, les cinq destinations les plus fréquentes sont dans une barre basse ;
Évaluer et les réglages passent dans le menu lorsque l'espace manque.

## 3. Routes fonctionnelles

```text
/today
/learn
/learn/modules/:moduleId
/practice
/practice/configure
/sprints/:runId
/vocabulary
/vocabulary/lists/:listId
/vocabulary/senses/:senseId
/progress
/progress/skills/:skillId
/assess
/assess/:modality
/assess/runs/:runId
/language-profile
/settings
/authoring/*
```

Chaque route sensible vérifie le profil de langue actif. Le changement de langue
cible est explicite et ne mélange jamais les données.

## 4. Onboarding et diagnostic

### Étapes

1. créer le compte ;
2. choisir langue maternelle ;
3. choisir italien ;
4. déclarer expérience, objectifs et temps ;
5. expliquer brièvement le diagnostic ;
6. exécuter les micro-épreuves ;
7. afficher profil par modalité et confiance ;
8. orienter vers fondations ou premier module ;
9. permettre de consulter les preuves sans imposer un score global.

États : nouveau, diagnostic sauvegardé, incomplet, indisponibilité audio,
résultat indéterminé, fondations requises, dispense et reprise.

Le chat futur est une étape du diagnostic, pas l'intégralité de la décision.

## 5. Aujourd'hui

### Zone primaire

- durée sélectionnée et modification ;
- sprint prêt ou en préparation ;
- bouton commencer/reprendre ;
- résumé des blocs ;
- explication concise des priorités ;
- indication dette/rappels/nouveauté ;
- aucun faux pourcentage de maîtrise.

### Zone secondaire

- deux recommandations principales et une optionnelle ;
- prochaine étape du module ;
- activité récente ;
- raccourci entraînement libre ;
- état des services uniquement lorsqu'il affecte l'action.

États : aucun profil, fondations, plan en préparation, prêt, repris, backlog,
contenu indisponible, sprint terminé et jour de repos volontaire.

## 6. Lecteur de sprint

### Shell stable

- en-tête compact : bloc, progression, temps indicatif, quitter ;
- objectif pédagogique court ;
- zone de stimulus stable ;
- zone de réponse ;
- actions contextuelles ;
- tiroir Word Bank ;
- sauvegarde visible mais discrète ;
- feedback dans le même flux ;
- navigation suivante seulement après état autorisé.

Le shell ne change pas de largeur/hauteur de façon brutale entre réponse,
correction et aide. Les contenus longs défilent dans la page, pas dans des cartes
imbriquées.

### Commandes

- sauvegarder automatiquement ;
- soumettre ;
- demander l'aide suivante ;
- écouter/rejouer ;
- signaler une ambiguïté ;
- contester la correction ;
- passer ;
- arrêter le sprint ;
- reprendre.

### Bilan

- activités réellement terminées ;
- éléments travaillés, pas déclarés acquis ;
- erreurs devenues dettes ;
- rappels planifiés ;
- durée réelle ;
- prochaine action ;
- détails optionnels.

## 7. Composants d'exercices

Le frontend fournit un renderer par famille :

- choix et discrimination ;
- appariement/classement ;
- carte et rappel ;
- texte à trou et grille morphologique ;
- réponse textuelle ;
- reconstruction ordonnée ;
- lecteur texte/compréhension ;
- lecteur audio/transcription ;
- transformation Gym ;
- production étendue ;
- shadowing ;
- auto-correction et comparaison.

Chaque renderer respecte le contrat commun et ne contient aucune règle italienne.

## 8. Word Bank

### Vue générale

- recherche instantanée ;
- filtres langue, état, modalité, domaine, liste, dette et échéance ;
- compteurs rencontré/reconnu/utilisable/fiable/à revoir ;
- couverture d'un référentiel choisi ;
- écarts écrit/oral et réception/production ;
- listes dynamiques recommandées ;
- ajout manuel.

### Fiche d'un sens

- lemme, formes, prononciations et sens ;
- équivalents français qualifiés ;
- cadres d'usage, collocations, registre ;
- relations et confusions ;
- état par modalité ;
- preuves, contradictions et confiance ;
- rencontres et contextes autorisés ;
- listes et prompts mémoire ;
- dette et prochaine activité ;
- corriger sens, fusionner/signaler doublon, archiver ou entraîner.

### Listes

- manuelles, éditoriales et dynamiques clairement distinguées ;
- clonage, fusion, archive et snapshot ;
- association à module/session ;
- prévisualisation de l'effet sur la nouveauté ;
- historique de révision ;
- export explicite.

## 9. Apprendre

- module actuel et mission ;
- journées ordonnées avec états ;
- objectifs et contextes ;
- détails de la journée courante ;
- modules disponibles/recommandés ;
- prérequis manquants ;
- pause, reprise ou abandon ;
- aucun verrou arbitraire fondé sur CECR.

Une journée terminée est affichée comme parcourue ; la maîtrise associée reste
visible séparément.

## 10. Entraînement libre

Configuration progressive :

- objectif rapide ou mode avancé ;
- modalité ;
- compétence/structure ;
- liste ou requête Word Bank ;
- primitive ;
- durée ;
- nouveauté autorisée ;
- entraînement ou test ;
- aperçu et avertissement de prérequis.

Les valeurs recommandées sont présélectionnées. Les réglages avancés restent
accessibles sans encombrer le parcours principal.

## 11. Progression

### Vue quatre compétences

- compréhension écrite ;
- compréhension orale ;
- expression écrite ;
- expression orale ;
- état, confiance, fraîcheur et dernière évaluation séparés ;
- historique sans moyenne globale trompeuse.

### Détails

- fonctions communicatives ;
- structures grammaticales ;
- lexique par référentiel ;
- prononciation ;
- stratégies ;
- preuves récentes ;
- contradictions ;
- prochaine vérification ;
- lancement d'un entraînement ou test ciblé.

La carte utilise `non observé`, `découvert`, `en cours`, `fiable`, `maîtrisé`,
`à revoir` et `non évaluable`, avec explications accessibles.

## 12. Évaluer

- quatre cartes de modalités, compactes et comparables ;
- dernière tentative, confiance et disponibilité ;
- détail du protocole avant départ ;
- matériel requis ;
- reprise ;
- minuteur ;
- résultats critériés ;
- historique ;
- recommandations ;
- aucun affichage de réponse avant finalisation.

Pour l'oral simulé, l'interface distingue nettement auto-évaluation, enregistrement
et éventuelle revue humaine.

## 13. Atelier pédagogique

Destinations : compétences, structures, lexique, contenus, exercices, modules,
packs, validations et jobs.

Fonctions :

- créer une révision ;
- comparer versions ;
- lancer validateurs ;
- prévisualiser avec fixture ;
- consulter erreurs ;
- demander revue ;
- approuver selon rôle ;
- publier ou retirer ;
- inspecter provenance et usages historiques ;
- exécuter le runner sans IA.

Les écrans privilégient tableaux, formulaires et diff ; pas de composition
marketing ni de cartes décoratives imbriquées.

## 14. États globaux obligatoires

Chaque écran définit :

- chargement initial ;
- contenu prêt ;
- état vide utile ;
- erreur récupérable ;
- autorisation refusée ;
- donnée retirée ;
- conflit de version ;
- sauvegarde en cours/confirmée/échouée ;
- mode hors connexion consultatif ;
- contenu extrême et texte long.

## 15. Design system fonctionnel

- grille et espacements constants ;
- typographie lisible sans taille liée à la largeur viewport ;
- couleurs non utilisées seules pour transmettre un état ;
- boutons icône pour actions familières, avec tooltip ;
- contrôles natifs adaptés : toggles, sliders, segments, menus, tabs ;
- rayons contenus, maximum 8 px hors composant historique justifié ;
- dimensions stables pour contrôles et lecteurs ;
- pas de carte dans une carte ;
- audio et feedback n'occasionnent aucun déplacement incohérent ;
- thème clair prioritaire, thème sombre optionnel après parité.

## 16. Responsive et accessibilité

- 320 px minimum ;
- aucune barre latérale permanente sur mobile ;
- Word Bank en panneau plein écran mobile ;
- cibles tactiles suffisantes ;
- lecteur utilisable sans survol ;
- clavier intégral ;
- focus restauré après correction/modal ;
- annonces live non intrusives ;
- transcriptions ;
- pause des contenus temporels ;
- zoom 200 % ;
- réduction d'animations ;
- WCAG 2.2 AA.

## 17. Télémétrie UX autorisée

- écran/bloc ouvert ;
- action soumise, passée ou abandonnée ;
- aide demandée ;
- sauvegarde/reprise ;
- latence et erreur ;
- contrôle audio ;
- correction contestée.

Aucun texte saisi, réponse, audio ou traduction privée n'est envoyé dans la
télémétrie générale.

## 18. Tests UX obligatoires

- nouvel utilisateur jusqu'au pilote jour 3 ;
- profil intermédiaire dispensé ;
- reprise sprint et évaluation ;
- Word Bank avec 0, 10 et 100 000 sens ;
- dette mixte ;
- correction ambiguë/contestée ;
- média absent ;
- réseau lent ;
- deux appareils/conflit ;
- clavier seul ;
- lecteur d'écran ;
- mobile 320 px ;
- zoom 200 % ;
- contenus italiens et français très longs ;
- audit visuel humain desktop/mobile.
