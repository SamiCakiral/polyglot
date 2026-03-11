"""
Gym Engine - FSRS-based structure selection and exercise generation.

The Gym follows a 4-step pedagogical flow:
1. DISCOVERY - Show structure + example, user copies to anchor
2. CONSTRUCTION - User creates original sentences with daily vocab
3. FSI SURPRISE - Random mutation of the sentence (negation, future, etc.)
4. TRANSLATION - Translate from native to target using the structure
"""
import random
from datetime import datetime, date
from app import db
from app.models import LegoStructure, TrainingProgram, ProgramSession


# =============================================================================
# FSRS-LIKE STRUCTURE SELECTION
# =============================================================================

def get_due_structures(program_id, limit=1):
    """
    Select structures due for practice based on FSRS-like scheduling.
    
    Priority:
    1. New structures (never reviewed)
    2. Overdue structures (due_date <= today)
    3. Structures with lowest stability
    
    Args:
        program_id: ID of the TrainingProgram
        limit: Maximum number of structures to return
    
    Returns:
        List of LegoStructure objects
    """
    today = date.today()
    
    # First: Get new structures (never reviewed)
    new_structures = LegoStructure.query.filter(
        LegoStructure.program_id == program_id,
        LegoStructure.is_active == True,
        LegoStructure.review_count == 0
    ).limit(limit).all()
    
    if len(new_structures) >= limit:
        return new_structures[:limit]
    
    remaining = limit - len(new_structures)
    
    # Second: Get overdue structures
    due_structures = LegoStructure.query.filter(
        LegoStructure.program_id == program_id,
        LegoStructure.is_active == True,
        LegoStructure.review_count > 0,
        db.or_(
            LegoStructure.due_date <= today,
            LegoStructure.due_date.is_(None)
        )
    ).order_by(
        LegoStructure.due_date.asc().nullsfirst(),
        LegoStructure.stability.asc()
    ).limit(remaining).all()
    
    return new_structures + due_structures


def get_structure_for_session(program_id):
    """
    Get the best structure for today's session.
    Returns one structure, prioritizing due structures.
    """
    structures = get_due_structures(program_id, limit=1)
    if structures:
        return structures[0]
    
    # Fallback: Get any active structure with lowest stability
    return LegoStructure.query.filter(
        LegoStructure.program_id == program_id,
        LegoStructure.is_active == True
    ).order_by(LegoStructure.stability.asc()).first()


