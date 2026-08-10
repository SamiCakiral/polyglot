# Revue independante - correctif scan historique des secrets

## Verdict: FAIL

## Perimetre

Revue read-only des commits RED `b7f8bc3` et GREEN `9651f74`, limites aux
changements de `backend/src/polyglot/platform/security_checks.py` et aux tests
associes. Aucun code produit n'a ete modifie.

## Point positif confirme

Le faux positif cible est ferme : le nom synthetique du rapport W17 n'est plus
fourni a `_find_secrets` par le scan
de patch historique. Les lignes de contenu ajoutees et supprimees sont
conservees, ce qui permet aussi de detecter une cle retiree plus tard.

Les preuves d'execution communiquees pour cet etat sont propres : scanner
courant/historique sans finding, quatre tests cibles verts et `219 passed` sur
un clone exact.

## Blocages

1. **P1 - faux negatif introduit pour une cle OpenAI precedee d'un caractere
   alphanumerique, `_` ou `-`.**

   La nouvelle regex `(?<![A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}` ne signale plus
   une vraie cle lorsqu'elle apparait dans une valeur enveloppee ou concatenee,
   par exemple `prefix_sk-...`, `xsk-...` ou `token-sk-...`. Le scanner est un
   garde-fou de depot et doit privilegier les faux positifs aux faux negatifs
   pour une valeur qui correspond exactement a la forme d'une cle. Ce recul
   n'est pas necessaire pour le faux positif de nom de fichier :
   `_patch_content()` retire deja les headers et noms de fichier du contenu
   analyse.

2. **P1 - `_patch_content()` ignore du contenu historique reel dont la ligne
   de patch commence par `+++` ou `---`.**

   Les conditions `line.startswith(("+++", "---"))` ne distinguent pas les
   headers Git `+++ b/path` et `--- a/path` d'une ligne ajoutee/supprimee dont
   le contenu commence lui-meme par deux signes. Exemple : une ligne de fichier
   ajoutee `++sk-...` est encodee `+++sk-...` dans le patch, puis entierement
   ignoree; une ligne supprimee `--sk-...` devient `---sk-...` et est egalement
   ignoree. Si le fichier est ensuite supprime, la cle n'existe plus dans le
   working tree et le scan historique ne la voit plus.

## Couverture manquante

Les deux tests ajoutes couvrent le nom de rapport et une cle OpenAI ajoutee
puis supprimee dans une ligne ordinaire. Ils ne couvrent pas :

- les cinq familles de secrets en contenu courant et dans une ligne retiree;
- une cle precedee d'un caractere de mot ou d'un underscore;
- une ligne de contenu commencant par `+++` ou `---` dans l'historique;
- un rename pur, un rename avec modification et les headers `diff --git`,
  `rename from` et `rename to`.

Un rename pur ne devrait pas faire disparaitre une cle historique, car son
ajout initial reste dans un patch plus ancien; il doit neanmoins etre teste
pour verrouiller ce contrat. Les headers sont correctement exclus pour le cas
cible, a condition de les reconnaitre comme headers exacts (`+++ ` et `--- `),
plutot que par leurs trois premiers caracteres.

## Condition de passage

Conserver l'extraction des seules lignes de contenu ajoutees/supprimees,
restaurer la detection de la forme `sk-...` independamment du caractere qui la
precede, et ne filtrer que les headers de chemin Git. Ajouter des tests de
regression pour les deux faux negatifs ci-dessus, le contenu retire et les
renames. Une nouvelle revue pourra alors statuer PASS.
