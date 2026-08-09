# Polyglot V2 - Curriculum, modules et compositeur de sprint

## 1. Contrat d'un module

Un module publié comporte :

- une intention communicative principale ;
- une mission finale ;
- `nominal_days` et `max_days`, avec
  `3 <= nominal_days <= max_days <= 30` journées actives ;
- des profils d'entrée compatibles ;
- des compétences prérequises ;
- des fonctions et structures cibles ;
- des référentiels lexicaux obligatoires, recommandés et d'extension ;
- des objectifs dans les quatre modalités ;
- une progression de contextes ;
- des politiques de rappel ;
- des critères de sortie ;
- des variantes de charge ;
- une révision immuable et une provenance.

Le module ne promet pas qu'une durée civile suffit. Une journée active est
consommée lorsque le noyau obligatoire du sprint correspondant est terminé. Un
sprint partiel conserve ses preuves, mais ne valide pas la journée. Une durée
longue approfondit une journée ; elle ne consomme jamais deux `ModuleDay`.

Le module publié est immuable. Une modification crée une nouvelle version. Un
enrôlement commencé garde sa version, sauf migration explicite avec table de
correspondance des objectifs et rapport de différences.

## 2. Arc pédagogique

```mermaid
flowchart LR
    A["Activer connaissances d'ancrage"] --> B["Introduire fonction et lexique"]
    B --> C["Comprendre en contexte"]
    C --> D["Produire avec guidage"]
    D --> E["Rappeler après délai"]
    E --> F["Varier et combiner"]
    F --> G["Transférer"]
    G --> H["Mission finale et consolidation"]
```

Chaque `ModuleDay` déclare :

- objectifs prioritaires et secondaires ;
- contexte et variation ;
- nouveau vocabulaire admissible ;
- vocabulaire support attendu fiable ;
- structures nouvelles ou dues ;
- modalités à couvrir ;
- rappels provenant de journées précédentes ;
- primitives candidates ;
- budget minimal utile ;
- contenu préparé et solutions de remplacement validées.

`ModuleDay` est un ordinal pédagogique, pas une date civile. La date locale
d'apprentissage est figée au démarrage du sprint dans le fuseau IANA du profil.
Un jour sans sprint ne consomme pas de journée de module. Par défaut, un seul
`ModuleDay` peut être validé par date locale ; les sessions supplémentaires
relèvent de l'entraînement libre.

Les types d'arc initiaux sont `discovery`, `guided_use`, `integration`,
`transfer` et `consolidation`. Les journées `transfer` et `consolidation`
partent avec un quota de nouveauté nul, sauf exception éditoriale explicite.

Un module peut publier des gabarits `AdaptiveDay` sans nouveauté. Le
planificateur personnel peut en insérer un avant une journée bloquée par un
prérequis, dans la limite de `max_days`. L'instance adaptative appartient à
l'enrôlement et ne modifie pas le module publié. Une fois `max_days` atteint,
la dette non bloquante est reportée ; une dette encore bloquante conduit à un
module de consolidation séparé.

## 3. Préparation d'un module

Le planificateur reçoit : profil, objectifs, pack, compétences, Word Bank,
disponibilité et préférences. Il produit une révision complète avant le début :

1. sélectionner objectifs et mission finale ;
2. calculer prérequis manquants ;
3. construire le graphe de dépendances ;
4. choisir les contextes et leur progression ;
5. répartir lexique, structures et modalités ;
6. placer rappels J+1 et espacés ;
7. sélectionner les primitives ;
8. préparer contenus et correcteurs ;
9. valider charge, couverture et cohérence ;
10. publier le module ou retourner des erreurs précises.

Une régénération partielle ne modifie jamais les journées déjà exécutées. Elle
crée une nouvelle révision et conserve une table de correspondance des objectifs.

## 4. Entrées du compositeur quotidien

- profil et journée pédagogique ;
- inscription et `ModuleDay` courant ;
- budget exact de 10 à 60 minutes inclus, par pas de 5 minutes ;
- date locale, fuseau et instant de coupure ;
- tâches J+1 dues ;
- invites mémoire dues ;
- dettes et urgences ;
- états de maîtrise et confiance ;
- snapshot Word Bank ;
- équilibre récent des quatre modalités ;
- contenus/instances prêts ;
- ressources média disponibles ;
- choix d'accessibilité ;
- version de politique et graine.

