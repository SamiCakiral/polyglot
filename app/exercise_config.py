"""
Configuration des exercices piliers: verbes irreguliers factorises,
types d'exercices par langue, pronoms par langue.
"""

# Types d'exercices
EXERCISE_TYPES = [
    ('conjugation', 'Conjugaison', 'Grille 6 pronoms + temps'),
    ('fill_blank', 'Phrases a trous', 'Completer avec la bonne forme'),
    ('transform', 'Transformation', 'Negation, question, temps'),
    ('word_order', 'Ordre des mots', 'Remettre les mots dans l\'ordre'),
    ('particles', 'Particules', 'Choisir la bonne particule'),
    ('gender', 'Genre et articles', 'Accord et determinants'),
]

# Pronoms par langue (pour grille conjugaison)
PRONOUNS_BY_LANG = {
    'it': ['io', 'tu', 'lui/lei', 'noi', 'voi', 'loro'],
    'es': ['yo', 'tú', 'él/ella/usted', 'nosotros', 'vosotros', 'ellos/ellas/ustedes'],
    'fr': ['je', 'tu', 'il/elle', 'nous', 'vous', 'ils/elles'],
    'de': ['ich', 'du', 'er/sie/es', 'wir', 'ihr', 'sie/Sie'],
    'ru': ['я', 'ты', 'он/она/оно', 'мы', 'вы', 'они'],
    'pt': ['eu', 'tu', 'ele/ela', 'nós', 'vós', 'eles/elas'],
    'ja': ['私', 'あなた', '彼/彼女', '私たち', 'あなたたち', '彼ら'],
    'zh': ['我', '你', '他/她', '我们', '你们', '他们'],
    'ko': ['나', '너', '그/그녀', '우리', '너희', '그들'],
    'tr': ['ben', 'sen', 'o', 'biz', 'siz', 'onlar'],
}

