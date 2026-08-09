# Polyglot V2 - Registre et contrats normatifs des exercices

## 1. Portee et autorite

Ce document ferme le registre commun des primitives et les contrats du domaine
Exercices. Il specialise `02-backend-pedagogique.md` sans modifier les decisions
de `06-glossaire-decisions.md`. En cas de conflit, l'ordre d'autorite defini par
ce dernier s'applique.

Une primitive decrit une interaction et le type de preuve qu'elle peut produire.
Elle ne contient ni regle propre a une langue, ni contenu de cours, ni decision
de planification. Une definition certifie une primitive pour un usage; une
instance fige le contenu; une tentative conserve ce qui s'est reellement passe.

Le registre couvre le sprint, l'entrainement libre et les quatre evaluations.
La Gym et le shadowing sont des protocoles composes: ils orchestrent plusieurs
primitives mais ne creent aucun contrat parallele.

## 2. Regles communes

1. Une instance reference une seule revision publiee de definition.
2. Une definition declare toutes ses reponses, aides, correcteurs et
   observations possibles; aucun champ ad hoc n'est autorise dans une instance.
3. Le contenu exact, les cibles, les versions du pack et la graine sont figes au
   demarrage du plan de session.
4. Une exposition, une revelation ou une auto-evaluation seule ne constitue pas
   une preuve de maitrise.
5. Une panne de correction produit `not_evaluable`, jamais `correct`.
6. Une correction nouvelle s'ajoute a l'historique; elle ne modifie ni la
   reponse brute, ni la correction precedente.
7. Une adaptation d'accessibilite ne coute aucune preuve. Si elle change la
   modalite mesuree, l'observation cible la modalite effectivement exercee.
8. Passer, abandonner, interrompre, etre indisponible et repondre faux sont des
   resultats distincts.
9. Une primitive peut observer plusieurs cibles, mais chacune declare son role
   `principal`, `secondaire`, `support` ou `distracteur`.
10. Seules les cibles principales et secondaires peuvent produire une preuve.
    Une cible support ne peut recevoir qu'une rencontre ou une erreur incidente.

## 3. Registre ferme des primitives

### 3.1 Statuts

- `core` : obligatoire pour le premier parcours complet;
- `extended` : contrat ferme, implementation apres le noyau;
- `future` : port reserve, aucune dependance obligatoire au MVP.

### 3.2 Exposition et discrimination

| ID | Primitive | Reponse canonique | Correction | Aides permises | Observation maximale | Statut |
|---|---|---|---|---|---|---|
| `EX-EXPOSE-01` | `micro_explanation` | `acknowledgement` | aucune | audio, glossaire, exemples | rencontre, aucune preuve | core |
| `EX-DISC-01` | `guided_observation` | `selection` ou `short_text` | ensemble accepte ou grille | surlignage, indice de contraste | reconnaissance guidee | core |
| `EX-DISC-02` | `matching` | `pairing` | appariement exact | reduction des candidats | reconnaissance | core |
| `EX-DISC-03` | `classification` | `grouping` | classes acceptees | exemple classe, reduction | discrimination | core |
| `EX-DISC-04` | `contrast_choice` | `single_choice` | choix + justification optionnelle | replay, indice de fonction | discrimination | core |
| `EX-DISC-05` | `acceptability_judgment` | `graded_choice` | grille `naturel/marque/incorrect` | contexte, contraste | jugement pragmatique | extended |
| `EX-DISC-06` | `target_detection` | `spans` | unites discriminantes | nombre de cibles, replay | reperage ecrit ou oral | core |

`intrus` est le mode `odd_one_out` de `classification`. Les questions de
naturalite entre deux formulations sont `contrast_choice`; celles a trois
niveaux sont `acceptability_judgment`. Elles ne sont pas des primitives
supplementaires.

### 3.3 Rappel et reconstruction