Ces entrées forment un `PlanningSnapshot` versionné. Les événements postérieurs
à l'instant de coupure n'influencent pas le plan. Le snapshot et la liste des
blocs sont figés quand le sprint passe de `ready` à `in_progress`.

Les raccourcis UX sont 15, 30, 45 et 60 minutes, mais 10, 20, 25, 35, 40, 50 et
55 sont des budgets de première classe, testés et persistés. Dix minutes est le
minimum utile : rappel dû, activité cible avec sortie produite et bilan. Il peut
produire des preuves, mais ne valide une journée que si le `ModuleDay` publie un
noyau minimal compatible.

## 5. Familles de blocs

| Famille | Rôle | Durée typique |
|---|---|---:|
| `recall_warmup` | rappels très dus et activation | 2-4 min |
| `lexical_acquisition` | apprendre/réactiver vocabulaire du jour | 3-7 min |
| `version_input` | langue cible vers langue d'appui | 4-8 min |
| `grammar_toolbox` | explication, contraste, rappel de moule | 3-6 min |
| `transformation_gym` | produire et transformer | 4-10 min |
| `listening` | compréhension orale | 4-8 min |
| `shadowing` | perception et production phonologique | 3-8 min |
| `guided_output` | réponse ou thème contraint | 4-8 min |
| `free_writing` | production plus libre | 6-12 min |
| `delayed_recode` | reconstruction J+1 | 4-8 min |
| `reflection_close` | bilan et prochaine action | 1-2 min |

Les durées sont estimées depuis les historiques disponibles ; les valeurs
ci-dessus servent de repli initial.

## 6. Noyau obligatoire

Tout sprint quotidien contient :

1. un rappel ou une activation ;
2. une activité liée à l'objectif principal du jour ;
3. une opportunité de production ou rappel sans aide ;
4. un bilan final.

Contraintes supplémentaires :

- `delayed_recode` dû a priorité et remplace une activité optionnelle ;
- aucune nouveauté si les prérequis bloquants manquent ;
- le vocabulaire nouveau est pré-exposé avant une tâche qui l'exige ;
- une structure nouvelle reçoit explication avant Gym ;
- une journée ne cible au plus qu'une nouvelle famille grammaticale ;
- une activité peut couvrir plusieurs rôles seulement si son contrat déclare les
  preuves distinctes ;
- une ressource indisponible est remplacée avant démarrage ou retirée du plan.

## 7. Compositions par durée

La durée annoncée inclut correction et transitions. Le plan réserve 10 % du
temps ; la somme p50 des instances reste sous le budget de contenu et leur
somme p80 sous la durée annoncée.

| Durée | Budget de contenu | Réserve | Blocs maximum | Nouveaux sens `P-ABS` |
|---:|---:|---:|---:|---:|
| 10 min | 9 min | 1 min | 3 | 3 |
| 15 min | 13 min 30 s | 1 min 30 s | 4 | 4 |
| 20 min | 18 min | 2 min | 4 | 5 |
| 25 min | 22 min 30 s | 2 min 30 s | 5 | 6 |
| 30 min | 27 min | 3 min | 5 | 8 |
| 35 min | 31 min 30 s | 3 min 30 s | 6 | 8 |
| 40 min | 36 min | 4 min | 6 | 9 |
| 45 min | 40 min 30 s | 4 min 30 s | 7 | 10 |
| 50 min | 45 min | 5 min | 7 | 10 |
| 55 min | 49 min 30 s | 5 min 30 s | 7 | 11 |
| 60 min | 54 min | 6 min | 7 | 12 |

### 7.0 Charge de nouveauté

Une nouveauté coûte des `novelty_points` : sens lexical `1`, moule grammatical
`3`, contraste phonologique `2`, stratégie discursive `2`. Une simple forme
fléchie d'un paradigme déjà ciblé coûte `0.5`. Le plafond de points pour `P-ABS`
est respectivement `3, 5, 6, 8, 10, 11, 12, 13, 14, 15, 16` pour les onze
budgets croissants. `P-FAUX` peut recevoir deux points supplémentaires et
`P-INT` quatre, uniquement si les prérequis et la fraîcheur le permettent.