# Verbes irreguliers factorises par langue (top 30 familles)
# Chaque entree: verbe principal -> famille (derivees) + sens
IRREGULAR_VERBS = {
    'it': {
        'essere': {'family': ['essere'], 'meaning': 'etre'},
        'avere': {'family': ['avere'], 'meaning': 'avoir'},
        'andare': {'family': ['andare'], 'meaning': 'aller'},
        'fare': {'family': ['fare', 'rifare', 'disfare', 'soddisfare'], 'meaning': 'faire'},
        'dare': {'family': ['dare', 'ridare'], 'meaning': 'donner'},
        'stare': {'family': ['stare', 'ristare'], 'meaning': 'rester'},
        'sapere': {'family': ['sapere'], 'meaning': 'savoir'},
        'volere': {'family': ['volere'], 'meaning': 'vouloir'},
        'potere': {'family': ['potere'], 'meaning': 'pouvoir'},
        'dovere': {'family': ['dovere'], 'meaning': 'devoir'},
        'venire': {'family': ['venire', 'avvenire', 'convenire', 'prevenire'], 'meaning': 'venir'},
        'tenere': {'family': ['tenere', 'sostenere', 'ottenere', 'mantenere', 'contenere'], 'meaning': 'tenir'},
        'uscire': {'family': ['uscire'], 'meaning': 'sortir'},
        'dire': {'family': ['dire', 'ridire', 'contraddire', 'predire'], 'meaning': 'dire'},
        'bere': {'family': ['bere'], 'meaning': 'boire'},
        'porre': {'family': ['porre', 'comporre', 'disporre', 'proporre'], 'meaning': 'poser'},
        'tradurre': {'family': ['tradurre'], 'meaning': 'traduire'},
        'produrre': {'family': ['produrre', 'ridurre', 'condurre', 'introdurre'], 'meaning': 'produire'},
        'morire': {'family': ['morire'], 'meaning': 'mourir'},
        'rimanere': {'family': ['rimanere'], 'meaning': 'rester'},
        'scegliere': {'family': ['scegliere', 'raccogliere'], 'meaning': 'choisir'},
        'sedere': {'family': ['sedere', 'assistere'], 'meaning': 's\'asseoir'},
        'correre': {'family': ['correre', 'scorrere', 'percorrere'], 'meaning': 'courir'},
        'cuocere': {'family': ['cuocere'], 'meaning': 'cuire'},
        'piacere': {'family': ['piacere', 'dispiacere'], 'meaning': 'plaire'},
        'salire': {'family': ['salire', 'risalire'], 'meaning': 'monter'},
        'aprire': {'family': ['aprire', 'coprire', 'scoprire', 'offrire'], 'meaning': 'ouvrir'},
        'scrivere': {'family': ['scrivere', 'descrivere', 'iscrivere'], 'meaning': 'ecrire'},
        'vivere': {'family': ['vivere', 'sopravvivere'], 'meaning': 'vivre'},
        'vedere': {'family': ['vedere', 'rivedere', 'prevedere'], 'meaning': 'voir'},
    },
    'es': {
        'ser': {'family': ['ser'], 'meaning': 'etre (essence)'},
        'estar': {'family': ['estar'], 'meaning': 'etre (etat)'},
        'haber': {'family': ['haber'], 'meaning': 'avoir (auxiliaire)'},
        'tener': {'family': ['tener', 'mantener', 'obtener', 'contener'], 'meaning': 'tenir'},
        'ir': {'family': ['ir'], 'meaning': 'aller'},
        'hacer': {'family': ['hacer', 'rehacer', 'deshacer'], 'meaning': 'faire'},
        'decir': {'family': ['decir', 'contradecir', 'predecir'], 'meaning': 'dire'},
        'poder': {'family': ['poder'], 'meaning': 'pouvoir'},
        'querer': {'family': ['querer'], 'meaning': 'vouloir'},
        'venir': {'family': ['venir', 'convenir', 'prevenir'], 'meaning': 'venir'},
        'saber': {'family': ['saber'], 'meaning': 'savoir'},
        'conocer': {'family': ['conocer', 'reconocer'], 'meaning': 'connaitre'},
        'dar': {'family': ['dar'], 'meaning': 'donner'},
        'ver': {'family': ['ver', 'prever'], 'meaning': 'voir'},
        'poner': {'family': ['poner', 'componer', 'disponer', 'proponer'], 'meaning': 'poser'},
        'salir': {'family': ['salir'], 'meaning': 'sortir'},
        'traer': {'family': ['traer'], 'meaning': 'apporter'},
        'oir': {'family': ['oir'], 'meaning': 'entendre'},
        'caer': {'family': ['caer'], 'meaning': 'tomber'},
        'leer': {'family': ['leer'], 'meaning': 'lire'},
        'creer': {'family': ['creer'], 'meaning': 'croire'},
        'pedir': {'family': ['pedir', 'impedir', 'despedir'], 'meaning': 'demander'},
        'seguir': {'family': ['seguir', 'conseguir', 'perseguir'], 'meaning': 'suivre'},
        'dormir': {'family': ['dormir', 'morir'], 'meaning': 'dormir'},
        'sentir': {'family': ['sentir', 'consentir'], 'meaning': 'sentir'},
        'reir': {'family': ['reir'], 'meaning': 'rire'},
        'elegir': {'family': ['elegir', 'recoger'], 'meaning': 'choisir'},
        'medir': {'family': ['medir'], 'meaning': 'mesurer'},
        'repetir': {'family': ['repetir'], 'meaning': 'repeter'},
        'servir': {'family': ['servir'], 'meaning': 'servir'},
    },
    'fr': {
        'etre': {'family': ['etre'], 'meaning': 'etre'},
        'avoir': {'family': ['avoir'], 'meaning': 'avoir'},
        'aller': {'family': ['aller'], 'meaning': 'aller'},
        'faire': {'family': ['faire', 'défaire', 'refaire'], 'meaning': 'faire'},
        'dire': {'family': ['dire', 'redire', 'contredire', 'médire'], 'meaning': 'dire'},
        'pouvoir': {'family': ['pouvoir'], 'meaning': 'pouvoir'},
        'vouloir': {'family': ['vouloir'], 'meaning': 'vouloir'},
        'savoir': {'family': ['savoir'], 'meaning': 'savoir'},
        'voir': {'family': ['voir', 'revoir', 'prévoir'], 'meaning': 'voir'},
        'venir': {'family': ['venir', 'revenir', 'convenir', 'devenir', 'parvenir'], 'meaning': 'venir'},
        'tenir': {'family': ['tenir', 'soutenir', 'détenir', 'maintenir', 'obtenir', 'contenir'], 'meaning': 'tenir'},
        'prendre': {'family': ['prendre', 'apprendre', 'comprendre', 'surprendre'], 'meaning': 'prendre'},
        'mettre': {'family': ['mettre', 'remettre', 'permettre', 'promettre'], 'meaning': 'mettre'},
        'devoir': {'family': ['devoir'], 'meaning': 'devoir'},
        'donner': {'family': ['donner', 'redonner', 'pardonner'], 'meaning': 'donner'},
        'écrire': {'family': ['écrire', 'décrire', 'inscrire', 'prescrire'], 'meaning': 'écrire'},
        'lire': {'family': ['lire', 'élire', 'relire'], 'meaning': 'lire'},
        'croire': {'family': ['croire'], 'meaning': 'croire'},
        'boire': {'family': ['boire'], 'meaning': 'boire'},
        'connaître': {'family': ['connaître', 'reconnaître'], 'meaning': 'connaître'},
        'courir': {'family': ['courir', 'accourir', 'secourir'], 'meaning': 'courir'},
        'vivre': {'family': ['vivre', 'survivre', 'revivre'], 'meaning': 'vivre'},
        'ouvrir': {'family': ['ouvrir', 'couvrir', 'découvrir', 'offrir'], 'meaning': 'ouvrir'},
        'partir': {'family': ['partir', 'repartir'], 'meaning': 'partir'},
        'sortir': {'family': ['sortir'], 'meaning': 'sortir'},
        'dormir': {'family': ['dormir', 's\'endormir'], 'meaning': 'dormir'},
        'servir': {'family': ['servir'], 'meaning': 'servir'},
        'sentir': {'family': ['sentir', 'consentir'], 'meaning': 'sentir'},
        'recevoir': {'family': ['recevoir', 'apercevoir', 'décevoir'], 'meaning': 'recevoir'},
        'falloir': {'family': ['falloir'], 'meaning': 'falloir'},
    },
    'de': {
        'sein': {'family': ['sein'], 'meaning': 'etre'},
        'haben': {'family': ['haben'], 'meaning': 'avoir'},
        'werden': {'family': ['werden'], 'meaning': 'devenir'},
        'können': {'family': ['können'], 'meaning': 'pouvoir'},
        'müssen': {'family': ['müssen'], 'meaning': 'devoir'},
        'sollen': {'family': ['sollen'], 'meaning': 'devoir (conseil)'},
        'wollen': {'family': ['wollen'], 'meaning': 'vouloir'},
        'dürfen': {'family': ['dürfen'], 'meaning': 'avoir le droit'},
        'mögen': {'family': ['mögen'], 'meaning': 'aimer'},
        'geben': {'family': ['geben', 'aufgeben', 'ergeben'], 'meaning': 'donner'},
        'kommen': {'family': ['kommen', 'bekommen', 'ankommen'], 'meaning': 'venir'},
        'nehmen': {'family': ['nehmen', 'annehmen', 'aufnehmen'], 'meaning': 'prendre'},
        'sehen': {'family': ['sehen', 'ansehen', 'versehen'], 'meaning': 'voir'},
        'sprechen': {'family': ['sprechen', 'besprechen'], 'meaning': 'parler'},
        'lesen': {'family': ['lesen'], 'meaning': 'lire'},
        'fahren': {'family': ['fahren', 'abfahren', 'mitfahren'], 'meaning': 'aller (véhicule)'},
        'schreiben': {'family': ['schreiben', 'beschreiben'], 'meaning': 'écrire'},
        'laufen': {'family': ['laufen'], 'meaning': 'courir'},
        'halten': {'family': ['halten', 'behalten', 'enthalten'], 'meaning': 'tenir'},
        'treffen': {'family': ['treffen', 'betreffen'], 'meaning': 'rencontrer'},
        'beginnen': {'family': ['beginnen'], 'meaning': 'commencer'},
        'essen': {'family': ['essen'], 'meaning': 'manger'},
        'trinken': {'family': ['trinken'], 'meaning': 'boire'},
        'vergessen': {'family': ['vergessen'], 'meaning': 'oublier'},
        'helfen': {'family': ['helfen'], 'meaning': 'aider'},
        'schlafen': {'family': ['schlafen'], 'meaning': 'dormir'},
        'tragen': {'family': ['tragen', 'betragen'], 'meaning': 'porter'},
        'wissen': {'family': ['wissen'], 'meaning': 'savoir'},
        'rufen': {'family': ['rufen', 'anrufen'], 'meaning': 'appeler'},
    },
}

