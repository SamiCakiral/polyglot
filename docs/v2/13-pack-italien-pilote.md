# Polyglot V2 - Pack italien initial et pilote normatif de trois jours

## 1. Objet

Ce document spécifie le premier `LanguagePack` italien utilisable par le moteur et
la fixture humaine du premier module de trois jours. Il ne regenere aucun des 44
cours V1 et ne depend d'aucun LLM, STT, TTS reseau ou contenu a la demande.

Le pilote sert a verifier ensemble : pack de langue, boite grammaticale,
lexique, contrats d'exercice, Gym, shadowing, composition sous budget,
observations, reprise et bilan. Il n'a pas vocation a representer tout le niveau
A0 ni a prouver une maitrise en trois jours.

Sources editoriales :

- la boite grammaticale francais vers italien jointe a la demande;
- les decisions et contrats de `01` a `07`;
- le registre d'exercices de `12-contrats-exercices.md`;
- les contenus V1 comme contre-exemples et archive seulement.

## 2. Manifeste du pack

### 2.1 Contrat générique `LanguagePack`

Tout pack, quelle que soit la langue, publie obligatoirement : identité stable,
révision immuable, langue d'appui, langue/variété cible, scripts, public,
licences, compatibilité moteur, fondations et gate, compétences et prérequis,
fonctions, structures et moules, lexique de référence, morphologie, phonologie,
normalisation, correcteurs, primitives certifiées, capacités médias, contenus,
validateurs, fixtures positives/négatives et manifeste d'empreintes.

Les fondations ne sont pas codées en dur pour l'italien. Tout pack publie des
`FoundationDefinitionRevision` composées de `FoundationBlockRevision` ordonnées
et de `FoundationGateRevision`. Un bloc déclare script/orthographe, perception,
production, interaction minimale, stratégies de réparation, prérequis,
exercices certifiés, médias alternatifs et critères de dispense. La gate épingle
les cibles bloquantes, seuils de couverture/confiance, délais et preuves
acceptées. Un pack sans système d'écriture distinct peut publier un bloc de
discrimination sonore ou marquer la composante script `not_applicable`, jamais
la supprimer implicitement.

Sont optionnels : étiquettes CECR d'interopérabilité, variantes régionales,
adaptateurs fournisseurs, corpus de couverture additionnels et contenus
culturels. Leur absence ne peut pas casser le parcours hors réseau.

Une révision passe `draft -> validating -> validated -> approved -> published`.
La certification exige schémas valides, graphe de prérequis acyclique, IDs
résolus, droits, runner hors réseau, fondations exécutables, au moins un module
minimal, correcteurs déterministes et revue linguistique humaine. La version de
moteur supportée est un intervalle explicite ; une incompatibilité exige une
nouvelle révision ou un upcaster testé, jamais une mutation du pack publié.

| Champ | Valeur normative du pilote |
|---|---|
| `pack_id` | `it-IT__fr-FR` |
| `pack_revision` | `pilot-1.0.0` |
| langue maternelle | francais `fr-FR` |
| langue cible | italien standard contemporain `it-IT` |
| public | adulte debutant, faux debutant ou intermediaire en calibration |
| module | `it-pilot-first-contact-3d` |
| duree | trois journees pedagogiques, sans lien avec le jour de semaine |
| mission | entrer en contact, obtenir quelque chose et reparer un echange simple |
| auteurs | contenu humain versionne |
| fournisseurs obligatoires | aucun |
| medias | audio fixtures publies; transcript et checksum epingles |
| certification | schema, linguistique, pedagogie, accessibilite et rejeu |
| prerequis module | `FOUNDATIONS_IT_V0` reussi ou dispense diagnostique explicable |

Le CECR peut etiqueter ce contenu `A0/A1 initial` pour interoperation. Il ne
determine ni l'ordre des activites, ni l'etat de progression.

## 3. Normalisation de la boite grammaticale

### 3.1 Familles

La boite jointe devient un catalogue de fonctions, pas un cours lineaire. Les
17 familles sont conservees avec un identifiant stable. `pilote` signifie qu'au
moins une structure est active pendant les trois jours; `pack suivant` qu'elle
est recevable apres prerequis; `differe` qu'une revue linguistique et des
prerequis plus avances sont obligatoires.