Une journée cible au plus une nouvelle **famille grammaticale**. Dans cette
famille, `P-ABS` reçoit au plus deux moules nouveaux, `P-FAUX` trois et `P-INT`
quatre. Les expressions figées fournies comme secours ne deviennent pas des
cibles et ne consomment pas de point ; elles ne produisent aucune preuve.

Quotas minimaux : une cible principale, une rencontre contextualisée et une
sortie produite pour tout budget ; rappel J+1 lorsqu'il est dû ; compréhension
et production séparées à partir de 20 minutes sauf si une primitive certifiée
observe explicitement les deux sans dupliquer la preuve.

Les plans 15/30/45/60 ci-dessous sont les ancres éditoriales. Pour un budget
intermédiaire, le moteur part de l'ancre inférieure, puis ajoute des instances
publiées selon l'ordre : dette due, consolidation, seconde modalité, oral,
réparation, extension. Il ne raccourcit jamais une instance sous sa durée
minimale et ne dépasse ni budget de contenu, ni blocs, ni novelty points. Cette
règle, les versions et la graine rendent les onze budgets reproductibles.

Légende : **M** obligatoire ; **C** obligatoire si la condition s'applique ;
**O** optionnel ; **-** absent de l'enveloppe standard. Plusieurs familles
peuvent partager un bloc si leurs observations restent séparables.

| Famille ou rôle | 15 | 30 | 45 | 60 | Condition |
|---|:---:|:---:|:---:|:---:|---|
| rappel, dette et activation | M | M | M | M | Sans échéance, consolide un ancrage pertinent. |
| `delayed_recode` J+1 | C | C | C | C | Obligatoire dès qu'une source valide est due. |
| `lexical_acquisition` dédiée | C | C | M | M | À 45/60, devient consolidation si aucune nouveauté n'est admise. |
| rencontre contextualisée | M | M | M | M | `version_input`, écoute, dialogue ou scène. |
| `grammar_toolbox` | C | C | C | C | Requise pour une structure nouvelle ou une erreur non comprise. |
| `transformation_gym` ou pratique guidée | M | M | M | M | Peut fusionner avec la rencontre à 15 minutes. |
| compréhension dédiée | O | C | M | M | Requise si elle est objectif principal du jour. |
| production sans réponse révélée | M | M | M | M | Réponse fonctionnelle courte admise à 15 minutes. |
| seconde modalité | - | O | M | M | Substitution accessible certifiée autorisée. |
| transfert ou mission | O | O | C | M | Obligatoire un jour `transfer`; intégré à la production si court. |
| `reflection_close` | M | M | M | M | Persiste preuves, dette et prochaine action. |

### 7.1 15 minutes, 4 blocs

| Bloc composé | Cible p50 |
|---|---:|
| Rappel, J+1 et réparation prioritaire | 4 min |
| Rencontre, lexique et focalisation intégrés | 4 min |
| Chaîne guidée vers une production autonome courte | 4 min |
| Bilan | 1 min 30 s |

Une seule cible principale et au plus une cible secondaire. Le sprint avance le
noyau, mais ne cherche pas à couvrir toutes les modalités.

### 7.2 30 minutes, 5 blocs

| Bloc composé | Cible p50 |
|---|---:|
| Rappel, J+1 et réparation | 5 min |
| Activation Word Bank et rencontre contextualisée | 5 min |
| Focalisation et pratique guidée | 7 min |
| Compréhension puis production autonome | 8 min |
| Bilan | 2 min |

Cette enveloppe est le noyau quotidien de référence. Une seconde modalité peut
remplacer une partie du quatrième bloc sans modifier les objectifs.

### 7.3 45 minutes, 7 blocs

| Bloc composé | Cible p50 |
|---|---:|
| Rappel, J+1 et réparation | 7 min |
| Activation Word Bank | 4 min |
| Rencontre et compréhension | 6 min |
| Focalisation et pratique guidée | 8 min |
| Seconde modalité | 5 min |
| Production autonome et transfert | 8 min |
| Bilan | 2 min 30 s |

Cette enveloppe ajoute diversité de preuve et transfert, pas une quantité
proportionnelle de règles nouvelles.

### 7.4 60 minutes, 7 blocs

