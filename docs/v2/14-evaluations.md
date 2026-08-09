# Polyglot V2 - Évaluations des quatre compétences

## 1. Principes

- Quatre évaluations indépendantes.
- Aucun score global ne masque une modalité absente.
- Les définitions et formes sont versionnées.
- Les réponses sont sauvegardées et les soumissions idempotentes.
- Une épreuve met à jour uniquement les facettes réellement mesurées.
- Les nouveaux éléments mesurent le transfert ; leur échec isolé n'ouvre pas
  automatiquement une dette.
- Les paramètres V0 sont calibrables, mais les contrats restent stables.

## 2. Protocole commun

1. Vérifier disponibilité et prérequis techniques.
2. Choisir une forme parallèle non récemment exposée.
3. Figer items, ordre, médias, critères et politique.
4. Démarrer un minuteur serveur.
5. Sauvegarder après chaque réponse.
6. Autoriser reprise selon la politique de la modalité.
7. Soumettre ou expirer.
8. Vérifier intégrité et couverture.
9. Corriger automatiquement, humainement ou en simulation.
10. Produire résultat, confiance et preuves admissibles.
11. Afficher recommandations sans révéler de banque active.

### 2.1 Sélection déterministe d'une forme

`ASSESSMENT_SELECTION_V0` reçoit profil, modalité, révision de référentiel,
vecteur de progression, historique d'exposition, accommodations, capacités
média, banque publiée et graine. Il exclut d'abord les formes retirées,
incompatibles, exposées à ce profil dans les 14 jours, ou contenant un item déjà
vu par ce profil dans sa fenêtre de sécurité.

La forme retenue respecte, par poids : 60 % de cibles dans la bande actuelle,
20 % d'ancrage inférieur et 20 % de transfert à un cran supérieur ou sur cibles
nouvelles compatibles. Les formes parallèles partagent 30 à 40 % d'items
d'ancrage au niveau de la banque, mais aucun ancrage déjà exposé à l'utilisateur
n'est resservi dans sa fenêtre. Les quotas de facettes des sections 3 à 6, le
temps, les médias et les accommodations sont des contraintes dures.

Parmi les formes admissibles, le moteur minimise successivement exposition
antérieure, écart aux quotas, incertitude de calibration et coût média ; les
égalités sont départagées par la graine. Forme, révisions, ordre et paramètres de
calibration sont épinglés dans `AssessmentRun`. Si aucune forme n'atteint les
minimums, le démarrage échoue avec `assessment_form_unavailable` : il n'existe
aucune forme improvisée ni fallback LLM.

## 3. Compréhension écrite

Protocole initial : 25 minutes, trois textes, dix-huit items.

Couverture :

- information littérale ;
- relation entre idées ;
- inférence ;
- intention et point de vue ;
- registre ;
- vocabulaire en contexte ;
- stratégie face à un élément inconnu.

Les QCM corrigent le hasard dans leur poids. Au moins un item par texte exige une
réponse construite courte ou un classement afin de diversifier le protocole.

Pondérations `READING_SCORE_V0` : information littérale `0.25`, relations et
inférence `0.30`, intention/point de vue `0.20`, registre `0.10`, vocabulaire en
contexte `0.10`, stratégie face à l'inconnu `0.05`. Chaque catégorie répartit
son poids entre ses items. Minimum valide : douze items évaluables et couverture
pondérée `>= 0.80`.

## 4. Compréhension orale

Protocole initial : 25 minutes, six segments et seize items.

- écoute globale puis détaillée ;
- nombre de lectures fixé par item et tracé ;
- vitesse et variété adaptées à la difficulté ;
- transcription masquée pendant l'épreuve ;
- indisponibilité audio entraîne remplacement avant départ ou couverture réduite
  explicite, jamais un échec utilisateur ;
- l'écoute ne produit aucune preuve de production orale.

Pondérations `LISTENING_SCORE_V0` : information globale `0.20`, détail `0.25`,
relations/inférence `0.25`, intention/registre `0.15`, stratégie perceptive
`0.15`. Minimum valide : dix items évaluables, au moins quatre segments et
couverture pondérée `>= 0.80`.

## 5. Expression écrite

Protocole initial : 40 minutes, deux tâches.

1. Message fonctionnel contraint.
2. Production plus soutenue : récit, description ou argumentation selon profil.

Grille `WRITING_RUBRIC_V0` :

| Critère | Poids |
|---|---:|
| Accomplissement de la tâche | 25 % |
| Cohérence et organisation | 25 % |
| Contrôle grammatical | 20 % |
| Étendue des moyens | 15 % |
| Adéquation lexicale et registre | 15 % |

La correction conserve annotations, critères, alternatives acceptables,
confiance et identité du correcteur.

Chaque critère est noté sur une échelle ancrée `0..4` : `0` absent ou
contradictoire, `1` très limité, `2` fonctionnel fragile, `3` solide, `4` précis
et autonome au niveau de difficulté de la forme. Le score critère est `note/4`.
Les deux tâches ont des poids `0.40` et `0.60`. Une seule tâche finalisée donne
un résultat indicatif avec couverture `0.40` ou `0.60`, jamais une bande valide.

## 6. Expression orale

Protocole initial : 18 minutes.

1. Lecture ciblée pour phénomènes phonologiques.
2. Réponses guidées courtes.
3. Monologue préparé court.
4. Interaction simulée.

Avant STT/temps réel :

- la consigne et le minuteur fonctionnent ;
- l'enregistrement local est facultatif et soumis au consentement ;
- l'auto-évaluation structurée crée une observation faible, jamais une maîtrise ;
- une revue humaine facultative peut produire des preuves ;
- sans correcteur qualifié, les critères concernés sont `not_evaluable`.

