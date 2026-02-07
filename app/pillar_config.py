"""
Configuration des langues et piliers fondamentaux.

Chaque langue a:
- Metadata (nom, drapeau, caracteristiques linguistiques)
- Piliers organises par niveau (0-5)
- Questions d'onboarding pour evaluer le niveau initial

Niveaux:
- 0: Prerequis (ecriture, phonetique)
- 1: Briques fondamentales (pronoms, etre/avoir, negation)
- 2: Structure de phrase (ordre, articles, accord)
- 3: Verbes essentiels (top 30-50)
- 4: Temps verbaux (present, passe, futur)
- 5: Phrases complexes (conjonctions, comparaison)
"""

# Liste des codes de langue supportes
SUPPORTED_LANGUAGES = ['ja', 'zh', 'ko', 'ru', 'tr', 'es', 'it']

# Niveaux CECRL
CECRL_LEVELS = ['A0', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2']

# Statuts de pilier
PILLAR_STATUS = ['locked', 'available', 'in_progress', 'completed']

LANGUAGES = {
    # =========================================================================
    # JAPONAIS
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
        "difficulty": 5,  # 1-5 scale
        
        "pillars": [
            # Niveau 0 - Ecriture
            {"id": "hiragana", "level": 0, "name": "Hiragana", "native_name": "ひらがな",
             "description": "Les 46 caracteres de base pour ecrire les mots japonais",
             "cards": 46, "required": True, "prereq": [],
             "estimated_hours": 10, "category": "writing"},
            
            {"id": "katakana", "level": 0, "name": "Katakana", "native_name": "カタカナ",
             "description": "Les 46 caracteres pour les mots etrangers et onomatopees",
             "cards": 46, "required": True, "prereq": ["hiragana"],
             "estimated_hours": 10, "category": "writing"},
            
            {"id": "kanji_n5", "level": 0, "name": "Kanji N5", "native_name": "漢字",
             "description": "Les 100 kanji essentiels du niveau N5",
             "cards": 100, "required": False, "prereq": ["hiragana", "katakana"],
             "estimated_hours": 40, "category": "writing"},
            
            # Niveau 1 - Fondamentaux
            {"id": "pronouns_ja", "level": 1, "name": "Pronoms", "native_name": "代名詞",
             "description": "私, あなた, 彼, 彼女, etc.",
             "cards": 12, "required": True, "prereq": ["hiragana"],
             "estimated_hours": 2, "category": "grammar"},
            
            {"id": "copula_ja", "level": 1, "name": "Copule です/だ", "native_name": "です・だ",
             "description": "L'equivalent de 'etre' en japonais",
             "cards": 8, "required": True, "prereq": ["pronouns_ja"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "particles_basic_ja", "level": 1, "name": "Particules de base", "native_name": "助詞",
             "description": "は, が, を, に, で - les marqueurs grammaticaux essentiels",
             "cards": 15, "required": True, "prereq": ["copula_ja"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "negation_ja", "level": 1, "name": "Negation", "native_name": "否定形",
             "description": "ません, ない - comment dire 'ne pas'",
             "cards": 10, "required": True, "prereq": ["copula_ja"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "questions_ja", "level": 1, "name": "Questions", "native_name": "疑問文",
             "description": "か, 何, どこ, いつ, だれ - poser des questions",
             "cards": 12, "required": True, "prereq": ["particles_basic_ja"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 2 - Structure
            {"id": "word_order_ja", "level": 2, "name": "Ordre SOV", "native_name": "語順",
             "description": "Sujet-Objet-Verbe: la structure de base",
             "cards": 20, "required": True, "prereq": ["questions_ja"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "particles_location_ja", "level": 2, "name": "Particules de lieu", "native_name": "場所の助詞",
             "description": "に (destination), で (lieu d'action), へ (direction)",
             "cards": 15, "required": True, "prereq": ["word_order_ja"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "counters_ja", "level": 2, "name": "Compteurs", "native_name": "助数詞",
             "description": "つ, 人, 枚, 本, 匹 - compter differents objets",
             "cards": 20, "required": False, "prereq": ["particles_location_ja"],
             "estimated_hours": 6, "category": "grammar"},
            
            # Niveau 3 - Verbes
            {"id": "verbs_essential_ja", "level": 3, "name": "Verbes essentiels", "native_name": "基本動詞",
             "description": "する, いる, ある, 行く, 来る... les 40 verbes les plus utiles",
             "cards": 40, "required": True, "prereq": ["word_order_ja"],
             "estimated_hours": 15, "category": "vocabulary"},
            
            # Niveau 4 - Temps
            {"id": "masu_form_ja", "level": 4, "name": "Forme polie -ます", "native_name": "ます形",
             "description": "食べます, 飲みます - la forme polie standard",
             "cards": 25, "required": True, "prereq": ["verbs_essential_ja"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "past_ja", "level": 4, "name": "Passe -ました", "native_name": "過去形",
             "description": "食べました - parler du passe",
             "cards": 20, "required": True, "prereq": ["masu_form_ja"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "te_form_ja", "level": 4, "name": "Forme en て", "native_name": "て形",
             "description": "食べて - la forme pivot pour connecter et demander",
             "cards": 25, "required": True, "prereq": ["past_ja"],
             "estimated_hours": 10, "category": "grammar"},
            
            {"id": "tai_form_ja", "level": 4, "name": "Forme -たい", "native_name": "たい形",
             "description": "食べたい - exprimer le desir",
             "cards": 15, "required": False, "prereq": ["te_form_ja"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 5 - Complexe
            {"id": "conjunctions_ja", "level": 5, "name": "Conjonctions", "native_name": "接続詞",
             "description": "そして, でも, から, けど - connecter les phrases",
             "cards": 15, "required": True, "prereq": ["te_form_ja"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "conditionals_ja", "level": 5, "name": "Conditionnels", "native_name": "条件形",
             "description": "たら, ば, と, なら - les 4 facons de dire 'si'",
             "cards": 20, "required": False, "prereq": ["conjunctions_ja"],
             "estimated_hours": 10, "category": "grammar"},
        ],
        
        "onboarding": [
            {"pillar": "hiragana", "question": "Tu connais les Hiragana (あいうえお) ?",
             "options": ["Non, je pars de zero", "Un peu, pas tous", "Oui, je les connais"]},
            {"pillar": "katakana", "question": "Et les Katakana (アイウエオ) ?",
             "options": ["Non", "Un peu", "Oui"]},
            {"pillar": "particles_basic_ja", "question": "Tu connais les particules は, が, を ?",
             "options": ["Non, c'est quoi ?", "J'en ai entendu parler", "Oui, je les utilise"]},
        ]
    },
    
    # =========================================================================
    # CHINOIS MANDARIN
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
            # Niveau 0 - Phonetique et Ecriture
            {"id": "pinyin_zh", "level": 0, "name": "Pinyin", "native_name": "拼音",
             "description": "Le systeme de romanisation du chinois",
             "cards": 60, "required": True, "prereq": [],
             "estimated_hours": 8, "category": "phonetics"},
            
            {"id": "tones_zh", "level": 0, "name": "Les 4 tons", "native_name": "四声",
             "description": "mā má mǎ mà - les tons qui changent le sens",
             "cards": 20, "required": True, "prereq": ["pinyin_zh"],
             "estimated_hours": 10, "category": "phonetics"},
            
            {"id": "radicals_zh", "level": 0, "name": "Radicaux", "native_name": "部首",
             "description": "Les 50 radicaux les plus frequents",
             "cards": 50, "required": False, "prereq": ["tones_zh"],
             "estimated_hours": 15, "category": "writing"},
            
            {"id": "hanzi_hsk1", "level": 0, "name": "Caracteres HSK1", "native_name": "汉字",
             "description": "Les 150 caracteres de base",
             "cards": 150, "required": True, "prereq": ["tones_zh"],
             "estimated_hours": 50, "category": "writing"},
            
            # Niveau 1 - Fondamentaux
            {"id": "pronouns_zh", "level": 1, "name": "Pronoms", "native_name": "代词",
             "description": "我, 你, 他/她/它, 我们, 你们, 他们",
             "cards": 10, "required": True, "prereq": ["pinyin_zh"],
             "estimated_hours": 2, "category": "grammar"},
            
            {"id": "shi_zh", "level": 1, "name": "是 (etre)", "native_name": "是",
             "description": "我是学生 - l'equivalent de 'etre'",
             "cards": 12, "required": True, "prereq": ["pronouns_zh"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "you_zh", "level": 1, "name": "有 (avoir)", "native_name": "有",
             "description": "我有书 - possession et existence",
             "cards": 12, "required": True, "prereq": ["shi_zh"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "negation_zh", "level": 1, "name": "Negation", "native_name": "否定",
             "description": "不 (general) et 没 (passe/有)",
             "cards": 15, "required": True, "prereq": ["you_zh"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "questions_zh", "level": 1, "name": "Questions", "native_name": "疑问句",
             "description": "吗, 什么, 哪里, 怎么 - poser des questions",
             "cards": 15, "required": True, "prereq": ["negation_zh"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 2 - Structure
            {"id": "word_order_zh", "level": 2, "name": "Ordre SVO", "native_name": "语序",
             "description": "Structure de base Sujet-Verbe-Objet",
             "cards": 20, "required": True, "prereq": ["questions_zh"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "classifiers_zh", "level": 2, "name": "Classificateurs", "native_name": "量词",
             "description": "个, 本, 张, 只... un par type d'objet",
             "cards": 25, "required": True, "prereq": ["word_order_zh"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "numbers_zh", "level": 2, "name": "Nombres", "native_name": "数字",
             "description": "一 à 万 et au-dela",
             "cards": 30, "required": True, "prereq": ["classifiers_zh"],
             "estimated_hours": 5, "category": "vocabulary"},
            
            # Niveau 3 - Verbes
            {"id": "verbs_essential_zh", "level": 3, "name": "Verbes essentiels", "native_name": "常用动词",
             "description": "做, 去, 来, 想, 要, 能, 会... les 50 verbes cles",
             "cards": 50, "required": True, "prereq": ["word_order_zh"],
             "estimated_hours": 15, "category": "vocabulary"},
            
            # Niveau 4 - Aspects
            {"id": "aspect_le_zh", "level": 4, "name": "Aspect 了", "native_name": "了",
             "description": "了 - action accomplie",
             "cards": 20, "required": True, "prereq": ["verbs_essential_zh"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "aspect_guo_zh", "level": 4, "name": "Aspect 过", "native_name": "过",
             "description": "过 - experience passee",
             "cards": 15, "required": True, "prereq": ["aspect_le_zh"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "future_zh", "level": 4, "name": "Futur", "native_name": "将来",
             "description": "会, 要, 将 - parler du futur",
             "cards": 15, "required": True, "prereq": ["aspect_guo_zh"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "progressive_zh", "level": 4, "name": "Progressif", "native_name": "进行",
             "description": "在...着 - action en cours",
             "cards": 15, "required": False, "prereq": ["future_zh"],
             "estimated_hours": 5, "category": "grammar"},
            
            # Niveau 5 - Complexe
            {"id": "conjunctions_zh", "level": 5, "name": "Conjonctions", "native_name": "连词",
             "description": "和, 或者, 但是, 因为, 所以",
             "cards": 15, "required": True, "prereq": ["future_zh"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "complements_zh", "level": 5, "name": "Complements", "native_name": "补语",
             "description": "得 (resultat), complements directionnels",
             "cards": 20, "required": False, "prereq": ["conjunctions_zh"],
             "estimated_hours": 10, "category": "grammar"},
        ],
        
        "onboarding": [
            {"pillar": "pinyin_zh", "question": "Tu connais le Pinyin (romanisation) ?",
             "options": ["Non, c'est quoi ?", "Un peu", "Oui"]},
            {"pillar": "tones_zh", "question": "Tu sais differencier les 4 tons ?",
             "options": ["Non", "J'ai du mal", "Oui"]},
            {"pillar": "hanzi_hsk1", "question": "Tu connais des caracteres chinois ?",
             "options": ["Non, aucun", "Quelques-uns (<50)", "Oui, beaucoup"]},
        ]
    },
    
    # =========================================================================
    # COREEN
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
            # Niveau 0 - Ecriture
            {"id": "hangul_ko", "level": 0, "name": "Hangul", "native_name": "한글",
             "description": "L'alphabet coreen - 24 lettres en blocs syllabiques",
             "cards": 40, "required": True, "prereq": [],
             "estimated_hours": 8, "category": "writing"},
            
            {"id": "syllables_ko", "level": 0, "name": "Blocs syllabiques", "native_name": "음절",
             "description": "가, 나, 다... combiner les lettres",
             "cards": 50, "required": True, "prereq": ["hangul_ko"],
             "estimated_hours": 10, "category": "writing"},
            
            {"id": "pronunciation_ko", "level": 0, "name": "Prononciation", "native_name": "발음",
             "description": "Liaisons et regles de prononciation",
             "cards": 25, "required": False, "prereq": ["syllables_ko"],
             "estimated_hours": 6, "category": "phonetics"},
            
            # Niveau 1 - Fondamentaux
            {"id": "pronouns_ko", "level": 1, "name": "Pronoms", "native_name": "대명사",
             "description": "나/저, 너/당신, 그/그녀, 우리, 그들",
             "cards": 12, "required": True, "prereq": ["hangul_ko"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "copula_ko", "level": 1, "name": "Copule 이다", "native_name": "이다",
             "description": "~입니다, ~이에요/예요 - etre",
             "cards": 15, "required": True, "prereq": ["pronouns_ko"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "existence_ko", "level": 1, "name": "있다/없다", "native_name": "있다/없다",
             "description": "Avoir / etre (existence)",
             "cards": 12, "required": True, "prereq": ["copula_ko"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "negation_ko", "level": 1, "name": "Negation", "native_name": "부정",
             "description": "안 + verbe, -지 않다",
             "cards": 12, "required": True, "prereq": ["existence_ko"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "questions_ko", "level": 1, "name": "Questions", "native_name": "의문문",
             "description": "-까?, -어요? + 뭐, 어디, 언제",
             "cards": 15, "required": True, "prereq": ["negation_ko"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 2 - Structure
            {"id": "word_order_ko", "level": 2, "name": "Ordre SOV", "native_name": "어순",
             "description": "Sujet-Objet-Verbe comme en japonais",
             "cards": 20, "required": True, "prereq": ["questions_ko"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "particles_ko", "level": 2, "name": "Particules", "native_name": "조사",
             "description": "은/는, 이/가, 을/를 - marqueurs grammaticaux",
             "cards": 20, "required": True, "prereq": ["word_order_ko"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "particles_location_ko", "level": 2, "name": "Particules de lieu", "native_name": "장소 조사",
             "description": "에 (lieu), 에서 (action), (으)로 (direction)",
             "cards": 15, "required": True, "prereq": ["particles_ko"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "politeness_ko", "level": 2, "name": "Niveaux de politesse", "native_name": "존댓말",
             "description": "존댓말 vs 반말 - les 2-3 niveaux essentiels",
             "cards": 20, "required": True, "prereq": ["particles_ko"],
             "estimated_hours": 8, "category": "grammar"},
            
            # Niveau 3 - Verbes
            {"id": "verbs_essential_ko", "level": 3, "name": "Verbes essentiels", "native_name": "기본 동사",
             "description": "하다, 가다, 오다, 먹다, 보다... les 40 verbes cles",
             "cards": 40, "required": True, "prereq": ["word_order_ko"],
             "estimated_hours": 12, "category": "vocabulary"},
            
            # Niveau 4 - Temps
            {"id": "present_ko", "level": 4, "name": "Present poli", "native_name": "현재형",
             "description": "-아요/-어요/-해요",
             "cards": 25, "required": True, "prereq": ["verbs_essential_ko"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "past_ko", "level": 4, "name": "Passe", "native_name": "과거형",
             "description": "-았어요/-었어요",
             "cards": 20, "required": True, "prereq": ["present_ko"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "future_ko", "level": 4, "name": "Futur", "native_name": "미래형",
             "description": "-ㄹ 거예요",
             "cards": 15, "required": True, "prereq": ["past_ko"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "go_form_ko", "level": 4, "name": "Forme -고", "native_name": "-고",
             "description": "Connexion (et)",
             "cards": 15, "required": False, "prereq": ["future_ko"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 5 - Complexe
            {"id": "conjunctions_ko", "level": 5, "name": "Conjonctions", "native_name": "접속사",
             "description": "그리고, 하지만, 왜냐하면",
             "cards": 15, "required": True, "prereq": ["future_ko"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "connectors_ko", "level": 5, "name": "Connecteurs verbaux", "native_name": "연결어미",
             "description": "-고, -서, -면 dans le verbe",
             "cards": 20, "required": False, "prereq": ["conjunctions_ko"],
             "estimated_hours": 8, "category": "grammar"},
        ],
        
        "onboarding": [
            {"pillar": "hangul_ko", "question": "Tu connais le Hangul (ㄱㄴㄷ) ?",
             "options": ["Non, je pars de zero", "Un peu", "Oui, je sais lire"]},
            {"pillar": "particles_ko", "question": "Tu connais les particules 은/는, 이/가 ?",
             "options": ["Non", "Vaguement", "Oui"]},
        ]
    },
    
    # =========================================================================
    # RUSSE
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
            # Niveau 0 - Ecriture
            {"id": "cyrillic_ru", "level": 0, "name": "Alphabet cyrillique", "native_name": "Кириллица",
             "description": "Les 33 lettres de l'alphabet russe",
             "cards": 33, "required": True, "prereq": [],
             "estimated_hours": 10, "category": "writing"},
            
            {"id": "pronunciation_ru", "level": 0, "name": "Prononciation", "native_name": "Произношение",
             "description": "Reduction vocalique, palatalisation",
             "cards": 25, "required": True, "prereq": ["cyrillic_ru"],
             "estimated_hours": 8, "category": "phonetics"},
            
            # Niveau 1 - Fondamentaux
            {"id": "pronouns_ru", "level": 1, "name": "Pronoms", "native_name": "Местоимения",
             "description": "я, ты, он/она/оно, мы, вы, они",
             "cards": 12, "required": True, "prereq": ["cyrillic_ru"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "to_be_ru", "level": 1, "name": "Verbe 'etre'", "native_name": "Быть",
             "description": "Omis au present ! Я студент = Je (suis) etudiant",
             "cards": 10, "required": True, "prereq": ["pronouns_ru"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "to_have_ru", "level": 1, "name": "Avoir (У меня есть)", "native_name": "У меня есть",
             "description": "'Avoir' n'existe pas - on dit 'chez moi il y a'",
             "cards": 12, "required": True, "prereq": ["to_be_ru"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "negation_ru", "level": 1, "name": "Negation", "native_name": "Отрицание",
             "description": "не + verbe, нет pour 'il n'y a pas'",
             "cards": 12, "required": True, "prereq": ["to_have_ru"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "questions_ru", "level": 1, "name": "Questions", "native_name": "Вопросы",
             "description": "Intonation + Что? Где? Как? Когда?",
             "cards": 15, "required": True, "prereq": ["negation_ru"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 2 - Structure (CAS!)
            {"id": "gender_ru", "level": 2, "name": "Genre", "native_name": "Род",
             "description": "Masculin (-∅), Feminin (-а/-я), Neutre (-о/-е)",
             "cards": 25, "required": True, "prereq": ["questions_ru"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "nominative_accusative_ru", "level": 2, "name": "Cas: Nominatif/Accusatif", "native_name": "Им./Вин. падеж",
             "description": "Sujet (qui?) vs COD (quoi?)",
             "cards": 30, "required": True, "prereq": ["gender_ru"],
             "estimated_hours": 10, "category": "grammar"},
            
            {"id": "genitive_ru", "level": 2, "name": "Cas: Genitif", "native_name": "Родительный падеж",
             "description": "Possession, negation, quantite - le plus frequent!",
             "cards": 30, "required": True, "prereq": ["nominative_accusative_ru"],
             "estimated_hours": 10, "category": "grammar"},
            
            {"id": "other_cases_ru", "level": 2, "name": "Autres cas", "native_name": "Другие падежи",
             "description": "Datif, Instrumental, Prepositionnel",
             "cards": 40, "required": False, "prereq": ["genitive_ru"],
             "estimated_hours": 15, "category": "grammar"},
            
            # Niveau 3 - Verbes
            {"id": "verbs_essential_ru", "level": 3, "name": "Verbes essentiels", "native_name": "Основные глаголы",
             "description": "быть, делать, идти, говорить... les 50 verbes cles",
             "cards": 50, "required": True, "prereq": ["nominative_accusative_ru"],
             "estimated_hours": 15, "category": "vocabulary"},
            
            # Niveau 4 - Temps et Aspects
            {"id": "present_ru", "level": 4, "name": "Present", "native_name": "Настоящее время",
             "description": "Conjugaison 1ere/2eme",
             "cards": 30, "required": True, "prereq": ["verbs_essential_ru"],
             "estimated_hours": 10, "category": "grammar"},
            
            {"id": "past_ru", "level": 4, "name": "Passe", "native_name": "Прошедшее время",
             "description": "Genre au passe! он делал, она делала",
             "cards": 25, "required": True, "prereq": ["present_ru"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "future_ru", "level": 4, "name": "Futur", "native_name": "Будущее время",
             "description": "быть + infinitif ou perfectif",
             "cards": 20, "required": True, "prereq": ["past_ru"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "aspects_ru", "level": 4, "name": "Aspects", "native_name": "Вид глагола",
             "description": "Imperfectif vs Perfectif - CLE du russe",
             "cards": 30, "required": True, "prereq": ["future_ru"],
             "estimated_hours": 15, "category": "grammar"},
            
            # Niveau 5 - Complexe
            {"id": "conjunctions_ru", "level": 5, "name": "Conjonctions", "native_name": "Союзы",
             "description": "и, но, потому что, если",
             "cards": 15, "required": True, "prereq": ["aspects_ru"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "prepositions_cases_ru", "level": 5, "name": "Prepositions + Cas", "native_name": "Предлоги",
             "description": "в + accusatif/prepositionnel, на, etc.",
             "cards": 25, "required": False, "prereq": ["conjunctions_ru"],
             "estimated_hours": 10, "category": "grammar"},
        ],
        
        "onboarding": [
            {"pillar": "cyrillic_ru", "question": "Tu connais l'alphabet cyrillique (А Б В Г) ?",
             "options": ["Non, pas du tout", "Quelques lettres", "Oui, je sais lire"]},
            {"pillar": "gender_ru", "question": "Tu connais les genres en russe (masculin/feminin/neutre) ?",
             "options": ["Non", "Vaguement", "Oui"]},
            {"pillar": "nominative_accusative_ru", "question": "Tu connais le systeme des cas ?",
             "options": ["Non, c'est quoi ?", "J'en ai entendu parler", "Oui"]},
        ]
    },
    
    # =========================================================================
    # TURC
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
            # Niveau 0 - Phonetique
            {"id": "special_chars_tr", "level": 0, "name": "Caracteres speciaux", "native_name": "Özel harfler",
             "description": "ö, ü, ş, ç, ğ, ı - les sons specifiques au turc",
             "cards": 12, "required": True, "prereq": [],
             "estimated_hours": 2, "category": "phonetics"},
            
            # Niveau 1 - Fondamentaux
            {"id": "pronouns_tr", "level": 1, "name": "Pronoms", "native_name": "Zamirler",
             "description": "ben, sen, o, biz, siz, onlar",
             "cards": 10, "required": True, "prereq": [],
             "estimated_hours": 2, "category": "grammar"},
            
            {"id": "to_be_tr", "level": 1, "name": "Etre (suffixes)", "native_name": "İsim cümlesi",
             "description": "-im, -sin, -dir - pas de verbe 'etre' separe!",
             "cards": 15, "required": True, "prereq": ["pronouns_tr"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "negation_tr", "level": 1, "name": "Negation", "native_name": "Olumsuzluk",
             "description": "değil, -ma/-me",
             "cards": 12, "required": True, "prereq": ["to_be_tr"],
             "estimated_hours": 3, "category": "grammar"},
            
            {"id": "questions_tr", "level": 1, "name": "Questions", "native_name": "Sorular",
             "description": "mi/mı/mu/mü - la particule interrogative",
             "cards": 15, "required": True, "prereq": ["negation_tr"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 2 - Structure
            {"id": "word_order_tr", "level": 2, "name": "Ordre SOV", "native_name": "Söz dizimi",
             "description": "Sujet-Objet-Verbe - verbe toujours a la fin",
             "cards": 20, "required": True, "prereq": ["questions_tr"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "vowel_harmony_tr", "level": 2, "name": "Harmonie vocalique", "native_name": "Ünlü uyumu",
             "description": "Voyelles claires (e,i,ö,ü) vs sombres (a,ı,o,u) - CLE du turc",
             "cards": 25, "required": True, "prereq": ["word_order_tr"],
             "estimated_hours": 10, "category": "grammar"},
            
            {"id": "case_suffixes_tr", "level": 2, "name": "Suffixes de cas", "native_name": "Hal ekleri",
             "description": "-i (accusatif), -e (datif), -de (locatif), -den (ablatif)",
             "cards": 30, "required": True, "prereq": ["vowel_harmony_tr"],
             "estimated_hours": 12, "category": "grammar"},
            
            {"id": "possessive_tr", "level": 2, "name": "Possessifs", "native_name": "İyelik ekleri",
             "description": "-m, -n, -si - les suffixes possessifs",
             "cards": 20, "required": True, "prereq": ["case_suffixes_tr"],
             "estimated_hours": 6, "category": "grammar"},
            
            # Niveau 3 - Verbes
            {"id": "verbs_essential_tr", "level": 3, "name": "Verbes essentiels", "native_name": "Temel fiiller",
             "description": "gitmek, gelmek, yapmak, almak... les 40 verbes cles",
             "cards": 40, "required": True, "prereq": ["word_order_tr"],
             "estimated_hours": 12, "category": "vocabulary"},
            
            # Niveau 4 - Temps
            {"id": "present_continuous_tr", "level": 4, "name": "Present continu", "native_name": "Şimdiki zaman",
             "description": "-iyor - action en cours",
             "cards": 25, "required": True, "prereq": ["verbs_essential_tr"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "past_di_tr", "level": 4, "name": "Passe -di", "native_name": "Geçmiş zaman (-di)",
             "description": "-di/-dı/-du/-dü - passe defini",
             "cards": 25, "required": True, "prereq": ["present_continuous_tr"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "future_tr", "level": 4, "name": "Futur", "native_name": "Gelecek zaman",
             "description": "-ecek/-acak",
             "cards": 20, "required": True, "prereq": ["past_di_tr"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "aorist_tr", "level": 4, "name": "Aoriste", "native_name": "Geniş zaman",
             "description": "-r/-ar/-er - habitudes et generalites",
             "cards": 25, "required": False, "prereq": ["future_tr"],
             "estimated_hours": 8, "category": "grammar"},
            
            # Niveau 5 - Complexe
            {"id": "conjunctions_tr", "level": 5, "name": "Conjonctions", "native_name": "Bağlaçlar",
             "description": "ve, ama, çünkü, eğer",
             "cards": 15, "required": True, "prereq": ["future_tr"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "postpositions_tr", "level": 5, "name": "Postpositions", "native_name": "Son takılar",
             "description": "için, ile, gibi, kadar - APRES le nom",
             "cards": 20, "required": False, "prereq": ["conjunctions_tr"],
             "estimated_hours": 6, "category": "grammar"},
        ],
        
        "onboarding": [
            {"pillar": "special_chars_tr", "question": "Tu connais les lettres turques speciales (ş, ğ, ı) ?",
             "options": ["Non", "Un peu", "Oui"]},
            {"pillar": "vowel_harmony_tr", "question": "Tu connais l'harmonie vocalique ?",
             "options": ["Non, c'est quoi ?", "J'en ai entendu parler", "Oui"]},
        ]
    },
    
    # =========================================================================
    # ESPAGNOL
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
            # Niveau 0 - Skip (latin) mais quelques sons
            {"id": "pronunciation_es", "level": 0, "name": "Prononciation", "native_name": "Pronunciación",
             "description": "ñ, ll, rr, accent tonique",
             "cards": 15, "required": False, "prereq": [],
             "estimated_hours": 3, "category": "phonetics"},
            
            # Niveau 1 - Fondamentaux
            {"id": "pronouns_es", "level": 1, "name": "Pronoms", "native_name": "Pronombres",
             "description": "yo, tú, él/ella, nosotros, vosotros, ellos",
             "cards": 12, "required": True, "prereq": [],
             "estimated_hours": 2, "category": "grammar"},
            
            {"id": "ser_estar_es", "level": 1, "name": "Ser vs Estar", "native_name": "Ser y Estar",
             "description": "Deux verbes 'etre'! Permanent vs temporaire",
             "cards": 25, "required": True, "prereq": ["pronouns_es"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "haber_tener_es", "level": 1, "name": "Haber vs Tener", "native_name": "Haber y Tener",
             "description": "Haber (auxiliaire) vs Tener (possession)",
             "cards": 20, "required": True, "prereq": ["ser_estar_es"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "negation_es", "level": 1, "name": "Negation", "native_name": "Negación",
             "description": "no + verbe - simple!",
             "cards": 10, "required": True, "prereq": ["haber_tener_es"],
             "estimated_hours": 2, "category": "grammar"},
            
            {"id": "questions_es", "level": 1, "name": "Questions", "native_name": "Preguntas",
             "description": "¿Qué? ¿Dónde? ¿Cómo? ¿Cuándo?",
             "cards": 15, "required": True, "prereq": ["negation_es"],
             "estimated_hours": 3, "category": "grammar"},
            
            # Niveau 2 - Structure
            {"id": "articles_es", "level": 2, "name": "Articles", "native_name": "Artículos",
             "description": "el/la/los/las, un/una/unos/unas",
             "cards": 15, "required": True, "prereq": ["questions_es"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "gender_number_es", "level": 2, "name": "Accord genre/nombre", "native_name": "Concordancia",
             "description": "-o/-a, -os/-as - les adjectifs s'accordent",
             "cards": 25, "required": True, "prereq": ["articles_es"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "word_order_es", "level": 2, "name": "Ordre SVO", "native_name": "Orden de palabras",
             "description": "Flexible mais SVO de base",
             "cards": 15, "required": True, "prereq": ["gender_number_es"],
             "estimated_hours": 4, "category": "grammar"},
            
            # Niveau 3 - Verbes
            {"id": "verbs_essential_es", "level": 3, "name": "Verbes essentiels", "native_name": "Verbos esenciales",
             "description": "hacer, ir, venir, querer, poder... les 50 verbes cles",
             "cards": 50, "required": True, "prereq": ["word_order_es"],
             "estimated_hours": 15, "category": "vocabulary"},
            
            # Niveau 4 - Temps
            {"id": "present_es", "level": 4, "name": "Present", "native_name": "Presente",
             "description": "-ar/-er/-ir conjugaisons, 6 personnes",
             "cards": 40, "required": True, "prereq": ["verbs_essential_es"],
             "estimated_hours": 12, "category": "grammar"},
            
            {"id": "past_perfect_es", "level": 4, "name": "Passe compose", "native_name": "Pretérito perfecto",
             "description": "he/has/ha + participio",
             "cards": 25, "required": True, "prereq": ["present_es"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "imperfect_es", "level": 4, "name": "Imparfait", "native_name": "Imperfecto",
             "description": "-aba/-ía - habitudes passees",
             "cards": 25, "required": True, "prereq": ["past_perfect_es"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "future_es", "level": 4, "name": "Futur", "native_name": "Futuro",
             "description": "-é/-ás/-á",
             "cards": 20, "required": True, "prereq": ["imperfect_es"],
             "estimated_hours": 6, "category": "grammar"},
            
            # Niveau 5 - Complexe
            {"id": "conjunctions_es", "level": 5, "name": "Conjonctions", "native_name": "Conjunciones",
             "description": "y, o, pero, porque, aunque",
             "cards": 15, "required": True, "prereq": ["future_es"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "prepositions_es", "level": 5, "name": "Prepositions", "native_name": "Preposiciones",
             "description": "a, de, en, con, para vs por",
             "cards": 20, "required": True, "prereq": ["conjunctions_es"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "subjunctive_intro_es", "level": 5, "name": "Subjonctif (intro)", "native_name": "Subjuntivo",
             "description": "Quiero que... - introduction au subjonctif",
             "cards": 25, "required": False, "prereq": ["prepositions_es"],
             "estimated_hours": 10, "category": "grammar"},
        ],
        
        "onboarding": [
            {"pillar": "ser_estar_es", "question": "Tu connais la difference entre 'ser' et 'estar' ?",
             "options": ["Non, c'est quoi ?", "Un peu", "Oui"]},
            {"pillar": "present_es", "question": "Tu sais conjuguer au present (-ar, -er, -ir) ?",
             "options": ["Non", "Un peu", "Oui"]},
        ]
    },
    
    # =========================================================================
    # ITALIEN
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
            # Niveau 0 - Phonetique
            {"id": "pronunciation_it", "level": 0, "name": "Prononciation", "native_name": "Pronuncia",
             "description": "Doubles consonnes, accent, c/g + voyelles",
             "cards": 15, "required": False, "prereq": [],
             "estimated_hours": 3, "category": "phonetics"},
            
            # Niveau 1 - Fondamentaux
            {"id": "pronouns_it", "level": 1, "name": "Pronoms", "native_name": "Pronomi",
             "description": "io, tu, lui/lei, noi, voi, loro - Lei = vous formel",
             "cards": 12, "required": True, "prereq": [],
             "estimated_hours": 2, "category": "grammar"},
            
            {"id": "essere_stare_it", "level": 1, "name": "Essere vs Stare", "native_name": "Essere e Stare",
             "description": "Similaire a l'espagnol mais moins marque",
             "cards": 20, "required": True, "prereq": ["pronouns_it"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "avere_it", "level": 1, "name": "Avere", "native_name": "Avere",
             "description": "ho, hai, ha, abbiamo, avete, hanno",
             "cards": 15, "required": True, "prereq": ["essere_stare_it"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "negation_it", "level": 1, "name": "Negation", "native_name": "Negazione",
             "description": "non + verbe",
             "cards": 10, "required": True, "prereq": ["avere_it"],
             "estimated_hours": 2, "category": "grammar"},
            
            {"id": "questions_it", "level": 1, "name": "Questions", "native_name": "Domande",
             "description": "Che? Dove? Come? Quando? Perché?",
             "cards": 15, "required": True, "prereq": ["negation_it"],
             "estimated_hours": 3, "category": "grammar"},
            
            # Niveau 2 - Structure
            {"id": "articles_it", "level": 2, "name": "Articles", "native_name": "Articoli",
             "description": "il/lo/la/i/gli/le, un/uno/una - lo devant s+consonne, z",
             "cards": 20, "required": True, "prereq": ["questions_it"],
             "estimated_hours": 5, "category": "grammar"},
            
            {"id": "contracted_articles_it", "level": 2, "name": "Articles contractes", "native_name": "Preposizioni articolate",
             "description": "di+il=del, a+la=alla, in+il=nel - TRES frequent",
             "cards": 30, "required": True, "prereq": ["articles_it"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "gender_number_it", "level": 2, "name": "Accord", "native_name": "Concordanza",
             "description": "-o/-a/-i/-e",
             "cards": 25, "required": True, "prereq": ["contracted_articles_it"],
             "estimated_hours": 6, "category": "grammar"},
            
            # Niveau 3 - Verbes
            {"id": "verbs_essential_it", "level": 3, "name": "Verbes essentiels", "native_name": "Verbi essenziali",
             "description": "fare, andare, venire, volere... les 50 verbes cles",
             "cards": 50, "required": True, "prereq": ["gender_number_it"],
             "estimated_hours": 15, "category": "vocabulary"},
            
            # Niveau 4 - Temps
            {"id": "present_it", "level": 4, "name": "Present", "native_name": "Presente",
             "description": "-are/-ere/-ire conjugaisons",
             "cards": 40, "required": True, "prereq": ["verbs_essential_it"],
             "estimated_hours": 12, "category": "grammar"},
            
            {"id": "passato_prossimo_it", "level": 4, "name": "Passe compose", "native_name": "Passato prossimo",
             "description": "essere/avere + participio - CHOIX auxiliaire!",
             "cards": 30, "required": True, "prereq": ["present_it"],
             "estimated_hours": 10, "category": "grammar"},
            
            {"id": "imperfetto_it", "level": 4, "name": "Imparfait", "native_name": "Imperfetto",
             "description": "-avo/-evo/-ivo",
             "cards": 25, "required": True, "prereq": ["passato_prossimo_it"],
             "estimated_hours": 8, "category": "grammar"},
            
            {"id": "future_it", "level": 4, "name": "Futur", "native_name": "Futuro",
             "description": "-ò/-ai/-à",
             "cards": 20, "required": True, "prereq": ["imperfetto_it"],
             "estimated_hours": 6, "category": "grammar"},
            
            # Niveau 5 - Complexe
            {"id": "conjunctions_it", "level": 5, "name": "Conjonctions", "native_name": "Congiunzioni",
             "description": "e, o, ma, perché, se",
             "cards": 15, "required": True, "prereq": ["future_it"],
             "estimated_hours": 4, "category": "grammar"},
            
            {"id": "prepositions_it", "level": 5, "name": "Prepositions", "native_name": "Preposizioni",
             "description": "di, a, da, in, con, su, per, tra",
             "cards": 20, "required": True, "prereq": ["conjunctions_it"],
             "estimated_hours": 6, "category": "grammar"},
            
            {"id": "pronouns_object_it", "level": 5, "name": "Pronoms COD/COI", "native_name": "Pronomi diretti/indiretti",
             "description": "lo, la, li, le, mi, ti, ci, vi",
             "cards": 25, "required": False, "prereq": ["prepositions_it"],
             "estimated_hours": 8, "category": "grammar"},
        ],
        
        "onboarding": [
            {"pillar": "essere_stare_it", "question": "Tu connais la difference entre 'essere' et 'stare' ?",
             "options": ["Non", "Un peu", "Oui"]},
            {"pillar": "contracted_articles_it", "question": "Tu connais les articles contractes (del, alla, nel) ?",
             "options": ["Non", "Un peu", "Oui"]},
        ]
    },
}


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
    """Get onboarding questions for a language."""
    lang = LANGUAGES.get(language_code)
    return lang.get('onboarding', []) if lang else []


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