def create_default_structures(program_id, target_language='italian', native_language='french'):
    """
    Create default Lego structures for a new program.
    These are universal structures that work for most languages.
    """
    default_structures = [
        {
            "pattern": "Quand [SUJET] [VERBE_PRESENT] [LIEU], [SUJET] [VERBE2_PRESENT]",
            "example_target": "Quando vado a scuola, studio molto",
            "example_native": "Quand je vais à l'école, j'étudie beaucoup",
            "description": "Structure temporelle avec 'quand' - Idéale pour décrire des habitudes liées à un lieu",
            "complexity_level": "A2",
            "tags": ["temporal", "habitude", "lieu"]
        },
        {
            "pattern": "[SUJET] non può [VERBE_INFINITIF] perché deve [VERBE2_INFINITIF]",
            "example_target": "Non posso uscire perché devo lavorare",
            "example_native": "Je ne peux pas sortir parce que je dois travailler",
            "description": "Structure de contrainte - Pour exprimer une impossibilité et sa raison",
            "complexity_level": "A2",
            "tags": ["modal", "negation", "cause"]
        },
        {
            "pattern": "[SUJET] vorrebbe [VERBE_INFINITIF] ma [SUJET] deve [VERBE2_INFINITIF]",
            "example_target": "Vorrei dormire ma devo studiare",
            "example_native": "Je voudrais dormir mais je dois étudier",
            "description": "Structure de souhait contrarié - Exprimer un désir face à une obligation",
            "complexity_level": "B1",
            "tags": ["modal", "conditionnel", "opposition"]
        },
        {
            "pattern": "Se [SUJET] [VERBE_PRESENT], [SUJET] [VERBE2_FUTUR]",
            "example_target": "Se piove, resterò a casa",
            "example_native": "S'il pleut, je resterai à la maison",
            "description": "Structure conditionnelle simple - Si... alors...",
            "complexity_level": "B1",
            "tags": ["conditionnel", "futur", "hypothèse"]
        },
        {
            "pattern": "[SUJET] [VERBE_PASSE] [OBJET] e poi [SUJET] [VERBE2_PASSE]",
            "example_target": "Ho mangiato la pizza e poi sono uscito",
            "example_native": "J'ai mangé la pizza et puis je suis sorti",
            "description": "Structure narrative séquentielle - Raconter des actions successives",
            "complexity_level": "A2",
            "tags": ["passé", "narration", "séquence"]
        },
        {
            "pattern": "Prima di [VERBE_INFINITIF], [SUJET] deve [VERBE2_INFINITIF]",
            "example_target": "Prima di uscire, devo finire il lavoro",
            "example_native": "Avant de sortir, je dois finir le travail",
            "description": "Structure de prérequis - Exprimer ce qui doit être fait avant",
            "complexity_level": "B1",
            "tags": ["temporal", "séquence", "infinitif"]
        },
        {
            "pattern": "[SUJET] pensa che [SUJET2] [VERBE_SUBJONCTIF]",
            "example_target": "Penso che lui sia simpatico",
            "example_native": "Je pense qu'il est sympa",
            "description": "Structure d'opinion avec subjonctif - Exprimer un avis",
            "complexity_level": "B1",
            "tags": ["opinion", "subjonctif"]
        },
        {
            "pattern": "Anche se [SUJET] [VERBE_PRESENT], [SUJET] [VERBE2_PRESENT]",
            "example_target": "Anche se sono stanco, vado in palestra",
            "example_native": "Même si je suis fatigué, je vais à la salle de sport",
            "description": "Structure concessive - Malgré une condition, faire quelque chose",
            "complexity_level": "B1",
            "tags": ["concession", "opposition"]
        }
    ]
    
    structures = []
    for struct_data in default_structures:
        structure = LegoStructure(
            program_id=program_id,
            pattern=struct_data["pattern"],
            example_target=struct_data["example_target"],
            example_native=struct_data["example_native"],
            description=struct_data["description"],
            complexity_level=struct_data["complexity_level"],
            tags=struct_data["tags"]
        )
        db.session.add(structure)
        structures.append(structure)
    
    db.session.commit()
    return structures


# =============================================================================
# DYNAMIC STRUCTURE GENERATION
# =============================================================================

def generate_dynamic_structure(program, user, session_context):
    """
    Generate a new Lego structure using LLM based on theme and level.
    
    Args:
        program: TrainingProgram object
        user: User object
        session_context: dict with theme_name, day_focus, vocab_domains, etc.
    
    Returns:
        LegoStructure: The newly created structure, or None if generation failed
    """
    from app.prompt_templates import build_prompt
    from app.llm_service import call_llm
    import json
    
    # Get existing patterns to avoid duplicates
    existing_structures = LegoStructure.query.filter_by(
        program_id=program.id,
        is_active=True
    ).all()
    existing_patterns = [s.pattern for s in existing_structures]
    existing_patterns_str = '\n'.join(existing_patterns[:10]) if existing_patterns else 'Aucune'
    
    # Extract context
    theme_name = session_context.get('theme_name', 'Général')
    day_focus = session_context.get('day_focus', 'Pratique générale')
    vocab_domains = ', '.join(session_context.get('vocab_domains', ['general']))
    key_situations = ', '.join(session_context.get('key_situations', []))
    daily_vocabulary = '\n'.join(session_context.get('daily_vocabulary', [])[:10])
    user_level = session_context.get('user_level', 'A2')
    
    # Build prompt
    try:
        prompt = build_prompt(
            'generate_dynamic_structure',
            program,
            user,
            theme_name=theme_name,
            day_focus=day_focus,
            vocab_domains=vocab_domains,
            key_situations=key_situations,
            daily_vocabulary=daily_vocabulary,
            user_level=user_level,
            existing_patterns=existing_patterns_str
        )
    except Exception as e:
        print(f"[Gym] Error building structure prompt: {e}")
        return None
    
    # Call LLM
    system_prompt = f"Tu es un expert en linguistique et enseignement de {program.target_language}. Réponds uniquement en JSON valide."
    response = call_llm(system_prompt, prompt, temperature=0.8)
    
    if not response:
        print("[Gym] LLM returned empty response for structure generation")
        return None
    
    # Parse response
    try:
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        
        data = json.loads(response.strip())
        
        # Validate required fields
        if not data.get('pattern') or not data.get('example_target'):
            print(f"[Gym] Invalid structure data: missing required fields")
            return None
        
        # Create and save structure
        structure = LegoStructure(
            program_id=program.id,
            pattern=data['pattern'],
            example_target=data['example_target'],
            example_native=data.get('example_native', ''),
            description=data.get('description', ''),
            complexity_level=data.get('complexity_level', user_level),
            tags=data.get('tags', []),
            stability=1.0,  # New structure starts fresh
            difficulty=0.5
        )
        db.session.add(structure)
        db.session.commit()
        
        print(f"[Gym] Generated new structure: {data['pattern'][:50]}...")
        return structure
        
    except json.JSONDecodeError as e:
        print(f"[Gym] Failed to parse structure JSON: {e}")
        return None
    except Exception as e:
        print(f"[Gym] Error creating structure: {e}")
        return None


