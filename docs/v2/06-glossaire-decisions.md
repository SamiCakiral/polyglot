# Polyglot V2 - Glossaire, décisions et exigences normatives

## 1. Autorité documentaire

En cas de conflit, l'ordre d'autorité est :

1. décisions explicitement approuvées dans ce document ;
2. contrats de domaine numérotés ;
3. invariants et machines d'état ;
4. matrice de conservation fonctionnelle ;
5. spécifications de parcours et UX ;
6. description générale de la vision ;
7. comportement historique de la V1.

Une modification d'une règle de niveau supérieur exige une nouvelle décision et
la mise à jour des documents dépendants. Les plans d'implémentation ne peuvent
pas modifier une décision d'architecture.

## 2. Glossaire normatif

### Identité et langues

- **Utilisateur** : personne possédant un compte Polyglot.
- **Langue maternelle** : langue principale utilisée pour les explications et
  équivalences au sein d'un profil d'apprentissage.
- **Langue cible** : langue entraînée par un profil.
- **Langue d'appui** : langue connue pouvant compléter la langue maternelle pour
  certaines explications. Elle n'est jamais choisie sans consentement.
- **Variété linguistique** : combinaison d'une langue, d'une région, d'une norme
  et éventuellement d'un système d'écriture.
- **Paire linguistique** : relation orientée langue d'appui vers langue cible.
- **Profil linguistique** : relation personnelle entre un utilisateur et une
  langue cible, avec objectifs, préférences et projections de connaissance.
- **Pack de langue** : catalogue versionné des fondations, structures,
  validateurs et contenus nécessaires pour utiliser le moteur avec une langue.

### Pédagogie

- **Modalité** : compréhension écrite, compréhension orale, expression écrite ou
  expression orale.
- **Opération** : reconnaître, rappeler, discriminer, transformer, produire,
  interagir, réparer ou transférer.
- **Compétence** : capacité pédagogique mesurable, définie par modalité,
  opération, cible, prérequis et protocoles de preuve.
- **Fonction communicative** : intention telle que demander, comparer, nuancer,
  raconter ou exprimer un besoin.
- **Structure grammaticale** : réalisation linguistique permettant une fonction
  et portant contraintes, contrastes et prérequis.
- **Moule** : patron productif d'une structure, comportant des emplacements et
  règles d'instanciation.
- **Fondation** : prérequis indispensable avant les modules ouverts : écriture,
  lecture, sons, conventions ou stratégies minimales.
- **Observation** : conclusion atomique tirée d'une tentative selon un protocole
  et une correction donnés.
- **Preuve** : observation recevable pour mettre à jour une facette de
  connaissance. Toute observation n'est pas nécessairement une preuve.
- **Facette** : dimension précise de connaissance, par exemple reconnaissance
  orale d'un sens ou production écrite d'une structure.
- **Maîtrise** : projection versionnée fondée sur plusieurs preuves, délais,
  contextes et contradictions. Ce n'est jamais un fait saisi directement.
- **Confiance** : estimation de la solidité d'une projection compte tenu du
  nombre, de la qualité et de la diversité des preuves.
- **Dette d'apprentissage** : besoin de remédiation ciblé, ouvert par une cause et
  fermé seulement par une preuve conforme.
- **Transfert** : réussite sans aide dans un contexte suffisamment différent de
  ceux utilisés pendant l'apprentissage.

### Lexique

- **Unité lexicale** : mot simple, expression multi-mots, nom propre pertinent ou
  construction lexicalisée possédant une identité stable.
- **Lemme** : représentation éditoriale conventionnelle d'une unité ; il n'est
  jamais son identifiant technique.
- **Forme** : réalisation orthographique ou phonologique avec traits
  morphologiques.
- **Sens lexical** : unité sémantique de grain pédagogique, distincte des autres
  sens d'une même unité.
- **Cadre d'usage** : contraintes de valence, préposition, collocation, registre
  et pragmatique.
- **Rencontre** : occurrence effectivement présentée ou produite dans un contexte
  identifiable. Elle ne prouve ni attention ni compréhension.
- **Word Bank** : projection personnelle complète des unités rencontrées ou
  ajoutées, de leurs preuves, facettes, dettes, listes et échéances.
