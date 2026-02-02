import json

# =========================
# CONFIGURATION
# =========================

pronouns = ["Io", "Tu", "Lui/Lei", "Noi", "Voi", "Loro"]

present_aux_essere = ["sono", "sei", "è", "siamo", "siete", "sono"]
present_aux_avere = ["ho", "hai", "ha", "abbiamo", "avete", "hanno"]

past_participle_endings = {
    "are": "ato",
    "ere": "uto",
    "ire": "ito"
}

future_endings = ["ò", "ai", "à", "emo", "ete", "anno"]
imperfetto_endings = {
    "are": ["avo", "avi", "ava", "avamo", "avate", "avano"],
    "ere": ["evo", "evi", "eva", "evamo", "evate", "evano"],
    "ire": ["ivo", "ivi", "iva", "ivamo", "ivate", "ivano"]
}

# =========================
# VERBES IRRÉGULIERS COMPLETS
# =========================

irregulars = {
    # === ESSENTIELS DU COURS ===
    "Essere": {
        "translation": "Être",
        "present": ["sono", "sei", "è", "siamo", "siete", "sono"],
        "future": ["sarò", "sarai", "sarà", "saremo", "sarete", "saranno"],
        "imperfetto": ["ero", "eri", "era", "eravamo", "eravate", "erano"],
        "aux": "essere",
        "pp": "stato"
    },
    "Avere": {
        "translation": "Avoir",
        "present": ["ho", "hai", "ha", "abbiamo", "avete", "hanno"],
        "future": ["avrò", "avrai", "avrà", "avremo", "avrete", "avranno"],
        "imperfetto": ["avevo", "avevi", "aveva", "avevamo", "avevate", "avevano"],
        "aux": "avere",
        "pp": "avuto"
    },
    "Stare": {
        "translation": "Aller/Rester (état)",
        "present": ["sto", "stai", "sta", "stiamo", "state", "stanno"],
        "future": ["starò", "starai", "starà", "staremo", "starete", "staranno"],
        "aux": "essere",
        "pp": "stato"
    },
    "Andare": {
        "translation": "Aller",
        "present": ["vado", "vai", "va", "andiamo", "andate", "vanno"],
        "future": ["andrò", "andrai", "andrà", "andremo", "andrete", "andranno"],
        "aux": "essere",
        "pp": "andato"
    },
    "Venire": {
        "translation": "Venir",
        "present": ["vengo", "vieni", "viene", "veniamo", "venite", "vengono"],
        "future": ["verrò", "verrai", "verrà", "verremo", "verrete", "verranno"],
        "aux": "essere",
        "pp": "venuto"
    },
    "Fare": {
        "translation": "Faire",
        "present": ["faccio", "fai", "fa", "facciamo", "fate", "fanno"],
        "future": ["farò", "farai", "farà", "faremo", "farete", "faranno"],
        "imperfetto": ["facevo", "facevi", "faceva", "facevamo", "facevate", "facevano"],
        "aux": "avere",
        "pp": "fatto"
    },
    "Dire": {
        "translation": "Dire",
        "present": ["dico", "dici", "dice", "diciamo", "dite", "dicono"],
        "future": ["dirò", "dirai", "dirà", "diremo", "direte", "diranno"],
        "imperfetto": ["dicevo", "dicevi", "diceva", "dicevamo", "dicevate", "dicevano"],
        "aux": "avere",
        "pp": "detto"
    },
    "Potere": {
        "translation": "Pouvoir",
        "present": ["posso", "puoi", "può", "possiamo", "potete", "possono"],
        "future": ["potrò", "potrai", "potrà", "potremo", "potrete", "potranno"],
        "aux": "avere",
        "pp": "potuto"
    },
    "Volere": {
        "translation": "Vouloir",
        "present": ["voglio", "vuoi", "vuole", "vogliamo", "volete", "vogliono"],
        "future": ["vorrò", "vorrai", "vorrà", "vorremo", "vorrete", "vorranno"],
        "aux": "avere",
        "pp": "voluto"
    },
    "Dovere": {
        "translation": "Devoir",
        "present": ["devo", "devi", "deve", "dobbiamo", "dovete", "devono"],
        "future": ["dovrò", "dovrai", "dovrà", "dovremo", "dovrete", "dovranno"],
        "aux": "avere",
        "pp": "dovuto"
    },
    "Sapere": {
        "translation": "Savoir",
        "present": ["so", "sai", "sa", "sappiamo", "sapete", "sanno"],
        "future": ["saprò", "saprai", "saprà", "sapremo", "saprete", "sapranno"],
        "aux": "avere",
        "pp": "saputo"
    },
    "Dare": {
        "translation": "Donner",
        "present": ["do", "dai", "dà", "diamo", "date", "danno"],
        "future": ["darò", "darai", "darà", "daremo", "darete", "daranno"],
        "aux": "avere",
        "pp": "dato"
    },
    "Uscire": {
        "translation": "Sortir",
        "present": ["esco", "esci", "esce", "usciamo", "uscite", "escono"],
        "future": ["uscirò", "uscirai", "uscirà", "usciremo", "uscirete", "usciranno"],
        "aux": "essere",
        "pp": "uscito"
    },
    "Rimanere": {
        "translation": "Rester",
        "present": ["rimango", "rimani", "rimane", "rimaniamo", "rimanete", "rimangono"],
        "future": ["rimarrò", "rimarrai", "rimarrà", "rimarremo", "rimarrete", "rimarranno"],
        "aux": "essere",
        "pp": "rimasto"
    },
    "Scegliere": {
        "translation": "Choisir",
        "present": ["scelgo", "scegli", "sceglie", "scegliamo", "scegliete", "scelgono"],
        "future": ["sceglierò", "sceglierai", "sceglierà", "sceglieremo", "sceglierete", "sceglieranno"],
        "aux": "avere",
        "pp": "scelto"
    },
    "Salire": {
        "translation": "Monter",
        "present": ["salgo", "sali", "sale", "saliamo", "salite", "salgono"],
        "future": ["salirò", "salirai", "salirà", "saliremo", "salirete", "saliranno"],
        "aux": "essere",
        "pp": "salito"
    },
    "Bere": {
        "translation": "Boire",
        "present": ["bevo", "bevi", "beve", "beviamo", "bevete", "bevono"],
        "future": ["berrò", "berrai", "berrà", "berremo", "berrete", "berranno"],
        "imperfetto": ["bevevo", "bevevi", "beveva", "bevevamo", "bevevate", "bevevano"],
        "aux": "avere",
        "pp": "bevuto"
    },
    "Morire": {
        "translation": "Mourir",
        "present": ["muoio", "muori", "muore", "moriamo", "morite", "muoiono"],
        "future": ["morirò", "morirai", "morirà", "moriremo", "morirete", "moriranno"],
        "aux": "essere",
        "pp": "morto"
    },
    "Nascere": {
        "translation": "Naître",
        "present": ["nasco", "nasci", "nasce", "nasciamo", "nascete", "nascono"],
        "future": ["nascerò", "nascerai", "nascerà", "nasceremo", "nascerete", "nasceranno"],
        "aux": "essere",
        "pp": "nato"
    },
    "Sedersi": {
        "translation": "S'asseoir",
        "present": ["mi siedo", "ti siedi", "si siede", "ci sediamo", "vi sedete", "si siedono"],
        "future": ["mi siederò", "ti siederai", "si siederà", "ci siederemo", "vi siederete", "si siederanno"],
        "aux": "essere",
        "pp": "seduto"
    },
    "Vedere": {
        "translation": "Voir",
        "present": ["vedo", "vedi", "vede", "vediamo", "vedete", "vedono"],
        "future": ["vedrò", "vedrai", "vedrà", "vedremo", "vedrete", "vedranno"],
        "aux": "avere",
        "pp": "visto"
    },
    "Vivere": {
        "translation": "Vivre",
        "present": ["vivo", "vivi", "vive", "viviamo", "vivete", "vivono"],
        "future": ["vivrò", "vivrai", "vivrà", "vivremo", "vivrete", "vivranno"],
        "aux": "avere",
        "pp": "vissuto"
    },
    "Scrivere": {
        "translation": "Écrire",
        "present": ["scrivo", "scrivi", "scrive", "scriviamo", "scrivete", "scrivono"],
        "future": ["scriverò", "scriverai", "scriverà", "scriveremo", "scriverete", "scriveranno"],
        "aux": "avere",
        "pp": "scritto"
    },
    "Leggere": {
        "translation": "Lire",
        "present": ["leggo", "leggi", "legge", "leggiamo", "leggete", "leggono"],
        "future": ["leggerò", "leggerai", "leggerà", "leggeremo", "leggerete", "leggeranno"],
        "aux": "avere",
        "pp": "letto"
    },
    "Prendere": {
        "translation": "Prendre",
        "present": ["prendo", "prendi", "prende", "prendiamo", "prendete", "prendono"],
        "future": ["prenderò", "prenderai", "prenderà", "prenderemo", "prenderete", "prenderanno"],
        "aux": "avere",
        "pp": "preso"
    },
    "Mettere": {
        "translation": "Mettre",
        "present": ["metto", "metti", "mette", "mettiamo", "mettete", "mettono"],
        "future": ["metterò", "metterai", "metterà", "metteremo", "metterete", "metteranno"],
        "aux": "avere",
        "pp": "messo"
    },
    "Aprire": {
        "translation": "Ouvrir",
        "present": ["apro", "apri", "apre", "apriamo", "aprite", "aprono"],
        "future": ["aprirò", "aprirai", "aprirà", "apriremo", "aprirete", "apriranno"],
        "aux": "avere",
        "pp": "aperto"
    },
    "Chiudere": {
        "translation": "Fermer",
        "present": ["chiudo", "chiudi", "chiude", "chiudiamo", "chiudete", "chiudono"],
        "future": ["chiuderò", "chiuderai", "chiuderà", "chiuderemo", "chiuderete", "chiuderanno"],
        "aux": "avere",
        "pp": "chiuso"
    },
    "Conoscere": {
        "translation": "Connaître",
        "present": ["conosco", "conosci", "conosce", "conosciamo", "conoscete", "conoscono"],
        "future": ["conoscerò", "conoscerai", "conoscerà", "conosceremo", "conoscerete", "conosceranno"],
        "aux": "avere",
        "pp": "conosciuto"
    },
    "Perdere": {
        "translation": "Perdre",
        "present": ["perdo", "perdi", "perde", "perdiamo", "perdete", "perdono"],
        "future": ["perderò", "perderai", "perderà", "perderemo", "perderete", "perderanno"],
        "aux": "avere",
        "pp": "perso"
    },
    "Vincere": {
        "translation": "Gagner/Vaincre",
        "present": ["vinco", "vinci", "vince", "vinciamo", "vincete", "vincono"],
        "future": ["vincerò", "vincerai", "vincerà", "vinceremo", "vincerete", "vinceranno"],
        "aux": "avere",
        "pp": "vinto"
    },
    "Correre": {
        "translation": "Courir",
        "present": ["corro", "corri", "corre", "corriamo", "correte", "corrono"],
        "future": ["correrò", "correrai", "correrà", "correremo", "correrete", "correranno"],
        "aux": "avere",
        "pp": "corso"
    },
    "Piangere": {
        "translation": "Pleurer",
        "present": ["piango", "piangi", "piange", "piangiamo", "piangete", "piangono"],
        "future": ["piangerò", "piangerai", "piangerà", "piangeremo", "piangerete", "piangeranno"],
        "aux": "avere",
        "pp": "pianto"
    },
    
    # === FAMILLE TENERE ===
    "Tenere": {
        "translation": "Tenir",
        "present": ["tengo", "tieni", "tiene", "teniamo", "tenete", "tengono"],
        "future": ["terrò", "terrai", "terrà", "terremo", "terrete", "terranno"],
        "aux": "avere",
        "pp": "tenuto",
        "family": "Tenere"
    },
    "Mantenere": {
        "translation": "Maintenir",
        "present": ["mantengo", "mantieni", "mantiene", "manteniamo", "mantenete", "mantengono"],
        "future": ["manterrò", "manterrai", "manterrà", "manterremo", "manterrete", "manterranno"],
        "aux": "avere",
        "pp": "mantenuto",
        "family": "Tenere"
    },
    "Ottenere": {
        "translation": "Obtenir",
        "present": ["ottengo", "ottieni", "ottiene", "otteniamo", "ottenete", "ottengono"],
        "future": ["otterrò", "otterrai", "otterrà", "otterremo", "otterrete", "otterranno"],
        "aux": "avere",
        "pp": "ottenuto",
        "family": "Tenere"
    },
    "Contenere": {
        "translation": "Contenir",
        "present": ["contengo", "contieni", "contiene", "conteniamo", "contenete", "contengono"],
        "future": ["conterrò", "conterrai", "conterrà", "conterremo", "conterrete", "conterranno"],
        "aux": "avere",
        "pp": "contenuto",
        "family": "Tenere"
    },
    
    # === FAMILLE PORRE ===
    "Porre": {
        "translation": "Poser/Mettre",
        "present": ["pongo", "poni", "pone", "poniamo", "ponete", "pongono"],
        "future": ["porrò", "porrai", "porrà", "porremo", "porrete", "porranno"],
        "aux": "avere",
        "pp": "posto",
        "family": "Porre"
    },
    "Proporre": {
        "translation": "Proposer",
        "present": ["propongo", "proponi", "propone", "proponiamo", "proponete", "propongono"],
        "future": ["proporrò", "proporrai", "proporrà", "proporremo", "proporrete", "proporranno"],
        "aux": "avere",
        "pp": "proposto",
        "family": "Porre"
    },
    "Imporre": {
        "translation": "Imposer",
        "present": ["impongo", "imponi", "impone", "imponiamo", "imponete", "impongono"],
        "future": ["imporrò", "imporrai", "imporrà", "imporremo", "imporrete", "imporranno"],
        "aux": "avere",
        "pp": "imposto",
        "family": "Porre"
    },
    "Supporre": {
        "translation": "Supposer",
        "present": ["suppongo", "supponi", "suppone", "supponiamo", "supponete", "suppongono"],
        "future": ["supporrò", "supporrai", "supporrà", "supporremo", "supporrete", "supporranno"],
        "aux": "avere",
        "pp": "supposto",
        "family": "Porre"
    },
    
    # === FAMILLE TRARRE ===
    "Trarre": {
        "translation": "Tirer",
        "present": ["traggo", "trai", "trae", "traiamo", "traete", "traggono"],
        "future": ["trarrò", "trarrai", "trarrà", "trarremo", "trarrete", "trarranno"],
        "aux": "avere",
        "pp": "tratto",
        "family": "Trarre"
    },
    "Attrarre": {
        "translation": "Attirer",
        "present": ["attraggo", "attrai", "attrae", "attraiamo", "attraete", "attraggono"],
        "future": ["attrarrò", "attrarrai", "attrarrà", "attraremo", "attrarrete", "attrarranno"],
        "aux": "avere",
        "pp": "attratto",
        "family": "Trarre"
    },
    "Distrarre": {
        "translation": "Distraire",
        "present": ["distraggo", "distrai", "distrae", "distraiamo", "distraete", "distraggono"],
        "future": ["distrarrò", "distrarrai", "distrarrà", "distraremo", "distrarrete", "distrarranno"],
        "aux": "avere",
        "pp": "distratto",
        "family": "Trarre"
    },
    
    # === FAMILLE TRADURRE ===
    "Tradurre": {
        "translation": "Traduire",
        "present": ["traduco", "traduci", "traduce", "traduciamo", "traducete", "traducono"],
        "future": ["tradurrò", "tradurrai", "tradurrà", "tradurremo", "tradurrete", "tradurranno"],
        "aux": "avere",
        "pp": "tradotto",
        "family": "Tradurre"
    },
    "Condurre": {
        "translation": "Conduire",
        "present": ["conduco", "conduci", "conduce", "conduciamo", "conducete", "conducono"],
        "future": ["condurrò", "condurrai", "condurrà", "condurremo", "condurrete", "condurranno"],
        "aux": "avere",
        "pp": "condotto",
        "family": "Tradurre"
    },
    "Produrre": {
        "translation": "Produire",
        "present": ["produco", "produci", "produce", "produciamo", "producete", "producono"],
        "future": ["produrrò", "produrrai", "produrrà", "produrremo", "produrrete", "produrranno"],
        "aux": "avere",
        "pp": "prodotto",
        "family": "Tradurre"
    },
    
    # === FAMILLE VENIRE ===
    "Intervenire": {
        "translation": "Intervenir",
        "present": ["intervengo", "intervieni", "interviene", "interveniamo", "intervenite", "intervengono"],
        "future": ["interverrò", "interverrai", "interverrà", "interverremo", "interverrete", "interverranno"],
        "aux": "essere",
        "pp": "intervenuto",
        "family": "Venire"
    },
    "Provenire": {
        "translation": "Provenir",
        "present": ["provengo", "provieni", "proviene", "proveniamo", "provenite", "provengono"],
        "future": ["proverrò", "proverrai", "proverrà", "proverremo", "proverrete", "proverranno"],
        "aux": "essere",
        "pp": "provenuto",
        "family": "Venire"
    },
}

