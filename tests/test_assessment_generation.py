import unittest
from unittest.mock import patch

from app import create_app, db
from app.assessment_generator import create_assessment
from app.models import Assessment, AssessmentSection, User


class TestConfig:
    TESTING = True
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class AssessmentGenerationTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestConfig)
        with self.app.app_context():
            db.create_all()
            user = User(username="learner")
            user.set_password("pass")
            db.session.add(user)
            db.session.commit()
            self.user_id = user.id

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def test_empty_generated_section_aborts_assessment(self):
        with self.app.app_context():
            with patch(
                "app.assessment_generator._generate_section_content",
                return_value={"questions": []},
            ):
                assessment = create_assessment(self.user_id, "it", "A1")

            self.assertIsNone(assessment)
            self.assertEqual(Assessment.query.count(), 0)
            self.assertEqual(AssessmentSection.query.count(), 0)


if __name__ == "__main__":
    unittest.main()