- **Liste de vocabulaire** : sélection intentionnelle ou dynamique de sens
  lexicaux. Elle ne duplique pas le catalogue.
- **Carte / invite mémoire** : protocole de rappel planifiable portant sur un
  sens, une forme, une relation ou une direction.
- **Référentiel lexical cible** : ensemble borné et versionné utilisé pour parler
  de couverture ou de lacune.

### Curriculum et exercices

- **Module** : arc d'apprentissage versionné de 3 à 30 jours avec objectifs,
  contextes, compétences, lexique et mission finale.
- **Journée** : plan pédagogique abstrait d'un module, indépendant d'une date
  civile tant qu'il n'est pas affecté.
- **Plan de session** : sélection figée d'activités, contenus et cibles pour une
  exécution donnée.
- **Sprint** : exécution quotidienne guidée d'un plan de session sous budget de
  temps.
- **Entraînement libre** : plan de session demandé par l'utilisateur hors du
  curriculum quotidien, utilisant le même moteur.
- **Primitive d'exercice** : interaction générique et mode de preuve communs aux
  langues.
- **Définition d'exercice** : contrat versionné d'une primitive, de ses entrées,
  aides, correction et observations.
- **Instance d'exercice** : contenu concret figé produit depuis une définition.
- **Tentative** : exécution d'une instance par un utilisateur, avec réponse brute,
  aides, durée et état.
- **Correction** : verdict versionné et explicable portant sur une tentative.
- **Aide** : information demandée ou révélée pendant une tentative et modifiant
  la force des preuves possibles.

### Contenu et génération

- **Contenu** : ressource pédagogique versionnée : texte, audio, structure,
  exemple, définition, exercice ou module.
- **Révision** : version immuable d'un contenu.
- **Brouillon** : révision non publiée, modifiable par remplacement.
- **Publication** : opération atomique rendant une révision disponible.
- **Provenance** : source, auteur, outil, modèle, prompt et transformations ayant
  produit une assertion ou un contenu.
- **Tâche de génération** : demande bornée de production de brouillon.
- **Tentative de génération** : appel concret à un auteur humain, fixture ou LLM.
- **Outil LLM** : commande strictement typée exposée par une façade contrôlée.

## 3. Décisions produit

### DEC-001 - Nouvelle base

- Statut : accepté.
- Décision : aucune donnée utilisateur de la V1 n'est migrée.
- Conséquence : la V1 reste référence fonctionnelle et visuelle. Les contenus
  anciens sont seulement des archives candidates à un nouvel audit.

### DEC-002 - Niveau et CECR

- Statut : accepté.
- Décision : Polyglot suit quatre compétences et des sous-compétences fondées sur
  des preuves. Le CECR peut être affiché comme estimation d'interopérabilité,
  jamais comme structure du curriculum ni vérité principale.

### DEC-003 - Piliers

- Statut : accepté.
- Décision : les Piliers deviennent une carte de progression et un accès aux
  évaluations. Les cours et exercices vivent dans modules et entraînement libre.

### DEC-004 - Word Bank

- Statut : accepté.
- Décision : la Word Bank est une projection personnelle complète des rencontres
  lexicales, agrégée par sens et facette. Les cartes et listes sont des vues.

### DEC-005 - Sprint

- Statut : accepté.
- Décision : le sprint est préparé déterministement avant exécution. Il compose
  rappels, vocabulaire, compréhension, boîte grammaticale, Gym, oral/shadowing,
  production et rappel différé selon le budget disponible.

### DEC-006 - Durées

- Statut : accepté.
- Décision : l'utilisateur choisit un budget libre de 10 à 60 minutes par pas de
  5 minutes. L'interface propose 15, 30, 45 et 60 comme raccourcis. Le moteur
  compose sous le budget exact.

### DEC-007 - Boîte grammaticale et Gym

- Statut : accepté.
- Décision : une structure est d'abord expliquée et contrastée, puis produite,
  transformée, rappelée à J+1 et transférée. La Gym n'introduit pas aléatoirement
  une règle et n'utilise que des transformations dont les prérequis sont acquis.

### DEC-008 - Quatre évaluations