| Bloc composé | Cible p50 |
|---|---:|
| Rappel, J+1 et réparation | 8 min |
| Activation Word Bank | 5 min |
| Rencontre et compréhension approfondie | 8 min |
| Focalisation, Gym et variation guidée | 10 min |
| Oral ou seconde modalité | 7 min |
| Production étendue, transfert ou mission | 13 min |
| Bilan et auto-réparation | 3 min |

Le bloc de production contient plusieurs instances sauvegardables. Il ne peut
pas devenir une interaction atomique de 13 minutes impossible à reprendre.

## 8. Sélection déterministe

### 8.1 Contraintes dures

Un bloc est admissible seulement si :

- prérequis satisfaits ou enseignés plus tôt dans le même plan ;
- instance et correcteur prêts ;
- média disponible ou remplacement prêt ;
- durée minimale tient dans le budget restant ;
- charge de nouveauté sous plafond ;
- consentements et accessibilité satisfaits ;
- aucune cible explicitement exclue ;
- snapshot compatible avec les versions publiées.

### 8.2 Priorité des besoins `SPRINT_PRIORITY_V0`

```text
need_priority = 0.30 debt_urgency
              + 0.25 memory_due
              + 0.20 module_criticality
              + 0.10 prerequisite_block
              + 0.10 modality_balance
              + 0.05 information_gain
```

Pénalités : surcharge nouvelle, répétition récente de primitive, contenu trop
similaire, durée incertaine et contexte incohérent.

### 8.3 Optimisation

Le compositeur sélectionne un ensemble ordonné maximisant :

- couverture des besoins prioritaires ;
- cohérence contextuelle ;
- diversité minimale des opérations ;
- réutilisation du vocabulaire du jour ;
- respect du budget avec marge de 10 % non dépassable ;
- qualité des preuves attendues.

Il applique d'abord les contraintes, puis un algorithme déterministe de sélection
avec tie-break par graine. Même entrée, versions et graine donnent le même plan.

### 8.4 Équilibre déterministe des modalités

`MODALITY_BALANCE_V0` observe les 14 dernières journées pédagogiques actives,
limitées aux 28 derniers jours civils. Sur toute fenêtre de 7 journées, les
opportunités cibles sont : lecture 4, écoute 3, écriture 3, oral 2. Une activité
peut compter pour plusieurs modalités seulement si elle publie des phases
séparées et observables ; le shadowing seul ne compte pas comme compréhension.

```text
balance_deficit_m = max(target_m - observed_opportunities_m, 0) / target_m
modality_balance = max(balance_deficit_m for admissible modalities)
```

À égalité, le moteur choisit la modalité au déficit le plus ancien, puis l'ordre
`listening`, `writing`, `speaking`, `reading`, puis la graine. Écoute et écriture
deviennent contraintes dures après trois journées actives sans opportunité ;
oral après quatre. Une impossibilité média/accessibilité documentée suspend la
contrainte, affiche la lacune et ne pénalise jamais l'utilisateur.

## 9. Règles Word Bank

Chaque unité sélectionnée reçoit un rôle :

- `new` : cible nouvelle pré-exposée ;
- `due` : invite mémoire échue ;
- `debt` : besoin ouvert ;
- `target` : nécessaire à l'objectif ;
- `support` : déjà suffisamment fiable ;
- `distractor` : contraste validé ;
- `rescue` : disponible comme aide sans être exigé.

Priorités : dette urgente, rappels dus, vocabulaire critique du module, écarts
réception/production, puis nouveauté. Une session fige la liste et les rôles.

Un mot peut servir de support grammatical sans recevoir de preuve lexicale. Une
production spontanée correcte peut créer une preuve même si le mot n'était pas
cible, lorsque le correcteur est fiable.

## 10. J-1, J+1 et jours manqués

- `J0` désigne l'ordre d'exécution, pas obligatoirement la date civile suivante.
- Une tâche `next_active_session` devient due à la prochaine session admissible.
- Une tâche `after_24h` exige au moins 24 heures réelles.
- Une reconstruction de texte épingle la source corrigée, jamais une production
  utilisateur non validée.
