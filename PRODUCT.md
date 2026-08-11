# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Polyglot sert d'abord un apprenant autonome qui travaille une langue cible depuis
une langue d'appui. Le premier parcours certifié est français vers italien. Il
utilise le produit fréquemment, le plus souvent pour une séance de 10 à 60
minutes, et doit pouvoir reprendre après une interruption sans perdre son travail.

Les auteurs et reviewers constituent un second public. Ils préparent, valident,
approuvent et publient le contenu pédagogique sans accéder aux données privées
qui ne relèvent pas de leur mandat.

## Product Purpose

Polyglot organise l'apprentissage d'une langue par le travail quotidien,
l'erreur, le rappel et le réemploi. Il relie vocabulaire personnel, structures
grammaticales, exercices, modules, sprints, évaluations et preuves de progression
dans un seul système explicable.

Le succès n'est pas une série entretenue artificiellement. C'est la capacité à
faire une séance cohérente, à retrouver ce qui a été appris, à comprendre les
corrections et à voir séparément ses progrès en lecture, écoute, écriture et oral.

## Positioning

Le mécanisme distinctif est un curriculum déterministe enrichi par des outils
génératifs bornés : chaque séance utilise une banque de mots personnelle, une
boîte grammaticale explicite, des rappels différés et des exercices dont les
observations alimentent une progression justifiable. Un modèle peut proposer un
brouillon, jamais publier ni attribuer une maîtrise.

## Operating Context

- onboarding avec choix de langue, objectifs, diagnostic et fondations requises ;
- séance du jour composée selon le temps disponible, le module et les dettes ;
- apprentissage lexical, version, boîte grammaticale, Gym, shadowing, production
  écrite et inversion différée ;
- entraînement libre distinct du curriculum quotidien ;
- banque de mots personnelle recensant chaque sens rencontré et son état ;
- quatre évaluations indépendantes et un protocole oral sans faux crédit ;
- atelier humain pour brouillons, validations, historique et publication.

## Capabilities and Constraints

- API FastAPI versionnée sous `/api/v1`, client TypeScript généré et PostgreSQL
  comme unique source de vérité.
- Les réponses, preuves et observations pédagogiques restent immuables ; une
  correction ajoute une interprétation.
- Les commandes à effet sont idempotentes et versionnées.
- Le TTS italien local utilise la voix Alice ; l'indisponibilité reste visible.
- Le STT, le professeur conversationnel permanent et le cloud sont post-MVP.
- L'oral reste non évaluable sans revue qualifiée.
- Le produit doit fonctionner localement sans fournisseur ni réseau pour son
  parcours pédagogique déterministe.

## Brand Commitments

Le nom du produit est **Polyglot**. La langue visible du produit MVP est le
français ; l'italien apparaît comme matière d'apprentissage. La voix est directe,
calme et précise. Elle ne gamifie pas artificiellement l'échec et n'affirme jamais
une maîtrise que les preuves ne permettent pas d'établir.

## Evidence on Hand

- Architecture, contrats et wireframes : `docs/v2/`.
- Curriculum italien pilote et fixtures canoniques : `fixtures/canonical/`.
- API et client généré : `contracts/openapi/v1.json` et
  `frontend/src/generated/`.
- Aucune photographie de marque, témoignage, métrique commerciale ou preuve
  marketing n'est disponible et rien de tel ne doit être inventé.

## Product Principles

1. Montrer la prochaine action utile avant les statistiques.
2. Expliquer chaque recommandation et chaque état de progression.
3. Préserver les productions et apprendre de l'erreur plutôt que la masquer.
4. Garder le curriculum déterministe et la génération sous contrôle humain.
5. Concevoir chaque parcours pour l'interruption, la reprise et l'accessibilité.

## Accessibility & Inclusion

Le MVP vise WCAG 2.2 AA, navigation clavier complète, focus visible, zoom 200 %,
largeur minimale de 320 px, réduction des mouvements et alternatives textuelles
aux médias. La couleur ne porte jamais seule un état pédagogique.