# =========================
# VERBES RÉGULIERS & ISC
# =========================

verbs = {
    # Verbes en -are
    "Nuotare": ("Nager", "are"),      # ATTENTION: pas "noter"
    "Guardare": ("Regarder", "are"),
    "Portare": ("Porter", "are"),
    "Parlare": ("Parler", "are"),
    "Mangiare": ("Manger", "are"),
    "Lavorare": ("Travailler", "are"),
    "Amare": ("Aimer", "are"),
    "Ascoltare": ("Écouter", "are"),
    "Cantare": ("Chanter", "are"),
    "Studiare": ("Étudier", "are"),
    "Giocare": ("Jouer", "are"),
    "Comprare": ("Acheter", "are"),
    "Pagare": ("Payer", "are"),
    "Cercare": ("Chercher", "are"),
    "Trovare": ("Trouver", "are"),
    "Aspettare": ("Attendre", "are"),
    "Chiamare": ("Appeler", "are"),
    
    # Verbes en -ere
    "Cadere": ("Tomber", "ere"),
    "Ridere": ("Rire", "ere"),         # ATTENTION: pas "lire"
    "Difendere": ("Défendre", "ere"),
    "Credere": ("Croire", "ere"),
    "Vendere": ("Vendre", "ere"),
    "Ricevere": ("Recevoir", "ere"),
    "Temere": ("Craindre", "ere"),
    
    # Verbes en -ire (réguliers)
    "Soffrire": ("Souffrir", "ire"),
    "Cucire": ("Coudre", "ire"),       # ATTENTION: pas "cuisiner"
    "Dormire": ("Dormir", "ire"),
    "Sentire": ("Sentir/Entendre", "ire"),
    "Partire": ("Partir", "ire"),
    "Seguire": ("Suivre", "ire"),
    
    # Verbes en -isc (présent irrégulier)
    "Capire": ("Comprendre", "isc"),
    "Pulire": ("Nettoyer", "isc"),     # ATTENTION: pas "polir"
    "Finire": ("Finir", "isc"),
    "Preferire": ("Préférer", "isc"),
    "Costruire": ("Construire", "isc"),
    "Spedire": ("Envoyer", "isc"),
    "Guarire": ("Guérir", "isc"),
}