| ID | Primitive | Reponse canonique | Correction | Aides permises | Observation maximale | Statut |
|---|---|---|---|---|---|---|
| `EX-RECALL-01` | `flashcard_recall` | `self_grade` avec reponse optionnelle | auto-evaluation encadree ou exact | initiale, audio, revelation | rappel si reponse verifiable, sinon activite | core |
| `EX-RECALL-02` | `cloze` | `tokens` | exact, ensemble accepte, morphologique | lemme, traits, choix | rappel controle | core |
| `EX-RECALL-03` | `cued_recall` | `short_text` ou `audio_ref` | exact, ensemble ou grille | echelle progressive | rappel guide ou autonome | core |
| `EX-RECALL-04` | `dictation` | `text` | normalisation + morphologie | replay, vitesse, segmentation | reception orale + graphie | core |
| `EX-RECALL-05` | `partial_transcription` | `tokens` | exact ou ensemble accepte | replay, nombre de mots | reception orale | core |
| `EX-RECALL-06` | `morphology_grid` | `cells` | morphologique par cellule | traits, lemme, cellule revelee | morphologie produite | core |
| `EX-RECALL-07` | `ordered_reconstruction` | `ordered_items` | ordre(s) accepte(s) | blocs fixes, ponctuation | syntaxe reconstruite | core |

`morphology_grid` couvre conjugaison, accord et flexion. Une langue sans la
categorie concernee ne certifie pas le mode correspondant.

### 3.4 Transformation et comprehension

| ID | Primitive | Reponse canonique | Correction | Aides permises | Observation maximale | Statut |
|---|---|---|---|---|---|---|
| `EX-TRANSFORM-01` | `controlled_transformation` | `text` ou `audio_ref` | morphologique + contraintes | etapes, lemme, segment | transformation | core |
| `EX-COMP-01` | `reading_comprehension` | choix, `spans` ou `short_text` | ensemble ou grille | glossaire cible, indice | comprehension ecrite | core |
| `EX-COMP-02` | `listening_comprehension` | choix, `spans` ou `short_text` | ensemble ou grille | replay, vitesse, indice | comprehension orale | core |
| `EX-COMP-03` | `translation` | `text` | traduction bornee ou grille | lexique, structure, revelation | comprehension ou production selon direction | core |

Resume, inference, intention, ordre d'evenements et extraction sont des modes
declares de `reading_comprehension` ou `listening_comprehension`. La definition
nomme les unites discriminantes; elle ne credite pas tous les tokens du support.

### 3.5 Production, interaction et reparation

| ID | Primitive | Reponse canonique | Correction | Aides permises | Observation maximale | Statut |
|---|---|---|---|---|---|---|
| `EX-PROD-01` | `constrained_response` | `text` ou `audio_ref` | contraintes + grille | amorce, lexique, structure | production contrainte | core |
| `EX-PROD-02` | `dialogue_continuation` | `text` ou `audio_ref` | grille fonctionnelle | intention, actes possibles | interaction simulee | core |
| `EX-PROD-03` | `extended_production` | `text` ou `audio_ref` | grille criteree | plan, lexique, checklist | production ou transfert | core |
| `EX-ORAL-01` | `oral_rehearsal` | `self_assessment` + `audio_ref` optionnel | auto-evaluation ou humain | modele, segmentation, vitesse | pratique orale, preuve faible au plus | core |
| `EX-REPAIR-01` | `self_repair` | `text` ou `audio_ref` revise | comparaison avant/apres | correction precedente | reparation | core |
| `EX-REPAIR-02` | `explain_choice` | `short_text` ou `selection` | grille | concepts proposes | metacognition, pas maitrise directe | extended |
| `EX-INTERACT-01` | `live_interaction` | flux de tours | humain ou futur STT/LLM | strategie de reparation | interaction | future |

Lecture a voix haute, repetition contrastive et les phases productives du
shadowing sont des modes de `oral_rehearsal`. Le protocole shadowing compose
`listening_comprehension`, `target_detection` et `oral_rehearsal`; il n'est pas
une primitive supplémentaire. Narration, description, argumentation,
reformulation et mission d'ecriture sont des modes de `extended_production`.

## 4. Contrat de donnees conceptuel

Les noms ci-dessous sont normatifs. Les types persistants, nullabilités et clés
sont fixés dans le document 26 ; les payloads coeur ne sont pas des blobs libres.

### 4.1 `ExerciseDefinition`

