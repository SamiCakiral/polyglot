# W17-shell / W17-T01 - Revue independante read-only

## Verdict

**FAIL**

Perimetre relu : commits `f7504f2` et `bc11427`, rapport
`task-W17-shell-report.md`, avec comparaison aux documents normatifs `15`, `20`,
`28`, au registre `W17-T01` et aux regles d'execution du document `27`.

Le shell est structure proprement, le client OpenAPI est effectivement genere de
maniere deterministe et les controles locaux annonces passent. Le lot ne peut
cependant pas etre accepte : la frontiere de session efface la semantique des
erreurs d'authentification, le faux serveur est actif par defaut dans un mode
hybride, aucun controle frontend ne tourne en CI, et les preuves responsive/a11y
ne couvrent ni le zoom 200 % ni le contraste. Une troncature visible existe a
320 px.

## Critical

Aucun finding Critical.

## Important

### I1 - La frontiere de session transforme toutes les erreurs en panne rejouable

`frontend/src/app/session.tsx:22-23` envoie indistinctement toute erreur reseau
et tout statut non-200 vers `SessionErrorState`. Ce composant affiche toujours
"Verifiez votre connexion" et propose toujours **Reessayer**
(`frontend/src/components/shell-states.tsx:23-33`). Un `401` ne conduit donc pas
a "Votre session a expire" / reconnexion, un `403` propose a tort de reessayer,
et les statuts `409`, `423`, `429` ou `503` perdent leur code et leur caractere
`retryable`.

Cela contredit la taxonomie normative du document 28, lignes 720-728, et ne
constitue pas la frontiere session/error attendue par W17. Les tests ne couvrent
qu'un `503` (`frontend/src/shell/states.test.tsx:23-44`). Il faut mapper les
reponses generees par statut/code, respecter `retryable`, et tester au minimum
`401`, `403`, `429`, `503` et erreur de transport.

### I2 - Le faux serveur est active par defaut et laisse passer le trafic non mocke

`frontend/src/main.tsx:10-16` demarre MSW pour tout `vite dev` sauf si
`VITE_ENABLE_API_MOCKS` vaut explicitement `false`, puis configure
`onUnhandledRequest: "bypass"`. L'environnement peut donc combiner une session
synthetique avec des requetes non interceptees vers une API reelle. Cette
configuration masque les regressions d'authentification et rend possible un
environnement hybride dans lequel une action non mockee quitte le faux serveur.

Le faux serveur doit etre explicitement active (`=== "true"`) et echouer ferme
sur les requetes inattendues, avec un mode d'integration API reelle distinct et
visible. Le build de production n'embarque pas ce demarrage grace a `DEV`, mais
la frontiere de securite et la fidelite des tests de developpement restent
insuffisantes.

### I3 - Aucun controle frontend n'est execute en CI

Le workflow `.github/workflows/ci.yml:11-150` ne contient aucun setup Node/pnpm,
aucune regeneration du client, aucun lint, typecheck, test ni build frontend.
Les deux commits ne modifient aucun workflow et `bc11427` n'est contenu dans
aucune branche distante ; il n'existe donc aucune preuve CI pour cet etat.

Le rapport affirme qu'aucune integration CI minimale n'etait necessaire, alors
que le document 27, lignes 122-126 et 152-156, impose le controle des artefacts
generes et les commandes frontend. Un job avec Node et pnpm verrouilles doit au
minimum executer installation gelee, regeneration avec diff nul, lint,
typecheck, tests et build.

### I4 - Le shell tronque des libelles a la largeur contractuelle de 320 px

La barre basse impose `text-overflow: ellipsis` et `white-space: nowrap`
(`frontend/src/app/styles.css:512-519`). En inspection reelle a 320 px,
**Aujourd'hui**, **Vocabulaire** et **Progression** debordent leur largeur utile
et sont visiblement tronques. Il n'y a pas de debordement horizontal de page ni
de chevauchement a 320, 768 ou 1440 px, mais cette troncature viole le document
28, lignes 841-844 et 934-942 : les labels longs doivent revenir sur deux lignes
et rester complets a 320 px et a 200 %.

Les tests jsdom ne calculent pas la mise en page et ne peuvent pas detecter ce
defaut. Il faut une preuve navigateur aux viewports contractuels.

### I5 - Les preuves accessibilite et zoom annoncees sont incompletes

Le seul test axe desactive explicitement `color-contrast`
(`frontend/src/shell/accessibility.test.tsx:7-20`), tout en filtrant ensuite les
violations serieuses/critiques. Il ne prouve donc pas le contraste WCAG demande
par le document 28, lignes 907-919. Aucun fichier Playwright, aucune dependance
`@playwright/test`, aucun projet `keyboard`/`zoom-200` et aucun test reel de
reflow ne sont presents. Les valeurs `320/768/1440` dans `FX-UI` sont des donnees
non consommees par un test de viewport.

Le lien d'evitement, la navigation native et la fermeture du menu par Echap avec
restauration du focus fonctionnent en inspection reelle. Cela ne remplace pas
les preuves de zoom 200 %, de contraste et de navigation clavier complete
requises par les documents 27 et 28. Ces preuves peuvent appartenir a W17-T04,
mais le rapport W17-T01 ne doit pas presenter leur conformite comme acquise.