# =========================
# RÈGLES DE GRAMMAIRE
# =========================

grammar_rules = [
    {
        "front": "Passato Prossimo : Formation",
        "back": "Auxiliaire (Essere/Avere) au présent + Participe Passé\nEx: Ho mangiato / Sono andato",
        "categories": ["Grammaire", "Passé"]
    },
    {
        "front": "Quand utiliser ESSERE comme auxiliaire ?",
        "back": "1. Verbes de mouvement (andare, venire, partire...)\n2. Changement d'état (nascere, morire, diventare...)\n3. Verbes pronominaux (alzarsi, sedersi...)\n4. Verbes impersonnels",
        "categories": ["Grammaire", "Passé"]
    },
    {
        "front": "Accord du participe passé avec ESSERE",
        "back": "Le participe s'accorde en genre et nombre avec le sujet:\n-o (masc. sing.)\n-a (fém. sing.)\n-i (masc. plur.)\n-e (fém. plur.)\nEx: Lei è andata / Loro sono andati",
        "categories": ["Grammaire", "Passé"]
    },
    {
        "front": "Terminaisons du Participe Passé régulier",
        "back": "-ARE → -ATO (mangiare → mangiato)\n-ERE → -UTO (credere → creduto)\n-IRE → -ITO (dormire → dormito)",
        "categories": ["Grammaire", "Passé"]
    },
    {
        "front": "Terminaisons de l'Imperfetto",
        "back": "-ARE → -avo, -avi, -ava, -avamo, -avate, -avano\n-ERE → -evo, -evi, -eva, -evamo, -evate, -evano\n-IRE → -ivo, -ivi, -iva, -ivamo, -ivate, -ivano",
        "categories": ["Grammaire", "Imperfetto"]
    },
    {
        "front": "Formation du Futur Simple",
        "back": "Infinitif (sans -e final pour -ere) + terminaisons:\n-ò, -ai, -à, -emo, -ete, -anno\nEx: parler-ò, creder-ò, dormir-ò",
        "categories": ["Grammaire", "Futur"]
    },
    {
        "front": "Verbes en -ISC- : quand l'utiliser ?",
        "back": "Certains verbes en -ire ajoutent -ISC- aux 3 personnes du singulier et 3ème pluriel au présent:\nCapire → capisco, capisci, capisce, capiamo, capite, capiscono",
        "categories": ["Grammaire", "Présent"]
    },
    {
        "front": "Famille TENERE : Modèle de conjugaison",
        "back": "Tengo, tieni, tiene, teniamo, tenete, tengono\nS'applique à: mantenere, ottenere, contenere, sostenere...\nFutur irrégulier: terrò, terrai...",
        "categories": ["Grammaire", "Familles"]
    },
    {
        "front": "Famille PORRE : Modèle de conjugaison",
        "back": "Pongo, poni, pone, poniamo, ponete, pongono\nS'applique à: proporre, imporre, supporre, disporre...\nPP: posto",
        "categories": ["Grammaire", "Familles"]
    },
    {
        "front": "Famille TRARRE : Modèle de conjugaison",
        "back": "Traggo, trai, trae, traiamo, traete, traggono\nS'applique à: attrarre, distrarre, contrarre...\nPP: tratto",
        "categories": ["Grammaire", "Familles"]
    },
    {
        "front": "Famille TRADURRE : Modèle de conjugaison",
        "back": "Traduco, traduci, traduce, traduciamo, traducete, traducono\nS'applique à: condurre, produrre, ridurre...\nPP: tradotto, condotto...",
        "categories": ["Grammaire", "Familles"]
    },
    {
        "front": "Famille VENIRE : Quels verbes ?",
        "back": "Tous se conjuguent comme VENIRE:\nintervenire, provenire, convenire, divenire, avvenire, sovvenire\nAuxiliaire: ESSERE",
        "categories": ["Grammaire", "Familles"]
    },
    {
        "front": "Famille FARE : Quels verbes ?",
        "back": "Tous se conjuguent comme FARE:\ndisfare, soddisfare, contrafare, rifare\nPP: fatto, disfatto, soddisfatto...",
        "categories": ["Grammaire", "Familles"]
    },
    {
        "front": "Famille DIRE : Quels verbes ?",
        "back": "Tous se conjuguent comme DIRE:\npredire, contraddire, maledire, benedire\nPP: detto, predetto, contraddetto...",
        "categories": ["Grammaire", "Familles"]
    },
]