Grille `SPEAKING_RUBRIC_V0` :

| Critère | Poids |
|---|---:|
| Interaction et réponse | 25 % |
| Intelligibilité | 25 % |
| Fluidité | 20 % |
| Contrôle grammatical | 15 % |
| Étendue, lexique et registre | 15 % |

La même échelle ancrée `0..4` s'applique. Lecture ciblée `0.15`, réponses
guidées `0.20`, monologue `0.25`, interaction `0.40`. Sans revue humaine ou
correcteur qualifié, les segments restent `not_evaluable` ; l'auto-évaluation
ne remplit pas cette grille et ne produit pas de score de modalité.

## 7. Calcul commun du résultat

Pour un item fermé : `incorrect = 0`, `partially_correct = 0.5`, `correct = 1`.
Pour un QCM à `k` options, la contribution est
`clamp((raw_score - 1/k) / (1 - 1/k), 0, 1)`. Une réponse construite n'applique
aucune correction de hasard.

```text
coverage = evaluable_answered_weight / planned_weight_after_defect_exclusion
score = Σ(item_or_criterion_weight × normalized_score)
        / Σevaluable_answered_weight
correction_factor = weighted_mean(correction_confidence)
sample_factor = min(sqrt(evaluable_units / minimum_units), 1)
integrity_factor = 1.00 normally, or a documented value in [0,1]

result_confidence = clamp(
  coverage × correction_factor × sample_factor × integrity_factor,
  0,
  1
)
```

Une accommodation déclarée, y compris temps étendu, pause, clavier ou
alternative gestuelle, conserve `integrity_factor = 1.00`. Une adaptation qui
change la modalité crée un protocole différent et ne crédite que la modalité
réellement mesurée. Une forme est `valid` si couverture `>= 0.80`, échantillon
minimum atteint, confiance `>= 0.60` et aucun incident bloquant. Sinon le
résultat est `indicative` ou `not_evaluable` et ne produit pas de preuve forte.

Exemple lecture : poids évaluables `0.90`, contributions correctes `0.63`,
partielles `0.09` à score `0.5`, soit score
`(0.63 + 0.045) / 0.90 = 0.75`. Avec confiance de correction `1`, 16 items pour
un minimum de 12 et intégrité `1`, la confiance vaut `0.90`. Résultat : bande
`ASSESS-B3`, confiance `0.90`, couverture `0.90`.

## 8. Bandes internes

Bandes `ASSESSMENT_BANDS_V0`, sans équivalence CECR automatique :

- `ASSESS-B0` : score < 0.25 ;
- `ASSESS-B1` : 0.25 à 0.44 ;
- `ASSESS-B2` : 0.45 à 0.64 ;
- `ASSESS-B3` : 0.65 à 0.79 ;
- `ASSESS-B4` : ≥ 0.80.

En écriture, `accomplissement de la tâche` est critique. À l'oral,
`interaction` et `intelligibilité` sont critiques. Une note brute inférieure à
`1` sur `4` sur un critère critique plafonne la modalité à `ASSESS-B1`. Le
résultat affiche score, bande, confiance, couverture et critères limitants.

## 9. Disponibilité et fréquence

- Une première évaluation est disponible après diagnostic ou sur demande.
- Le système recommande une nouvelle évaluation lorsqu'il existe assez de
  nouvelles preuves ou après 30 jours, sans l'imposer.
- Une forme abandonnée ou terminée ne peut être reprise.
- Une forme interrompue est reprenable pendant 24 heures si son protocole
  autorise la pause.
- Une forme parallèle équivalente n'est réutilisée qu'après 14 jours.
- Le nombre de tentatives n'est pas limité, mais leur indépendance est tracée et
  les formes récentes sont évitées.

## 10. Intégrité et confiance

La confiance diminue lorsque :

- couverture insuffisante ;
- média indisponible ;
- trop d'items non évaluables ;
- correction incertaine ;
- interruption longue ;
- comportement technique anormal ;
- forme partiellement déjà exposée.

Une confiance insuffisante produit un résultat indicatif, sans mise à jour forte
de maîtrise.

## 11. Effets sur le profil

- Chaque item finalisé peut produire des preuves atomiques.
- Les preuves d'évaluation ont le poids source maximal, pas une autorité absolue.
- Une évaluation ne valide aucun ensemble inférieur par défaut.
- Le résultat de modalité devient une projection indépendante.
- Une estimation CECR éventuelle est calculée à partir du vecteur et marquée avec
  confiance/méthode ; elle ne pilote ni déblocage ni contenu.

## 12. Reprise et erreurs

- section, réponse, média, temps restant et ordre sont restaurés exactement ;
- double soumission retourne le même résultat ;
- réponse divergente après soumission provoque un conflit ;
- expiration fige les réponses présentes ;
- correction en panne place le run en `review_required` ;
- aucun fallback LLM/fournisseur silencieux ;
- un item défectueux est exclu et la couverture recalculée.

## 13. Tests normatifs

1. Reprise navigateur sans perte ni minuteur réinitialisé.
2. Double soumission sans duplication.
3. Expiration avec réponses partielles.
4. Audio absent avant et pendant une épreuve.
5. Item défectueux exclu sans sanction.
6. Lecture n'améliore ni écoute ni production.
7. Oral simulé sans STT reste exécutable.
8. Auto-évaluation orale ne produit pas `reliable`.
9. Correction contestée suspend les preuves.
10. Forme récente non reproposée avant délai.
11. Couverture insuffisante réduit confiance.
12. Aucun niveau CECR automatique avant calibration validée.
