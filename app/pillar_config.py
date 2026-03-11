"""
Configuration des piliers d'apprentissage par langue, alignes sur le CECR.

Organisation:
- Chaque pilier a un champ 'cefr' (A0, A1, A2, B1, B2, C1, C2) et un 'level' numerique
- level 0=A0, 1=A1, 2=A2, 3=B1, 4=B2, 5=C1, 6=C2 (pour les langues refondues: it, ja, tr)
- Les 4 autres langues (es, zh, ko, ru) gardent leur ancien level mais ont un champ 'cefr' exact
- Chaque pilier a un champ 'exercise_types' listant les types d'exercices pertinents

Groupes de langues:
- Romance (it, es): conjugaison, genre, articles, SVO
- Est-asiatiques (ja, zh, ko): systemes d'ecriture, paradigmes differents
- Slaves (ru): cas, aspects, genre, cyrillique
- Turciques (tr): agglutination, harmonie vocalique, SOV
"""

SUPPORTED_LANGUAGES = ['ja', 'zh', 'ko', 'ru', 'tr', 'es', 'it']

CECRL_LEVELS = ['A0', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2']

PILLAR_STATUS = ['locked', 'available', 'in_progress', 'completed']

LANGUAGE_GROUPS = {
    'romance': {
        'languages': ['it', 'es'],
        'features': ['conjugation', 'gender', 'articles'],
        'word_order': 'SVO',
    },
    'east_asian': {
        'languages': ['ja', 'zh', 'ko'],
        'features': ['writing_system'],
        'word_order': 'varied',
    },
    'slavic': {
        'languages': ['ru'],
        'features': ['conjugation', 'gender', 'cases'],
        'word_order': 'SVO',
    },
    'turkic': {
        'languages': ['tr'],
        'features': ['conjugation', 'agglutination'],
        'word_order': 'SOV',
    },
}

CEFR_LEVEL_NAMES = {
    'A0': 'Prerequis',
    'A1': 'Decouverte',
    'A2': 'Survie',
    'B1': 'Seuil',
    'B2': 'Avance',
    'C1': 'Autonome',
    'C2': 'Maitrise',
}

# Niveaux pour l'onboarding (commun a toutes les langues)
ONBOARDING_LEVELS = [
    {"cefr": "A0", "label": "Debutant complet", "desc": "Je n'ai jamais appris cette langue"},
    {"cefr": "A1", "label": "Faux debutant", "desc": "Je connais quelques mots et les bases"},
    {"cefr": "A2", "label": "Elementaire", "desc": "Je me debrouille dans les situations simples"},
    {"cefr": "B1", "label": "Intermediaire", "desc": "Je peux tenir une conversation courante"},
    {"cefr": "B2", "label": "Avance", "desc": "Je comprends la plupart des textes et discussions"},
    {"cefr": "C1", "label": "Courant", "desc": "Je m'exprime couramment et spontanement"},
    {"cefr": "C2", "label": "Bilingue / natif", "desc": "Je comprends tout sans effort"},
]


LANGUAGES = {
    # =========================================================================
    # ITALIEN (refonte complete A0-C2)
    # =========================================================================
    "it": {
        "name": "Italien",
        "native_name": "Italiano",
        "flag": "it",
        "writing_system": "latin",
        "word_order": "SVO",
        "has_tones": False,
        "has_gender": True,
        "has_cases": False,
        "has_particles": False,
        "has_conjugation": True,
        "romanization": None,
        "difficulty": 2,

        "pillars": [
            # === A0 - Prerequis (level 0) ===
            {"id": "pronunciation_it", "level": 0, "cefr": "A0",
             "name": "Alphabet & Prononciation", "native_name": "Alfabeto e Pronuncia",
             "description": "L'alphabet italien, doubles consonnes, c/g devant voyelles, gl/gn/sc, accent tonique",
             "cards": 20, "required": True, "prereq": [],
             "estimated_hours": 3, "category": "phonetics", "exercise_types": []},

            {"id": "greetings_it", "level": 0, "cefr": "A0",
             "name": "Salutations & Politesse", "native_name": "Saluti e Cortesia",
             "description": "Ciao, buongiorno, buonasera, arrivederci, per favore, grazie, scusi, prego",
             "cards": 15, "required": True, "prereq": [],
             "estimated_hours": 2, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            # === A1 - Decouverte (level 1) ===
            {"id": "pronouns_it", "level": 1, "cefr": "A1",
             "name": "Pronoms personnels", "native_name": "Pronomi personali",
             "description": "io, tu, lui/lei, noi, voi, loro - Lei (forme de politesse)",
             "cards": 12, "required": True, "prereq": ["greetings_it"],
             "estimated_hours": 2, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "essere_stare_it", "level": 1, "cefr": "A1",
             "name": "Essere & Stare", "native_name": "Essere e Stare",
             "description": "Conjugaison au present, usages: essere = identite/etat permanent, stare = etat temporaire/sante",
             "cards": 20, "required": True, "prereq": ["pronouns_it"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "avere_it", "level": 1, "cefr": "A1",
             "name": "Avere", "native_name": "Avere",
             "description": "Conjugaison + expressions: ho fame, ho freddo, ho bisogno di, ho paura, ho voglia di",
             "cards": 15, "required": True, "prereq": ["essere_stare_it"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "present_regular_it", "level": 1, "cefr": "A1",
             "name": "Present regulier", "native_name": "Presente regolare",
             "description": "Les 3 groupes: -are (parlare), -ere (scrivere), -ire (dormire/capire). 6 personnes",
             "cards": 40, "required": True, "prereq": ["avere_it"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "present_irregular_it", "level": 1, "cefr": "A1",
             "name": "Irreguliers courants", "native_name": "Irregolari comuni",
             "description": "andare, fare, dare, dire, venire, uscire, sapere, volere, potere, dovere",
             "cards": 30, "required": True, "prereq": ["present_regular_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "negation_it", "level": 1, "cefr": "A1",
             "name": "Negation & Questions", "native_name": "Negazione e Domande",
             "description": "non + verbe. Che? Dove? Come? Quando? Perche? Chi? Quanto?",
             "cards": 15, "required": True, "prereq": ["essere_stare_it"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "transform", "word_order"]},

            {"id": "articles_gender_it", "level": 1, "cefr": "A1",
             "name": "Articles & Genre", "native_name": "Articoli e Genere",
             "description": "il/lo/la/i/gli/le, un/uno/una. Accord -o/-a/-i/-e. Lo devant s+cons, z, gn, ps",
             "cards": 25, "required": True, "prereq": ["pronouns_it"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["gender", "fill_blank"]},

            {"id": "numbers_it", "level": 1, "cefr": "A1",
             "name": "Nombres & Temps", "native_name": "Numeri e Tempo",
             "description": "1-1000, heures (Che ore sono?), jours, mois, dates, saisons",
             "cards": 30, "required": True, "prereq": ["greetings_it"],
             "estimated_hours": 4, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "vocab_basic_it", "level": 1, "cefr": "A1",
             "name": "Vocabulaire fondamental", "native_name": "Vocabolario fondamentale",
             "description": "Famiglia, colori, cibo, corpo, casa, vestiti, animali (~200 mots essentiels)",
             "cards": 60, "required": True, "prereq": ["greetings_it"],
             "estimated_hours": 8, "category": "vocabulary", "exercise_types": ["fill_blank", "word_order"]},

            # === A2 - Survie (level 2) ===
            {"id": "passato_prossimo_it", "level": 2, "cefr": "A2",
             "name": "Passe compose", "native_name": "Passato prossimo",
             "description": "Ho mangiato, sono andato/a. Choix essere/avere. Accord du participe avec essere",
             "cards": 30, "required": True, "prereq": ["present_irregular_it"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "imperfetto_it", "level": 2, "cefr": "A2",
             "name": "Imparfait", "native_name": "Imperfetto",
             "description": "-avo/-evo/-ivo. Descriptions, habitudes passees. Contraste passato prossimo vs imperfetto",
             "cards": 25, "required": True, "prereq": ["passato_prossimo_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "prepositions_it", "level": 2, "cefr": "A2",
             "name": "Prepositions simples", "native_name": "Preposizioni semplici",
             "description": "di, a, da, in, con, su, per, tra/fra - usages et expressions",
             "cards": 20, "required": True, "prereq": ["negation_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "contracted_articles_it", "level": 2, "cefr": "A2",
             "name": "Articles contractes", "native_name": "Preposizioni articolate",
             "description": "di+il=del, a+la=alla, in+il=nel, su+lo=sullo, da+gli=dagli - TRES frequent",
             "cards": 30, "required": True, "prereq": ["prepositions_it", "articles_gender_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "gender"]},

            {"id": "object_pronouns_it", "level": 2, "cefr": "A2",
             "name": "Pronoms COD/COI", "native_name": "Pronomi diretti e indiretti",
             "description": "lo, la, li, le (COD), mi, ti, gli, le, ci, vi (COI), ne. Position avant le verbe",
             "cards": 25, "required": True, "prereq": ["present_irregular_it"],
             "estimated_hours": 7, "category": "grammar", "exercise_types": ["fill_blank", "word_order", "transform"]},

            {"id": "reflexive_it", "level": 2, "cefr": "A2",
             "name": "Verbes pronominaux", "native_name": "Verbi riflessivi",
             "description": "svegliarsi, lavarsi, vestirsi, sentirsi, trovarsi. Accord au passe compose avec essere",
             "cards": 20, "required": True, "prereq": ["present_regular_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "comparatives_it", "level": 2, "cefr": "A2",
             "name": "Comparatifs & Superlatifs", "native_name": "Comparativi e Superlativi",
             "description": "piu...di, meno...di, il piu, il meno. Irreguliers: migliore, peggiore, maggiore, minore",
             "cards": 15, "required": True, "prereq": ["articles_gender_it"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "vocab_daily_it", "level": 2, "cefr": "A2",
             "name": "Vocabulaire quotidien", "native_name": "Vocabolario quotidiano",
             "description": "Shopping, transport, sante, directions, meteo, restaurant, hotel (~300 mots)",
             "cards": 50, "required": True, "prereq": ["vocab_basic_it"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank", "word_order"]},

            # === B1 - Seuil (level 3) ===
            {"id": "future_it", "level": 3, "cefr": "B1",
             "name": "Futur simple", "native_name": "Futuro semplice",
             "description": "-ero/-erai/-era. Irreguliers: andro, faro, saro, avro, vedro, potro, dovro, vorro",
             "cards": 25, "required": True, "prereq": ["imperfetto_it"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "conditional_it", "level": 3, "cefr": "B1",
             "name": "Conditionnel present", "native_name": "Condizionale presente",
             "description": "-erei/-eresti/-erebbe. Politesse: vorrei, potrei. Irreguliers comme le futur",
             "cards": 25, "required": True, "prereq": ["future_it"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "subjunctive_intro_it", "level": 3, "cefr": "B1",
             "name": "Subjonctif present (intro)", "native_name": "Congiuntivo presente",
             "description": "Penso che, credo che, bisogna che, e necessario che, voglio che + subjonctif",
             "cards": 25, "required": True, "prereq": ["conditional_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "relative_clauses_it", "level": 3, "cefr": "B1",
             "name": "Propositions relatives", "native_name": "Proposizioni relative",
             "description": "che (sujet/COD), cui (apres preposition), il/la quale, dove (relatif)",
             "cards": 15, "required": True, "prereq": ["object_pronouns_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "conjunctions_it", "level": 3, "cefr": "B1",
             "name": "Conjonctions complexes", "native_name": "Congiunzioni complesse",
             "description": "benche, affinche, purche, sebbene, nonostante, a meno che, prima che",
             "cards": 20, "required": True, "prereq": ["subjunctive_intro_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order", "transform"]},

            {"id": "indirect_speech_it", "level": 3, "cefr": "B1",
             "name": "Discours indirect", "native_name": "Discorso indiretto",
             "description": "Ha detto che... Ha chiesto se... Concordance des temps au discours indirect",
             "cards": 15, "required": True, "prereq": ["imperfetto_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "formal_register_it", "level": 3, "cefr": "B1",
             "name": "Registre formel", "native_name": "Registro formale",
             "description": "Lei vs tu, condizionale di cortesia, formules epistolaires, egregio/gentile",
             "cards": 15, "required": True, "prereq": ["conditional_it"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "vocab_thematic_it", "level": 3, "cefr": "B1",
             "name": "Vocabulaire thematique", "native_name": "Vocabolario tematico",
             "description": "Lavoro, cultura, attualita, ambiente, tecnologia, politica (~500 mots)",
             "cards": 60, "required": True, "prereq": ["vocab_daily_it"],
             "estimated_hours": 8, "category": "vocabulary", "exercise_types": ["fill_blank", "word_order"]},

            # === B2 - Avance (level 4) ===
            {"id": "passato_remoto_it", "level": 4, "cefr": "B2",
             "name": "Passe simple", "native_name": "Passato remoto",
             "description": "mangiai, andai, feci, dissi, vissi. Usage litteraire et Sud de l'Italie",
             "cards": 30, "required": True, "prereq": ["imperfetto_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "trapassato_it", "level": 4, "cefr": "B2",
             "name": "Plus-que-parfait", "native_name": "Trapassato prossimo",
             "description": "avevo mangiato, ero andato. Anteriorite dans le passe",
             "cards": 20, "required": True, "prereq": ["passato_prossimo_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "subjunctive_advanced_it", "level": 4, "cefr": "B2",
             "name": "Subjonctif avance", "native_name": "Congiuntivo avanzato",
             "description": "Tous les temps: imperfetto (fossi, avessi), trapassato. Concordance des temps",
             "cards": 30, "required": True, "prereq": ["subjunctive_intro_it"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "passive_it", "level": 4, "cefr": "B2",
             "name": "Voix passive", "native_name": "Forma passiva",
             "description": "e stato fatto, viene fatto, si impersonale (si dice), si passivante (si vendono)",
             "cards": 20, "required": True, "prereq": ["passato_prossimo_it"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "gerundio_it", "level": 4, "cefr": "B2",
             "name": "Gerondif & Infinitif", "native_name": "Gerundio e Infinito",
             "description": "stare + gerundio (progressif), prima di + inf, dopo aver + pp, pur + gerundio",
             "cards": 20, "required": True, "prereq": ["present_irregular_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "hypothetical_it", "level": 4, "cefr": "B2",
             "name": "Periode hypothetique", "native_name": "Periodo ipotetico",
             "description": "3 types: realta (se + presente), possibilita (se + congiuntivo impf + condiz), impossibilita (se + cong trapassato)",
             "cards": 20, "required": True, "prereq": ["subjunctive_advanced_it", "conditional_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "connectors_it", "level": 4, "cefr": "B2",
             "name": "Connecteurs du discours", "native_name": "Connettivi del discorso",
             "description": "tuttavia, infatti, pertanto, nonostante, d'altra parte, in conclusione, insomma",
             "cards": 20, "required": True, "prereq": ["conjunctions_it"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "idiomatic_it", "level": 4, "cefr": "B2",
             "name": "Expressions idiomatiques", "native_name": "Espressioni idiomatiche",
             "description": "In bocca al lupo, non vedo l'ora, avere la testa fra le nuvole, fare il furbo",
             "cards": 30, "required": True, "prereq": ["vocab_thematic_it"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            # === C1 - Autonome (level 5) ===
            {"id": "grammar_mastery_it", "level": 5, "cefr": "C1",
             "name": "Maitrise grammaticale", "native_name": "Padronanza grammaticale",
             "description": "Concordance complete, subjonctif dans toutes les subordonnees, nuances modales",
             "cards": 25, "required": True, "prereq": ["subjunctive_advanced_it", "hypothetical_it"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "complex_structures_it", "level": 5, "cefr": "C1",
             "name": "Structures complexes", "native_name": "Strutture complesse",
             "description": "Conditionnel passe, hypothetique mixte, nominalisation, phrases participiales",
             "cards": 20, "required": True, "prereq": ["grammar_mastery_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "professional_writing_it", "level": 5, "cefr": "C1",
             "name": "Ecriture professionnelle", "native_name": "Scrittura professionale",
             "description": "Emails formels, rapports, lettres, CV, argumentation structuree",
             "cards": 15, "required": True, "prereq": ["formal_register_it", "connectors_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "cultural_refs_it", "level": 5, "cefr": "C1",
             "name": "References culturelles", "native_name": "Riferimenti culturali",
             "description": "Proverbes, expressions regionales, references classiques, cinema/litterature italienne",
             "cards": 25, "required": True, "prereq": ["idiomatic_it"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "literary_forms_it", "level": 5, "cefr": "C1",
             "name": "Formes litteraires", "native_name": "Forme letterarie",
             "description": "Passato remoto avance, trapassato remoto, registre soutenu et bureaucratique",
             "cards": 20, "required": True, "prereq": ["passato_remoto_it"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            # === C2 - Maitrise (level 6) ===
            {"id": "dialectal_it", "level": 6, "cefr": "C2",
             "name": "Conscience dialectale", "native_name": "Consapevolezza dialettale",
             "description": "Differences Nord/Sud, regionalismes, italien parle vs ecrit, influences dialectales",
             "cards": 20, "required": True, "prereq": ["cultural_refs_it"],
             "estimated_hours": 8, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "literary_analysis_it", "level": 6, "cefr": "C2",
             "name": "Analyse litteraire", "native_name": "Analisi letteraria",
             "description": "Stylistique, argumentation, rhetorique, commentaire de texte",
             "cards": 15, "required": True, "prereq": ["literary_forms_it"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "translation_it", "level": 6, "cefr": "C2",
             "name": "Traduction & Mediation", "native_name": "Traduzione e Mediazione",
             "description": "Competences de traduction, resume, synthese, mediation interculturelle",
             "cards": 15, "required": True, "prereq": ["professional_writing_it"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "native_fluency_it", "level": 6, "cefr": "C2",
             "name": "Fluidite native", "native_name": "Fluidita nativa",
             "description": "Automatismes, nuances fines, humour, sous-entendus, registres multiples",
             "cards": 15, "required": True, "prereq": ["grammar_mastery_it"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
        ],

        "onboarding": ONBOARDING_LEVELS,
    },

    # =========================================================================
    # JAPONAIS (refonte complete A0-C2)
    # =========================================================================
    "ja": {
        "name": "Japonais",
        "native_name": "日本語",
        "flag": "jp",
        "writing_system": "kana+kanji",
        "word_order": "SOV",
        "has_tones": False,
        "has_gender": False,
        "has_cases": False,
        "has_particles": True,
        "has_conjugation": True,
        "romanization": "romaji",
        "difficulty": 5,

        "pillars": [
            # === A0 - Prerequis (level 0) ===
            {"id": "hiragana", "level": 0, "cefr": "A0",
             "name": "Hiragana", "native_name": "ひらがな",
             "description": "Les 46 caracteres de base pour ecrire les mots japonais + combinaisons",
             "cards": 46, "required": True, "prereq": [],
             "estimated_hours": 10, "category": "writing", "exercise_types": []},

            {"id": "katakana", "level": 0, "cefr": "A0",
             "name": "Katakana", "native_name": "カタカナ",
             "description": "Les 46 caracteres pour les mots etrangers et onomatopees",
             "cards": 46, "required": True, "prereq": ["hiragana"],
             "estimated_hours": 10, "category": "writing", "exercise_types": []},

            {"id": "pronunciation_ja", "level": 0, "cefr": "A0",
             "name": "Prononciation", "native_name": "発音",
             "description": "Sons japonais, voyelles longues/courtes, doubles consonnes, intonation",
             "cards": 20, "required": True, "prereq": ["hiragana"],
             "estimated_hours": 5, "category": "phonetics", "exercise_types": []},

            # === A1 - Decouverte (level 1) ===
            {"id": "pronouns_ja", "level": 1, "cefr": "A1",
             "name": "Pronoms", "native_name": "代名詞",
             "description": "私, あなた, 彼, 彼女, 私たち. Pronoms demonstratifs: これ/それ/あれ",
             "cards": 15, "required": True, "prereq": ["hiragana"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "copula_ja", "level": 1, "cefr": "A1",
             "name": "Copule です/だ", "native_name": "です・だ",
             "description": "L'equivalent de 'etre'. Affirmatif, negatif, passe. Poli vs familier",
             "cards": 10, "required": True, "prereq": ["pronouns_ja"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "particles_basic_ja", "level": 1, "cefr": "A1",
             "name": "Particules de base", "native_name": "基本助詞",
             "description": "は (theme), が (sujet), を (COD), に (destination/temps), で (lieu/moyen)",
             "cards": 15, "required": True, "prereq": ["copula_ja"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["particles", "fill_blank"]},

            {"id": "negation_ja", "level": 1, "cefr": "A1",
             "name": "Negation & Questions", "native_name": "否定形と疑問文",
             "description": "ません/ない, じゃありません. か, 何, どこ, いつ, だれ, どう",
             "cards": 12, "required": True, "prereq": ["copula_ja"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "numbers_ja", "level": 1, "cefr": "A1",
             "name": "Nombres & Temps", "native_name": "数字と時間",
             "description": "1-10000, heures, jours, mois, dates. Compteurs de base (つ, 人)",
             "cards": 25, "required": True, "prereq": ["hiragana"],
             "estimated_hours": 4, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "verb_groups_ja", "level": 1, "cefr": "A1",
             "name": "Groupes verbaux", "native_name": "動詞のグループ",
             "description": "Ichidan (-eru/-iru), Godan (-u), Irreguliers (する/来る). Forme du dictionnaire",
             "cards": 30, "required": True, "prereq": ["particles_basic_ja"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "masu_form_ja", "level": 1, "cefr": "A1",
             "name": "Forme polie -ます", "native_name": "ます形",
             "description": "食べます, 飲みます, 行きます. La forme standard pour parler poliment",
             "cards": 25, "required": True, "prereq": ["verb_groups_ja"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "vocab_basic_ja", "level": 1, "cefr": "A1",
             "name": "Vocabulaire fondamental", "native_name": "基本語彙",
             "description": "Famille, nourriture, corps, maison, couleurs, animaux (~200 mots N5)",
             "cards": 60, "required": True, "prereq": ["hiragana"],
             "estimated_hours": 10, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            # === A2 - Survie (level 2) ===
            {"id": "past_ja", "level": 2, "cefr": "A2",
             "name": "Passe", "native_name": "過去形",
             "description": "ました/た forme. 食べました, 行った, 見た. Passe negatif: ませんでした/なかった",
             "cards": 20, "required": True, "prereq": ["masu_form_ja"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "te_form_ja", "level": 2, "cefr": "A2",
             "name": "Forme en て", "native_name": "て形",
             "description": "食べて, 飲んで, 行って. Pivot: demander (ください), progressif (ている), permission (もいい)",
             "cards": 25, "required": True, "prereq": ["past_ja"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "particles_advanced_ja", "level": 2, "cefr": "A2",
             "name": "Particules avancees", "native_name": "助詞（応用）",
             "description": "へ (direction), から/まで (de/jusqu'a), と (avec/citation), も (aussi), の (possession)",
             "cards": 15, "required": True, "prereq": ["particles_basic_ja"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["particles", "fill_blank"]},

            {"id": "counters_ja", "level": 2, "cefr": "A2",
             "name": "Compteurs", "native_name": "助数詞",
             "description": "つ, 人, 枚, 本, 匹, 台, 冊. Le systeme japonais de classification",
             "cards": 20, "required": True, "prereq": ["numbers_ja"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank"]},

            {"id": "adjectives_ja", "level": 2, "cefr": "A2",
             "name": "Adjectifs", "native_name": "形容詞",
             "description": "い-adjectifs (大きい, 小さい), な-adjectifs (静かな, 綺麗な). Conjugaison, negation, passe",
             "cards": 25, "required": True, "prereq": ["copula_ja"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "tai_form_ja", "level": 2, "cefr": "A2",
             "name": "Forme -たい (desir)", "native_name": "たい形",
             "description": "食べたい (je veux manger), 行きたい (je veux aller). Desirs et souhaits",
             "cards": 15, "required": True, "prereq": ["masu_form_ja"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "vocab_daily_ja", "level": 2, "cefr": "A2",
             "name": "Vocabulaire quotidien", "native_name": "日常語彙",
             "description": "Transports, shopping, restaurant, directions, meteo, sante (~300 mots N4)",
             "cards": 50, "required": True, "prereq": ["vocab_basic_ja"],
             "estimated_hours": 8, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            # === B1 - Seuil (level 3) ===
            {"id": "potential_ja", "level": 3, "cefr": "B1",
             "name": "Forme potentielle", "native_name": "可能形",
             "description": "食べられる, 読める, できる. Exprimer la capacite, la possibilite",
             "cards": 20, "required": True, "prereq": ["te_form_ja"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "conditional_ja", "level": 3, "cefr": "B1",
             "name": "Conditionnels", "native_name": "条件形",
             "description": "Les 4 facons de dire 'si': たら, ば, と, なら. Nuances d'usage",
             "cards": 20, "required": True, "prereq": ["past_ja"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "passive_ja", "level": 3, "cefr": "B1",
             "name": "Passif", "native_name": "受身形",
             "description": "食べられる, 言われる. Passif direct, indirect (nuisance), honorifique",
             "cards": 20, "required": True, "prereq": ["potential_ja"],
             "estimated_hours": 7, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "causative_ja", "level": 3, "cefr": "B1",
             "name": "Causatif", "native_name": "使役形",
             "description": "食べさせる, 行かせる. Faire faire, laisser faire. Causatif-passif",
             "cards": 20, "required": True, "prereq": ["passive_ja"],
             "estimated_hours": 7, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "conjunctions_ja", "level": 3, "cefr": "B1",
             "name": "Conjonctions", "native_name": "接続詞",
             "description": "そして, でも, から, けど, ので, のに, ために, ように",
             "cards": 20, "required": True, "prereq": ["te_form_ja"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "keigo_intro_ja", "level": 3, "cefr": "B1",
             "name": "Keigo (introduction)", "native_name": "敬語（入門）",
             "description": "丁寧語 (poli standard), distinction ます/です, bases de la politesse japonaise",
             "cards": 20, "required": True, "prereq": ["masu_form_ja"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "vocab_thematic_ja", "level": 3, "cefr": "B1",
             "name": "Vocabulaire thematique", "native_name": "テーマ語彙",
             "description": "Travail, culture, actualites, technologie, nature (~500 mots N3)",
             "cards": 60, "required": True, "prereq": ["vocab_daily_ja"],
             "estimated_hours": 10, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            # === B2 - Avance (level 4) ===
            {"id": "keigo_advanced_ja", "level": 4, "cefr": "B2",
             "name": "Keigo avance", "native_name": "敬語（応用）",
             "description": "尊敬語 (respectueux: いらっしゃる, おっしゃる), 謙譲語 (humble: 参る, 申す)",
             "cards": 30, "required": True, "prereq": ["keigo_intro_ja"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "grammar_patterns_ja", "level": 4, "cefr": "B2",
             "name": "Patterns N3/N2", "native_name": "文法パターン",
             "description": "~ように, ~ために, ~ことにする, ~ことになる, ~はずだ, ~わけだ, ~べきだ",
             "cards": 30, "required": True, "prereq": ["conjunctions_ja"],
             "estimated_hours": 12, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "kanji_n3_ja", "level": 4, "cefr": "B2",
             "name": "Kanji N3", "native_name": "漢字N3",
             "description": "~370 kanji intermediaires pour lire articles et textes courants",
             "cards": 100, "required": True, "prereq": ["vocab_thematic_ja"],
             "estimated_hours": 40, "category": "writing", "exercise_types": []},

            {"id": "formal_writing_ja", "level": 4, "cefr": "B2",
             "name": "Ecriture formelle", "native_name": "フォーマルな文章",
             "description": "Emails, lettres, style ecrit formel (である体), locutions ecrites",
             "cards": 20, "required": True, "prereq": ["keigo_advanced_ja"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "idiomatic_ja", "level": 4, "cefr": "B2",
             "name": "Expressions idiomatiques", "native_name": "慣用句",
             "description": "猫の手も借りたい, 花より団子, 七転び八起き. Proverbes et expressions",
             "cards": 25, "required": True, "prereq": ["vocab_thematic_ja"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "connectors_ja", "level": 4, "cefr": "B2",
             "name": "Connecteurs du discours", "native_name": "談話の接続詞",
             "description": "つまり, 要するに, 一方, それにもかかわらず. Structurer un argument",
             "cards": 20, "required": True, "prereq": ["conjunctions_ja"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            # === C1 - Autonome (level 5) ===
            {"id": "grammar_mastery_ja", "level": 5, "cefr": "C1",
             "name": "Maitrise grammaticale N2", "native_name": "N2文法マスター",
             "description": "Patterns avances: ~ものなら, ~ないことはない, ~ずにはいられない, ~に違いない",
             "cards": 30, "required": True, "prereq": ["grammar_patterns_ja"],
             "estimated_hours": 15, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "kanji_n2_ja", "level": 5, "cefr": "C1",
             "name": "Kanji N2", "native_name": "漢字N2",
             "description": "~1000 kanji pour lire journaux, romans, documents professionnels",
             "cards": 200, "required": True, "prereq": ["kanji_n3_ja"],
             "estimated_hours": 80, "category": "writing", "exercise_types": []},

            {"id": "professional_writing_ja", "level": 5, "cefr": "C1",
             "name": "Ecriture professionnelle", "native_name": "ビジネス文書",
             "description": "Rapports, presentations, emails d'affaires, keigo professionnel",
             "cards": 20, "required": True, "prereq": ["formal_writing_ja"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "cultural_refs_ja", "level": 5, "cefr": "C1",
             "name": "References culturelles", "native_name": "文化的知識",
             "description": "Usages sociaux, expressions saisonnieres, references historiques et pop culture",
             "cards": 25, "required": True, "prereq": ["idiomatic_ja"],
             "estimated_hours": 8, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "literary_forms_ja", "level": 5, "cefr": "C1",
             "name": "Formes litteraires", "native_name": "文語表現",
             "description": "Style classique (古文 bases), formes litteraires, poesie (haiku/tanka)",
             "cards": 20, "required": True, "prereq": ["grammar_mastery_ja"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank"]},

            # === C2 - Maitrise (level 6) ===
            {"id": "dialectal_ja", "level": 6, "cefr": "C2",
             "name": "Conscience dialectale", "native_name": "方言意識",
             "description": "関西弁, 東北弁, 九州弁. Comprendre les variations regionales",
             "cards": 20, "required": True, "prereq": ["cultural_refs_ja"],
             "estimated_hours": 10, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "literary_analysis_ja", "level": 6, "cefr": "C2",
             "name": "Analyse litteraire", "native_name": "文学分析",
             "description": "Commentaire de texte, rhetorique japonaise, styles narratifs",
             "cards": 15, "required": True, "prereq": ["literary_forms_ja"],
             "estimated_hours": 12, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "translation_ja", "level": 6, "cefr": "C2",
             "name": "Traduction & Mediation", "native_name": "翻訳と仲介",
             "description": "Traduction FR/JP, resume, synthese, mediation interculturelle",
             "cards": 15, "required": True, "prereq": ["professional_writing_ja"],
             "estimated_hours": 12, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "native_fluency_ja", "level": 6, "cefr": "C2",
             "name": "Fluidite native", "native_name": "ネイティブ力",
             "description": "Automatismes, nuances, humour japonais, lecture implicite (空気を読む)",
             "cards": 15, "required": True, "prereq": ["grammar_mastery_ja"],
             "estimated_hours": 12, "category": "grammar", "exercise_types": ["fill_blank"]},
        ],

        "onboarding": ONBOARDING_LEVELS,
    },

    # =========================================================================
    # TURC (refonte complete A0-C2)
    # =========================================================================
    "tr": {
        "name": "Turc",
        "native_name": "Türkçe",
        "flag": "tr",
        "writing_system": "latin",
        "word_order": "SOV",
        "has_tones": False,
        "has_gender": False,
        "has_cases": True,
        "has_particles": False,
        "has_conjugation": True,
        "romanization": None,
        "difficulty": 3,

        "pillars": [
            # === A0 - Prerequis (level 0) ===
            {"id": "alphabet_tr", "level": 0, "cefr": "A0",
             "name": "Alphabet & Caracteres", "native_name": "Alfabe ve Özel Harfler",
             "description": "29 lettres dont ö, ü, ş, ç, ğ, ı. Differences avec le francais",
             "cards": 15, "required": True, "prereq": [],
             "estimated_hours": 2, "category": "writing", "exercise_types": []},

            {"id": "pronunciation_tr", "level": 0, "cefr": "A0",
             "name": "Prononciation", "native_name": "Telaffuz",
             "description": "Chaque lettre = un son. ğ muet, ı vs i, ö vs o, ü vs u",
             "cards": 15, "required": True, "prereq": ["alphabet_tr"],
             "estimated_hours": 3, "category": "phonetics", "exercise_types": []},

            # === A1 - Decouverte (level 1) ===
            {"id": "pronouns_tr", "level": 1, "cefr": "A1",
             "name": "Pronoms", "native_name": "Zamirler",
             "description": "ben, sen, o, biz, siz, onlar. Pronoms demonstratifs: bu/şu/o",
             "cards": 12, "required": True, "prereq": ["alphabet_tr"],
             "estimated_hours": 2, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "to_be_tr", "level": 1, "cefr": "A1",
             "name": "Etre (suffixes)", "native_name": "İsim Cümlesi",
             "description": "Pas de verbe 'etre'! Suffixes: -(y)im, -sin, -dir, -(y)iz, -siniz, -dirler",
             "cards": 15, "required": True, "prereq": ["pronouns_tr"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "negation_tr", "level": 1, "cefr": "A1",
             "name": "Negation & Questions", "native_name": "Olumsuzluk ve Sorular",
             "description": "değil (ne pas etre), -ma/-me (verbes). mı/mi/mu/mü? ne? nerede? nasıl? kim?",
             "cards": 15, "required": True, "prereq": ["to_be_tr"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "numbers_tr", "level": 1, "cefr": "A1",
             "name": "Nombres & Temps", "native_name": "Sayılar ve Zaman",
             "description": "1-1000, heures (Saat kaç?), jours, mois, dates",
             "cards": 25, "required": True, "prereq": ["alphabet_tr"],
             "estimated_hours": 3, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "present_continuous_tr", "level": 1, "cefr": "A1",
             "name": "Present continu", "native_name": "Şimdiki Zaman",
             "description": "-iyor/-ıyor/-uyor/-üyor. gidiyorum, yapıyorsun, geliyor",
             "cards": 25, "required": True, "prereq": ["negation_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "word_order_tr", "level": 1, "cefr": "A1",
             "name": "Ordre SOV", "native_name": "Söz Dizimi",
             "description": "Sujet-Objet-Verbe. Le verbe toujours a la fin. Adjectif avant le nom",
             "cards": 15, "required": True, "prereq": ["to_be_tr"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["word_order", "fill_blank"]},

            {"id": "vocab_basic_tr", "level": 1, "cefr": "A1",
             "name": "Vocabulaire fondamental", "native_name": "Temel Kelimeler",
             "description": "Aile, renkler, yiyecek, vücut, ev, hayvanlar (~200 mots essentiels)",
             "cards": 50, "required": True, "prereq": ["alphabet_tr"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank", "word_order"]},

            # === A2 - Survie (level 2) ===
            {"id": "vowel_harmony_tr", "level": 2, "cefr": "A2",
             "name": "Harmonie vocalique", "native_name": "Ünlü Uyumu",
             "description": "CLE du turc: voyelles claires (e,i,ö,ü) vs sombres (a,ı,o,u). Regit tous les suffixes",
             "cards": 25, "required": True, "prereq": ["present_continuous_tr"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank"]},

            {"id": "case_suffixes_tr", "level": 2, "cefr": "A2",
             "name": "Suffixes de cas", "native_name": "Hal Ekleri",
             "description": "Accusatif -(y)i, Datif -(y)e, Locatif -de, Ablatif -den, Genitif -(n)in",
             "cards": 30, "required": True, "prereq": ["vowel_harmony_tr"],
             "estimated_hours": 12, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "past_di_tr", "level": 2, "cefr": "A2",
             "name": "Passe defini -di", "native_name": "Geçmiş Zaman (-di)",
             "description": "-di/-dı/-du/-dü + suffixes personnels. Temoin direct du passe",
             "cards": 25, "required": True, "prereq": ["present_continuous_tr"],
             "estimated_hours": 7, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "past_mis_tr", "level": 2, "cefr": "A2",
             "name": "Passe rapporte -miş", "native_name": "Geçmiş Zaman (-miş)",
             "description": "-miş/-mış/-muş/-müş. Passe non-temoin, ouï-dire, decouverte. Specifique au turc!",
             "cards": 20, "required": True, "prereq": ["past_di_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "possessive_tr", "level": 2, "cefr": "A2",
             "name": "Possessifs", "native_name": "İyelik Ekleri",
             "description": "-(i)m, -(i)n, -(s)i, -(i)miz, -(i)niz, -leri. Constructions genitivales",
             "cards": 20, "required": True, "prereq": ["case_suffixes_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank"]},

            {"id": "comparatives_tr", "level": 2, "cefr": "A2",
             "name": "Comparatifs & Superlatifs", "native_name": "Karşılaştırma",
             "description": "daha (plus), en (le plus), kadar (autant que), -den daha",
             "cards": 15, "required": True, "prereq": ["case_suffixes_tr"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "postpositions_tr", "level": 2, "cefr": "A2",
             "name": "Postpositions", "native_name": "Son Takılar",
             "description": "için (pour), ile (avec), gibi (comme), kadar (jusqu'a). APRES le nom",
             "cards": 20, "required": True, "prereq": ["case_suffixes_tr"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "vocab_daily_tr", "level": 2, "cefr": "A2",
             "name": "Vocabulaire quotidien", "native_name": "Günlük Kelimeler",
             "description": "Shopping, transport, sante, directions, restaurant (~300 mots)",
             "cards": 50, "required": True, "prereq": ["vocab_basic_tr"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank", "word_order"]},

            # === B1 - Seuil (level 3) ===
            {"id": "future_tr", "level": 3, "cefr": "B1",
             "name": "Futur", "native_name": "Gelecek Zaman",
             "description": "-ecek/-acak + suffixes personnels. gideceğim, yapacaksın",
             "cards": 20, "required": True, "prereq": ["past_mis_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},

            {"id": "conditional_tr", "level": 3, "cefr": "B1",
             "name": "Conditionnel", "native_name": "Şart Kipi",
             "description": "-se/-sa. gitsem, yapsanız. Conditions reelles et irreelles",
             "cards": 20, "required": True, "prereq": ["future_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "aorist_tr", "level": 3, "cefr": "B1",
             "name": "Aoriste", "native_name": "Geniş Zaman",
             "description": "-r/-ar/-er/-ir. Habitudes, generalites, capacite. gelirim, yaparım",
             "cards": 25, "required": True, "prereq": ["present_continuous_tr"],
             "estimated_hours": 7, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},

            {"id": "relative_clauses_tr", "level": 3, "cefr": "B1",
             "name": "Propositions relatives", "native_name": "Sıfat Cümleleri",
             "description": "Participes en -en/-an, -dik/-dığı. Pas de pronom relatif en turc!",
             "cards": 20, "required": True, "prereq": ["past_di_tr"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "conjunctions_tr", "level": 3, "cefr": "B1",
             "name": "Conjonctions", "native_name": "Bağlaçlar",
             "description": "ve (et), ama/fakat (mais), çünkü (parce que), eğer (si), ya da (ou), hem...hem (et...et)",
             "cards": 15, "required": True, "prereq": ["conditional_tr"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "formal_register_tr", "level": 3, "cefr": "B1",
             "name": "Registre formel", "native_name": "Resmi Dil",
             "description": "Siz (vouvoiement), formules de politesse, style administratif",
             "cards": 15, "required": True, "prereq": ["aorist_tr"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "vocab_thematic_tr", "level": 3, "cefr": "B1",
             "name": "Vocabulaire thematique", "native_name": "Tematik Kelimeler",
             "description": "İş, kültür, teknoloji, doğa, politika (~500 mots)",
             "cards": 60, "required": True, "prereq": ["vocab_daily_tr"],
             "estimated_hours": 8, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            # === B2 - Avance (level 4) ===
            {"id": "passive_tr", "level": 4, "cefr": "B2",
             "name": "Passif", "native_name": "Edilgen Çatı",
             "description": "-il/-in/-ın/-un/-ül/-ün. yapılmak, görülmek, bilinmek",
             "cards": 20, "required": True, "prereq": ["aorist_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "causative_tr", "level": 4, "cefr": "B2",
             "name": "Causatif", "native_name": "Ettirgen Çatı",
             "description": "-dir/-t/-ir. yaptırmak, gezdirmek. Faire faire quelque chose",
             "cards": 20, "required": True, "prereq": ["passive_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "gerund_tr", "level": 4, "cefr": "B2",
             "name": "Gerondifs & Participes", "native_name": "Ortaçlar ve Ulaçlar",
             "description": "-erek, -ip, -ince, -meden, -dikten sonra. Connecter les actions",
             "cards": 25, "required": True, "prereq": ["relative_clauses_tr"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "hypothetical_tr", "level": 4, "cefr": "B2",
             "name": "Hypothese", "native_name": "Koşul ve Dilek",
             "description": "keşke (si seulement), -seydi (si c'etait), conditions irreelles",
             "cards": 15, "required": True, "prereq": ["conditional_tr"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "connectors_tr", "level": 4, "cefr": "B2",
             "name": "Connecteurs du discours", "native_name": "Söylem Bağlaçları",
             "description": "ancak, bununla birlikte, dolayısıyla, öte yandan, sonuç olarak",
             "cards": 20, "required": True, "prereq": ["conjunctions_tr"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},

            {"id": "idiomatic_tr", "level": 4, "cefr": "B2",
             "name": "Expressions idiomatiques", "native_name": "Deyimler",
             "description": "Ağzı açık kalmak, gözden düşmek, el ele vermek. Proverbes turcs",
             "cards": 25, "required": True, "prereq": ["vocab_thematic_tr"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            # === C1 - Autonome (level 5) ===
            {"id": "grammar_mastery_tr", "level": 5, "cefr": "C1",
             "name": "Maitrise grammaticale", "native_name": "Dilbilgisi Ustalığı",
             "description": "Agglutination complexe, nominalisation, suffixes multiples, style soutenu",
             "cards": 25, "required": True, "prereq": ["gerund_tr", "causative_tr"],
             "estimated_hours": 12, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "complex_structures_tr", "level": 5, "cefr": "C1",
             "name": "Structures complexes", "native_name": "Karmaşık Yapılar",
             "description": "Phrases a tiroirs, subordination multiple, style journalistique turc",
             "cards": 20, "required": True, "prereq": ["grammar_mastery_tr"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "professional_writing_tr", "level": 5, "cefr": "C1",
             "name": "Ecriture professionnelle", "native_name": "İş Yazışması",
             "description": "Emails formels, rapports, style administratif ottoman-turc moderne",
             "cards": 15, "required": True, "prereq": ["formal_register_tr", "connectors_tr"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "cultural_refs_tr", "level": 5, "cefr": "C1",
             "name": "References culturelles", "native_name": "Kültürel Referanslar",
             "description": "Proverbes, expressions regionales, traditions, references litteraires turques",
             "cards": 20, "required": True, "prereq": ["idiomatic_tr"],
             "estimated_hours": 6, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "literary_forms_tr", "level": 5, "cefr": "C1",
             "name": "Formes litteraires", "native_name": "Edebi Biçimler",
             "description": "Influence arabo-persane (osmanlıca), style litteraire contemporain",
             "cards": 15, "required": True, "prereq": ["grammar_mastery_tr"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank"]},

            # === C2 - Maitrise (level 6) ===
            {"id": "dialectal_tr", "level": 6, "cefr": "C2",
             "name": "Conscience dialectale", "native_name": "Ağız Farkındalığı",
             "description": "Variations regionales: İstanbul, Karadeniz, Güneydoğu, azéri/turkmène",
             "cards": 15, "required": True, "prereq": ["cultural_refs_tr"],
             "estimated_hours": 8, "category": "vocabulary", "exercise_types": ["fill_blank"]},

            {"id": "literary_analysis_tr", "level": 6, "cefr": "C2",
             "name": "Analyse litteraire", "native_name": "Edebi Analiz",
             "description": "Commentaire de texte, Nazım Hikmet a Orhan Pamuk, rhetorique turque",
             "cards": 15, "required": True, "prereq": ["literary_forms_tr"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},

            {"id": "native_fluency_tr", "level": 6, "cefr": "C2",
             "name": "Fluidite native", "native_name": "Ana Dil Düzeyi",
             "description": "Automatismes, humour turc, sous-entendus, registres multiples",
             "cards": 15, "required": True, "prereq": ["grammar_mastery_tr"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank"]},
        ],

        "onboarding": ONBOARDING_LEVELS,
    },

    # =========================================================================
    # CHINOIS MANDARIN (structure existante + cefr/exercise_types)
    # =========================================================================
    "zh": {
        "name": "Chinois Mandarin",
        "native_name": "中文",
        "flag": "cn",
        "writing_system": "hanzi",
        "word_order": "SVO",
        "has_tones": True,
        "has_gender": False,
        "has_cases": False,
        "has_particles": False,
        "has_conjugation": False,
        "romanization": "pinyin",
        "difficulty": 5,

        "pillars": [
            {"id": "pinyin_zh", "level": 0, "cefr": "A0", "name": "Pinyin", "native_name": "拼音",
             "description": "Le systeme de romanisation du chinois",
             "cards": 60, "required": True, "prereq": [],
             "estimated_hours": 8, "category": "phonetics", "exercise_types": []},
            {"id": "tones_zh", "level": 0, "cefr": "A0", "name": "Les 4 tons", "native_name": "四声",
             "description": "mā má mǎ mà - les tons qui changent le sens",
             "cards": 20, "required": True, "prereq": ["pinyin_zh"],
             "estimated_hours": 10, "category": "phonetics", "exercise_types": []},
            {"id": "radicals_zh", "level": 0, "cefr": "A0", "name": "Radicaux", "native_name": "部首",
             "description": "Les 50 radicaux les plus frequents",
             "cards": 50, "required": False, "prereq": ["tones_zh"],
             "estimated_hours": 15, "category": "writing", "exercise_types": []},
            {"id": "hanzi_hsk1", "level": 0, "cefr": "A0", "name": "Caracteres HSK1", "native_name": "汉字",
             "description": "Les 150 caracteres de base",
             "cards": 150, "required": True, "prereq": ["tones_zh"],
             "estimated_hours": 50, "category": "writing", "exercise_types": []},
            {"id": "pronouns_zh", "level": 1, "cefr": "A1", "name": "Pronoms", "native_name": "代词",
             "description": "我, 你, 他/她/它, 我们, 你们, 他们",
             "cards": 10, "required": True, "prereq": ["pinyin_zh"],
             "estimated_hours": 2, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "shi_zh", "level": 1, "cefr": "A1", "name": "是 (etre)", "native_name": "是",
             "description": "我是学生 - l'equivalent de 'etre'",
             "cards": 12, "required": True, "prereq": ["pronouns_zh"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "you_zh", "level": 1, "cefr": "A1", "name": "有 (avoir)", "native_name": "有",
             "description": "我有书 - possession et existence",
             "cards": 12, "required": True, "prereq": ["shi_zh"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "negation_zh", "level": 1, "cefr": "A1", "name": "Negation", "native_name": "否定",
             "description": "不 (general) et 没 (passe/有)",
             "cards": 15, "required": True, "prereq": ["you_zh"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "questions_zh", "level": 1, "cefr": "A1", "name": "Questions", "native_name": "疑问句",
             "description": "吗, 什么, 哪里, 怎么 - poser des questions",
             "cards": 15, "required": True, "prereq": ["negation_zh"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "word_order_zh", "level": 2, "cefr": "A1", "name": "Ordre SVO", "native_name": "语序",
             "description": "Structure de base Sujet-Verbe-Objet",
             "cards": 20, "required": True, "prereq": ["questions_zh"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["word_order", "fill_blank"]},
            {"id": "classifiers_zh", "level": 2, "cefr": "A2", "name": "Classificateurs", "native_name": "量词",
             "description": "个, 本, 张, 只... un par type d'objet",
             "cards": 25, "required": True, "prereq": ["word_order_zh"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "numbers_zh", "level": 2, "cefr": "A1", "name": "Nombres", "native_name": "数字",
             "description": "一 à 万 et au-dela",
             "cards": 30, "required": True, "prereq": ["classifiers_zh"],
             "estimated_hours": 5, "category": "vocabulary", "exercise_types": ["fill_blank"]},
            {"id": "verbs_essential_zh", "level": 3, "cefr": "A2", "name": "Verbes essentiels", "native_name": "常用动词",
             "description": "做, 去, 来, 想, 要, 能, 会... les 50 verbes cles",
             "cards": 50, "required": True, "prereq": ["word_order_zh"],
             "estimated_hours": 15, "category": "vocabulary", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "aspect_le_zh", "level": 4, "cefr": "A2", "name": "Aspect 了", "native_name": "了",
             "description": "了 - action accomplie",
             "cards": 20, "required": True, "prereq": ["verbs_essential_zh"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "aspect_guo_zh", "level": 4, "cefr": "A2", "name": "Aspect 过", "native_name": "过",
             "description": "过 - experience passee",
             "cards": 15, "required": True, "prereq": ["aspect_le_zh"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "future_zh", "level": 4, "cefr": "B1", "name": "Futur", "native_name": "将来",
             "description": "会, 要, 将 - parler du futur",
             "cards": 15, "required": True, "prereq": ["aspect_guo_zh"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "progressive_zh", "level": 4, "cefr": "B1", "name": "Progressif", "native_name": "进行",
             "description": "在...着 - action en cours",
             "cards": 15, "required": False, "prereq": ["future_zh"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "conjunctions_zh", "level": 5, "cefr": "B1", "name": "Conjonctions", "native_name": "连词",
             "description": "和, 或者, 但是, 因为, 所以",
             "cards": 15, "required": True, "prereq": ["future_zh"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "complements_zh", "level": 5, "cefr": "B1", "name": "Complements", "native_name": "补语",
             "description": "得 (resultat), complements directionnels",
             "cards": 20, "required": False, "prereq": ["conjunctions_zh"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank"]},
        ],

        "onboarding": ONBOARDING_LEVELS,
    },

    # =========================================================================
    # COREEN (structure existante + cefr/exercise_types)
    # =========================================================================
    "ko": {
        "name": "Coreen",
        "native_name": "한국어",
        "flag": "kr",
        "writing_system": "hangul",
        "word_order": "SOV",
        "has_tones": False,
        "has_gender": False,
        "has_cases": False,
        "has_particles": True,
        "has_conjugation": True,
        "romanization": "romanization",
        "difficulty": 4,

        "pillars": [
            {"id": "hangul_ko", "level": 0, "cefr": "A0", "name": "Hangul", "native_name": "한글",
             "description": "L'alphabet coreen - 24 lettres en blocs syllabiques",
             "cards": 40, "required": True, "prereq": [],
             "estimated_hours": 8, "category": "writing", "exercise_types": []},
            {"id": "syllables_ko", "level": 0, "cefr": "A0", "name": "Blocs syllabiques", "native_name": "음절",
             "description": "가, 나, 다... combiner les lettres",
             "cards": 50, "required": True, "prereq": ["hangul_ko"],
             "estimated_hours": 10, "category": "writing", "exercise_types": []},
            {"id": "pronunciation_ko", "level": 0, "cefr": "A0", "name": "Prononciation", "native_name": "발음",
             "description": "Liaisons et regles de prononciation",
             "cards": 25, "required": False, "prereq": ["syllables_ko"],
             "estimated_hours": 6, "category": "phonetics", "exercise_types": []},
            {"id": "pronouns_ko", "level": 1, "cefr": "A1", "name": "Pronoms", "native_name": "대명사",
             "description": "나/저, 너/당신, 그/그녀, 우리, 그들",
             "cards": 12, "required": True, "prereq": ["hangul_ko"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "copula_ko", "level": 1, "cefr": "A1", "name": "Copule 이다", "native_name": "이다",
             "description": "~입니다, ~이에요/예요 - etre",
             "cards": 15, "required": True, "prereq": ["pronouns_ko"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "existence_ko", "level": 1, "cefr": "A1", "name": "있다/없다", "native_name": "있다/없다",
             "description": "Avoir / etre (existence)",
             "cards": 12, "required": True, "prereq": ["copula_ko"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "negation_ko", "level": 1, "cefr": "A1", "name": "Negation", "native_name": "부정",
             "description": "안 + verbe, -지 않다",
             "cards": 12, "required": True, "prereq": ["existence_ko"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "questions_ko", "level": 1, "cefr": "A1", "name": "Questions", "native_name": "의문문",
             "description": "-까?, -어요? + 뭐, 어디, 언제",
             "cards": 15, "required": True, "prereq": ["negation_ko"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "word_order_ko", "level": 2, "cefr": "A1", "name": "Ordre SOV", "native_name": "어순",
             "description": "Sujet-Objet-Verbe comme en japonais",
             "cards": 20, "required": True, "prereq": ["questions_ko"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["word_order", "fill_blank"]},
            {"id": "particles_ko", "level": 2, "cefr": "A1", "name": "Particules", "native_name": "조사",
             "description": "은/는, 이/가, 을/를 - marqueurs grammaticaux",
             "cards": 20, "required": True, "prereq": ["word_order_ko"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["particles", "fill_blank"]},
            {"id": "particles_location_ko", "level": 2, "cefr": "A2", "name": "Particules de lieu", "native_name": "장소 조사",
             "description": "에 (lieu), 에서 (action), (으)로 (direction)",
             "cards": 15, "required": True, "prereq": ["particles_ko"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["particles", "fill_blank"]},
            {"id": "politeness_ko", "level": 2, "cefr": "A2", "name": "Niveaux de politesse", "native_name": "존댓말",
             "description": "존댓말 vs 반말 - les 2-3 niveaux essentiels",
             "cards": 20, "required": True, "prereq": ["particles_ko"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "verbs_essential_ko", "level": 3, "cefr": "A2", "name": "Verbes essentiels", "native_name": "기본 동사",
             "description": "하다, 가다, 오다, 먹다, 보다... les 40 verbes cles",
             "cards": 40, "required": True, "prereq": ["word_order_ko"],
             "estimated_hours": 12, "category": "vocabulary", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "present_ko", "level": 4, "cefr": "A2", "name": "Present poli", "native_name": "현재형",
             "description": "-아요/-어요/-해요",
             "cards": 25, "required": True, "prereq": ["verbs_essential_ko"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "past_ko", "level": 4, "cefr": "A2", "name": "Passe", "native_name": "과거형",
             "description": "-았어요/-었어요",
             "cards": 20, "required": True, "prereq": ["present_ko"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},
            {"id": "future_ko", "level": 4, "cefr": "B1", "name": "Futur", "native_name": "미래형",
             "description": "-ㄹ 거예요",
             "cards": 15, "required": True, "prereq": ["past_ko"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "go_form_ko", "level": 4, "cefr": "B1", "name": "Forme -고", "native_name": "-고",
             "description": "Connexion (et)",
             "cards": 15, "required": False, "prereq": ["future_ko"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "conjunctions_ko", "level": 5, "cefr": "B1", "name": "Conjonctions", "native_name": "접속사",
             "description": "그리고, 하지만, 왜냐하면",
             "cards": 15, "required": True, "prereq": ["future_ko"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "connectors_ko", "level": 5, "cefr": "B1", "name": "Connecteurs verbaux", "native_name": "연결어미",
             "description": "-고, -서, -면 dans le verbe",
             "cards": 20, "required": False, "prereq": ["conjunctions_ko"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
        ],

        "onboarding": ONBOARDING_LEVELS,
    },

    # =========================================================================
    # RUSSE (structure existante + cefr/exercise_types)
    # =========================================================================
    "ru": {
        "name": "Russe",
        "native_name": "Русский",
        "flag": "ru",
        "writing_system": "cyrillic",
        "word_order": "SVO",
        "has_tones": False,
        "has_gender": True,
        "has_cases": True,
        "has_particles": False,
        "has_conjugation": True,
        "romanization": "romanization",
        "difficulty": 4,

        "pillars": [
            {"id": "cyrillic_ru", "level": 0, "cefr": "A0", "name": "Alphabet cyrillique", "native_name": "Кириллица",
             "description": "Les 33 lettres de l'alphabet russe",
             "cards": 33, "required": True, "prereq": [],
             "estimated_hours": 10, "category": "writing", "exercise_types": []},
            {"id": "pronunciation_ru", "level": 0, "cefr": "A0", "name": "Prononciation", "native_name": "Произношение",
             "description": "Reduction vocalique, palatalisation",
             "cards": 25, "required": True, "prereq": ["cyrillic_ru"],
             "estimated_hours": 8, "category": "phonetics", "exercise_types": []},
            {"id": "pronouns_ru", "level": 1, "cefr": "A1", "name": "Pronoms", "native_name": "Местоимения",
             "description": "я, ты, он/она/оно, мы, вы, они",
             "cards": 12, "required": True, "prereq": ["cyrillic_ru"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "to_be_ru", "level": 1, "cefr": "A1", "name": "Verbe 'etre'", "native_name": "Быть",
             "description": "Omis au present ! Я студент = Je (suis) etudiant",
             "cards": 10, "required": True, "prereq": ["pronouns_ru"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "to_have_ru", "level": 1, "cefr": "A1", "name": "Avoir (У меня есть)", "native_name": "У меня есть",
             "description": "'Avoir' n'existe pas - on dit 'chez moi il y a'",
             "cards": 12, "required": True, "prereq": ["to_be_ru"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "negation_ru", "level": 1, "cefr": "A1", "name": "Negation", "native_name": "Отрицание",
             "description": "не + verbe, нет pour 'il n'y a pas'",
             "cards": 12, "required": True, "prereq": ["to_have_ru"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "questions_ru", "level": 1, "cefr": "A1", "name": "Questions", "native_name": "Вопросы",
             "description": "Intonation + Что? Где? Как? Когда?",
             "cards": 15, "required": True, "prereq": ["negation_ru"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "gender_ru", "level": 2, "cefr": "A1", "name": "Genre", "native_name": "Род",
             "description": "Masculin (-∅), Feminin (-а/-я), Neutre (-о/-е)",
             "cards": 25, "required": True, "prereq": ["questions_ru"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["gender", "fill_blank"]},
            {"id": "nominative_accusative_ru", "level": 2, "cefr": "A2", "name": "Cas: Nominatif/Accusatif", "native_name": "Им./Вин. падеж",
             "description": "Sujet (qui?) vs COD (quoi?)",
             "cards": 30, "required": True, "prereq": ["gender_ru"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "genitive_ru", "level": 2, "cefr": "A2", "name": "Cas: Genitif", "native_name": "Родительный падеж",
             "description": "Possession, negation, quantite - le plus frequent!",
             "cards": 30, "required": True, "prereq": ["nominative_accusative_ru"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "other_cases_ru", "level": 2, "cefr": "A2", "name": "Autres cas", "native_name": "Другие падежи",
             "description": "Datif, Instrumental, Prepositionnel",
             "cards": 40, "required": False, "prereq": ["genitive_ru"],
             "estimated_hours": 15, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "verbs_essential_ru", "level": 3, "cefr": "A2", "name": "Verbes essentiels", "native_name": "Основные глаголы",
             "description": "быть, делать, идти, говорить... les 50 verbes cles",
             "cards": 50, "required": True, "prereq": ["nominative_accusative_ru"],
             "estimated_hours": 15, "category": "vocabulary", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "present_ru", "level": 4, "cefr": "A2", "name": "Present", "native_name": "Настоящее время",
             "description": "Conjugaison 1ere/2eme",
             "cards": 30, "required": True, "prereq": ["verbs_essential_ru"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "past_ru", "level": 4, "cefr": "A2", "name": "Passe", "native_name": "Прошедшее время",
             "description": "Genre au passe! он делал, она делала",
             "cards": 25, "required": True, "prereq": ["present_ru"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},
            {"id": "future_ru", "level": 4, "cefr": "B1", "name": "Futur", "native_name": "Будущее время",
             "description": "быть + infinitif ou perfectif",
             "cards": 20, "required": True, "prereq": ["past_ru"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "aspects_ru", "level": 4, "cefr": "B1", "name": "Aspects", "native_name": "Вид глагола",
             "description": "Imperfectif vs Perfectif - CLE du russe",
             "cards": 30, "required": True, "prereq": ["future_ru"],
             "estimated_hours": 15, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "conjunctions_ru", "level": 5, "cefr": "B1", "name": "Conjonctions", "native_name": "Союзы",
             "description": "и, но, потому что, если",
             "cards": 15, "required": True, "prereq": ["aspects_ru"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "prepositions_cases_ru", "level": 5, "cefr": "B1", "name": "Prepositions + Cas", "native_name": "Предлоги",
             "description": "в + accusatif/prepositionnel, на, etc.",
             "cards": 25, "required": False, "prereq": ["conjunctions_ru"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["fill_blank"]},
        ],

        "onboarding": ONBOARDING_LEVELS,
    },

    # =========================================================================
    # ESPAGNOL (structure existante + cefr/exercise_types)
    # =========================================================================
    "es": {
        "name": "Espagnol",
        "native_name": "Español",
        "flag": "es",
        "writing_system": "latin",
        "word_order": "SVO",
        "has_tones": False,
        "has_gender": True,
        "has_cases": False,
        "has_particles": False,
        "has_conjugation": True,
        "romanization": None,
        "difficulty": 2,

        "pillars": [
            {"id": "pronunciation_es", "level": 0, "cefr": "A0", "name": "Prononciation", "native_name": "Pronunciación",
             "description": "ñ, ll, rr, accent tonique",
             "cards": 15, "required": False, "prereq": [],
             "estimated_hours": 3, "category": "phonetics", "exercise_types": []},
            {"id": "pronouns_es", "level": 1, "cefr": "A1", "name": "Pronoms", "native_name": "Pronombres",
             "description": "yo, tú, él/ella, nosotros, vosotros, ellos",
             "cards": 12, "required": True, "prereq": [],
             "estimated_hours": 2, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "ser_estar_es", "level": 1, "cefr": "A1", "name": "Ser vs Estar", "native_name": "Ser y Estar",
             "description": "Deux verbes 'etre'! Permanent vs temporaire",
             "cards": 25, "required": True, "prereq": ["pronouns_es"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "haber_tener_es", "level": 1, "cefr": "A1", "name": "Haber vs Tener", "native_name": "Haber y Tener",
             "description": "Haber (auxiliaire) vs Tener (possession)",
             "cards": 20, "required": True, "prereq": ["ser_estar_es"],
             "estimated_hours": 5, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "negation_es", "level": 1, "cefr": "A1", "name": "Negation", "native_name": "Negación",
             "description": "no + verbe - simple!",
             "cards": 10, "required": True, "prereq": ["haber_tener_es"],
             "estimated_hours": 2, "category": "grammar", "exercise_types": ["fill_blank", "transform"]},
            {"id": "questions_es", "level": 1, "cefr": "A1", "name": "Questions", "native_name": "Preguntas",
             "description": "¿Qué? ¿Dónde? ¿Cómo? ¿Cuándo?",
             "cards": 15, "required": True, "prereq": ["negation_es"],
             "estimated_hours": 3, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "articles_es", "level": 2, "cefr": "A1", "name": "Articles", "native_name": "Artículos",
             "description": "el/la/los/las, un/una/unos/unas",
             "cards": 15, "required": True, "prereq": ["questions_es"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["gender", "fill_blank"]},
            {"id": "gender_number_es", "level": 2, "cefr": "A1", "name": "Accord genre/nombre", "native_name": "Concordancia",
             "description": "-o/-a, -os/-as - les adjectifs s'accordent",
             "cards": 25, "required": True, "prereq": ["articles_es"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["gender", "fill_blank"]},
            {"id": "word_order_es", "level": 2, "cefr": "A1", "name": "Ordre SVO", "native_name": "Orden de palabras",
             "description": "Flexible mais SVO de base",
             "cards": 15, "required": True, "prereq": ["gender_number_es"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["word_order", "fill_blank"]},
            {"id": "verbs_essential_es", "level": 3, "cefr": "A1", "name": "Verbes essentiels", "native_name": "Verbos esenciales",
             "description": "hacer, ir, venir, querer, poder... les 50 verbes cles",
             "cards": 50, "required": True, "prereq": ["word_order_es"],
             "estimated_hours": 15, "category": "vocabulary", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "present_es", "level": 4, "cefr": "A1", "name": "Present", "native_name": "Presente",
             "description": "-ar/-er/-ir conjugaisons, 6 personnes",
             "cards": 40, "required": True, "prereq": ["verbs_essential_es"],
             "estimated_hours": 12, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "past_perfect_es", "level": 4, "cefr": "A2", "name": "Passe compose", "native_name": "Pretérito perfecto",
             "description": "he/has/ha + participio",
             "cards": 25, "required": True, "prereq": ["present_es"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},
            {"id": "imperfect_es", "level": 4, "cefr": "A2", "name": "Imparfait", "native_name": "Imperfecto",
             "description": "-aba/-ía - habitudes passees",
             "cards": 25, "required": True, "prereq": ["past_perfect_es"],
             "estimated_hours": 8, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},
            {"id": "future_es", "level": 4, "cefr": "B1", "name": "Futur", "native_name": "Futuro",
             "description": "-é/-ás/-á",
             "cards": 20, "required": True, "prereq": ["imperfect_es"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["conjugation", "fill_blank"]},
            {"id": "conjunctions_es", "level": 5, "cefr": "B1", "name": "Conjonctions", "native_name": "Conjunciones",
             "description": "y, o, pero, porque, aunque",
             "cards": 15, "required": True, "prereq": ["future_es"],
             "estimated_hours": 4, "category": "grammar", "exercise_types": ["fill_blank", "word_order"]},
            {"id": "prepositions_es", "level": 5, "cefr": "A2", "name": "Prepositions", "native_name": "Preposiciones",
             "description": "a, de, en, con, para vs por",
             "cards": 20, "required": True, "prereq": ["conjunctions_es"],
             "estimated_hours": 6, "category": "grammar", "exercise_types": ["fill_blank"]},
            {"id": "subjunctive_intro_es", "level": 5, "cefr": "B1", "name": "Subjonctif (intro)", "native_name": "Subjuntivo",
             "description": "Quiero que... - introduction au subjonctif",
             "cards": 25, "required": False, "prereq": ["prepositions_es"],
             "estimated_hours": 10, "category": "grammar", "exercise_types": ["conjugation", "fill_blank", "transform"]},
        ],

        "onboarding": ONBOARDING_LEVELS,
    },
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_language(code):
    """Get language config by code."""
    return LANGUAGES.get(code)


def get_language_name(code):
    """Get display name for a language."""
    lang = LANGUAGES.get(code)
    return lang['name'] if lang else code


def get_language_flag(code):
    """Get flag code for a language."""
    lang = LANGUAGES.get(code)
    return lang['flag'] if lang else code


def get_pillars_for_language(code):
    """Get all pillars for a language."""
    lang = LANGUAGES.get(code)
    return lang['pillars'] if lang else []


def get_pillar(language_code, pillar_id):
    """Get a specific pillar config."""
    pillars = get_pillars_for_language(language_code)
    for p in pillars:
        if p['id'] == pillar_id:
            return p
    return None


def get_pillars_by_level(language_code, level):
    """Get all pillars for a specific level."""
    pillars = get_pillars_for_language(language_code)
    return [p for p in pillars if p['level'] == level]


def get_pillars_by_cefr(language_code, cefr_level):
    """Get all pillars for a specific CEFR level."""
    pillars = get_pillars_for_language(language_code)
    return [p for p in pillars if p.get('cefr') == cefr_level]


def get_required_pillars(language_code):
    """Get all required pillars for a language."""
    pillars = get_pillars_for_language(language_code)
    return [p for p in pillars if p.get('required', False)]


def get_pillar_prereqs(language_code, pillar_id):
    """Get prerequisites for a pillar."""
    pillar = get_pillar(language_code, pillar_id)
    return pillar.get('prereq', []) if pillar else []


def check_pillar_available(language_code, pillar_id, completed_pillars):
    """Check if a pillar is available (all prereqs completed)."""
    prereqs = get_pillar_prereqs(language_code, pillar_id)
    return all(p in completed_pillars for p in prereqs)


def get_onboarding_questions(language_code):
    """Get onboarding levels for a language (CEFR level picker)."""
    lang = LANGUAGES.get(language_code)
    if not lang:
        return ONBOARDING_LEVELS
    onb = lang.get('onboarding', ONBOARDING_LEVELS)
    # Support both old format (list of question dicts) and new format (ONBOARDING_LEVELS)
    return onb


def get_cefr_for_pillar(language_code, pillar_id):
    """Get the CEFR level of a specific pillar."""
    pillar = get_pillar(language_code, pillar_id)
    return pillar.get('cefr', 'A0') if pillar else 'A0'


def estimate_total_hours(language_code):
    """Estimate total hours to complete all required pillars."""
    pillars = get_required_pillars(language_code)
    return sum(p.get('estimated_hours', 5) for p in pillars)


def get_all_languages_summary():
    """Get a summary of all supported languages."""
    return [
        {
            'code': code,
            'name': lang['name'],
            'native_name': lang['native_name'],
            'flag': lang['flag'],
            'difficulty': lang['difficulty'],
            'pillar_count': len(lang['pillars']),
            'estimated_hours': estimate_total_hours(code)
        }
        for code, lang in LANGUAGES.items()
    ]
