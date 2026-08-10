# W17-shell - Rerevue ciblee du correctif CI tooltip

## Verdict

**PASS**

Perimetre read-only : RED `f106c81`, GREEN `2dd2275`, limite au debordement du
dernier tooltip de compte et aux regressions hover, focus et zoom.

## Findings

Aucun finding Critical ou Important.

### Minor - L'oracle pourrait etre execute dans davantage de projets

Le nouveau test geometrique s'execute uniquement dans `shell-1440`, alors que la
defaillance distante a aussi ete observee en compact et sous zoom. Ce n'est pas
bloquant : le positionnement corrige est independant de la largeur, la matrice
Playwright complete reste verte et les tests existants couvrent hover/focus en
compact ainsi que le projet zoom. Parametrer le meme oracle sur
`shell-compact` et `browser-zoom-200` rendrait toutefois la preuve plus directe.

## Verification du correctif

- Le fix ne masque pas l'overflow : aucun `overflow: hidden`, clipping ou
  reduction artificielle de largeur n'est ajoute.
- Le dernier tooltip de `.account-nav` est ancre avec `right: 0`, `left: auto`
  et sans translation. Son bord droit suit donc celui de son ancre au lieu
  d'etre centre au-dela du viewport.
- Les regles communes d'affichage restent intactes : hover et `focus-within`
  continuent de piloter `opacity` et `visibility`.
- Le zoom n'est pas neutralise et aucune taille, transformation globale ou
  media query n'est modifiee.
- Le test elargit volontairement le texte a
  "Preferences utilisateur detaillees", puis exige `left >= 0` et
  `right <= viewportWidth`. Il teste donc le risque reel plutot qu'une valeur CSS
  interne.
- Mesurer un element `visibility: hidden` reste geometriquement valide : son
  rectangle de layout est conserve. Les tests hover/focus separes prouvent son
  affichage interactif.

## Preuves prises en compte

- Playwright complet : 22 tests passes, 20 skips, sur l'arbre exact.
- lint : PASS.
- typecheck : PASS.
- Vitest : 33 tests PASS.
- build : PASS.
- `git diff --check` du delta : PASS.

Le correctif ferme la regression Linux sans degrader l'accessibilite, le focus,
le hover ou le zoom. Il peut etre accepte.
