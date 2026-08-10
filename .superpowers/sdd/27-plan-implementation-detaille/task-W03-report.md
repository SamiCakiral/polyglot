# W03 - Rapport d'implementation

## Statut

Implemente localement, sans push. Le lot couvre le profil de langue personnel,
le diagnostic deterministe et son expiration a 24 h, les fondations F1-F5 et
leur gate pure differee. Il ne cree aucune projection de maitrise, dette ou
preuve pedagogique implicite.

## Livrables

- `0004_language_profiles` : huit tables privees, contraintes UUIDv7,
  append-only pour les reponses/resultats, index de reprise et RLS proprietaire.
- Politique `DIAGNOSTIC_V0` et golden cases P-ABS, P-FAUX et P-INT.
- Gate de fondations F1-F5, deux sessions, controle F1 a 24 h et audio absent
  explicitement `not_evaluable`.
- Service HTTP authentifie : profils, objectifs, pauses/archivage/restauration,
  creation et consultation de diagnostic, soumission de reponse et completion.
- Recu idempotent, version attendue, evenement/outbox personnel et controle
  proprietaire pour les commandes implementables sans correcteur externe.
- OpenAPI regeneree et controlee contre le registre.

## Verification

Execute avec PostgreSQL local :

- `pytest tests/unit/language_profiles tests/property/language_profiles tests/integration/language_profiles tests/contract/language_profiles -q` : `19 passed`.
- `ruff check src tests` : vert.
- `mypy src` : vert.
- `alembic downgrade 0003_catalogue`, `alembic upgrade 0004_language_profiles`,
  puis `alembic upgrade head` : vert.
- `alembic check` : `No new upgrade operations detected`.
- export OpenAPI et test de contrat plateforme : `4 passed`.

## Commits W03

- `173deb4` `test(w03): define diagnostic policy golden cases`
- `f960d5d` `feat(w03): add deterministic diagnostic policy`
- `da84a44` `test(w03): define foundation gate invariants`
- `c531f68` `feat(w03): enforce delayed foundation gate`
- `c6d8266` `test(w03): define profile migration and rls contracts`
- `d728257` `feat(w03): persist language profiles with rls`
- `2bafe5b` `test(w03): define profile http contracts`
- `010fc42` `feat(w03): expose authenticated profile onboarding`

## Limites explicites

La correction qualifiee et la production des blocs de fondation restent les
responsabilites des lots contenus/exercices suivants. Le W03 persiste et evalue
seulement les mesures explicites ; il ne transforme jamais une declaration,
une dispense ou une modalite non evaluee en credit de maitrise.