# Temps verbaux par langue (pour selector conjugaison)
TENSES_BY_LANG = {
    'it': [
        ('presente', 'Présent'),
        ('passato_prossimo', 'Passé composé'),
        ('imperfetto', 'Imparfait'),
        ('futuro_semplice', 'Futur'),
        ('condizionale_presente', 'Conditionnel présent'),
    ],
    'es': [
        ('presente', 'Présent'),
        ('preterito_indefinido', 'Passé simple'),
        ('imperfecto', 'Imparfait'),
        ('futuro', 'Futur'),
        ('condicional', 'Conditionnel'),
    ],
    'fr': [
        ('present', 'Présent'),
        ('passe_compose', 'Passé composé'),
        ('imparfait', 'Imparfait'),
        ('futur', 'Futur'),
        ('conditionnel', 'Conditionnel'),
    ],
    'de': [
        ('prasens', 'Présent'),
        ('perfekt', 'Parfait'),
        ('prateritum', 'Prétérit'),
        ('futur_i', 'Futur I'),
    ],
}


def get_pronouns(lang_code):
    """Return list of pronouns for conjugation grid."""
    return PRONOUNS_BY_LANG.get(lang_code, PRONOUNS_BY_LANG['it'])


def get_irregular_verbs(lang_code):
    """Return dict of irregular verb families for a language."""
    return IRREGULAR_VERBS.get(lang_code, {})


def get_tenses(lang_code):
    """Return list of (code, label) for tense selector."""
    return TENSES_BY_LANG.get(lang_code, TENSES_BY_LANG['it'])


def get_available_exercise_types(lang_config):
    """
    Return list of (type_id, name, description) available for this language.
    lang_config: dict from pillar_config.get_language(lang_code).
    """
    available = []
    has_conjugation = lang_config.get('has_conjugation', False)
    has_particles = lang_config.get('has_particles', False)
    has_gender = lang_config.get('has_gender', False)

    if has_conjugation:
        available.append(('conjugation', 'Conjugaison', 'Grille 6 pronoms + temps'))
        available.append(('fill_blank', 'Phrases a trous', 'Completer avec la bonne forme'))
        available.append(('transform', 'Transformation', 'Negation, question, temps'))
    available.append(('word_order', 'Ordre des mots', 'Remettre les mots dans l\'ordre'))
    if has_particles:
        available.append(('particles', 'Particules', 'Choisir la bonne particule'))
    if has_gender:
        available.append(('gender', 'Genre et articles', 'Accord et determinants'))

    return available