| Champ | Type conceptuel | Regle |
|---|---|---|
| `definition_id` | UUID stable | identite fonctionnelle |
| `revision_id` | UUID | revision immuable |
| `schema_version` | entier | version du contrat |
| `primitive_id` | enum du registre | exactement une primitive |
| `status` | `content_revision_status` du registre 25 | seule `published` est planifiable ; la certification par langue reste séparée |
| `language_certifications` | liste de pack revisions | au moins une |
| `modes` | liste fermee | modes admis par la primitive |
| `response_contract` | `AnswerContract` | union et limites explicites |
| `target_contract` | liste de `SkillTargetSpec` | cible, role, poids maximal |
| `prerequisites` | liste de capacites | satisfaits ou dispenses avant selection |
| `difficulty_profile` | quatre axes | lexique, structure, tache, support |
| `stimulus_contract` | schema type | texte, audio, image, tours ou combinaison |
| `hint_policy_id` | revision | politique certifiee |
| `correction_policy_id` | revision | strategie et seuils |
| `observation_policy_id` | revision | mapping vers observations |
| `accessibility_contract` | liste | clavier, lecteur d'ecran, alternatives |
| `time_budget` | intervalle en secondes | estimation testee |
| `examples` | valides et invalides | au moins deux de chaque pour `core` |

### 4.2 `ExerciseInstance`

| Champ | Regle |
|---|---|
| `instance_id`, `definition_revision_id` | identite et contrat epingle |
| `session_plan_revision_id` | nullable seulement en entrainement libre isole |
| `language_pack_revision_id` | obligatoire |
| `stimulus_revision_ids` | contenus immuables affiches ou joues |
| `targets` | cibles concretes conformes a la definition |
| `lexical_bindings` | sens et roles `cible/support/distracteur/secours` |
| `grammar_bindings` | structures et traits morphologiques |
| `accepted_answer_set_revision_id` | obligatoire quand utilise |
| `rubric_revision_id` | obligatoire quand utilise |
| `seed` | entier, reproductible |
| `available_from`, `expires_at` | expiration facultative, jamais retroactive |
| `provenance` | auteur, source, validation, publication |

L'instance ne contient pas d'etat utilisateur. Deux utilisateurs peuvent
executer la meme instance avec des tentatives independantes.

### 4.3 `Answer`

`Answer` est une union fermee discriminee par `kind` :

- `acknowledgement` : confirmation sans contenu evalue;
- `single_choice`, `graded_choice`, `selection` : identifiants d'options;
- `pairing`, `grouping`, `ordered_items`, `cells`, `spans` : structures typees;
- `tokens`, `text`, `short_text` : texte brut et locale de saisie;
- `audio_ref` : reference a un enregistrement, jamais octets dans l'evenement;
- `self_grade` : `again/hard/good/easy` avec confiance optionnelle;
- `self_assessment` : grille remplie, notes et enregistrement optionnel;
- `no_answer` : utilise seulement avec une raison terminale explicite.

Toute reponse conserve `raw_value`, `submitted_at`, `input_method` et, si une
normalisation est appliquee, sa revision et sa valeur derivee.

### 4.4 `Attempt`

| Champ | Regle |
|---|---|
| `attempt_id`, `instance_id`, `profile_id` | propriete immuable |
| `attempt_no` | croissant pour cette instance et ce profil |
| `status` | machine d'etat de la section 5 |
| `started_at`, `active_duration_ms` | temps brut et temps actif separes |
| `answer` | nullable avant soumission |
| `hint_uses` | journal ordonne, append-only |
| `media_events` | lectures, pauses, vitesse, transcript |
| `correction_revision_ids` | historique ordonne |
| `terminal_reason` | non nullable : `none` sauf si `status=not_evaluable`, où une raison non `none` est obligatoire |
| `idempotency_key` | obligatoire pour soumettre ou terminer |

### 4.5 `Hint`, `Correction` et `Observation`

`HintDefinition` declare niveau, contenu, prerequis d'affichage, effet sur les
preuves et alternative accessible. `HintUse` conserve l'instant, le motif,
l'etat de la reponse et la revision montree.

`Correction` conserve strategie, verdict, scores par critere, reponse proposee,
alternatives, explication, confiance, provenance, erreurs typees et drapeau de
revue. `Observation` conserve cible, facette, operation, modalite, role, resultat,
force, confiance, contexte, aide, correction et politique de calcul.

## 5. Cycle bloc, tentative et correction

Les valeurs d'enum sont nommées par le document 25 ; les transitions et leurs
préconditions appartiennent au document 09. Le domaine Exercices respecte trois
cycles distincts :

- `ExerciseBlockRun` : `pending -> available -> in_progress -> completed`, avec
  terminaux alternatifs `skipped`, `abandoned` et `unavailable` ;
