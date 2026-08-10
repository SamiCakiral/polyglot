# W17-shell / W17-T01 - Rapport de correction

## Verdict

**PASS local.** Les six findings bloquants de
`task-W17-shell-review.md` sont fermes dans le perimetre W17-T01.

La configuration CI est versionnee mais n'a pas ete executee sur GitHub, aucun
push n'ayant ete effectue.

## Commits TDD

1. `c334a2e test(w17): expose shell review regressions`
   - RED Vitest : 8 echecs attendus, 24 tests deja verts.
   - RED Playwright : 12 echecs attendus, 8 tests deja verts.
   - Les echecs couvraient la semantique session, la baseline Node/CI, les
     libelles mobiles, l'opt-in MSW et le comportement fail-closed.
2. `825c4ca fix(w17): close shell review blockers`
   - GREEN complet : session, mocks, CI, responsive, axe, Playwright et versions
     runtime.
3. `96bcd18 fix(w17): isolate browser tests from Vitest`
   - RED cible : le test d'outillage echouait tant que `tests/e2e/**` restait
     collectable par Vitest.
   - GREEN : `vite.config.ts` etend les exclusions Vitest par defaut avec
     `tests/e2e/**`, sans exclure `src/shell/**` ni les tests composants.
   - Les scripts build/dev appellent Orval directement afin de conserver le
     runtime Node exact dans les sous-commandes.
4. `539161d test(w17): require visible labels and zoom proof`
   - RED cible : 2 echecs attendus, libelles 320 px reduits a 1 px et absence de
     tooltip dans le rail compact ; 10 tests deja verts et 6 skips attendus.
   - Ajoute les oracles de geometrie des cinq libelles, hover/focus des
     tooltips et doublement mesurable du rendu a 200 %.
5. `5548016 fix(w17): restore labels and compact tooltips`
   - GREEN : libelles complets, tooltips accessibles et oracle Playwright type.

## Findings fermes

### 1. Erreurs de session

- `401 unauthenticated` affiche **Votre session a expire** et
  **Se reconnecter** vers `/login`, sans bouton Reessayer.
- `403 forbidden` affiche **Vous n'avez pas acces a cette page** et une
  destination de connexion sure, sans bouton Reessayer.
- Une erreur marquee `retryable: false` n'offre aucune relance.
- `429 rate_limited`, `503 dependency_unavailable` et les erreurs de transport
  proposent une relance manuelle adaptee.
- Couverture cible : `401`, `403`, `423`, `429`, `503` et transport.

### 2. MSW developpement

- Les mocks navigateur ne demarrent que si
  `VITE_ENABLE_API_MOCKS === "true"`.
- `pnpm dev` reste connecte a l'API reelle ; `pnpm dev:mock` active
  explicitement les contrats simules.
- `onUnhandledRequest: "error"` ferme les requetes inattendues. Le test
  navigateur verifie une reponse `500` MSW et exclut le pass-through `200` de
  Vite.

### 3. CI frontend

Deux jobs ont ete ajoutes a `.github/workflows/ci.yml` :

- `frontend-quality` : installation gelee, generation Orval, diff nul du client,
  lint, typecheck, Vitest et build ;
- `frontend-browser` : Chromium Playwright epingle, tests navigateur et archivage
  des preuves sous forme d'artefact non approuve automatiquement.

### 4. Navigation 320 px

- Les cinq destinations conservent leur nom accessible et visuel complet.
- A `320px`, chaque libelle reste visible sur une ou deux lignes. Playwright
  verifie pour chacun une largeur et une hauteur utiles, l'absence d'overflow
  interne et son inclusion geometrique dans le lien parent.
- A `768px`, les libelles complets restent visibles.

### 5. Tooltips accessibles

- Le rail compact expose un tooltip `role="tooltip"` au focus clavier et au
  hover pour chaque destination dont le libelle visuel est masque.
- Les controles profil, reglages, langue et menu icon-only/non evidents sont
  relies a leur tooltip par `aria-describedby`.