# =========================
# FONCTIONS
# =========================

def present_regular(stem, t):
    if t == "are":
        return [stem+"o", stem+"i", stem+"a", stem+"iamo", stem+"ate", stem+"ano"]
    if t == "ere":
        return [stem+"o", stem+"i", stem+"e", stem+"iamo", stem+"ete", stem+"ono"]
    if t == "ire":
        return [stem+"o", stem+"i", stem+"e", stem+"iamo", stem+"ite", stem+"ono"]

def present_isc(stem):
    return [stem+"isco", stem+"isci", stem+"isce", stem+"iamo", stem+"ite", stem+"iscono"]

def future_simple(inf):
    # Handle -are verbs (drop 'a' from 'are')
    if inf.endswith("are"):
        base = inf[:-3] + "er"
    else:
        base = inf[:-1]
    return [base + e for e in future_endings]

def imperfetto_regular(stem, t):
    return [stem + e for e in imperfetto_endings[t]]

def passato_prossimo(aux, pp, verb_name=""):
    aux_forms = present_aux_essere if aux == "essere" else present_aux_avere
    return [aux_forms[i] + " " + pp for i in range(6)]

# =========================
# GÉNÉRATION DU DECK
# =========================

deck = {
    "_format_version": "1.0",
    "name": "Italien – Conjugaisons Complètes",
    "description": "Tous les temps, verbes irréguliers, familles et règles de grammaire",
    "categories": [
        {"name": "Infinitif", "color": "#64748b"},
        {"name": "Présent", "color": "#0ea5e9"},
        {"name": "Passé", "color": "#8b5cf6"},
        {"name": "Futur", "color": "#f59e0b"},
        {"name": "Imperfetto", "color": "#14b8a6"},
        {"name": "3 Temps", "color": "#ef4444"},
        {"name": "Grammaire", "color": "#22c55e"},
        {"name": "Familles", "color": "#d946ef"},
    ],
    "cards": []
}

