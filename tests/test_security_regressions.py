import os
import tempfile
import unittest

from config import Config
from app import create_app, db
from app.models import Card, Category, Deck, TrainingSession, User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class SecurityRegressionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            db.create_all()
            self.owner = User(username="owner")
            self.owner.set_password("pass")
            self.attacker = User(username="attacker")
            self.attacker.set_password("pass")
            db.session.add_all([self.owner, self.attacker])
            db.session.flush()

            self.owner_deck = Deck(user_id=self.owner.id, name="Italian", description="Owner deck")
            self.attacker_deck = Deck(user_id=self.attacker.id, name="Other", description="Attacker deck")
            db.session.add_all([self.owner_deck, self.attacker_deck])
            db.session.flush()

            self.owner_card = Card(deck_id=self.owner_deck.id, front="ciao", back="salut")
            self.owner_category = Category(deck_id=self.owner_deck.id, name="Basics")
            db.session.add_all([self.owner_card, self.owner_category])
            db.session.flush()

            self.owner_session = TrainingSession(
                deck_id=self.owner_deck.id,
                data={
                    "card_ids": [self.owner_card.id],
                    "card_modes": ["flip"],
                    "card_directions": ["type_back"],
                    "current_index": 0,
                    "reviewed_indices": [],
                    "deck_id": self.owner_deck.id,
                    "results": {
                        "correct": 0,
                        "incorrect": 0,
                        "direction_stats": {
                            "type_back": {"correct": 0, "total": 0},
                            "type_front": {"correct": 0, "total": 0},
                            "flip": {"correct": 0, "total": 0},
                        },
                    },
                },
            )
            db.session.add(self.owner_session)
            db.session.commit()

            self.owner_id = self.owner.id
            self.attacker_id = self.attacker.id
            self.owner_deck_id = self.owner_deck.id
            self.owner_card_id = self.owner_card.id
            self.owner_category_id = self.owner_category.id
            self.owner_session_id = self.owner_session.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def login_attacker(self):
        response = self.client.post(
            "/login",
            data={"username": "attacker", "password": "pass"},
            follow_redirects=False,
        )
        self.assertIn(response.status_code, (302, 303))

    def test_deck_mutations_require_ownership(self):
        self.login_attacker()

        self.client.post(
            f"/decks/{self.owner_deck_id}/edit",
            data={"name": "pwned", "description": "changed"},
            follow_redirects=False,
        )
        self.client.post(f"/decks/{self.owner_deck_id}/reset", data={}, follow_redirects=False)
        self.client.post(f"/decks/{self.owner_deck_id}/delete", follow_redirects=False)

        with self.app.app_context():
            deck = db.session.get(Deck, self.owner_deck_id)
            self.assertIsNotNone(deck)
            self.assertEqual(deck.name, "Italian")

    def test_card_and_import_routes_require_deck_ownership(self):
        self.login_attacker()

        self.client.post(f"/cards/{self.owner_card_id}/delete", follow_redirects=False)
        self.client.post(
            f"/cards/bulk-create/{self.owner_deck_id}",
            data={"data": "uno;un", "separator": ";"},
            follow_redirects=False,
        )
        self.client.post(
            f"/cards/json-import/{self.owner_deck_id}",
            data={"json_text": '{"cards":[{"front":"due","back":"deux"}]}'},
            follow_redirects=False,
        )

        with self.app.app_context():
            self.assertIsNotNone(db.session.get(Card, self.owner_card_id))
            cards = Card.query.filter_by(deck_id=self.owner_deck_id).all()
            self.assertEqual([c.front for c in cards], ["ciao"])

    def test_category_routes_require_ownership(self):
        self.login_attacker()

        self.client.post(
            f"/categories/deck/{self.owner_deck_id}/new",
            data={"name": "pwned", "color": "#000000"},
            follow_redirects=False,
        )
        self.client.post(
            f"/categories/{self.owner_category_id}/edit",
            data={"name": "changed", "color": "#111111"},
            follow_redirects=False,
        )
        self.client.post(f"/categories/{self.owner_category_id}/delete", follow_redirects=False)

        with self.app.app_context():
            category = db.session.get(Category, self.owner_category_id)
            self.assertIsNotNone(category)
            self.assertEqual(category.name, "Basics")
            names = [c.name for c in Category.query.filter_by(deck_id=self.owner_deck_id).all()]
            self.assertEqual(names, ["Basics"])

    def test_training_count_and_session_require_ownership(self):
        self.login_attacker()

        count_response = self.client.get(f"/train/deck/{self.owner_deck_id}/count")
        self.assertNotEqual(count_response.status_code, 200)

        with self.client.session_transaction() as flask_session:
            flask_session["training_session_id"] = self.owner_session_id

        response = self.client.get("/train/card", follow_redirects=False)
        self.assertNotEqual(response.status_code, 200)

    def test_login_next_rejects_external_redirect(self):
        response = self.client.post(
            "/login?next=https://evil.example/phish",
            data={"username": "owner", "password": "pass"},
            follow_redirects=False,
        )

        self.assertIn(response.status_code, (302, 303))
        self.assertNotEqual(response.headers["Location"], "https://evil.example/phish")

    def test_empty_password_hash_does_not_accept_any_password(self):
        with self.app.app_context():
            user = User(username="legacy")
            db.session.add(user)
            db.session.commit()
            self.assertFalse(user.check_password("anything"))


class StaticTemplateSecurityTests(unittest.TestCase):
    def read_file(self, relative_path):
        root = os.path.dirname(os.path.dirname(__file__))
        with open(os.path.join(root, relative_path), encoding="utf-8") as handle:
            return handle.read()

    def test_chat_helper_escapes_plain_text_before_inner_html(self):
        source = self.read_file("app/templates/base.html")

        self.assertIn("escapeHtml", source)
        self.assertNotIn("div.innerHTML = parsedText;", source)

    def test_training_expected_answer_is_not_raw_inner_html(self):
        source = self.read_file("app/templates/training/card.html")

        self.assertNotIn("expectedDiv.innerHTML = '<strong>Réponse :</strong> ' + expected;", source)

    def test_language_pillars_template_has_valid_jinja_interpolations(self):
        source = self.read_file("app/templates/pillars/language.html")

        self.assertNotIn("{ {", source)
        self.assertNotIn("} }", source)


class ConfigSecurityTests(unittest.TestCase):
    def test_default_secret_key_is_not_public_constant(self):
        self.assertNotEqual(Config.SECRET_KEY, "dev-secret-key-change-in-prod")


if __name__ == "__main__":
    unittest.main()