def generate_themed_examples(structure, session_context, count=3):
    """
    Generate themed examples for a Lego structure using daily vocabulary.
    
    Args:
        structure: LegoStructure object
        session_context: dict with theme_name, day_focus, daily_vocabulary, etc.
        count: Number of examples to generate
    
    Returns:
        list: List of example dicts [{target, native, vocab_used}, ...]
    """
    from app.llm_service import call_llm
    import json
    
    # Extract context
    theme_name = session_context.get('theme_name', 'Général')
    day_focus = session_context.get('day_focus', 'Pratique générale')
    vocab_domains = ', '.join(session_context.get('vocab_domains', ['general']))
    key_situations = ', '.join(session_context.get('key_situations', []))
    daily_vocabulary = '\n'.join(session_context.get('daily_vocabulary', [])[:15])
    user_level = session_context.get('user_level', 'A2')
    target_language = session_context.get('target_language', 'langue cible')
    native_language = session_context.get('native_language', 'français')
    
    prompt = f"""Tu es un professeur expert de {target_language}.

STRUCTURE LEGO: {structure.pattern}
EXEMPLE DE BASE: {structure.example_target}
TRADUCTION: {structure.example_native}

CONTEXTE DU JOUR:
- Thème de la semaine: {theme_name}
- Focus du jour: {day_focus}
- Domaines: {vocab_domains}
- Situations clés: {key_situations}

VOCABULAIRE À INTÉGRER:
{daily_vocabulary}

NIVEAU: {user_level}

Génère {count} exemples de phrases utilisant EXACTEMENT cette structure grammaticale,
mais avec le vocabulaire du jour et en correspondant au thème.

RÈGLES:
1. Chaque exemple doit suivre le MÊME pattern grammatical que l'exemple de base
2. Utilise le vocabulaire du jour dans les exemples
3. Les phrases doivent correspondre aux situations clés
4. Adapte la complexité au niveau {user_level}

Réponds UNIQUEMENT en JSON:
{{
    "examples": [
        {{
            "target": "phrase en {target_language}",
            "native": "traduction en {native_language}",
            "vocab_used": ["mot1", "mot2"]
        }}
    ]
}}"""

    system_prompt = f"Tu es un professeur expert de {target_language}. Réponds uniquement en JSON valide."
    response = call_llm(system_prompt, prompt, temperature=0.7)
    
    if not response:
        # Fallback: return the original example
        return [{
            'target': structure.example_target,
            'native': structure.example_native,
            'vocab_used': []
        }]
    
    try:
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]
        
        data = json.loads(response.strip())
        examples = data.get('examples', [])
        
        if not examples:
            return [{
                'target': structure.example_target,
                'native': structure.example_native,
                'vocab_used': []
            }]
        
        return examples
        
    except (json.JSONDecodeError, Exception) as e:
        print(f"[Gym] Failed to parse themed examples: {e}")
        return [{
            'target': structure.example_target,
            'native': structure.example_native,
            'vocab_used': []
        }]