- Playwright verifie focus et hover sur le rail compact et les controles de
  compte.

### 6. Axe et contraste

- La desactivation de la regle `color-contrast` a ete retiree du test Vitest.
- Axe est aussi execute dans Chromium reel ; aucune violation contraste,
  serious ou critical n'est acceptee.

### 7. Playwright, zoom et clavier

- Projets : `shell-320`, `shell-768`, `shell-compact`, `shell-1440`,
  `reflow-720` et `browser-zoom-200`.
- `reflow-720` est nomme comme un test de reflow et verifie un viewport CSS de
  `720px` ; il n'est plus presente comme une preuve de zoom.
- `browser-zoom-200` applique `document.documentElement.style.zoom = "2"` dans
  Chromium. Le test affirme le zoom calcule a `2` et mesure que la hauteur du
  titre et du controle de compte atteint au moins `1.9x` leur reference avant
  zoom, tout en conservant les destinations du shell.
- Les tests couvrent overflow horizontal, libelles, skip-link, focus principal,
  navigation native, menu mobile, Echap avec restauration du focus, axe et
  frontiere MSW.
- Les captures sont des preuves, jamais des snapshots approuves ou mis a jour
  automatiquement.

### 8. Runtime exact

- `.node-version` : `22.18.0`.
- `frontend/package.json` : Node `22.18.0`, pnpm `11.16.0` et
  `packageManager: pnpm@11.16.0`.
- La matrice finale a ete executee avec l'archive officielle Node `22.18.0`
  Darwin ARM64, verifiee avec `SHASUMS256.txt` : `OK`.

## Verification finale bornee

Environnement : copie locale exacte du frontend, contrat OpenAPI courant,
Node `v22.18.0`, pnpm `11.16.0`, dependances issues du lockfile.

| Commande | Limite | Resultat |
|---|---:|---|
| `pnpm install --offline --frozen-lockfile` | installation locale | PASS |
| `pnpm generate:api` puis `diff -qr <avant> src/generated` | 90 s | PASS, diff nul |
| `pnpm lint` | 120 s | PASS, 0 erreur/warning |
| `pnpm typecheck` | 120 s | PASS |
| `pnpm test --run --pool=threads --maxWorkers=1 --no-file-parallelism` | 180 s | PASS, 4 fichiers / 33 tests ; aucune spec Playwright collectee |
| `pnpm build` | 180 s | PASS, generation Orval + TypeScript + Vite ; 1 859 modules |
| `pnpm exec playwright test` | 240 s | PASS, 21 passes / 15 skips attendus |

Les quinze skips Playwright correspondent aux deux tests MSW executes une fois
dans `shell-320` et au test tooltip execute une fois dans `shell-compact`. Les
tests responsive, clavier et axe passent dans les six projets.

La verification finale a affiche `node v22.18.0` et `pnpm 11.16.0` avant les
commandes. Le build final ne contient plus l'avertissement Node 24 observe avec
l'ancien appel `pnpm run generate:api` imbrique.

## Preuves navigateur

Copies locales conservees sous :

- `frontend/test-results/w17-shell/**/shell-shell-320.png`
- `frontend/test-results/w17-shell/**/shell-shell-768.png`
- `frontend/test-results/w17-shell/**/shell-shell-1440.png`
- `frontend/test-results/w17-shell/**/shell-shell-compact.png`
- `frontend/test-results/w17-shell/**/shell-reflow-720.png`
- `frontend/test-results/w17-shell/**/shell-browser-zoom-200.png`

Ce dossier est ignore par Git. En CI, le meme dossier est archive sous
`w17-shell-browser-evidence` sans mecanisme d'approbation visuelle automatique.

## Limites respectees

- Aucun fichier genere Orval edite manuellement.
- Aucune feature W17-T02, W17-T03 ou W17-T04 ajoutee.
- Aucune logique pedagogique ajoutee.
- Aucun changement backend ou W04 embarque.
- Aucun push effectue.