- Statut : accepté.
- Décision : lecture, écoute, écriture et oral sont évalués indépendamment. Une
  épreuve ne modifie que les facettes réellement mesurées.

### DEC-009 - Expression orale initiale

- Statut : accepté.
- Décision : avant STT ou conversation temps réel, l'architecture fournit un
  protocole simulé : consigne, enregistrement facultatif local, auto-évaluation
  structurée et validation humaine facultative. Aucune note automatique forte.

### DEC-010 - Fonctionnement sans IA

- Statut : accepté.
- Décision : tout le produit fonctionne avec contenus humains et fixtures. Le
  LLM produit uniquement des brouillons ou propositions via des outils fermés.

### DEC-011 - Référentiel de maîtrise

- Statut : accepté.
- Décision : aucun pourcentage de « langue connue » sans référentiel borné,
  nommé et versionné.

### DEC-012 - Nouveau dépôt

- Statut : accepté.
- Décision : l'implémentation cible un nouveau dépôt `polyglot-v2`. Les documents
  sont d'abord finalisés dans la V1 puis copiés comme baseline.

## 4. Décisions techniques

### DEC-T01 - Architecture

- Monolithe modulaire avec frontières de domaines explicites.
- Aucun microservice au MVP.
- Dépendances dirigées vers le coeur métier ; fournisseurs derrière des ports.

### DEC-T02 - Stack de référence

- Backend Python asynchrone avec FastAPI, Pydantic, SQLAlchemy et Alembic.
- PostgreSQL comme source de vérité.
- Frontend React et TypeScript, application web responsive même origine.
- Contrat OpenAPI versionné entre frontend et backend.
- Tests Python et TypeScript, navigateur automatisé avec Playwright.
- Les versions majeures, mineures et correctives seront verrouillées à la
  création du dépôt après vérification de compatibilité. Les spécifications ne
  dépendent pas d'un numéro de version encore non éprouvé par le projet.

### DEC-T03 - Authentification

- Un compte peut posséder une ou plusieurs identités de connexion derrière un
  `IdentityProviderPort` : mot de passe local ou fournisseur OIDC.
- Les mots de passe locaux sont hachés avec Argon2id. Un compte OIDC ne stocke
  aucun mot de passe fournisseur.
- Session serveur même origine dans cookie `HttpOnly`, `Secure`, `SameSite=Lax`.
- Protection CSRF sur commandes navigateur.
- Pas de JWT persistant dans le stockage navigateur.
- Rôles initiaux : `learner`, `author`, `reviewer`, `support`, `admin` et
  `worker`, avec séparation auteur/reviewer et refus par défaut.

### DEC-T04 - Identifiants et temps

- Identifiants UUIDv7 générés par l'application.
- Horodatages UTC avec précision suffisante pour ordonner les événements.
- Fuseau IANA enregistré par profil ; les journées pédagogiques utilisent ce
  fuseau et une heure de bascule configurable, par défaut 04:00 locale.
- Une journée de module n'est pas liée à un jour de semaine.

### DEC-T05 - API et transactions

- API HTTP JSON sous `/api/v1`.
- Commandes synchrones lorsqu'elles terminent sous le budget de latence.
- Génération, analyse média et travaux longs utilisent des jobs persistants.
- Concurrence optimiste par version d'agrégat.
- Idempotence obligatoire pour soumissions, imports et jobs.
- Outbox transactionnelle ; pas de dual-write.
- Le système conserve des événements d'apprentissage, sans imposer un event
  sourcing intégral à tous les agrégats.

### DEC-T06 - Jobs

- État, tentatives, résultats et idempotence des jobs en PostgreSQL ; la file
  n'est jamais la source de vérité.
- Dispatcher PostgreSQL local ; Cloud Tasks peut transporter les livraisons en
  production. Aucun Redis n'est requis au MVP.
- Les retries de livraison technique sont bornés. Un appel fournisseur, payé ou
  non déterministe n'est jamais relancé sans politique explicite et budget.
- Aucun fallback silencieux vers un fournisseur différent.

### DEC-T07 - Médias

- Métadonnées en PostgreSQL, fichiers dans un stockage compatible S3.
- En développement, adaptateur filesystem compatible avec le même port.
- Texte, transcription, droits, source et checksum versionnés.