def _structure_matches_intent(structure, intent):
    """Check if a structure's tags or description match the suggested_lego_intent."""
    if not intent or intent == 'general':
        return False
    
    intent_lower = intent.lower().replace('_', ' ')
    
    # Check tags
    tags = structure.tags or []
    for tag in tags:
        if intent_lower in tag.lower() or tag.lower() in intent_lower:
            return True
    
    # Check description
    desc = (structure.description or '').lower()
    if intent_lower in desc:
        return True
    
    # Check pattern keywords
    pattern = (structure.pattern or '').lower()
    # Map common intents to pattern keywords
    intent_pattern_map = {
        'se_presenter': ['sujet', 'present', 'appel'],
        'exprimer_souhait': ['vorr', 'voul', 'aimer'],
        'raconter_passe': ['passe', 'pass'],
        'exprimer_obligation': ['dev', 'doit', 'falloir'],
        'exprimer_condition': ['se ', 'si '],
        'exprimer_cause': ['perch', 'parce'],
        'comparer': ['più', 'plus', 'moin'],
        'donner_avis': ['pens', 'cred', 'opinion'],
        'demander': ['question', 'demand'],
    }
    
    keywords = intent_pattern_map.get(intent, [])
    for kw in keywords:
        if kw in pattern or kw in desc:
            return True
    
    return False


def get_or_generate_structure_for_session(program, user, session_context):
    """
    Get an existing due structure or generate a new one if needed.
    
    Uses suggested_lego_intent from the daily_breakdown to prioritize
    structures that match the day's communicative intent.
    
    Priority:
    1. Due structure matching today's intent
    2. Due structure (any)
    3. New structure matching intent
    4. New structure (any)
    5. Generate a new structure if few exist or all mastered
    6. Lowest stability structure
    """
    today = date.today()
    
    # Get today's suggested intent
    lego_intent = 'general'
    if session_context:
        lego_intent = session_context.get('suggested_lego_intent', 'general')
        # If not directly in context, try to extract from day breakdown
        if lego_intent == 'general' and session_context.get('day_focus'):
            # Infer intent from day_focus keywords
            focus = session_context.get('day_focus', '').lower()
            if any(w in focus for w in ['present', 'introdui', 'arriv']):
                lego_intent = 'se_presenter'
            elif any(w in focus for w in ['pass', 'hier', 'racont', 'souvenir']):
                lego_intent = 'raconter_passe'
            elif any(w in focus for w in ['futur', 'projet', 'plan', 'demain']):
                lego_intent = 'exprimer_souhait'
            elif any(w in focus for w in ['travail', 'bureau', 'reunion']):
                lego_intent = 'exprimer_obligation'
    
    # Get all active structures for this program
    all_structures = LegoStructure.query.filter_by(
        program_id=program.id,
        is_active=True
    ).all()
    
    # Case 1: No structures at all -> create defaults
    if not all_structures:
        all_structures = create_default_structures(
            program.id,
            program.target_language,
            program.native_language
        )
    
    # Case 2: Few structures (< 10) -> try to generate a new one matching intent
    if len(all_structures) < 10 and user and session_context:
        new_structure = generate_dynamic_structure(program, user, session_context)
        if new_structure:
            all_structures.append(new_structure)
    
    # Categorize structures
    due_matching = []
    due_other = []
    new_matching = []
    new_other = []
    rest = []
    
    for s in all_structures:
        is_due = s.due_date and s.due_date <= today
        is_new = s.review_count == 0
        matches_intent = _structure_matches_intent(s, lego_intent)
        
        if is_due and matches_intent:
            due_matching.append(s)
        elif is_due:
            due_other.append(s)
        elif is_new and matches_intent:
            new_matching.append(s)
        elif is_new:
            new_other.append(s)
        else:
            rest.append(s)
    
    # Priority 1: Due structure matching intent
    if due_matching:
        due_matching.sort(key=lambda s: s.due_date)
        return due_matching[0]
    
    # Priority 2: Due structure (any)
    if due_other:
        due_other.sort(key=lambda s: s.due_date)
        return due_other[0]
    
    # Priority 3: New structure matching intent
    if new_matching:
        return new_matching[0]
    
    # Priority 4: New structure (any)
    if new_other:
        return new_other[0]
    
    # Priority 5: All reviewed, all non-due => try to generate a new one for variety
    if user and session_context:
        min_stability = min(s.stability for s in all_structures) if all_structures else 0
        if min_stability > 20 or len(all_structures) < 8:
            # All somewhat mastered or few structures => generate new challenge
            new_structure = generate_dynamic_structure(program, user, session_context)
            if new_structure:
                return new_structure
    
    # Priority 6: Pick randomly among the 3 lowest stability structures (for variety)
    all_structures.sort(key=lambda s: s.stability)
    import random
    pool = all_structures[:min(3, len(all_structures))]
    return random.choice(pool) if pool else None