| ID | Famille fonctionnelle | Statut initial | Motif |
|---|---|---|---|
| `IT-F01` | existence et identification | pilote | besoins immediats, faible charge |
| `IT-F02` | volonte, capacite, permission, obligation, besoin | pilote partiel | demandes utiles; paradigmes complets exclus |
| `IT-F03` | temps et deroulement | pack suivant | aspect et temps prealables |
| `IT-F04` | habitude et frequence | pack suivant | present puis imparfait |
| `IT-F05` | gouts, preferences et emotions | pack suivant | accord de `piacere` a construire |
| `IT-F06` | essai, reussite et difficulte | pack suivant | infinitifs et clitiques partiels |
| `IT-F07` | cause, consequence et but | pack suivant | connecteurs apres propositions simples |
| `IT-F08` | condition et hypothese | differe | conditionnel et subjonctif |
| `IT-F09` | comparaison et degre | pack suivant | accords et complements de comparaison |
| `IT-F10` | maniere et simultaneite | pack suivant | gerondif et infinitif prepositionnel |
| `IT-F11` | questions generales | pilote partiel | questions de lieu et existence |
| `IT-F12` | demandes polies | pilote | coeur de la mission |
| `IT-F13` | opinion, certitude et doute | differe | alternance indicatif/subjonctif |
| `IT-F14` | relations entre les idees | pack suivant | coordination avant subordination |
| `IT-F15` | relatives | differe | fonctions syntaxiques et prepositions |
| `IT-F16` | pronoms et evitement des repetitions | differe | clitiques et combinaisons |
| `IT-F17` | ordres, conseils et interdictions | pack suivant | imperatif et registre |

### 3.2 Registre des 30 moules productifs fournis

| ID | Moule italien | Fonction | Prerequis principal | Activation |
|---|---|---|---|---|
| `IT-GRAM-001` | `voglio + infinitif` | volonte directe | present, infinitif | suivant |
| `IT-GRAM-002` | `vorrei + nom/infinitif` | demande douce | lexique cible | J2 |
| `IT-GRAM-003` | `posso + infinitif?` | permission pour soi | infinitif | J2 |
| `IT-GRAM-004` | `può + infinitif?` | demande formelle | infinitif, registre | J3 |
| `IT-GRAM-005` | `devo + infinitif` | obligation personnelle | infinitif | suivant |
| `IT-GRAM-006` | `bisogna + infinitif` | obligation generale | infinitif | suivant |
| `IT-GRAM-007` | `ho bisogno di + nom` | besoin | `avere`, preposition `di` | J3 |
| `IT-GRAM-008` | `mi serve/servono + nom` | necessite | nombre, clitique | suivant |
| `IT-GRAM-009` | `stare + gerondif` | action en cours | `stare`, gerondif | suivant |
| `IT-GRAM-010` | `avere appena + participe` | passe recent | passe compose | differe |
| `IT-GRAM-011` | `continuare a + infinitif` | continuation | infinitif | suivant |
| `IT-GRAM-012` | `cominciare a + infinitif` | commencement | infinitif | suivant |
| `IT-GRAM-013` | `smettere di + infinitif` | arret | infinitif | suivant |
| `IT-GRAM-014` | `cercare di + infinitif` | essai | infinitif | suivant |
| `IT-GRAM-015` | `riuscire a + infinitif` | reussite | infinitif | suivant |
| `IT-GRAM-016` | `non riuscire a + infinitif` | echec | negation, infinitif | suivant |
| `IT-GRAM-017` | `fare fatica a + infinitif` | difficulte | `fare`, infinitif | suivant |
| `IT-GRAM-018` | `essere abituato a + infinitif` | habitude | accord, infinitif | differe |
| `IT-GRAM-019` | `avere voglia di + infinitif` | envie | `avere`, infinitif | suivant |
| `IT-GRAM-020` | `mi piace/piacciono + nom/infinitif` | gout | nombre, construction indirecte | suivant |
| `IT-GRAM-021` | `se + present` | condition reelle | present | suivant |
| `IT-GRAM-022` | `per + infinitif` | but | infinitif | suivant |
| `IT-GRAM-023` | `prima di + infinitif` | anteriorite | infinitif | suivant |
| `IT-GRAM-024` | `dopo aver + participe` | posteriorite | participe passe | differe |
| `IT-GRAM-025` | `senza + infinitif` | absence d'action | infinitif | suivant |
| `IT-GRAM-026` | `mentre + verbe` | simultaneite | present | suivant |
| `IT-GRAM-027` | `c'è/ci sono + nom` | existence | nombre nominal | J2 |
| `IT-GRAM-028` | `è + nom/adjectif?` | identification/question | `essere` | J1 |
| `IT-GRAM-029` | `non so se + proposition` | incertitude | proposition simple | differe |
| `IT-GRAM-030` | `penso che + proposition` | opinion | indicatif/subjonctif | differe |