- `Attempt` : `draft -> submitted -> correcting -> corrected`, avec terminal
  alternatif `not_evaluable` ; l'autosauvegarde ne change pas l'etat `draft` ;
- `CorrectionCase` : `closed -> contested -> review_pending -> resolved`.

| Resultat | Objet | Activite | Preuve | Dette | Plan |
|---|---|---:|---:|---|---|
| `corrected` | tentative | oui | selon observation | selon erreurs | bloc peut se terminer |
| `not_evaluable` | tentative | oui | aucune avant revue | aucune automatique | bloc peut poursuivre |
| `skipped` | bloc | oui, distincte | aucune | optionnelle si cible due | poursuit ou remplace |
| `abandoned` | bloc | temps seulement | aucune | aucune automatique | sprint incomplet |
| `unavailable` | bloc | incident | aucune | aucune | remplacement contractuel |
| `interrupted` | sprint | activité partielle | aucune nouvelle | aucune | reprise exacte |

Interrompre un sprint laisse le bloc `in_progress` et la tentative `draft`.
Reprendre restaure réponse, aides, position média et temps actif. Une panne de
correction termine la tentative `not_evaluable` avec raison
`correction_unavailable`; elle n'est ni un verdict faux, ni un état de bloc. Une
contestation ouvre un `CorrectionCase` sans modifier la tentative ou la réponse.

## 6. Politique normative des aides

### 6.1 Echelle et cout initial

| Niveau | Nature | Exemples | Multiplicateur maximal de force |
|---|---|---|---:|
| `H0` | aucune aide pedagogique | consigne et stimulus prevus | `1.00` |
| `H1` | orientation | objectif, rappel de contraste, nombre de mots | `0.85` |
| `H2` | indice partiel | initiale, traits morphologiques, choix reduits | `0.60` |
| `H3` | contenu substantiel | lemme cible, segment traduit, ordre partiel | `0.25` |
| `H4` | revelation | reponse ou traduction complete | `0.00` |

Le multiplicateur le plus bas utilise pendant la tentative s'applique a la
cible concernee. Une definition peut abaisser ce plafond, jamais l'augmenter.
La calibration peut changer dans une nouvelle revision de politique sans
reecrire les observations historiques.

### 6.2 Regles d'usage

- Les aides sont ordonnees du moins informatif au plus informatif.
- Le bouton SOS choisit l'aide minimale satisfaisant la demande; une traduction
  complete est `H4`, pas un indice neutre.
- Une aide portant sur un mot support ne diminue pas automatiquement la preuve
  grammaticale principale, mais interdit une preuve lexicale autonome sur ce mot.
- Un premier passage audio prevu par le protocole est `H0`. Chaque replay est
  journalise; au-dela du quota de la definition, il devient `H1` ou `H2`.
- Afficher le transcript pendant une mesure d'ecoute bascule la preuve vers la
  lecture. L'activite orale peut continuer, mais aucune comprehension orale
  n'est deduite de cette phase.
- Une aide automatique et une aide demandee sont distinguees.
- La revelation cree une dette ciblee seulement si la cible etait due ou
  obligatoire; elle ne penalise pas arbitrairement une carte.

### 6.3 Accessibilite

Navigation clavier, focus, lecteur d'ecran, agrandissement, contraste, sous-titres,
commande sans geste fin et temps non contraint sont des adaptations `A0`, sans
cout pedagogique. Si une alternative remplace audio par texte, glisser-deposer
par selection ordonnee ou oral par saisie, l'instance declare la modalite ou le
geste reellement mesure. Le produit ne pretend pas avoir teste la modalite
remplacee.

Chaque primitive `core` doit fournir :

- une execution complete au clavier;
- des libelles non visuels pour stimulus, controles et correction;
- une alternative a toute limite de temps;
- une representation textuelle des informations non purement auditives;
- un comportement explicite quand l'objectif meme est auditif ou oral.

## 7. Correction

### 7.1 Strategies fermees