- Vocabulaire, structures, textes et erreurs ont leurs propres politiques.
- Un jour manqué n'avance pas le module et ne supprime aucun rappel.
- Plusieurs rappels accumulés sont triés par urgence et charge ; ils peuvent être
  répartis sur plusieurs sprints.

### 10.1 Contrat de recodage différé

Un `DelayedRecodeSpec` est créé à J0 seulement depuis une tentative corrigée et
évaluable de version, cible vers langue d'appui. Il épingle : tentative et
correction sources, stimulus cible original, traduction d'appui corrigée,
ensemble de réponses acceptées ou grille, langues/directions, cibles, politique
de correction et révisions de contenu. Aucune réponse utilisateur non validée ne
devient le corrigé.

La tâche demande à J+1 de reconstruire la langue cible depuis la traduction
d'appui corrigée. Elle devient due à la prochaine journée pédagogique active,
jamais avant 12 heures réelles ; un contrôle `after_24h` est créé séparément si
le protocole exige un délai strict. L'instance J+1 est immuable, compare au texte
source et aux variantes publiées, et produit uniquement des preuves de production.
Une source J0 `not_evaluable`, contestée ou invalidée annule la tâche avant
présentation. Un jour manqué reporte la tâche sans la dupliquer.

## 11. Interruption et adaptation

- Le plan reste figé après démarrage.
- Une interruption sauvegarde bloc, tentative et temps actif.
- À la reprise, le moteur vérifie expiration et disponibilité média.
- Un bloc devenu indisponible est marqué tel quel et remplacé par une instance
  équivalente seulement avec confirmation de nouvelle version du plan.
- Une session arrêtée conserve les preuves confirmées.
- Les blocs non ouverts retournent au planificateur comme besoins non satisfaits.
- Une durée réelle très différente ajuste les estimations futures, jamais les
  résultats pédagogiques.

## 12. Entraînement libre

L'utilisateur choisit cible, liste, primitive, modalité, durée, mode entraînement
ou test, thème/contexte et défi `gentler`, `matched` ou `stretch`. Le défi est un
écart borné par rapport à ses projections, jamais un niveau arbitraire : `gentler`
retire une dimension de charge, `matched` reste dans l'intervalle courant et
`stretch` ajoute au plus une dimension tout en conservant les prérequis. Le
compositeur :

- vérifie prérequis ;
- avertit si le choix est trop difficile ;
- respecte les mêmes contrats de correction et preuve ;
- n'altère pas le plan quotidien ;
- met à jour les projections avec le poids source `free_practice` ;
- permet de choisir zéro nouveauté.

Le contexte peut être un `ContextFamily` publié, une intention libre privée ou
« surprends-moi ». Une intention libre est conservée dans le snapshot du plan,
pas utilisée comme vérité pédagogique, et doit être transformée en contraintes
publiées avant exécution. À défaut de contenu compatible, la composition échoue
explicitement avec `no_valid_composition`.

## 13. Validation d'un plan

Avant `ready`, les validateurs vérifient :

- budget et estimations ;
- ordre des prérequis ;
- charge lexicale et grammaticale ;
- cibles réellement observables ;
- cohérence des contenus ;
- couverture du noyau obligatoire ;
- présence des rappels prioritaires ;
- diversité de contexte et de modalité sur la fenêtre du module ;
- correcteurs et médias ;
- accessibilité ;
- absence de fuite de réponses d'évaluation.

## 14. Tests normatifs

1. Même snapshot/graine produit le même plan.
2. Aucun bloc ne dépasse un prérequis manquant.
3. Un budget de 10 minutes reste utile et complet selon son noyau.
4. Un rappel J+1 dû remplace une activité optionnelle.
5. La dette urgente déplace de la nouveauté.
6. Une dette planifiée reste ouverte.
7. Un jour manqué n'avance pas le module.
8. Un changement de fuseau ne duplique pas le sprint.
9. Une ressource absente avant départ est remplacée ou retirée explicitement.
10. Un plan démarré ne mute pas silencieusement.
11. Les valeurs 10, 15, 20, 30, 45 et 60 respectent le budget.
12. Le maximum de nouveaux sens est respecté.
13. Une structure complexe n'est pas introduite dans un sprint trop court.
14. Une modalité négligée remonte dans la priorité future.
15. Un entraînement libre ne consomme pas la journée du module.