# === IRRÉGULIERS ===
for v, d in irregulars.items():
    verb_cat = d.get("family", v)
    
    # Infinitif
    deck["cards"].append({
        "front": v,
        "back": d["translation"],
        "categories": ["Infinitif", verb_cat]
    })
    
    # 3 Temps Clés
    deck["cards"].append({
        "front": f"{v.upper()} : 3 Temps",
        "back": f"Présent (1p): {d['present'][0]}\nParticipe Passé: {d['pp']}\nFutur (1p): {d['future'][0]}",
        "categories": ["3 Temps", verb_cat]
    })
    
    past = passato_prossimo(d["aux"], d["pp"])
    
    for i in range(6):
        # Présent
        deck["cards"].append({
            "front": f"{pronouns[i]} ({v})",
            "back": d["present"][i],
            "categories": ["Présent", verb_cat]
        })
        # Passato Prossimo
        deck["cards"].append({
            "front": f"{pronouns[i]} ({v}) – Passato P.",
            "back": past[i],
            "categories": ["Passé", verb_cat]
        })
        # Futur
        deck["cards"].append({
            "front": f"{pronouns[i]} ({v}) – Futur",
            "back": d["future"][i],
            "categories": ["Futur", verb_cat]
        })
        # Imperfetto si disponible
        if "imperfetto" in d:
            deck["cards"].append({
                "front": f"{pronouns[i]} ({v}) – Imperfetto",
                "back": d["imperfetto"][i],
                "categories": ["Imperfetto", verb_cat]
            })

