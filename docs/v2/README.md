# Polyglot V2 - Dossier d'architecture

Ce dossier spécifie la reconstruction de Polyglot dans un dépôt et une base
vides. Il conserve les capacités utiles de la V1, mais aucun compte, historique,
contenu ou état V1 n'est migré. La première implémentation doit fonctionner sans
LLM ni fournisseur réseau ; l'IA intervient ensuite comme auteur assisté derrière
des outils bornés et une publication humaine.

## Statut exact

- `specified` : décisions, contrats, données, pédagogie, API, UX et plan existent.
- `not_implemented` : le dépôt V2, les schémas exécutables, fixtures et écrans
  n'existent pas encore.
- `not_verified` : aucune gate V2 `G1-G7`, revue linguistique, restauration,
  pilote humain ou canary n'est présentée comme obtenue.
- Les captures `assets/v1` sont des preuves historiques de la V1 uniquement.

Le registre [TASKS.md](./TASKS.md) suit la fermeture documentaire. Le plan
[27-plan-implementation-detaille.md](./27-plan-implementation-detaille.md)
sépare ensuite implémentation, preuve et acceptation.

## Ordre d'autorité

En cas de conflit, appliquer d'abord une décision explicitement approuvée du
document 06, puis le document propriétaire de la règle. Une décision ne vaut
pas définition locale : pour les noms, champs, transitions et formules, le
contrat spécialisé indiqué ci-dessous reste la source normative. Les documents
de vision, UX et transition ne peuvent modifier ni l'un ni l'autre.

| Sujet | Propriétaire normatif |
|---|---|
| termes, décisions, NFR et frontières produit | [06](./06-glossaire-decisions.md) |
| noms techniques, enums, commandes, routes et erreurs | [25](./25-registre-enums-commandes-api.md) |
| entités, champs, nullabilité, clés, cardinalités et rétention | [26](./26-dictionnaire-donnees.md) |
| agrégats et invariants métier | [08](./08-modele-metier.md) |
| transitions, événements, idempotence et concurrence | [09](./09-etats-commandes-evenements.md), puis 25 pour les noms |
| calcul d'une observation d'exercice | [12](./12-contrats-exercices.md) |
| agrégation des preuves et états de maîtrise | [10](./10-pedagogie-maitrise.md) |
| mémoire planifiée et FSRS | [24](./24-memoire-et-fsrs.md) |
| Word Bank et graphe lexical personnel | [07](./07-graphe-lexical-personnel.md) |
| curriculum, budget et composition du sprint | [11](./11-curriculum-sprint.md) |
| pack générique et pilote italien | [13](./13-pack-italien-pilote.md) |
| évaluations des quatre compétences | [14](./14-evaluations.md) |
| architecture applicative et modules | [15](./15-architecture-applicative.md) |
| transport, client et lecteur frontend | [16](./16-api-et-contrats-frontend.md) |
| sécurité, confidentialité, jobs et médias | [17](./17-securite-confidentialite-jobs-medias.md) |
| exploitation, sauvegarde et livraison | [18](./18-exploitation-environnements-livraison.md) |
| preuves, fixtures, quality gates et délégation | [19](./19-tests-quality-gates-delegation.md) et [23](./23-tracabilite-execution.md) |
| parcours, états limites et ergonomie | [21](./21-personas-parcours-limites.md), [20](./20-architecture-ux-frontend.md) et [28](./28-wireframes-et-design-system.md) |
| imports, édition et validation | [22](./22-imports-edition-validation.md) |
| lots, ordre, write sets et critères de sortie | [27](./27-plan-implementation-detaille.md) |
| contrats de la façade d'outils | [30](./30-contrats-outils-auteur.md) |
| incréments red/green W00-W19 | [31](./31-registre-increments-implementation.md) |

Toute modification d'une règle propriétaire exige une mise à jour des documents
dépendants, de la traçabilité et du plan avant implémentation.

## Documents

### Référence et transition

