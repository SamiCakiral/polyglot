# Rerevue independante W07-T01

- Correctifs revus : `0c2dee0`, `c545973`
- Revision executee : `c545973a562d3a48c456c2ded0a00d1f4c188e0e`
- Copie propre : `/tmp/polyglot-w07-t01-rereview`
- Verdict : **PASS technique**
- Gate humaine : `P-LING = pending_human`

## Findings precedents

### Spike temporel : ferme

`test_spk_fsrs_temporal.py` execute maintenant trois histoires fournisseur
distinctes :

- review anticipee avant la due initiale ;
- review retardee apres la due initiale ;
- date `Europe/Rome` refusee par le fournisseur, puis normalisee explicitement
  en UTC avant execution.

Le harness compare les snapshots complets aux constantes versionnees de
`docs/evidence/W07/spk-fsrs-raw.json`. Il ne calcule ni ne reecrit ses attendus :
le fichier est uniquement lu. Le commit RED `0c2dee0` echoue par absence de
`temporal_cases`; `c545973` ajoute les attendus figes et la preuve documentee.

### Recuperabilite hors bornes : ferme

L'adaptateur refuse maintenant toute recuperabilite non finie ou hors de
`[0, 1]` avec `dependency_unavailable`. Le test RED `0c2dee0` prouve que `1.5`
traversait auparavant le port ; il passe apres `c545973` et confirme que l'etat
d'entree reste inchange.

Une sonde adversariale complementaire a confirme le rejet de `-0.001`, `1.001`,
`NaN`, `+inf` et `-inf`, l'acceptation exacte de `0` et `1`, l'absence de
mutation et l'absence de fallback.

## Matrice executee

- Python : `3.13.11`.
- Fournisseur : `fsrs==6.3.1`.
- Installation : `uv sync --frozen --offline --all-groups` reussie.
- Lock : `uv lock --check --offline` reussi.
- Hash `uv.lock` :
  `fc227db2f7afe96473da3107744394c2fbbb338a4b7b7774d1c2606edfbb38fe`.
- Spike + unit + property T01 : **19 passes**.
- Ruff cible : **passe**.
- mypy strict cible : **passe, 8 fichiers**.
- Cycle RED confirme a `0c2dee0` : **2 echecs attendus** sur les deux findings.

## Conclusion

Les deux blocages de la revue initiale sont reellement fermes au HEAD exact
`c545973`. W07-T01 obtient un **PASS technique**. La validation linguistique
humaine `P-LING` reste volontairement `pending_human` et n'est pas fermee par
cette suite.