Les accents graphiques font partie des formes publiees : `può`, `c'è`, `è`.
Les identifiants restent ASCII, mais stimulus, reponse et correction conservent
la graphie italienne correcte.

### 3.3 Capacites ajoutees au pilote

La boite de 30 moules ne couvre pas seule une interaction reelle. Le pilote
ajoute des capacites pragmatiques et lexicalisees, sans les presenter comme des
regles universelles :

| ID | Capacite | Realisations publiees | Jour |
|---|---|---|---|
| `IT-PRAG-001` | saluer selon la situation | `Buongiorno`, `Buonasera`, `Salve` | J1 |
| `IT-PRAG-002` | prendre conge et remercier | `Arrivederci`, `Grazie`, `Prego` | J1 |
| `IT-ID-001` | s'identifier | `Sono + prenom` | J1 |
| `IT-ID-002` | presenter quelque chose | `Ecco + nom` | J1/J2 |
| `IT-QUEST-001` | demander un lieu | `Dove...?`, `Dov'è...?` | J3 |
| `IT-POLITE-001` | attirer l'attention | `Scusi` | J1/J3 |
| `IT-POLITE-002` | demander de repeter/ralentir | `Può ripetere?`, `Può parlare più lentamente?` | J3 |
| `IT-REPAIR-001` | signaler une rupture | `Non capisco` | J3 |

`Sono + prenom` n'enseigne pas que le pronom sujet doit etre exprime. Le modele
italien du pilote omet normalement `io` et evite toute regle absolue sur la
position du sujet.

## 4. Inventaire linguistique du pilote

### 4.1 Formes morphologiques certifiees

Le pilote ne certifie pas des paradigmes complets. Il publie seulement les
formes necessaires aux capacites actives :

- `essere` : `sono`, `è` dans les contenus;
- `potere` : `posso`, `può` de politesse;
- `volere` : `vorrei` comme forme fonctionnelle;
- `avere` : `ho` dans `ho bisogno di`;
- existence : `c'è`, `ci sono`;
- articles et elision requis : `un`, `una`, `un'`;
- pluriel cible publie : `camera/camere`.

Les identifiants et cles de recherche peuvent rester ASCII. Ils ne sont jamais
des reponses de reference.

Dans le pilote, ces moules ont deja ete presentes pendant F4/F5 ou verifies par
diagnostic. Ils sont `due` ou `target`, pas `new`. Si l'un manque, le plan du
jour est invalide et un `AdaptiveDay` de fondations est insere. Les expressions
de dialogue non ciblees restent `support` et ne produisent aucune preuve. Ainsi,
la limite d'une nouvelle famille grammaticale par `ModuleDay` n'est jamais
contournee par un regroupement de noms.

### 4.2 Prononciation

| ID | Cible | Exemples du pilote | Preuve permise |
|---|---|---|---|
| `IT-PHON-001` | voyelles nettes et rythme syllabique | `salve`, `camera`, `grazie` | discrimination + oral faible |
| `IT-PHON-002` | accent tonique de mots frequents | `caffè`, `per favore`, `arrivederci` | reperage + auto-evaluation |
| `IT-PHON-003` | `c/g` devant voyelle et graphies associees | `caffè`, `centro`, `grazie` | discrimination |
| `IT-PHON-004` | `gn`, `gli` et consonnes doubles | `bagno`, `biglietto`, `caffè` | exposition + oral faible |

Le pilote expose `IT-PHON-004` sans exiger une maitrise articulatoire. Aucun
score de prononciation automatique n'est produit.

### 4.3 Lexique cible

Chaque entree reference un sens du catalogue, pas une chaine isolee.

| Jour d'introduction | Sens cibles |
|---|---|
| J1 | `buongiorno`, `buonasera`, `salve`, `piacere`, `arrivederci`, `grazie`, `prego`, `scusi` |
| J2 | `caffè`, `acqua`, `conto`, `camera`, `bagno`, `farmacia`, `autobus`, `biglietto` |
| J3 | `stazione`, `centro`, `aiuto`, `qui`, `lentamente`, `diretto`, `parlare`, `ripetere` |

`per favore`, `certo`, `si`/`sì`, `parte` et les prenoms des dialogues sont lexique support :
ils sont expliques si necessaire mais ne recoivent aucune preuve lexicale cible.
Pour un debutant absolu, le compositeur ne presente pas plus de huit sens
nouveaux comme cibles dans un sprint; les autres restent support ou sont reportes.

Les ensembles publies sont `IT-LEXSET-D1`, `IT-LEXSET-D2` et `IT-LEXSET-D3`.
Ils referencent exactement les sens de la ligne correspondante et sont les seuls
identifiants collectifs autorises dans une definition d'exercice du pilote.