### DEC-T08 - Graphe

- Relations lexicales dans PostgreSQL avec tables d'arêtes typées.
- Pas de base graphe au MVP.
- Une future projection graphe doit être reconstruisible depuis PostgreSQL.

### DEC-T09 - Versionnement

- Identité stable séparée des révisions immuables.
- Une révision publiée n'est jamais modifiée.
- Tentatives et preuves épinglent toutes les versions utilisées.
- Les changements incompatibles créent une nouvelle version de schéma.

### DEC-T10 - Frontend

- Le frontend n'embarque aucune règle de maîtrise ou de planification.
- Il rend des contrats d'exercice et envoie des commandes utilisateur.
- Les mises à jour optimistes sont réservées aux actions réversibles.
- Sauvegarde automatique avec état visible et reprise exacte.

## 5. Exigences non fonctionnelles

### Performance cible MVP

- disponibilité API et web : 99,5 % mensuel ;
- lectures API ordinaires : p95 inférieur ou égal à 300 ms côté serveur ;
- commandes ordinaires : p95 inférieur ou égal à 700 ms ;
- recherche Word Bank : p95 inférieur à 100 ms sur le corpus de charge ;
- file de rappels dus : p95 inférieur à 100 ms ;
- voisinage lexical à deux sauts, limité à 500 noeuds : p95 inférieur à 200 ms ;
- composition d'un sprint préparé : moins de 2 secondes hors génération ;
- reprise de session : première donnée utile en moins d'une seconde côté serveur ;
- aucun appel fournisseur sur le chemin obligatoire d'un sprint déjà prêt.

### Volumétrie de preuve

Le banc synthétique minimal contient :

- 1 000 000 unités et sens partagés pour une langue ;
- 100 000 sens personnels pour un profil extrême ;
- 5 000 000 rencontres lexicales ;
- 10 000 000 événements d'apprentissage ;
- 10 000 listes et 1 000 sessions historiques pour le profil de charge.

Ces volumes valident l'architecture ; ils ne constituent pas une prévision
d'utilisation moyenne.

### Accessibilité et compatibilité

- cible WCAG 2.2 AA ;
- navigation complète au clavier ;
- focus visible et ordre logique ;
- zoom 200 % sans perte de fonctionnalité ;
- alternatives aux contenus audio et aux interactions temporelles ;
- Chrome, Safari, Firefox et Edge sur leurs deux versions majeures courantes ;
- Safari iOS et Chrome Android courants ;
- largeur fonctionnelle minimale : 320 pixels CSS.

### Fiabilité

- aucune réponse confirmée perdue après accusé de réception ;
- reprise déterministe après interruption navigateur ou worker ;
- sauvegardes quotidiennes chiffrées en production ;
- test de restauration régulier avant toute déclaration de disponibilité ;
- objectif initial RPO 5 minutes et RTO 4 heures ;
- migrations de schéma réversibles ou accompagnées d'un plan de restauration.

### Sécurité et confidentialité

- moindre privilège et isolation stricte par utilisateur ;
- validation serveur de toute autorisation ressource ;
- chiffrement TLS en transit et chiffrement du stockage de production ;
- secrets hors dépôt ;
- contexte privé minimisé avant tout fournisseur ;
- productions brutes exportables et supprimables par l'utilisateur ;
- audit de sécurité distinct des événements pédagogiques ;
- logs techniques sans réponses complètes ni secrets ;
- limitation de débit sur authentification, imports et génération.

### Observabilité

- logs structurés avec corrélation et causalité ;
- métriques de latence, erreur, queue, contenu rejeté et correction contestée ;
- traces des commandes longues et adaptateurs ;
- chaque recommandation et projection pédagogique est explicable ;
- aucune donnée privée brute dans les métriques.

## 6. Politique de décision restante

Les paramètres pédagogiques numériques sont des politiques versionnées. Leur
valeur initiale est fixée dans la spécification pédagogique, puis calibrée sur le
pilote italien sans changer les faits historiques. Les choix purement visuels
seront validés lors de la conception UX ; ils ne bloquent pas les contrats du
backend.
