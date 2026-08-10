# W17-shell / W17-T01 - Rapport d'implementation

## Verdict

PASS pour le perimetre W17-T01.

Le frontend React/TypeScript/Vite strict, le client et les mocks OpenAPI generes,
les providers Query/session/error, le routeur, le shell responsive et les etats
globaux du shell sont implementes. Aucune feature W17-T02, W17-T03 ou W17-T04,
ni logique pedagogique, n'a ete ajoutee.

## Perimetre livre

- Dependances et outils verrouilles dans `frontend/package.json` et
  `frontend/pnpm-lock.yaml`; Ajv est explicitement fixe en `6.14.0` pour rester
  compatible avec le chargeur CommonJS d'ESLint 10.
- TypeScript strict avec `noUncheckedIndexedAccess`,
  `exactOptionalPropertyTypes`, `noUnusedLocals` et `noUnusedParameters`.
- Generation Orval depuis `contracts/openapi/v1.json`; aucun fichier de
  `frontend/src/generated/**` n'est edite manuellement.
- Mock Service Worker Node pour Vitest et worker navigateur versionne copie de
  l'artefact `msw@2.15.0`, sans initialisation interactive.
- React Router pour toutes les routes structurelles de `FX-UI`, avec route 404.
- `QueryClientProvider`, frontiere de session issue de `GET /api/v1/session`,
  frontiere d'erreur applicative et frontiere d'erreur de route.
- Shell desktop: rail de six destinations, topbar, langue active et actions de
  compte. Shell mobile: topbar, navigation basse a cinq destinations et menu
  secondaire pour Evaluation, Profil de langue et Preferences.
- Etats shell loading, erreur recuperable, erreur inattendue et empty, sans
  contenu metier.
- Accessibilite de base: skip-link, landmarks, focus visible, navigation clavier,
  Escape du menu mobile, cibles de 44 px et controle axe serious/critical.
- Aucune modification CI: le perimetre frontend dispose de commandes locales
  deterministes et aucune integration CI minimale supplementaire n'etait
  necessaire pour W17-T01.

## TDD et commits

1. `f7504f2 test(w17): add failing frontend shell contracts`
   - RED confirme: `pnpm test --run src/shell` echouait sur l'import absent
     `../app/providers` avant implementation.
   - Contient le scaffold verrouille, les fixtures `FX-UI`, le client genere et
     les tests de contrat du shell.
2. `bc11427 feat(w17): implement responsive frontend shell`
   - GREEN: providers, session, routeur, shell responsive, etats, mocks runtime,
     worker MSW, corrections strictes de configuration et regeneration Orval.
   - Le contrat OpenAPI ayant evolue en parallele avec W04, le client a ete
     regenere depuis le contrat courant; aucun fichier W04 n'a ete modifie.

## Fichiers

### Configuration et entree

- `frontend/package.json`
- `frontend/pnpm-lock.yaml`
- `frontend/pnpm-workspace.yaml`
- `frontend/tsconfig.json`
- `frontend/tsconfig.app.json`
- `frontend/tsconfig.node.json`
- `frontend/vite.config.ts`
- `frontend/eslint.config.js`
- `frontend/orval.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/public/mockServiceWorker.js`

### Application et shell

- `frontend/src/app/app-shell.tsx`
- `frontend/src/app/navigation.ts`
- `frontend/src/app/providers.tsx`
- `frontend/src/app/query-client.ts`
- `frontend/src/app/route-error-boundary.tsx`
- `frontend/src/app/router.tsx`
- `frontend/src/app/session-context.ts`
- `frontend/src/app/session.tsx`
- `frontend/src/app/shell-route.tsx`
- `frontend/src/app/styles.css`
- `frontend/src/components/shell-states.tsx`
- `frontend/src/lib/mocks/browser.ts`
- `frontend/src/lib/mocks/handlers.ts`

### Generation, fixtures et tests

- `frontend/src/generated/**` (Orval uniquement)
- `fixtures/canonical/FX-UI/manifest.json`
- `fixtures/canonical/FX-UI/fixture-metadata.json`
- `fixtures/canonical/FX-UI/shell.json`
- `frontend/src/shell/accessibility.test.tsx`
- `frontend/src/shell/routes.test.tsx`
- `frontend/src/shell/states.test.tsx`
- `frontend/src/shell/test-utils.tsx`
- `frontend/tests/setup.ts`
- `frontend/tests/support/server.ts`

## Verification finale bornee

Les commandes ont ete bornees a 90 secondes (tests, lint, typecheck) et 120
secondes (build). Resultats sur l'etat final exact, avec installation
`pnpm install --offline --frozen-lockfile`:

- `pnpm test --run src/shell --pool=threads --maxWorkers=1 --no-file-parallelism`
  - PASS: 3 fichiers, 24 tests.
- `pnpm lint`
  - PASS: 0 erreur, 0 warning.
- `pnpm typecheck`
  - PASS: `tsc -b --pretty false`.
- `pnpm build`
  - PASS: regeneration Orval, TypeScript strict et build Vite.
  - 1 859 modules; JS 329.68 kB (103.92 kB gzip), CSS 7.05 kB
    (2.09 kB gzip).

## Point TypeScript et environnement local

Les erreurs TypeScript initiales ont ete resolues: types Jest retires du tableau
global au profit de l'import Vitest deja present, `defineConfig` importe depuis
`vitest/config`, declaration `@types/debug` ajoutee pour Orval, et configuration
Node autorisant le fichier JavaScript ESLint.

Dans le checkout sous `/Users/sami/Documents`, les processus Node de TypeScript,
ESLint et Vitest ont ensuite subi des blocages de lecture sans diagnostic. Un
echantillonnage du processus `tsc` le montrait suspendu dans `read(2)` sur
`@types/node/web-globals/navigator.d.ts`; la lecture directe du meme fichier
prenait moins de 3 ms. Pour borner et fiabiliser la preuve, le contenu exact du
frontend et des fixtures a ete synchronise dans `/tmp`, les dependances ont ete
reinstallees depuis le lockfile gele et le store pnpm local, puis les quatre
commandes ci-dessus ont passe en 15.1 secondes au total. Il ne reste aucun
diagnostic TypeScript applicatif ou de configuration.

## Hors perimetre preserve

- Aucun contenu Learn, Practice, Vocabulary ou Progress.
- Aucun moteur pedagogique, audio, sous-titre ou runner de sprint.
- Aucun fichier backend, contrat, base, service ou configuration CI modifie.
- Aucun push effectue.