| Strategie | Usage | Sortie minimale |
|---|---|---|
| `exact_normalized` | forme courte non ambigue | ecarts apres normalisation |
| `accepted_set` | plusieurs formulations publiees | variante reconnue |
| `morphological` | flexion, accord, conjugaison | traits attendus/observes |
| `structural_constraints` | ordre, transformations | contraintes satisfaites |
| `bounded_translation` | traduction avec sens et structures bornes | criteres semantiques et linguistiques |
| `rubric` | comprehension ouverte ou production | score par critere |
| `self_assessment` | oral sans mesure automatique | grille et confiance utilisateur |
| `human_review` | ambiguite ou production sensible | auteur et decision tracee |
| `llm_review` | futur adaptateur borne | rapport structure et confiance |

Une politique peut composer plusieurs strategies dans un ordre declare. La
sortie commune reste identique.

### 7.2 Verdicts

- `correct` : tous les criteres obligatoires satisfaits;
- `partially_correct` : intention recevable mais au moins un critere obligatoire
  manque sans rendre la reponse contradictoire;
- `incorrect` : cible non produite, sens faux ou contrainte essentielle violee;
- `ambiguous` : plusieurs interpretations plausibles empechent le verdict;
- `invalid_answer` : format vide, corrompu ou hors contrat;
- `not_evaluable` : correcteur, media ou donnees insuffisants;
- `contested` : vue de lecture indiquant une contestation ouverte, pas un nouveau
  verdict pedagogique.

La confiance appartient a la correction, pas a l'utilisateur. Sous `0.80`, une
correction automatique ne peut produire qu'une observation `not_evaluable` ou
une preuve plafonnee a `0.25`; sous `0.60`, elle exige une revue ou reste
`not_evaluable`.

### 7.3 Normalisation

La normalisation generique peut traiter Unicode canonique, espaces, casse et
ponctuation declaree non discriminante. Les accents, apostrophes, traits
morphologiques, ordre et registre ne sont jamais ignores globalement: le pack de
langue decide lesquels sont discriminants pour chaque cible. La valeur brute est
toujours conservee.

### 7.4 Contestation et correction tardive

Contester ne retire aucune donnee. La tentative pointe vers la correction
courante et conserve toutes les revisions. Une nouvelle correction peut
invalider les observations derivees et en emettre de nouvelles avec un lien de
remplacement. Les projections sont recalculees; l'historique utilisateur ne
change pas silencieusement.

### 7.5 Fonctionnement hors LLM

Le noyau quotidien hors réseau ne sélectionne comme obligatoires que des
exercices corrigibles par `exact_normalized`, `accepted_set`, `morphological`,
`structural_constraints` ou `bounded_translation`. Une production ouverte peut
rester disponible avec contraintes déterministes, checklist publiée, exemples
et phase de `self_repair`, mais son verdict final est `not_evaluable` tant qu'un
humain ou correcteur qualifié n'a pas appliqué la grille. Elle crée de l'activité
et conserve l'artefact ; elle ne produit ni preuve de maîtrise ni dette négative.

Un plan n'est `ready` que si tous ses blocs obligatoires possèdent un chemin de
correction local publié. L'indisponibilité d'un correcteur externe ne déclenche
aucun fallback caché : l'exercice ouvert est optionnel ou passe explicitement en
revue différée.

## 8. Mapping tentative vers observations

### 8.1 Valeur d'observation

| Operation | Force de base maximale |
|---|---:|
| exposition ou acknowledgement | `0.00` |
| reconnaissance/discrimination | `0.35` |
| rappel controle | `0.55` |
| transformation | `0.65` |
| production contrainte | `0.75` |
| production ouverte | `0.85` |
| transfert dans un contexte nouveau | `1.00` |

Le verdict reçoit une valeur signee : `correct = +1.00`,
`partially_correct = +0.35`, `incorrect = -1.00`. `ambiguous`,
`invalid_answer` et `not_evaluable` ne produisent pas de valeur pedagogique ;
ils restent des faits d'activite ou de revue.

Pour une cible :

```text
observation_value = clamp(
  signed_outcome
  x min(operation_cap, target_weight_cap)
  x help_multiplier
  x correction_confidence
  x target_coverage,
  -1,
  1
)
```

`help_multiplier` vient exclusivement de la politique H0-H4 de la section 6.
`target_coverage` vaut la part des contraintes discriminantes reellement
observees, dans `[0,1]`. Le contexte, la session, le delai et la source sont
conserves comme metadonnees mais ne sont pas remultiplies ici. Le document 10
ajoute uniquement poids de source et independance.

