# Rerevue finale ciblee W04 - round 2

## Verdict

**PASS**

Le delta RED `02db7e5` / GREEN `c1ef0ec` ferme la derniere condition bloquante
de `task-W04-rereview.md`. Aucun nouveau blocage evident n'a ete trouve dans le
perimetre examine.

## Verification de l'immutabilite

`catalogue.guard_published_child()` construit maintenant deux ensembles
distincts, `old_revisions` et `new_revisions`, pour les operations `UPDATE`.
Il appelle `assert_published_revisions_immutable()` sur les deux cotes avant de
laisser l'ecriture continuer.

La couverture est complete pour les cinq familles demandees :

- `language_pack_support_varieties` : `OLD.pack_revision_id` et
  `NEW.pack_revision_id` ;
- `grammar_patterns` : `OLD.structure_revision_id` et
  `NEW.structure_revision_id` ;
- `form_analyses` : `OLD.unit_revision_id` et `NEW.unit_revision_id` ;
- `form_realizations` : anciens et nouveaux proprietaires de l'analyse, de
  l'unite et du sens ;
- `expression_components` : anciennes et nouvelles revisions de la racine et
  du composant.

Les chemins `INSERT` et `DELETE` restent corrects : `INSERT` controle seulement
`NEW`, `DELETE` seulement `OLD`. Le retour du trigger reste adapte a
l'operation.

## Tests de reparentage

Le test parametre
`test_database_rejects_reparenting_child_from_published_to_draft_revision`
cree de vrais proprietaires brouillons et tente un reparentage depuis une
revision publiee pour chacune des cinq familles. Chaque ecriture doit echouer
avec `published revision is immutable`.

Ces regressions completent les tests precedents qui couvraient deja mutation en
place et suppression. Le contournement identifie lors de la premiere rerevue
n'est plus possible par les chemins testes et inspectes.

## Absence de regression evidente

- La correction reste limitee a la garde PostgreSQL et aux tests d'integration
  W04.
- Les validations de coherence forme/unite/sens et MWE ne sont pas modifiees.
- La serialisation et les bornes du DAG ne sont pas modifiees.
- La pagination SQL, le validateur de fixture et les stable codes ne sont pas
  modifies.
- Les semantiques `INSERT`, `UPDATE` et `DELETE` du trigger restent coherentes.

## Preuves

- Suite W04 annoncee : **40 passed**.
- `ruff` et `mypy` annonces verts.
- Round-trip Alembic annonce vert.
- Revue strictement read-only : aucun code produit modifie.

W04 satisfait desormais toutes les conditions minimales de PASS des deux revues
precedentes. La revue linguistique humaine `P-LING` reste une approbation
distincte et n'est pas presumee acquise par ce verdict technique.
