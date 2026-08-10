# W17-shell / W17-T01 - Rerevue independante

## Verdict

**FAIL**

Perimetre relu en read-only : corrections `c334a2e`, `825c4ca` et `96bcd18`,
avec reprise de chaque conclusion de la revue initiale. La matrice exacte fournie
est verte et les quatre captures Playwright ont ete inspectees sous
`/tmp/polyglot-v2-w17-verify2.eeJFsz/frontend/test-results/w17-shell`.

Les blocages session, mocks, CI, pins, axe et generation client sont fermes. Le
lot ne peut cependant pas passer : la correction 320 px supprime visuellement
les libelles au lieu de les rendre lisibles, les aides demandees pour les modes
icon-only restent absentes, et la preuve nommee `zoom-200` ne declenche pas un
zoom navigateur reel.

## Critical

Aucun finding Critical.

## Important

### I1 - Les libelles de navigation sont masques a 320 px

Le finding initial sur les libelles tronques n'est pas corrige conformement au
contrat. Sous `380px`, `.mobile-navigation__label` devient un texte uniquement
accessible aux technologies d'assistance : position absolue, `1px x 1px` et
clip integral (`frontend/src/app/styles.css:537-558`). La capture
`shell-shell-320.png` confirme une barre basse composee de cinq icones sans aucun
libelle visible.

Le test Playwright ne detecte pas ce contournement. Il verifie seulement que
`text-overflow` n'est pas `ellipsis` et que les liens possedent encore un nom
accessible (`frontend/tests/e2e/shell/shell.spec.ts:26-51`) ; il ne verifie ni
la visibilite, ni la taille rendue, ni le texte complet. Cela contredit le
wireframe mobile et les exigences du document 28 imposant des labels complets,
sans troncature ni perte d'action a 320 px et a 200 %.

La correction attendue est un libelle visible court ou sur deux lignes, avec un
test `toBeVisible()` et une assertion geometrique `scrollWidth <= clientWidth`
sur chaque libelle visible.

### I2 - Le rail compact et les controles icon-only n'ont toujours pas d'aide visible

Le finding Minor initial n'est pas ferme. Entre 1024 et 1199 px, les libelles du
rail restent clipses (`frontend/src/app/styles.css:349-383`). Les liens du rail,
les actions de compte et les cinq icones mobiles a 320 px ne possedent ni
tooltip, ni `title`, ni aide visible au focus. La recherche du delta ne montre
aucun composant ou contrat de tooltip ajoute.

Les noms accessibles sont corrects, mais ils ne renseignent pas un utilisateur
voyant face aux icones seules. Le document 28 demande une aide pour les icones
non evidentes et une experience clavier/focus complete. Il faut fournir un
tooltip accessible au survol et au focus, puis le tester au clavier dans le
projet compact.

### I3 - Le projet `zoom-200` ne realise pas un zoom navigateur a 200 %

`frontend/playwright.config.ts:45-49` annote le projet avec
`zoomPercent: 200`, mais configure seulement un viewport de `720x450`. Le test
verifie ensuite cette metadata et `clientWidth === 720`
(`frontend/tests/e2e/shell/shell.spec.ts:18-24`). Aucune commande navigateur,
CDP, preference de contexte ou facteur de zoom n'est appliquee.

La capture `shell-zoom-200.png` prouve le reflow a 720 px, pas le comportement
du texte et des controles sous un zoom navigateur reel de 200 %. Cette
simulation est utile, mais elle ne doit pas etre presentee comme la preuve
`zoom-200` exigee par les documents 27 et 28. Il faut une preuve distincte de
zoom reel ou documenter explicitement une methode equivalente qui valide aussi
l'agrandissement physique du texte, la troncature et la perte d'actions.

## Minor

### M1 - Le test fail-close MSW valide un statut 500 plutot qu'un rejet de transport

Le mode mock est bien opt-in et `onUnhandledRequest: "error"` ferme les requetes
inattendues. Le test attend toutefois `{ rejected: false, status: 500 }`
(`frontend/tests/e2e/shell/shell.spec.ts:104-115`). Le trafic n'atteint pas une
API reelle, donc le risque initial est ferme, mais le nom "rejects unexpected
requests" est plus fort que l'oracle observe. Renommer le test ou verifier
explicitement l'absence de requete aval rendrait la preuve plus precise.

## Findings initiaux fermes

### Erreurs de session et retryability - FERME

- `401` et `unauthenticated` conduisent a la reconnexion sans retry.
- `403` et `forbidden` conduisent a une destination sure sans retry.
- toute reponse `retryable: false` est non rejouable avant le mapping `429/5xx`.
- `429` et `5xx` retryables proposent uniquement une tentative manuelle.
- l'erreur de transport est distincte et rejouable.
- les tests couvrent `401`, `403`, `423` non retryable, `429`, `503` et transport.

### MSW opt-in et fail-close - FERME

`frontend/src/main.tsx:10-16` exige maintenant
`VITE_ENABLE_API_MOCKS === "true"` et utilise
`onUnhandledRequest: "error"`. Deux serveurs Playwright separent explicitement
le mode mock du mode API non mocke.

### CI et versions - FERME

- `.node-version` epingle Node `22.18.0`.
- `package.json` epingle Node `22.18.0` et pnpm `11.16.0`.
- les dependances Playwright/axe sont en versions exactes.
- les jobs `frontend-quality` et `frontend-browser` installent les dependances
  gelees, regenerent le client, verifient le diff, lintent, typecheckent, testent,
  buildent et executent Chromium.

La configuration CI est correcte. La branche n'etant pas encore poussee au
moment de la rerevue, cette conclusion porte sur la configuration et la matrice
locale exacte annoncee verte, pas sur un run GitHub de ces commits.

### Axe et contraste - FERME

Le test Vitest ne desactive plus `color-contrast`. Le test Playwright execute
`@axe-core/playwright` sur le shell reel et bloque explicitement toute violation
`color-contrast`, serious ou critical.

### Clavier et focus - FERME hors aide icon-only

Playwright verifie le skip-link, le focus du `main`, la navigation native et la
fermeture du menu par Echap avec restauration du focus. Le manque de tooltip du
mode compact reste traite en I2.

### Generation client - FERME

Les corrections ne modifient pas manuellement `frontend/src/generated/**`. Le
job CI regenere Orval puis exige un diff nul. La generation deterministe deja
prouvee lors de la revue initiale reste valide.

## Inspection visuelle

- `1440px` : aucune collision ni troncature observee ; rail et topbar stables.
- `768px` : labels visibles, aucun chevauchement ni debordement horizontal.
- `320px` : aucun chevauchement horizontal, mais les cinq labels sont absents.
- `zoom-200` : reflow 720 px propre, mais preuve de zoom reel absente.

## Conditions de PASS

1. Conserver des libelles visibles et complets dans la barre basse a 320 px,
   avec assertions de visibilite et de geometrie.
2. Ajouter des tooltips accessibles au survol/focus pour le rail compact et les
   controles icon-only non evidents.
3. Remplacer ou completer la simulation 720 px par une preuve de zoom navigateur
   200 % qui valide texte, controles, focus, troncature et absence de perte
   d'action.