Exemples : production contrainte correcte, H0, correction certaine et couverture
complete : `+0.75`. La meme reponse partiellement correcte :
`0.35 x 0.75 = +0.2625`. Reponse incorrecte sans aide : `-0.75`. Reponse correcte
apres revelation H4 : `0.00`.

Cette valeur qualifie une observation; elle ne decide jamais seule de l'etat de
maitrise. Les erreurs peuvent emettre des observations de dette separees, typees
par sens, forme, structure, pragmatique ou phonologie.

### 8.2 Regles de credit

- Une traduction cible vers maternelle observe la comprehension, pas la
  production en langue cible.
- Une structure fournie dans une aide ne recoit aucune preuve de rappel.
- Un mot support correctement copie ne recoit aucune preuve lexicale autonome.
- Une auto-evaluation orale sans enregistrement ni revue ne depasse pas `0.25`
  de force et garde une confiance faible.
- Un exercice reexecute avec le meme contenu ne cree pas de diversite de contexte.
- Une correction `ambiguous` ou `not_evaluable` ne cree aucune dette d'erreur.

## 9. Contrat de la Gym

### 9.1 Nature

Une `GymPlan` est une sequence versionnee d'instances centree sur une structure
principale. Elle separe :

- `grammar_target` : structure dont le rappel ou le transfert est mesure;
- `lexical_support` : lexique deja fiable ou fourni;
- `transformation_chain` : operations autorisees et leurs preconditions;
- `invariants` : sens, registre ou elements devant rester stables;
- `exit_evidence` : preuve attendue a la fin de la sequence.

La Gym ne choisit jamais une transformation seulement pour varier. Elle est
planifiable si tous ses prerequis sont acquis, dispenses par diagnostic ou
explicitement fournis comme support non evalue.

### 9.2 Registre des transformations

| ID | Operation | Preconditions | Invariant principal |
|---|---|---|---|
| `GYM-01` | substitution lexicale | cadre d'usage compatible | structure |
| `GYM-02` | personne | paradigme requis | intention |
| `GYM-03` | nombre ou genre | accord requis | referent |
| `GYM-04` | polarite | negation acquise | proposition |
| `GYM-05` | interrogation | type de question acquis | information demandee |
| `GYM-06` | temps ou aspect | deux formes acquises | evenement |
| `GYM-07` | modalite | moules concernes acquis | action centrale |
| `GYM-08` | registre/politesse | contraste pragmatique acquis | demande |
| `GYM-09` | point de vue | personnes et deictiques acquis | situation |
| `GYM-10` | pronominalisation | fonction du complement acquise | referent |
| `GYM-11` | combinaison | connecteur/relative acquis | deux propositions |
| `GYM-12` | reduction/expansion | variante cible acquise | noyau semantique |
| `GYM-13` | reformulation idiomatique | contraste publie | intention |
| `GYM-14` | reparation d'un calque | erreur typee publiee | intention L1 |
| `GYM-15` | chaine controlee | toutes les etapes acquises | invariants declares |

### 9.3 Cycle temporel

| Etape | Moment | Contrat minimal |
|---|---|---|
| `G0` | J0 | micro-explication, contraste, aucune preuve |
| `G1` | J0 | une production guidee puis 1 a 3 transformations |
| `G2` | J+1 pedagogique | rappel sans modele, contexte proche |
| `G3` | rappel espace | transformation sans aide, contexte varie |
| `G4` | transfert | nouvelle scene, aucune indication de la structure |

Un echec a une etape ouvre ou renforce une dette et replanifie l'etape adaptee;
il ne remet pas arbitrairement toutes les etapes a zero. La fin d'une Gym ne
signifie pas `maitrise`: elle produit des observations que le modele de
progression agrege.

### 9.4 Selection et erreurs

Meme profil, revisions, dette et graine produisent le meme plan. Une operation
dont un prerequis manque est rejetee avant instanciation. Si une instance devient
indisponible, le compositeur utilise seulement un remplacement publie couvrant
la meme cible et la meme operation; sinon le bloc devient `unavailable`.

## 10. Shadowing et oral simule

### 10.1 `OralAsset`

Un support oral publie contient : langue et variete, texte exact, segments,
horodatages lorsqu'ils existent, locuteur ou voix, debit de reference, registre,
droits, source, checksum, transcription, revision et provenance. Une variante
TTS est une revision media distincte, jamais un remplacement silencieux.

### 10.2 Protocole `shadowing`