0. [Inventaire fonctionnel factuel de la V1](./00-inventaire-fonctionnel-v1.md)
1. [Vision et architecture globale](./01-vision-architecture.md)
2. [Backend pédagogique et moteur d'exercices](./02-backend-pedagogique.md)
3. [Données, vocabulaire, progression et statistiques](./03-donnees-progression.md)
4. [UX, transition et feuille de route](./04-ux-migration-roadmap.md)
5. [Matrice de conservation V1 vers V2](./05-matrice-conservation-v1-v2.md)

Les documents 01-04 expliquent l'intention. Si un détail diverge, le contrat
spécialisé indiqué dans la table d'autorité prévaut.

### Contrats métier et pédagogiques

6. [Glossaire, décisions et exigences](./06-glossaire-decisions.md)
7. [Graphe lexical personnel et Word Bank](./07-graphe-lexical-personnel.md)
8. [Modèle métier canonique](./08-modele-metier.md)
9. [États, commandes, événements et erreurs](./09-etats-commandes-evenements.md)
10. [Preuves, maîtrise, diagnostic et recommandations](./10-pedagogie-maitrise.md)
11. [Curriculum, modules et compositeur de sprint](./11-curriculum-sprint.md)
12. [Contrats et primitives d'exercices](./12-contrats-exercices.md)
13. [Pack italien et pilote déterministe](./13-pack-italien-pilote.md)
14. [Évaluations des quatre compétences](./14-evaluations.md)
24. [Mémoire planifiée et FSRS](./24-memoire-et-fsrs.md)

### Application, UX et exploitation

15. [Architecture applicative et stack](./15-architecture-applicative.md)
16. [API et contrats frontend](./16-api-et-contrats-frontend.md)
17. [Sécurité, confidentialité, jobs et médias](./17-securite-confidentialite-jobs-medias.md)
18. [Exploitation, sauvegarde et livraison](./18-exploitation-environnements-livraison.md)
19. [Tests, quality gates et délégation](./19-tests-quality-gates-delegation.md)
20. [Architecture UX et frontend](./20-architecture-ux-frontend.md)
21. [Personas, parcours et situations limites](./21-personas-parcours-limites.md)
22. [Imports, édition et validation](./22-imports-edition-validation.md)
28. [Wireframes et design system](./28-wireframes-et-design-system.md)
29. [Revue de clôture de l'architecture](./29-revue-cloture-architecture.md)
30. [Contrats de la façade d'outils auteur](./30-contrats-outils-auteur.md)

### Exécution

23. [Traçabilité des exigences et preuves](./23-tracabilite-execution.md)
25. [Registre canonique des enums, commandes et routes](./25-registre-enums-commandes-api.md)
26. [Dictionnaire de données](./26-dictionnaire-donnees.md)
27. [Plan d'implémentation détaillé W00-W19](./27-plan-implementation-detaille.md)
31. [Registre des incréments d'implémentation](./31-registre-increments-implementation.md)

## Invariants de transition

1. La V1 reste une archive fonctionnelle et visuelle, pas une dépendance runtime.
2. PostgreSQL est la source de vérité V2 ; listes, cartes et graphes sont des
   vues ou agrégats au-dessus des faits personnels et catalogues versionnés.
3. Le backend choisit le parcours, les cibles, le budget et les critères de
   maîtrise. Le frontend n'invente aucun score.
4. Une activité, une exposition ou une auto-évaluation ne devient jamais seule
   une preuve de maîtrise.
5. Les quatre compétences restent distinctes ; le CECR n'est qu'une éventuelle
   étiquette d'interopérabilité calibrée, jamais la structure du produit.
6. Une panne, ambiguïté ou absence de média ne devient ni réussite ni échec.
7. Aucun retry payant, fallback fournisseur ou publication IA n'est implicite.
8. Le pack italien complet est un chantier éditorial séparé de l'architecture ;
   seul le pilote minimal est normatif avant le noyau.