### 4.4 Fondations exécutables

| ID | Bloc | Primitive/mode | Cibles | Sortie attendue |
|---|---|---|---|---|
| `ITF-F1-01` | F1 | `contrast_choice` audio | `[IT-PHON-001, IT-PHON-003]` | 8/10 discriminations |
| `ITF-F1-02` | F1 | `cued_recall` lecture | `[IT-PHON-001, IT-PHON-003]` | 8/10 lectures ciblées |
| `ITF-F2-01` | F2 | `target_detection` | `IT-PHON-002` | accent repéré sans révélation |
| `ITF-F2-02` | F2 | `oral_rehearsal` | `[IT-PHON-002, IT-PHON-004]` | pratique, preuve faible seulement |
| `ITF-F3-01` | F3 | `matching` | `[IT-PRAG-001, IT-PRAG-002]` | situation et formule adaptées |
| `ITF-F3-02` | F3 | `dialogue_continuation` | `[IT-PRAG-001, IT-ID-001]` | échange de survie guidé |
| `ITF-F4-01` | F4 | `cloze` | `[IT-GRAM-002, IT-GRAM-003, IT-GRAM-007, IT-GRAM-027]` | choix fonctionnel correct |
| `ITF-F4-02` | F4 | `controlled_transformation` | `[IT-ID-001, IT-GRAM-027]` | personne ou nombre contrôlé |
| `ITF-F5-01` | F5 | `ordered_reconstruction` | `IT-POLITE-002` | demande de répétition |
| `ITF-F5-02` | F5 | `constrained_response` | `IT-REPAIR-001` | réparer quatre échanges sur cinq |

La gate `FOUNDATIONS_IT_V0` compose ces définitions sur au moins deux sessions
et répète les contrôles discriminants après 24 heures. L'oral sans correcteur ne
bloque pas la sortie, conformément au document 10.

### 4.5 Validateurs italiens partagés

| ID | Usage commun | Contrat |
|---|---|---|
| `IT-VAL-ORTHO-001` | cartes, cloze, dictée, Gym | NFC, apostrophes, accents discriminants par cible |
| `IT-VAL-MORPH-001` | cloze, Gym, production | traits personne/nombre et formes certifiées |
| `IT-VAL-EXIST-001` | `c'è/ci sono` | accord nombre nominal et construction publiée |
| `IT-VAL-PRAG-001` | dialogue, traduction, mission | rôles `Posso/Può`, politesse et registre |
| `IT-VAL-PHON-001` | audio, shadowing, TTS fixture | texte/transcript/segments/checksum cohérents, aucun score automatique |

Une définition référence ces IDs et leur révision. Elle ne recopie pas une règle
différente selon carte, dictée, Gym ou média.

## 5. Contenu humain publie

### 5.1 Dialogue J1 - Entrer en contact

`IT-MEDIA-D1-001` :

> A : Buongiorno.<br>
> B : Buongiorno. Sono Luca.<br>
> A : Piacere, sono Camille.<br>
> B : Piacere. Arrivederci.<br>
> A : Arrivederci.

Contrastes publies : `Buongiorno` convient dans la journee, `Buonasera` le soir,
`Salve` est neutre; `Sono Camille` identifie le locuteur; `Ecco Camille` le
presente. `Grazie, prego` est un echange, pas une phrase fusionnee.

### 5.2 Dialogue J2 - Obtenir quelque chose

`IT-MEDIA-D2-001` :

> A : Buongiorno. Vorrei un caffè e un'acqua, per favore.<br>
> B : Certo. Ecco il caffè.<br>
> A : Grazie. Posso avere il conto?<br>
> B : Certo.

La version publiee porte `caffè` dans le texte, le transcript et l'audio. Une
forme sans accent n'est pas ajoutee silencieusement aux variantes acceptees.

Contrastes publies : `Vorrei` est adapte a la demande; `Voglio` est grammatical
mais plus direct. `Posso avere...?` porte sur ce que demande le locuteur.
`C'è una camera?` appelle le singulier; `Ci sono due camere?` le pluriel.

### 5.3 Dialogue J3 - Comprendre et reparer

`IT-MEDIA-D3-001` :

> A : Scusi, c'è un autobus diretto per il centro?<br>
> B : Sì, parte da qui.<br>
> A : Può ripetere più lentamente, per favore?<br>
> B : L'autobus parte da qui.<br>
> A : Grazie. Ho bisogno di un biglietto.<br>
> B : Ecco.