1. `listen_global` : une ecoute sans transcript;
2. `listen_segmented` : segments rejouables et reperes rythmiques;
3. `shadow_with_model` : parole simultanee avec vitesse choisie;
4. `shadow_without_text` : transcript masque, modele audio conserve;
5. `oral_recall` : repetition apres le modele, facultative selon le budget;
6. `self_assess` : grille courte et dette eventuelle.

Chaque phase est declaree dans la definition. Les vitesses publiees initiales
sont `0.75`, `0.90` et `1.00`; changer la vitesse est journalise mais n'est pas
une aide tant que l'objectif n'est pas la comprehension au debit naturel.

### 10.3 Grille sans STT

L'utilisateur evalue chaque critere de `0` a `3` :

- continuite sans pauses non voulues;
- respect des groupes rythmiques;
- accent tonique cible;
- sons ou contrastes explicitement vises;
- intelligibilite percue.

`0` signifie non tente, `1` difficile, `2` globalement tenu, `3` tenu avec
aisance. Cette grille produit activite, perception et dette volontaire; elle ne
produit jamais une note orale forte. Un enregistrement est facultatif et local
par defaut. Son envoi ou sa conservation exige une action explicite et une
politique de retention visible.

### 10.4 Indisponibilite et accessibilite

- Si le media principal manque mais qu'un media alternatif publie est lie a la
  definition, le moteur propose ce remplacement et journalise la revision.
- Aucun appel TTS reseau et aucun changement de fournisseur ne sont declenches
  pendant un sprint deja prepare.
- Sans media certifie, le shadowing devient `unavailable`. Une lecture a voix
  haute peut etre planifiee comme nouvelle instance, pas maquillee en shadowing.
- Le transcript complet, les controles clavier et une version sans contrainte de
  vitesse sont disponibles. Utiliser le transcript retire seulement la preuve
  d'ecoute concernee, pas l'acces a l'activite.

### 10.5 Port futur STT

Un adaptateur futur recoit `audio_ref`, `oral_asset_revision_id`, segments cibles
et grille attendue. Il retourne mesures par segment, confiance, erreurs typees et
version du moteur. Sous les seuils de confiance de correction, son resultat reste
`not_evaluable`. L'ajout du STT ne change ni `Attempt`, ni `Correction`, ni
`Observation`.

## 11. Certification d'une primitive

Une primitive est de maturité `core` seulement si au moins une
`ExerciseDefinitionRevision` publiée possède une
`ExerciseLanguageCertification.status=certified` et satisfait :

1. schema valide et exemples invalides rejetes;
2. fixture deterministe avec correction attendue;
3. parcours clavier et lecteur d'ecran;
4. fixtures couvrant `Attempt.status=corrected` et `not_evaluable`,
   `ExerciseBlockRun.status=completed`, `skipped` et `unavailable`, et reprise
   d'un `SprintRun.status=interrupted` vers `in_progress` ;
5. mapping exact vers observations;
6. reprise idempotente sans double comptabilisation;
7. contenu et versions epingles dans la tentative;
8. preuve qu'aucune panne n'est transformee en reussite.

## 12. Cas canoniques de validation

| Cas | Resultat attendu |
|---|---|
| Reponse correcte sans aide | observation selon operation et cible |
| Reponse correcte apres revelation | activite, force `0.00`, dette si cible due |
| Mot support revele dans une Gym | preuve grammaticale possible, aucune preuve lexicale sur ce mot |
| Transcript affiche pendant une ecoute | aucune preuve de comprehension orale pour cette phase |
| Correcteur en timeout | raison `correction_unavailable`, tentative `not_evaluable` |
| Correction contestee puis revisee | deux corrections, observations remplacees, reponse brute intacte |
| Meme soumission rejouee | une tentative et un seul ensemble d'evenements |
| Passage volontaire | `skipped`, aucune erreur inventee |
| Media shadowing absent | `unavailable` ou alternative publiee explicite |
| Auto-evaluation orale maximale | force plafonnee a `0.25`, confiance faible |
| Transformation avec prerequis absent | non planifiee |
| Meme graine et memes revisions | meme sequence Gym |

Ces contrats ferment F01 a F07 au niveau documentaire. Les seuils de maitrise,
les schemas de persistance et les composants frontend restent respectivement la
responsabilite des specifications Progression, Donnees et UX.
