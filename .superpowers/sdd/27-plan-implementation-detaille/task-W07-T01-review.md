# Revue independante W07-T01

- Perimetre : `7e2f9ae`, `d3e708d`, puis correctif de style `1aefd7b`
- Revision executee : `1aefd7bd89d67aa2811ba4fac37704c2ef2e0c78`
- Copie propre : `/tmp/polyglot-w07-t01-review`
- Verdict : **FAIL technique cible**
- Gate humaine : `P-LING = pending_human` (hors verdict technique T01)

## Finding bloquant

### [P1] Le rapport SPK-FSRS affirme des scenarios absents du harness

`docs/evidence/W07/SPK-FSRS.md:15-18` affirme que le harness couvre une review
anticipee, une review tardive et un changement de fuseau normalise en UTC.
Pourtant, `backend/tests/spikes/memory/test_spk_fsrs.py:20-70` n'execute aucun
de ces trois scenarios : les instants de la golden history sont fixes sans
comparaison a une echeance anticipee ou depassee, et toutes les dates sont deja
en UTC. Le JSON brut contient une paire de valeurs de fuseau, mais aucune
execution reproductible ne la relie au fournisseur.

Le brief T01 exige explicitement ces cas dans `SPK-FSRS` avant la decision
`adopt`. La suite unitaire prouve ensuite la normalisation `Europe/Rome -> UTC`
de l'adaptateur, mais elle ne remplace pas la preuve fournisseur pre-produit et
ne couvre toujours pas les reviews anticipee/retardee.

Correction attendue : ajouter au harness de spike des oracles figes pour une
review avant echeance, une review apres echeance et une entree dans un fuseau
non UTC, puis aligner la preuve brute et le rapport sur les sorties reellement
executees. Les golden outputs doivent rester constants et ne pas etre derives
automatiquement pendant le test.

### [P1] Une recuperabilite fournisseur hors bornes traverse le port

`backend/src/polyglot/modules/lexicon/memory/providers/fsrs_v6.py:214-229`
convertit directement le retour de `get_card_retrievability` en `Decimal` sans
verifier l'intervalle `[0, 1]`. Un fournisseur injecte renvoyant `1.5` produit
effectivement `Decimal("1.5")` au lieu de `dependency_unavailable`.

Le brief impose que l'adaptateur valide les sorties et leurs bornes. La property
existante ne detecte pas cette faille puisqu'elle n'exerce que le fournisseur
officiel dans son comportement nominal.

Correction attendue : refuser toute valeur non finie ou hors de `[0, 1]` avec
`dependency_unavailable`, et ajouter un test RED adversarial couvrant les bornes
basse et haute avant le correctif produit.

## Verifications conformes

- Ordre TDD confirme : `7e2f9ae` est ancetre de `d3e708d`; le spike passe au
  premier commit et les tests du port/adaptateur echouent alors par absence du
  module produit (`ModuleNotFoundError`).
- `1aefd7b` modifie uniquement les imports et usages de `datetime.UTC` dans les
  trois fichiers de test; aucun oracle ni comportement n'est modifie.
- Python exact : `3.13.11`.
- Pin exact : `fsrs==6.3.1` dans `pyproject.toml` et `uv.lock`.
- Hash `uv.lock` confirme :
  `fc227db2f7afe96473da3107744394c2fbbb338a4b7b7774d1c2606edfbb38fe`.
- Resolution verrouillee hors reseau : `uv sync --frozen --offline --all-groups`
  et `uv lock --check --offline` reussis.
- Tests spike, unitaires et property : **17 passes**.
- Ruff cible : **passe**.
- mypy strict cible : **passe, 7 fichiers**.
- Golden history codee en constantes, deux identites de carte distinctes,
  reset, fusion triee et deux reviews le meme jour presents.
- H0-H4, `not_evaluable`, `after_24h`, UTC de l'adaptateur, determinisme,
  bornes nominales du fournisseur officiel et exception sans transition
  couverts.
- Aucun client reseau, fallback ou formule FSRS locale trouve.
- Le domaine (`policy.py`, `ports.py`) n'importe pas `fsrs`; seul l'adaptateur
  fournisseur le fait.

## Conclusion

T01 ne peut pas etre accepte tant que le spike fournisseur et ses preuves ne
couvrent pas reellement les trois scenarios annonces et requis, et tant que le
port laisse traverser une recuperabilite fournisseur hors bornes.