`Può` s'adresse formellement a une personne; `Posso` parle de la possibilite du
locuteur. `Non capisco` et `Può ripetere?` sont des strategies normales, pas des
aveux d'echec.

### 5.4 Mission finale

`IT-MISSION-001` donne trois informations en francais :

1. vous arrivez dans une gare et saluez;
2. vous cherchez un autobus direct pour le centre et avez besoin d'un billet;
3. la reponse est trop rapide; vous demandez de repeter plus lentement puis
   remerciez et prenez conge.

La reponse peut etre ecrite ou dite. Les criteres obligatoires sont : salutation,
une question d'existence ou de lieu, une demande polie, une strategie de
reparation, l'expression du besoin et une cloture. Aucun script unique n'est
exige. Le correcteur utilise une grille, pas une comparaison de chaine globale.

## 6. Definitions et fixtures d'exercices

### 6.1 Catalogue du pilote

| ID | Primitive | Cible principale | Correcteur | Reponse de reference ou critere |
|---|---|---|---|---|
| `ITP-D1-01` | `micro_explanation` | `IT-ID-001` | aucune | acknowledgement seulement |
| `ITP-D1-02` | `matching` | `[IT-PRAG-001, IT-PRAG-002]` | appariement exact | situation vers salutation/cloture |
| `ITP-D1-03` | `contrast_choice` | `[IT-ID-001, IT-ID-002]` | ensemble accepte | `Sono Luca` vs `Ecco Luca` |
| `ITP-D1-04` | `oral_rehearsal` mode `shadowing` | `[IT-PHON-001, IT-PHON-002]` | auto-evaluation | media D1, cinq segments |
| `ITP-D1-05` | `cued_recall` | `[IT-PRAG-001, IT-PRAG-002]` | ensemble accepte | salutations naturelles publiees |
| `ITP-D1-06` | `controlled_transformation` | `IT-ID-001` | structurel | `Sono Luca` -> `Sono Camille` |
| `ITP-D1-07` | `dialogue_continuation` | `[IT-PRAG-001, IT-PRAG-002]` | grille | saluer, s'identifier, clore |
| `ITP-D1-08` | `oral_rehearsal` | `[IT-PHON-001, IT-PHON-002]` | auto-evaluation | trois groupes rythmiques |
| `ITP-D1-09` | `self_repair` | `IT-ID-001` | comparaison | reponse corrigee explicite |
| `ITP-D1-10` | `flashcard_recall` | `IT-LEXSET-D1` | exact + auto-grade | huit sens, deux directions |
| `ITP-D1-11` | `translation` cible -> appui | `[IT-PRAG-001, IT-ID-001]` | traduction bornee | mini-échange italien vers français, source J+1 |
| `ITP-D2-01` | `cued_recall` | `[IT-PRAG-001, IT-ID-001]` | ensemble accepte | rappel sans modele |
| `ITP-D2-02` | `micro_explanation` | `[IT-GRAM-002, IT-GRAM-003]` | aucune | contrastes publies |
| `ITP-D2-03` | `listening_comprehension` | `[IT-GRAM-002, IT-GRAM-003]` | ensemble accepte | qui demande quoi |
| `ITP-D2-04` | `cloze` | `IT-GRAM-027` | morphologique | `c'è` singulier, `ci sono` pluriel |
| `ITP-D2-05` | `controlled_transformation` | `IT-GRAM-002` | structurel | substitution de l'objet demande |
| `ITP-D2-06` | `oral_rehearsal` mode `shadowing` | `IT-PHON-003` | auto-evaluation | media D2 |
| `ITP-D2-07` | `constrained_response` | `[IT-GRAM-002, IT-GRAM-003]` | grille | commande et demande du compte |
| `ITP-D2-08` | `translation` | `[IT-GRAM-002, IT-GRAM-003]` | traduction bornee | quatre variantes publiees |
| `ITP-D2-09` | `dictation` | `[IT-PHON-002, IT-PHON-003]` | normalise + graphie | deux segments D2 |
| `ITP-D2-10` | `self_repair` | `IT-GRAM-002` | comparaison | correction puis explication courte |
| `ITP-D2-11` | `delayed_recode` appui -> cible | source `ITP-D1-11` | ensemble accepte | reconstruire le mini-échange J1 depuis le français corrigé |
| `ITP-D2-12` | `translation` cible -> appui | `[IT-GRAM-002, IT-GRAM-003]` | traduction bornee | demandes italiennes vers français, source J+1 |
| `ITP-D3-01` | `cued_recall` | `[IT-GRAM-002, IT-GRAM-003]` | ensemble accepte | demande polie sans modele |
| `ITP-D3-02` | `micro_explanation` | `[IT-GRAM-004, IT-GRAM-007]` | aucune | personne, besoin, reparation |
| `ITP-D3-03` | `listening_comprehension` | `IT-REPAIR-001` | grille | lieu, besoin, demande de repetition |
| `ITP-D3-04` | `oral_rehearsal` mode `shadowing` | `[IT-PHON-003, IT-PHON-004]` | auto-evaluation | media D3 |
| `ITP-D3-05` | `controlled_transformation` | `[IT-GRAM-004, IT-GRAM-007]` | structurel | `parlare`/`ripetere`, `aiuto`/`biglietto` |
| `ITP-D3-06` | `ordered_reconstruction` | `IT-POLITE-002` | ordres acceptes | `Può ripetere più lentamente?` |
| `ITP-D3-07` | `dialogue_continuation` | `[IT-QUEST-001, IT-REPAIR-001]` | grille | demander, reparer, remercier |
| `ITP-D3-08` | `extended_production` | `IT-MISSION-001` | grille | six criteres obligatoires |
| `ITP-D3-09` | `oral_rehearsal` | `IT-MISSION-001` | auto-evaluation | enregistrement local optionnel |
| `ITP-D3-10` | `self_repair` | `IT-MISSION-001` | grille avant/apres | seconde production ciblee |
| `ITP-D3-11` | `delayed_recode` appui -> cible | source `ITP-D2-12` | traduction bornee | reconstruire les demandes J2 depuis le français corrigé |
| `ITP-D3-12` | `translation` cible -> appui | `[IT-REPAIR-001, IT-MISSION-001]` | traduction bornee | échange de réparation italien vers français, source post-pilote |

