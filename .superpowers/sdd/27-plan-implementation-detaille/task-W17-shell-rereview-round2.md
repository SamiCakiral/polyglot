# W17-shell / W17-T01 - Rerevue finale round 2

## Verdict

**PASS**

Perimetre read-only : commits `539161d` et `5548016`, limite aux trois
conditions de PASS de la rerevue precedente et aux regressions eventuelles.
Les artefacts Playwright fournis sous
`/private/tmp/polyglot-w17.9KnSpb/frontend/test-results/w17-shell` indiquent une
execution passee et les captures ont ete inspectees.

## Critical

Aucun finding Critical.

## Important

Aucun finding Important.

## Minor

Aucun finding Minor bloquant pour W17-shell.

## Conditions de PASS

### 1. Labels visibles et complets a 320 px - PASS

- Sous 380 px, les labels ne sont plus clipses : ils restent visibles, utilisent
  `white-space: normal` et `overflow-wrap: anywhere`.
- Le test `shell-320` exige `toBeVisible()` pour les cinq labels.
- Il verifie dimensions utiles superieures a 1 px, absence de debordement
  horizontal et vertical, et inclusion de chaque label dans son lien parent.
- La capture `shell-shell-320.png` montre les cinq libelles visibles et complets,
  sans chevauchement ni debordement de page.

### 2. Tooltips hover/focus du mode compact et des controles icon-only - PASS

- `TooltipNavLink` relie chaque controle a un `role="tooltip"` via
  `aria-describedby`.
- Les tooltips sont affiches par `:hover` et `:focus-within`.
- Le rail compact active ses tooltips lateraux entre 1024 et 1199 px.
- Le selecteur de langue, les actions Profil/Preferences et le bouton de menu
  possedent egalement une aide accessible.
- Le projet `shell-compact` a 1100 px verifie focus et hover sur Apprendre,
  Progression, Preferences et Profil de langue.
- La capture compacte ne presente aucune collision structurelle.

### 3. Preuve zoom 200 %, dimensions, focus et actions - PASS

- L'ancien projet ambigu est separe en `reflow-720` et
  `browser-zoom-200`.
- `browser-zoom-200` applique un zoom CSS de `2` apres mesure de reference.
- Le test exige une hauteur de titre et de controle au moins egale a 1,9 fois la
  baseline, et verifie que les six actions principales et les deux actions de
  compte restent presentes.
- Le test clavier commun s'execute aussi dans ce projet zoome : skip-link,
  transfert de focus, navigation et activation restent couverts.
- `reflow-720` verifie separement le comportement correspondant a la largeur CSS
  resultante d'un viewport desktop zoome.
- La capture `shell-browser-zoom-200.png` montre texte et controles agrandis,
  lisibles, sans commande masquee ; `shell-reflow-720.png` ne montre aucun
  chevauchement.

La combinaison zoom CSS mesure + reflow 720 constitue ici une methode
equivalente explicite : elle couvre l'agrandissement physique, la largeur CSS
resultante, le focus et la disponibilite des actions.

## Regressions

- Aucun debordement ou chevauchement visible dans les captures 320, compact,
  reflow 720 et zoom 200.
- Les noms accessibles des liens restent conserves.
- Les tooltips n'alterent pas la structure de navigation ni les cibles tactiles.
- Aucun fichier genere, contrat API, logique de session ou logique pedagogique
  n'est modifie par ces deux commits.

## Preuves examinees

- `.last-run.json` : `status: passed`, aucune liste de test en echec.
- `shell-shell-320.png` : labels visibles et complets.
- `shell-shell-compact.png` : rail compact stable.
- `shell-browser-zoom-200.png` : agrandissement 2x sans perte d'action.
- `shell-reflow-720.png` : reflow mobile propre.
- Le delta passe `git diff --check`.

W17-shell / W17-T01 peut etre accepte sur ce perimetre.