# === RÉGULIERS ===
for v, (tr, t) in verbs.items():
    if t == "isc":
        stem = v[:-3]
        present = present_isc(stem)
        real_type = "ire"
    else:
        stem = v[:-3]
        present = present_regular(stem, t)
        real_type = t
    
    future = future_simple(v)
    pp = stem + past_participle_endings[real_type]
    past = passato_prossimo("avere", pp)  # Most regular verbs use avere
    imperf = imperfetto_regular(stem, real_type)
    
    # Infinitif
    deck["cards"].append({
        "front": v,
        "back": tr,
        "categories": ["Infinitif", v]
    })
    
    # 3 Temps
    deck["cards"].append({
        "front": f"{v.upper()} : 3 Temps",
        "back": f"Présent (1p): {present[0]}\nParticipe Passé: {pp}\nFutur (1p): {future[0]}",
        "categories": ["3 Temps", v]
    })
    
    for i in range(6):
        # Présent
        deck["cards"].append({
            "front": f"{pronouns[i]} ({v})",
            "back": present[i],
            "categories": ["Présent", v]
        })
        # Passato Prossimo
        deck["cards"].append({
            "front": f"{pronouns[i]} ({v}) – Passato P.",
            "back": past[i],
            "categories": ["Passé", v]
        })
        # Futur
        deck["cards"].append({
            "front": f"{pronouns[i]} ({v}) – Futur",
            "back": future[i],
            "categories": ["Futur", v]
        })
        # Imperfetto
        deck["cards"].append({
            "front": f"{pronouns[i]} ({v}) – Imperfetto",
            "back": imperf[i],
            "categories": ["Imperfetto", v]
        })

# === RÈGLES DE GRAMMAIRE ===
for rule in grammar_rules:
    deck["cards"].append(rule)

# === EXPORT ===
with open("card_sets/deck_italien.json", "w", encoding="utf-8") as f:
    json.dump(deck, f, ensure_ascii=False, indent=2)

print(f"✅ deck_italien.json généré avec {len(deck['cards'])} cartes")
print(f"   - {len(irregulars)} verbes irréguliers")
print(f"   - {len(verbs)} verbes réguliers")
print(f"   - {len(grammar_rules)} règles de grammaire")