Les reponses de reference sont publiees avec accents. Les identifiants et les
descriptions ASCII ci-dessus n'elargissent pas l'ensemble accepte.

### 6.2 Gym du pilote

| Jour | Structure | Operations | Preconditions | Sortie |
|---|---|---|---|---|
| J1 | `Sono + prenom` | `GYM-01` substitution | explication `Sono/Ecco` | deux identifications sans modele |
| J2 | `Vorrei + nom` | `GYM-01` substitution | noms connus ou fournis | trois demandes, dont une sans aide |
| J2 | `c'è/ci sono` | `GYM-03` nombre | `camera/camere`, nombres 1/2 | contraste singulier/pluriel |
| J3 | `Può + infinitif?` | `GYM-01`, `GYM-08` | registre formel fourni | deux demandes polies |
| J3 | `Ho bisogno di + nom` | `GYM-01` | noms connus ou support | besoin dans un nouveau contexte |

Le cycle G2 de J+1 rappelle J1 au debut de J2 et J2 au debut de J3. Les sorties
J3 ouvrent un rappel espace a J+3 et un transfert a J+7; elles ne ferment aucune
maitrise le soir du troisieme jour.

## 7. Journees et compositions sous budget

### 7.1 Intention de chaque jour

| Jour | Objectif communicatif | Nouveaute grammaticale | Rappel | Production finale du jour |
|---|---|---|---|---|
| J1 | saluer, s'identifier, clore | `Sono`, `E`, `Ecco` | aucun | mini-echange de trois tours |
| J2 | obtenir et demander si quelque chose existe | `Vorrei`, `Posso`, `c'è/ci sono` | J1 sans modele | commande + question d'existence |
| J3 | localiser, demander de repeter, exprimer un besoin | `Può`, `Ho bisogno di`, `Dov'è` | J2 sans modele | mission finale integree |

### 7.2 Plans 15, 30 et 60 minutes

Chaque total reserve un tampon pour navigation, correction et sauvegarde. Le
compositeur peut reduire le nombre d'items d'une activite, jamais supprimer le
rappel du jour precedent ni la production finale du budget concerne.

| Jour | Budget | Instances ordonnees | Temps planifie | Tampon |
|---|---:|---|---:|---:|
| J1 | 15 | `ITP-D1-01, ITP-D1-11, ITP-D1-04, ITP-D1-07` | 12 min 30 | 2 min 30 |
| J1 | 30 | plan 15 + `ITP-D1-02, ITP-D1-03, ITP-D1-05, ITP-D1-06` | 27 min | 3 min |
| J1 | 60 | plan 30 + `ITP-D1-08, ITP-D1-09, ITP-D1-10` avec repetitions | 54 min | 6 min |
| J2 | 15 | bloc traduction `ITP-D2-11 + ITP-D2-12`, puis `ITP-D2-02, ITP-D2-04, ITP-D2-07` | 12 min 30 | 2 min 30 |
| J2 | 30 | plan 15 + `ITP-D2-03, ITP-D2-05, ITP-D2-06` | 27 min | 3 min |
| J2 | 60 | plan 30 + `ITP-D2-08, ITP-D2-09, ITP-D2-10` avec repetitions | 54 min | 6 min |
| J3 | 15 | bloc traduction `ITP-D3-11 + ITP-D3-12`, puis `ITP-D3-02, ITP-D3-03, ITP-D3-08` | 12 min 30 | 2 min 30 |
| J3 | 30 | plan 15 + `ITP-D3-04, ITP-D3-05, ITP-D3-07` | 27 min | 3 min |
| J3 | 60 | plan 30 + `ITP-D3-06, ITP-D3-09, ITP-D3-10` et mission etendue | 54 min | 6 min |

