# Polyglot Visual System

## Direction

**Le studio linguistique annoté** traite Polyglot comme un outil de travail
personnel entre cahier de langue, index éditorial et table de contrôle. Les
surfaces sont blanches, réglées par des lignes fines, avec des annotations de
statut colorées et des extraits italiens composés comme une matière à étudier.
Le produit doit paraître sérieux sans être scolaire, dense sans être froid.

Cette direction évite l'imagerie de voyage et la gamification enfantine. Elle
peut porter aussi bien une séance focalisée, une banque de 100 000 mots, une
projection de progression ou un atelier éditorial.

## Mode

Operate. La prochaine action, la continuité du travail et la lisibilité des
états priment sur la décoration.

## Composition

- Rail desktop fixe de 232 px, barre supérieure de 64 px, contenu limité à
  1280 px sauf lecteurs de séance et tableaux denses.
- Les pages sont des plans de travail non encadrés. Les séparations utilisent
  des règles, des changements de fond et des colonnes, jamais des sections
  flottantes empilées.
- Les cartes sont réservées aux éléments répétés : modules, mots, évaluations et
  brouillons. Rayon maximal 6 px.
- Les titres de page restent entre 28 et 36 px. Les panneaux compacts utilisent
  14 à 20 px ; aucun texte ne grandit avec la largeur de l'écran.
- Les extraits italiens importants peuvent employer une serif de lecture ; les
  commandes et données restent en sans-serif.

## Palette

| Token | Valeur | Usage |
|---|---|---|
| `canvas` | `#f3f1ec` | fond général légèrement minéral |
| `paper` | `#fffefd` | surfaces de travail |
| `ink` | `#202422` | texte principal |
| `muted` | `#626964` | texte secondaire |
| `rule` | `#c9cec9` | séparateurs et contrôles |
| `forest` | `#175c4c` | action principale et états prêts |
| `cobalt` | `#245ea8` | écoute, information et focus |
| `vermilion` | `#bd3f2c` | erreur, échéance et accent italien |
| `mustard` | `#d39a24` | attention et revue humaine |
| `charcoal` | `#27302d` | rail et lecteurs focalisés |

Il n'y a ni gradient, ni halo, ni blob décoratif. Les couleurs fonctionnelles
sont toujours accompagnées d'un label ou d'une icône.

## Typography

- Interface : `Inter`, puis la pile système sans-serif.
- Matière italienne et citations : `Iowan Old Style`, `Palatino Linotype`,
  `Book Antiqua`, `Georgia`, serif.
- Données stables, minuteurs et numéros d'étape : `SFMono-Regular`, `Consolas`,
  monospace.
- Letter spacing toujours nul. Capitales uniquement pour de courts repères de
  navigation ou d'état.

## Controls

- Boutons d'action à 44 px minimum, rayon 5 px, icône Lucide lorsque le symbole
  est familier.
- Boutons secondaires blancs avec bordure ; boutons tertiaires sans contenant
  lorsque le contexte suffit.
- Segments pour le temps de séance et les modes, cases pour les filtres binaires,
  menus pour les ensembles d'options, champs numériques pour les budgets.
- Focus cobalt de 3 px avec décalage de 2 px.
- Les états occupés conservent leur taille et leur label de base.

## Signature Elements

- Une règle vermillon courte signale le point de travail actif.
- Les étapes portent un index monospace stable (`03/07`) et une ligne de
  progression segmentée, sans animation obligatoire.
- Les preuves et raisons sont présentées comme annotations reliées à leur cible,
  avec date de coupure et niveau de confiance visibles.
- Les mots italiens sont la première information de chaque entrée lexicale ; le
  sens français et les contextes suivent dans une hiérarchie plus calme.

## Responsive

- À 1024-1199 px, le rail devient une colonne d'icônes de 72 px avec tooltips.
- Sous 768 px, navigation basse de cinq destinations et menu secondaire plein
  écran. Les lecteurs masquent cette navigation.
- Aucun tableau ne force le défilement horizontal de page : il devient liste
  structurée ou région défilante explicitement nommée.
- Les actions persistantes respectent les zones sûres et ne recouvrent jamais le
  dernier champ.

## Motion

Transitions de 120 à 180 ms pour focus de panneau, ouverture de tiroir et
validation. Aucun mouvement décoratif continu. Avec `prefers-reduced-motion`,
tous les changements deviennent instantanés sauf indicateur de chargement rendu
par texte.

## Content Rules

- Dire « Séance du jour », jamais « sprint » dans l'interface apprenant.
- Ne jamais confondre réponse correcte, preuve et maîtrise.
- Montrer une indisponibilité comme telle ; ne pas inventer de fallback.
- Les explications apparaissent à l'endroit de la décision, pas dans une page
  d'aide générale.
