from app import create_app, db
from app.models import Deck, Card, Category
import re

def enrich_deck(deck_name="Italien – Conjugaisons Complètes"):
    app = create_app()
    with app.app_context():
        # Find deck
        deck = Deck.query.filter(Deck.name.ilike(f"%{deck_name}%")).first()
        if not deck:
            print(f"❌ Deck '{deck_name}' not found.")
            # Fallback to any deck
            deck = Deck.query.first()
            if deck:
                print(f"⚠️ Using deck '{deck.name}' instead.")
            else:
                return

        print(f"Enriching Deck: {deck.name} ({len(deck.cards)} cards)")
        
        # Helper to get or create category
        def get_or_create_cat(name, color="#95a5a6"):
            cat = Category.query.filter_by(deck_id=deck.id, name=name).first()
            if not cat:
                cat = Category(deck_id=deck.id, name=name, color=color)
                db.session.add(cat)
                db.session.flush()
                print(f"   + Created Category: {name}")
            return cat

        cat_sujet = get_or_create_cat("Sujet", "#e74c3c")
        cat_verbe = get_or_create_cat("Verbe", "#3498db")
        cat_infinitif = get_or_create_cat("Infinitif", "#2980b9")
        cat_objet = get_or_create_cat("Objet", "#f1c40f")
        cat_connecteur = get_or_create_cat("Connecteur", "#9b59b6")
        
        count_updated = 0
        
        for card in deck.cards:
            original_cats = [c.name for c in card.categories]
            front = card.front.lower()
            
            new_slot_type = None
            new_cat_to_add = None
            
            # 1. SUJETS (Pronoms)
            if any(p in front for p in ["io (", "tu (", "lui/lei (", "noi (", "voi (", "loro ("]):
                # Usually these are conjugated verbs in this specific deck, BUT logic might be tricky.
                # In this deck "Io (Essere)" -> back "sono". Ideally this is a VERB form for "Io".
                # But for Lego we need standalone PRONOUNS like "Io", "Tu".
                # If the card is JUST "Io", "Tu" -> Sujet.
                pass
            
            if front in ["io", "tu", "lui", "lei", "noi", "voi", "loro"]:
                new_slot_type = "SUJET"
                new_cat_to_add = cat_sujet
            
            # 2. VERBES (Infinitif)
            elif "Infinitif" in original_cats:
                new_slot_type = "VERBE_INF"
                new_cat_to_add = cat_infinitif
                
            # 3. VERBES (Conjugués - Présent, Futur, etc)
            elif any(t in original_cats for t in ["Présent", "Futur", "Passé", "Imperfetto", "Conditionnel"]):
                # Check based on pronoun in parenthesis for VERBE slot
                if "io (" in front:
                    new_slot_type = "VERBE_IO"
                elif "tu (" in front:
                    new_slot_type = "VERBE_TU"
                else:
                    new_slot_type = "VERBE" # General
                
                new_cat_to_add = cat_verbe

            # 4. OBJETS (par défaut si pas de ( ) et pas verbe)
            elif "(" not in front and "Verbe" not in str(original_cats):
                new_slot_type = "OBJET"
                new_cat_to_add = cat_objet
            
            # Apply changes
            if new_slot_type or new_cat_to_add:
                updated = False
                
                if new_slot_type and card.slot_type != new_slot_type:
                    card.slot_type = new_slot_type
                    updated = True
                    
                if new_cat_to_add and new_cat_to_add not in card.categories:
                    card.categories.append(new_cat_to_add)
                    updated = True
                
                if updated:
                    count_updated += 1
        
        # Create dedicated PRONOUN cards if they don't exist
        pronouns = {
            "Io": "Je", "Tu": "Tu", "Lui": "Il", "Lei": "Elle", 
            "Noi": "Nous", "Voi": "Vous", "Loro": "Ils/Elles"
        }
        
        for p_front, p_back in pronouns.items():
            exists = Card.query.filter_by(deck_id=deck.id, front=p_front).first()
            if not exists:
                print(f"Creating missing pronoun card: {p_front}")
                card = Card(deck_id=deck.id, front=p_front, back=p_back, slot_type="SUJET")
                card.categories.append(cat_sujet)
                db.session.add(card)
                count_updated += 1

        db.session.commit()
        print(f"✅ Enrichment Complete. Updated {count_updated} cards.")

if __name__ == '__main__':
    enrich_deck()