# =============================================================================
# FSI MUTATIONS
# =============================================================================

FSI_MUTATIONS = {
    "negation": {
        "id": "negation",
        "name": "Negation",
        "instruction_template": "Mets cette phrase a la forme NEGATIVE",
        "config_key": "NEGATION"
    },
    "future": {
        "id": "future",
        "name": "Futur",
        "instruction_template": "Mets cette phrase au FUTUR",
        "config_key": "FUTUR"
    },
    "past": {
        "id": "past",
        "name": "Passe",
        "instruction_template": "Mets cette phrase au PASSE",
        "config_key": "PASSE"
    },
    "question": {
        "id": "question",
        "name": "Question",
        "instruction_template": "Transforme cette phrase en QUESTION",
        "config_key": "QUESTION"
    },
    "plural": {
        "id": "plural",
        "name": "Pluriel",
        "instruction_template": "Mets cette phrase au PLURIEL (change le sujet)",
        "config_key": "PLURIEL"
    },
    "conditionnel": {
        "id": "conditionnel",
        "name": "Conditionnel",
        "instruction_template": "Mets cette phrase au CONDITIONNEL",
        "config_key": "CONDITIONNEL"
    },
    "formel": {
        "id": "formel",
        "name": "Formel/Informel",
        "instruction_template": "Reformule en VOUVOYANT (registre formel)",
        "config_key": "FORMEL"
    },
    "point_de_vue": {
        "id": "point_de_vue",
        "name": "Changement de sujet",
        "instruction_template": "Raconte comme si c'etait QUELQU'UN D'AUTRE (3e personne)",
        "config_key": "POINT_DE_VUE"
    }
}

# Backward compat: list version
FSI_MUTATIONS_LIST = list(FSI_MUTATIONS.values())


def get_random_mutation():
    """Get a random FSI mutation (backward compat fallback)."""
    return random.choice(FSI_MUTATIONS_LIST)


def get_contextual_mutation(session_context=None, program=None, used_mutations=None):
    """
    Get a contextual FSI mutation based on:
    1. suggested_fsi_mutations from the daily_breakdown
    2. program.fsi_mutations (user-configured allowed mutations)
    3. Avoid repeating mutations already used in this session
    
    Args:
        session_context: dict with day_focus, vocab_domains, etc.
        program: TrainingProgram (to get fsi_mutations config)
        used_mutations: list of mutation IDs already used in this session
    
    Returns:
        dict: mutation with id, name, instruction_template
    """
    used_mutations = used_mutations or []
    
    # 1. Get allowed mutations from program config
    allowed_config_keys = None
    if program and hasattr(program, 'fsi_mutations') and program.fsi_mutations:
        allowed_config_keys = set(program.fsi_mutations)
    
    # Filter available mutations by program config
    available = {}
    for mut_id, mut in FSI_MUTATIONS.items():
        if allowed_config_keys is None or mut['config_key'] in allowed_config_keys:
            available[mut_id] = mut
    
    if not available:
        available = FSI_MUTATIONS  # Fallback to all
    
    # 2. Get suggested mutations from daily_breakdown
    suggested = []
    if session_context:
        # Try to get from day's breakdown
        day_suggested = session_context.get('suggested_fsi_mutations', [])
        if not day_suggested:
            # Try to get from the full context
            day_focus = session_context.get('day_focus', '')
            # Infer from context if no explicit suggestions
            if any(word in day_focus.lower() for word in ['passe', 'hier', 'racont', 'souvenir']):
                day_suggested = ['past', 'point_de_vue']
            elif any(word in day_focus.lower() for word in ['futur', 'demain', 'projet', 'plan']):
                day_suggested = ['future', 'conditionnel']
            elif any(word in day_focus.lower() for word in ['formel', 'professionnel', 'bureau', 'travail']):
                day_suggested = ['formel', 'question']
        
        # Normalize: lowercase for matching
        suggested = [s.lower() for s in day_suggested]
    
    # 3. Build weighted candidates (suggested mutations have higher weight)
    candidates = []
    for mut_id, mut in available.items():
        # Skip already used mutations
        if mut_id in used_mutations:
            continue
        
        # Weight: suggested = 3x, others = 1x
        weight = 3 if mut_id in suggested else 1
        candidates.extend([mut] * weight)
    
    # If all mutations were used, allow repeats
    if not candidates:
        candidates = list(available.values())
    
    return random.choice(candidates)