### I6 - Le runtime Node n'est pas verrouille comme une baseline compatible

Les versions npm directes et `pnpm@11.16.0` sont exactes, et le lockfile est
gele. En revanche, `frontend/package.json:7-9` declare seulement
`node >=22.18.0`. Cette plage accepte notamment Node 23, alors que plusieurs
dependances verrouillees dans le lockfile (dont Vite et des dependances DOM)
excluent les versions Node impaires correspondantes. Aucun fichier de version
racine ni job CI ne ferme la baseline.

Le document 15, lignes 11-14, demande une baseline exacte enregistree et testee
comme un ensemble. Il faut epingler une version Node supportee exacte (ou une
plage explicite compatible), l'enregistrer dans le depot et l'utiliser en CI.

## Minor

### M1 - Le rail compact repose sur des icones sans aide visuelle

Entre 1024 et 1199 px, les libelles du rail sont caches visuellement
(`frontend/src/app/styles.css:349-383`). Les liens restent correctement nommes
pour les technologies d'assistance, mais aucun tooltip ou libelle visible au
survol/focus n'aide les utilisateurs voyants a distinguer certaines icones. Les
deux actions de compte sont egalement icon-only
(`frontend/src/app/app-shell.tsx:98-104`). Ajouter une aide visible au focus et
au survol alignerait ce mode sur le catalogue de composants du document 28.

### M2 - Le write set W17 documente ne couvre pas le scaffold reel

Le lot ajoute plusieurs fichiers necessaires mais absents du write set "exact"
du document 27 : `.npmrc`, `eslint.config.js`, `index.html`, `orval.config.ts`,
`pnpm-workspace.yaml`, les `tsconfig` et `public/mockServiceWorker.js`. Ce n'est
pas un defaut fonctionnel, mais le registre doit etre corrige ou l'ecart approuve
explicitement pour que les revues suivantes puissent appliquer les limites de
propriete sans ambiguite.

## Conformites observees

- Les dependances directes sont en versions exactes et le lockfile s'installe
  hors reseau avec `pnpm 11.16.0`.
- Deux generations Orval successives produisent les memes empreintes que
  `frontend/src/generated/**` versionne ; aucun indice d'edition manuelle n'a ete
  trouve.
- Router, QueryClient provider, session context, frontiere d'erreur applicative,
  frontiere d'erreur de route et faux serveur Node/navigateur sont presents.
- Les 16 routes de `FX-UI` sont montees ; la navigation desktop et mobile suit
  l'ordre attendu.
- Aucun calcul de score, maitrise, correction, dette ou planification n'existe
  hors code genere. Le shell ne contient pas de logique pedagogique.
- L'inspection a 768 et 1440 px ne montre ni chevauchement, ni debordement
  horizontal, ni texte coupe. A 320 px, le contenu principal reste lisible et
  seul le probleme de libelles de navigation decrit en I4 est observe.
- `pnpm audit --audit-level high` ne signale aucune vulnerabilite connue au
  moment de la revue.

## Preuves executees

Sur une archive isolee exacte de `bc11427`, sans utiliser les changements W04
non committes du worktree :

| Preuve | Resultat |
|---|---|
| `pnpm install --offline --frozen-lockfile` | PASS, pnpm `11.16.0`, 377 paquets depuis le store local |
| generation Orval, empreinte avant/apres puis seconde generation | PASS, aucun diff |
| `pnpm lint` | PASS, 0 warning/erreur |
| `pnpm typecheck` | PASS |
| `pnpm test --run` | PASS, 3 fichiers / 24 tests |
| `pnpm build` | PASS, 1 859 modules, JS 329.68 kB / 103.92 kB gzip, CSS 7.05 kB / 2.09 kB gzip |
| `pnpm audit --audit-level high` | PASS, aucune vulnerabilite connue |
| `git diff --check` sur les deux commits | PASS |
| CI frontend | FAIL, job absent et commit non pousse |
| Playwright / zoom 200 % | FAIL, infrastructure et preuve absentes |
| Inspection navigateur 1440/768/320 | FAIL global, troncature a 320 px |

Le serveur demande `http://127.0.0.1:4174` n'etait pas actif au debut de la
revue. Une copie exacte de `bc11427` a donc ete lancee sur ce port avec le faux
serveur contractuel, puis inspectee. Les captures de revue ont ete conservees
hors depot : `/tmp/polyglot-w17-1440-v2.png`,
`/tmp/polyglot-w17-768-v2.png` et `/tmp/polyglot-w17-320-v2.png`.

## Conditions minimales de rerevue

1. Distinguer les erreurs de session/authentification selon le contrat genere.
2. Rendre les mocks navigateur opt-in et fermer les requetes inattendues.
3. Ajouter un job CI frontend avec regeneration-diff, lint, typecheck, tests et
   build sur une version Node verrouillee.
4. Corriger les libelles a 320 px.
5. Ajouter les preuves navigateur axe/contraste, clavier, 320/768/1440 et zoom
   200 %, ou marquer explicitement ces gates comme differees a W17-T04 sans les
   declarer conformes dans le rapport T01.
