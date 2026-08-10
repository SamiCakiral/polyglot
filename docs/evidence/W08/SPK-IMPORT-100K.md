# W08 - Spike import 100 000 lignes

## Resultat

Le fixture canonique `FX-IMPORTS` produit et parse reellement 100 000 lignes
lexicales hors reseau. Le payload JSON canonique mesure 9 977 850 octets et
reste sous la limite de 20 Mio.

Sur macOS arm64 avec Python 3.13.11, neuf executions du parseur donnent :

- p50 : 0,794789 s ;
- p95 : 0,829307 s ;
- p99 : 0,837981 s.

Le test Pytest complet du cas volumetrique et des contrats FX a termine en
1,83 s avec un RSS maximal mesure a 206 979 072 octets.

## Portee De La Preuve

Cette preuve couvre la generation, le decodage JSON, les limites, la
normalisation, la validation UUID et la production de 100 000 candidats. Elle
ne couvre pas encore l'insertion PostgreSQL de 100 000 lignes, le commit W06 ni
son profil SQL. W08 ne peut donc pas etre accepte sur la seule base de ce spike.

Les mesures brutes sont dans `spk-import-100k-raw.json`.