Les raccourcis utilisent les identifiants complets `ITP-...`. Un budget de 10 a
60 minutes par pas de cinq est derive du palier inferieur en ajoutant ou retirant
des repetitions publiees selon leur priorite. A 45 minutes, le moteur part du
plan 30 et ajoute oral, reparation et rappel lexical dans cet ordre, sous 40 min
30 de contenu planifie et 4 min 30 de tampon.

À J2 et J3, le premier bloc contient deux micro-instances de directions opposées
mais conserve une seule enveloppe de temps. Si aucune source J0
valide n'existe à J2/J3, le recodage n'est pas improvisé : le rappel
`ITP-D2-01` ou `ITP-D3-01` le remplace et aucune preuve de production différée
n'est déclarée.

### 7.3 Priorites de composition

1. dette J+1 et reprise interrompue;
2. micro-explication necessaire a une nouvelle structure;
3. une preuve guidee puis une production;
4. Gym si les prerequis sont presents;
5. oral/shadowing si le media publie est disponible;
6. extension lexicale, dictee et reparation supplementaire.

Si le media manque, le plan utilise seulement l'alternative publiee. Sans
alternative, l'instance devient `unavailable` et le temps est realloue a une
production ou comprehension couvrant une autre cible declaree; aucune preuve
orale n'est inventee.

## 8. Profils et resultats attendus

### 8.1 Debutant absolu `P-ABS`

- Entree : alphabet latin familier, aucune preuve d'italien.
- Composition : toutes les micro-explications, au plus huit sens nouveaux cibles
  par jour, aides H1/H2 disponibles avant H3/H4.
- Apres trois reussites parfaites sans aide : capacites `decouvert` ou
  `in_progress`, jamais `reliable` ni `mastered` faute de délai et de contextes.
- En cas de difficulte phonologique : dette ciblee et pratique orale sans note.

### 8.2 Faux debutant `P-FAUX`

- Entree : reconnaissance de salutations et de quelques noms, aucune production
  recente prouvee.
- Composition : exposition courte, davantage de Gym et rappels sans modele.
- Une preuve existante ne dispense un bloc que si sa cible, sa modalite et sa
  fraicheur conviennent.
- Les productions J2/J3 peuvent rendre une facette candidate à `reliable` si des
  preuves anterieures independantes satisfont aussi le modele de progression.

### 8.3 Intermediaire `P-INT`

- Entrée : preuves `reliable` sur toutes les structures du pilote.
- Composition : mission J3, variantes de contexte, reparation et oral; les
  explications sont omises mais restent consultables.
- Reussir la mission confirme des facettes precises. Echouer ouvre une dette
  ciblee sans degrader un profil global arbitrairement.
- Un diagnostic suffisant peut recommander la dispense du module; la dispense
  ne cree aucune nouvelle preuve.

## 9. Correction italienne du pilote

### 9.1 Normalisation permise

- Unicode NFC, espaces multiples, casse initiale et ponctuation finale peuvent
  etre normalises lorsqu'ils ne sont pas la cible;
- apostrophe droite et typographique sont equivalentes;
- ordre des tours, choix de registre, nombre et prepositions cibles restent
  discriminants;
- `e/è`, `ce/c'è` et `puo/può` ne sont pas declares equivalents corrects.

Une reponse sans accent peut recevoir `partially_correct` si l'intention et la
structure sont exactes, avec erreur `orthography.accent`; elle n'est `correct`
que lorsque la definition ne cible pas la graphie et que la politique publiee
l'autorise. En dictee ou rappel ecrit de la forme, l'accent manquant est un
critere obligatoire non satisfait.

### 9.2 Grilles

La mission finale note chaque critere `0/1` : intention accomplie, structure
attendue, intelligibilite semantique, registre adapte, lexique cible pertinent,
et absence de contradiction. Le verdict est :