# =============================================================================
# GYM SESSION ENGINE
# =============================================================================

class GymSessionEngine:
    """
    New Gym Engine with 4-step pedagogical flow.
    
    Flow:
    1. DISCOVERY - See structure + example, copy it once
    2. CONSTRUCTION - Create original sentence with daily vocab
    3. FSI_SURPRISE - Transform the sentence (random mutation)
    4. TRANSLATION - Translate phrases from native to target
    """
    
    def __init__(self, program: TrainingProgram, session: ProgramSession = None, session_context: dict = None):
        self.program = program
        self.session = session
        self.daily_vocab = session.daily_words if session else []
        self.context = session_context or {}
        self._themed_examples = None  # Cache for themed examples
    
    def get_structure_of_the_day(self):
        """Get the structure to practice today based on FSRS and session context."""
        user = self.session.user if self.session else None
        
        # Use the new smart selection/generation function
        structure = get_or_generate_structure_for_session(
            self.program,
            user,
            self.context
        )
        
        if not structure:
            # Fallback to old method
            structure = get_structure_for_session(self.program.id)
            
            if not structure:
                # Create defaults if none exist
                structures = create_default_structures(
                    self.program.id,
                    self.program.target_language,
                    self.program.native_language
                )
                structure = structures[0] if structures else None
        
        return structure
    
    def get_themed_examples(self, structure, count=3):
        """Get themed examples for the structure using daily vocabulary."""
        if not self.context.get('daily_vocabulary'):
            return None
        
        # Cache themed examples for this session
        if self._themed_examples is None:
            self._themed_examples = generate_themed_examples(
                structure,
                self.context,
                count=count
            )
        
        return self._themed_examples
    
    def generate_gym_session(self, duration_minutes=10):
        """
        Generate a complete Gym session with themed examples.
        
        Args:
            duration_minutes: Target duration (5, 10, or 15 minutes)
        
        Returns:
            dict with session structure and steps
        """
        structure = self.get_structure_of_the_day()
        
        if not structure:
            return {"error": "No structures available", "steps": []}
        
        # Calculate volume based on duration
        # Approx timing: Discovery=2min, Construction=2min each, FSI=1min each, Translation=1min each
        if duration_minutes <= 5:
            n_construction = 1
            n_translation = 2
        elif duration_minutes <= 10:
            n_construction = 2
            n_translation = 3
        else:  # 15 min
            n_construction = 3
            n_translation = 5
        
        # Build session
        steps = []
        
        # Get relevant vocabulary for this session
        vocab_list = self._get_relevant_vocab()
        
        # =========================================================
        # GENERATE THEMED EXAMPLES (if context available)
        # =========================================================
        themed_examples = self.get_themed_examples(structure, count=n_translation + 1)
        
        # Use first themed example for discovery if available, otherwise use structure's example
        discovery_example_target = structure.example_target
        discovery_example_native = structure.example_native
        if themed_examples and len(themed_examples) > 0:
            first_example = themed_examples[0]
            if first_example.get('target') and first_example.get('native'):
                discovery_example_target = first_example['target']
                discovery_example_native = first_example['native']
        
        # =========================================================
        # STEP 1: DISCOVERY (first time seeing structure)
        # =========================================================
        is_first_time = structure.review_count == 0
        
        # Build theme context string for display
        theme_context = ""
        if self.context.get('theme_name'):
            theme_context = f" (Thème: {self.context['theme_name']}"
            if self.context.get('day_focus'):
                theme_context += f" - {self.context['day_focus']}"
            theme_context += ")"
        
        steps.append({
            "id": "discovery",
            "type": "discovery",
            "phase": 1,
            "title": "Découverte de la structure" + theme_context,
            "structure_id": structure.id,
            "pattern": structure.pattern,
            "example_target": discovery_example_target,
            "example_native": discovery_example_native,
            "original_example_target": structure.example_target,  # Keep original for reference
            "original_example_native": structure.example_native,
            "description": structure.description,
            "is_first_time": is_first_time,
            "is_themed_example": themed_examples is not None,
            "instruction": "Observe cette structure et son exemple. Ensuite, recopie l'exemple pour l'ancrer." if is_first_time else "Rappelle-toi cette structure. Recopie l'exemple pour te remettre dans le bain."
        })
        
        # =========================================================
        # STEP 2: CONSTRUCTION (create original sentences)
        # =========================================================
        for i in range(n_construction):
            # Add theme hint if available
            theme_hint = ""
            if self.context.get('key_situations'):
                situations = self.context['key_situations']
                if situations:
                    theme_hint = f" Inspire-toi des situations: {', '.join(situations[:2])}."
            
            steps.append({
                "id": f"construction_{i+1}",
                "type": "construction",
                "phase": 2,
                "title": f"Construction ({i+1}/{n_construction})",
                "structure_id": structure.id,
                "pattern": structure.pattern,
                "example_target": discovery_example_target,
                "vocabulary": vocab_list,
                "instruction": f"Crée une phrase ORIGINALE en suivant la structure. Utilise le vocabulaire du jour si possible.{theme_hint}",
                "hint": "Ta phrase doit suivre le même schéma grammatical que l'exemple, mais avec des mots différents."
            })
            
            # =========================================================
            # STEP 3: FSI SURPRISE (after each construction)
            # =========================================================
            mutation = get_random_mutation()
            steps.append({
                "id": f"fsi_{i+1}",
                "type": "fsi",
                "phase": 3,
                "title": f"{mutation.get('emoji', '🔄')} FSI: {mutation['name']}",
                "structure_id": structure.id,
                "mutation": mutation,
                "instruction": f"SURPRISE ! {mutation['instruction_template']}",
                "hint": "Réécris TOUTE la phrase transformée. Pas de raccourcis !",
                # The sentence to transform will be set after construction validation
                "context_sentence": None
            })
        
        # =========================================================
        # STEP 4: TRANSLATION (native to target)
        # =========================================================
        steps.append({
            "id": "translation_intro",
            "type": "translation_intro",
            "phase": 4,
            "title": "Traduction",
            "structure_id": structure.id,
            "pattern": structure.pattern,
            "example_target": discovery_example_target,
            "example_native": discovery_example_native,
            "n_phrases": n_translation,
            "instruction": f"Maintenant, traduis {n_translation} phrases en utilisant la même structure.",
            "vocabulary": vocab_list
        })
        
        # Use themed examples for translation if available
        translation_examples = themed_examples[1:n_translation+1] if themed_examples and len(themed_examples) > 1 else None
        
        for i in range(n_translation):
            native_phrase = None
            expected_target = None
            
            # Pre-fill with themed examples if available
            if translation_examples and i < len(translation_examples):
                native_phrase = translation_examples[i].get('native')
                expected_target = translation_examples[i].get('target')
            
            steps.append({
                "id": f"translation_{i+1}",
                "type": "translation",
                "phase": 4,
                "title": f"Traduction ({i+1}/{n_translation})",
                "structure_id": structure.id,
                "pattern": structure.pattern,
                # Pre-filled if themed examples available, otherwise will be generated by LLM
                "native_phrase": native_phrase,
                "expected_target": expected_target,
                "instruction": "Traduis cette phrase en suivant la structure apprise."
            })
        
        return {
            "structure": structure.to_dict(),
            "steps": steps,
            "total_steps": len(steps),
            "duration_target": duration_minutes,
            "themed": themed_examples is not None,
            "theme_context": {
                "theme_name": self.context.get('theme_name'),
                "day_focus": self.context.get('day_focus'),
                "vocab_domains": self.context.get('vocab_domains', [])
            }
        }
    
    def _get_relevant_vocab(self, max_words=10):
        """Get vocabulary relevant for the gym session (deduplicated, target language only)."""
        if not self.daily_vocab:
            return []
        
        # Deduplicate: skip reverse cards from old bidirectional format
        seen_fronts = set()
        formatted = []
        for word in self.daily_vocab:
            if isinstance(word, dict):
                # Skip reverse cards
                if word.get('direction') == 'reverse':
                    continue
                front = word.get("front", "")
                if front and front not in seen_fronts:
                    seen_fronts.add(front)
                    formatted.append({
                        "front": front,
                        "back": word.get("back", "")
                    })
            if len(formatted) >= max_words:
                break
        
        return formatted
    
    def validate_construction(self, user_text, structure_pattern, example, conversation_history=None):
        """
        Validate a construction attempt using LLM.
        Supports conversation history for context-aware correction.
        
        Returns:
            dict with is_valid, errors, feedback, corrected
        """
        from app.prompt_templates import build_prompt
        from app.llm_service import call_llm
        import json
        
        prompt = build_prompt(
            'gym_lego_validate',
            self.program,
            self.session.user if self.session else None,
            pattern=structure_pattern,
            example_target=example,
            example_native="",  # Could add if available
            user_text=user_text,
            conversation_history=conversation_history
        )
        
        system_prompt = f"Tu es un tuteur bienveillant de {self.program.target_language}. Réponds en JSON valide."
        
        response = call_llm(system_prompt, prompt, temperature=0.3)
        
        if response:
            try:
                # Parse JSON from response
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0]
                
                return json.loads(response.strip())
            except:
                pass
        
        # Fallback
        return {
            "is_valid": True,
            "follows_structure": True,
            "errors": [],
            "corrected": "",
            "feedback": "Phrase acceptée."
        }
    
    def validate_fsi(self, original_sentence, mutation_type, user_text, conversation_history=None):
        """
        Validate an FSI mutation attempt using LLM.
        """
        from app.prompt_templates import build_prompt
        from app.llm_service import call_llm
        import json
        
        prompt = build_prompt(
            'gym_fsi_validate',
            self.program,
            self.session.user if self.session else None,
            original_sentence=original_sentence,
            mutation_type=mutation_type,
            user_text=user_text,
            conversation_history=conversation_history
        )
        
        system_prompt = f"Tu es un tuteur de {self.program.target_language}. Réponds en JSON valide."
        
        response = call_llm(system_prompt, prompt, temperature=0.3)
        
        if response:
            try:
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0]
                
                return json.loads(response.strip())
            except:
                pass
        
        return {
            "is_valid": True,
            "expected": "",
            "errors": [],
            "feedback": "Transformation acceptée."
        }
    
    def generate_translation_phrases(self, structure, n_phrases, vocabulary):
        """
        Generate phrases in native language for translation exercise.
        Uses LLM to create contextually relevant phrases.
        
        Uses session context (theme, vocab_domains, key_situations) for coherent generation.
        """
        from app.prompt_templates import build_prompt
        from app.llm_service import call_llm
        import json
        
        # Use context if available
        vocab_str = ", ".join([v.get("front", "") for v in vocabulary[:5]]) if vocabulary else "vocabulaire courant"
        
        # Build context block for LLM
        context_block = ""
        if self.context:
            context_block = f"""
CONTEXTE THÉMATIQUE:
- Thème de la semaine: {self.context.get('theme_name', 'Général')}
- Focus du jour: {self.context.get('day_focus', 'Pratique générale')}
- Domaines de vocabulaire: {', '.join(self.context.get('vocab_domains', ['général']))}
- Situations clés: {', '.join(self.context.get('key_situations', []))}

IMPORTANT: Génère des phrases qui correspondent au thème et au focus du jour.
Les phrases doivent utiliser le vocabulaire du jour et correspondre aux situations clés.
"""
        
        prompt = build_prompt(
            'gym_generate_translations',
            self.program,
            self.session.user if self.session else None,
            pattern=structure.pattern,
            example_target=structure.example_target,
            vocabulary=vocab_str,
            count=n_phrases,
            context_block=context_block  # Pass the context block
        )
        
        system_prompt = f"Tu es un professeur de {self.program.target_language}. Réponds en JSON valide."
        
        response = call_llm(system_prompt, prompt, temperature=0.7)
        
        if response:
            try:
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0]
                elif "```" in response:
                    response = response.split("```")[1].split("```")[0]
                
                data = json.loads(response.strip())
                return data.get("phrases", [])
            except:
                pass
        
        # Fallback phrases
        return [
            {"native": structure.example_native, "expected_target": structure.example_target}
            for _ in range(n_phrases)
        ]
    
    def complete_structure_review(self, structure_id, grade):
        """
        Mark a structure as reviewed and update FSRS scheduling.
        
        Args:
            structure_id: ID of the LegoStructure
            grade: 1 (fail), 2 (hard), 3 (good), 4 (easy)
        """
        structure = LegoStructure.query.get(structure_id)
        if structure:
            structure.update_after_review(grade)
            db.session.commit()
            return True
        return False