- `correct` : toutes les intentions obligatoires et aucune contradiction;
- `partially_correct` : echange fonctionnel mais un element obligatoire manque;
- `incorrect` : besoin central non communique ou sens contradictoire;
- `ambiguous` : interpretation non decidable depuis la production.

Naturalite et orthographe sont des criteres separes. Une formulation naturelle
non prevue peut etre envoyee en revue humaine; elle ne devient pas fausse parce
qu'elle n'est pas dans une liste courte.

### 9.3 Reponses et contrastes invalides connus

- `Arrivederci, prego` comme echange complet sans contexte;
- `Grazie, prego` attribue aux paroles d'un seul locuteur;
- regle « le pronom sujet se place toujours avant le verbe »;
- `andare + infinitif` comme equivalent general du futur proche francais;
- `c'è` avec un nom pluriel ou `ci sono` avec un singulier non coordonne;
- confusion de `Posso...?` et `Può...?` dans les roles de locuteur;
- usage de `Voglio` presente comme seule demande polie.

Ces cas sont des fixtures de rejet ou de contraste, pas seulement des notes
editoriales.

## 10. Scenarios end-to-end

| ID | Scenario | Resultat attendu |
|---|---|---|
| `PILOT-E2E-01` | `P-ABS`, 15 min, trois jours, sans aide | trois sprints termines, rappels J+1, aucune maitrise prematuree |
| `PILOT-E2E-02` | `P-ABS`, revelation sur `c'e` | force nulle sur cette cible, dette J3, autres cibles independantes |
| `PILOT-E2E-03` | `P-FAUX`, 30 min, dette J1 | rappel prioritaire avant nouveaute, Gym adaptee |
| `PILOT-E2E-04` | `P-INT`, 15 min | mission et transfert, explications omises |
| `PILOT-E2E-05` | interruption au milieu du shadowing | reprise au segment, vitesse et aides restaurees, aucun doublon |
| `PILOT-E2E-06` | audio D2 absent, alternative publiee | alternative explicite, revision tracee |
| `PILOT-E2E-07` | audio et alternative absents | shadowing indisponible, aucune preuve orale, plan poursuit |
| `PILOT-E2E-08` | transcript affiche en ecoute | activite conservee, aucune preuve d'ecoute sur la phase |
| `PILOT-E2E-09` | correction de mission ambigue | `ambiguous`, aucune dette automatique, revue possible |
| `PILOT-E2E-10` | meme soumission rejouee | un effet metier et une serie d'observations |
| `PILOT-E2E-11` | bloc passe volontairement | `skipped`, distinct d'une erreur et d'un abandon |
| `PILOT-E2E-12` | correcteur indisponible | réponse conservée, `not_evaluable`, jamais réussite |

## 11. Gates de certification

Le pilote peut devenir fixture normative seulement si :

1. les trois dialogues, alternatives, reponses et contre-exemples passent une
   revue par un italophone competent;
2. chaque cible renvoie a une capacite, un sens lexical ou une cible
   phonologique du pack;
3. chaque instance respecte une primitive certifiee de `12` sans champ special;
4. les neuf plans 15/30/60 respectent budget, ordre et limite de nouveaute;
5. meme profil, revisions et graine produisent le meme plan;
6. les trois profils produisent les resultats attendus sans LLM ni reseau;
7. aides, replays, transcript, saut, interruption et contestation sont traces;
8. aucune auto-evaluation orale ne devient une preuve forte;
9. clavier, lecteur d'ecran, zoom 200 % et largeur 320 px sont verifies lors de
   l'implementation du lecteur;
10. les evenements permettent de reconstruire tentative, correction,
    observations, dette et bilan;
11. aucun contenu V1 n'est importe sans decision et provenance explicites;
12. une revue pedagogique confirme naturalite, charge de nouveaute et coherence
    entre dialogues, lexique, Gym et mission finale.

La validation de ces gates ferme G05 et fournit la premiere preuve de G5
Pedagogy-ready. Tant que la revue linguistique humaine et l'essai sur les trois
profils n'ont pas eu lieu, le statut de ce document est `specifie`, pas
`pedagogiquement valide`.

## 12. Hors perimetre explicite

- regeneration des cours italiens V1;
- paradigmes complets de conjugaison;
- evaluation CECR globale;
- reconnaissance automatique de prononciation;
- conversation temps reel;
- calibration finale des seuils de maitrise;
- contenu culturel ou regional approfondi;
- ouverture publique du pack italien.

Ces exclusions empechent le pilote de devenir un mini-curriculum implicite. Son
role est de demontrer un parcours quotidien court, naturel, deterministe et
mesurable avant toute extension du pack.
