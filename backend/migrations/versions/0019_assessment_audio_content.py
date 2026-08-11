"""Publish usable Italian assessment content and durable listening limits.

Revision ID: 0019_assessment_audio
Revises: 0018_memory_prompt_identity
"""

# ruff: noqa: E501

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_assessment_audio"
down_revision: str | None = "0018_memory_prompt_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


READING_GROUPS = (
    (
        "Il bar della stazione",
        "Marta arriva in stazione alle sette e venti. Il suo treno parte alle otto, quindi entra nel bar. Ordina un cappuccino e un cornetto, ma scopre che il pagamento con la carta non funziona. Paga in contanti e raggiunge il binario cinque con dieci minuti di anticipo.",
        (
            ("A che ora arriva Marta?", ("Alle sette e venti", "Alle otto", "Alle otto e venti", "Alle sette"), "Alle sette e venti"),
            ("Perché entra nel bar?", ("Ha tempo prima del treno", "Ha perso il treno", "Aspetta un amico", "Cerca il binario"), "Ha tempo prima del treno"),
            ("Che cosa ordina?", ("Un cappuccino e un cornetto", "Un tè e una pizza", "Un caffè e un panino", "Solo un cornetto"), "Un cappuccino e un cornetto"),
            ("Qual è il problema?", ("La carta non funziona", "Non ha contanti", "Il bar è chiuso", "Il treno è cancellato"), "La carta non funziona"),
            ("Dove deve andare?", ("Al binario cinque", "Al binario dieci", "Alla biglietteria", "All'uscita"), "Al binario cinque"),
            ("Con quanto anticipo arriva?", ("Dieci minuti", "Venti minuti", "Cinque minuti", "Mezz'ora"), "Dieci minuti"),
        ),
    ),
    (
        "Un cambio di programma",
        "Luca doveva incontrare Anna venerdì sera, ma il suo turno di lavoro finisce più tardi del previsto. Le scrive per proporre sabato alle undici. Anna accetta, però preferisce vedersi davanti al museo invece che al solito caffè, perché dopo vuole visitare una mostra fotografica.",
        (
            ("Quando era previsto l'incontro?", ("Venerdì sera", "Sabato mattina", "Venerdì mattina", "Domenica sera"), "Venerdì sera"),
            ("Perché Luca cambia programma?", ("Finisce tardi al lavoro", "È malato", "Il museo è chiuso", "Ha perso il telefono"), "Finisce tardi al lavoro"),
            ("Quale nuovo orario propone?", ("Sabato alle undici", "Sabato alle otto", "Venerdì alle undici", "Domenica alle dieci"), "Sabato alle undici"),
            ("Dove vuole incontrarsi Anna?", ("Davanti al museo", "Alla stazione", "Al solito caffè", "In ufficio"), "Davanti al museo"),
            ("Che cosa vuole fare dopo?", ("Visitare una mostra", "Prendere un treno", "Andare al lavoro", "Comprare un regalo"), "Visitare una mostra"),
            ("Come reagisce Anna alla proposta?", ("Accetta con un cambio di luogo", "Rifiuta", "Non risponde", "Propone venerdì"), "Accetta con un cambio di luogo"),
        ),
    ),
    (
        "Una deviazione inattesa",
        "Durante un viaggio in autobus verso Siena, la strada principale viene chiusa per un incidente. L'autista annuncia una deviazione di circa quaranta minuti. Paolo avvisa l'albergo del ritardo e chiede di conservare la prenotazione. La receptionist conferma e gli spiega come entrare dopo le ventidue.",
        (
            ("Qual è la destinazione?", ("Siena", "Roma", "Firenze", "Pisa"), "Siena"),
            ("Perché la strada è chiusa?", ("Per un incidente", "Per il mercato", "Per la neve", "Per una manifestazione"), "Per un incidente"),
            ("Quanto dura la deviazione?", ("Circa quaranta minuti", "Dieci minuti", "Due ore", "Un'ora esatta"), "Circa quaranta minuti"),
            ("Chi avvisa Paolo?", ("L'albergo", "La polizia", "La stazione", "Un collega"), "L'albergo"),
            ("Che cosa chiede?", ("Di conservare la prenotazione", "Di cambiare camera", "Di annullare il viaggio", "Di inviare un taxi"), "Di conservare la prenotazione"),
            ("Quale informazione riceve?", ("Come entrare dopo le ventidue", "Dove comprare un biglietto", "Quando parte l'autobus", "Come evitare la deviazione"), "Come entrare dopo le ventidue"),
        ),
    ),
)


LISTENING_GROUPS = (
    (
        "Buongiorno, il regionale per Bologna delle nove e dieci partirà con venti minuti di ritardo dal binario sette.",
        (
            ("Quale treno viene annunciato?", ("Il regionale per Bologna", "L'Intercity per Roma", "Il regionale per Parma", "Il treno per Milano"), "Il regionale per Bologna"),
            ("A che ora doveva partire?", ("Alle nove e dieci", "Alle nove e venti", "Alle dieci", "Alle sette"), "Alle nove e dieci"),
            ("Quanto ritardo ha?", ("Venti minuti", "Dieci minuti", "Sette minuti", "Mezz'ora"), "Venti minuti"),
            ("Da quale binario partirà?", ("Dal sette", "Dal nove", "Dal venti", "Dal dieci"), "Dal sette"),
        ),
    ),
    (
        "Scusi, ho prenotato una camera a nome Martin. Certo, la camera è pronta, ma la colazione domani inizierà alle sette e mezza invece che alle sette.",
        (
            ("Che cosa ha prenotato il cliente?", ("Una camera", "Un tavolo", "Un taxi", "Un biglietto"), "Una camera"),
            ("A quale nome è la prenotazione?", ("Martin", "Marta", "Marini", "Marco"), "Martin"),
            ("La camera è disponibile?", ("Sì, è pronta", "No, è occupata", "Solo domani", "Non si sa"), "Sì, è pronta"),
            ("A che ora inizia la colazione?", ("Alle sette e mezza", "Alle sette", "Alle otto", "Alle sei e mezza"), "Alle sette e mezza"),
        ),
    ),
    (
        "Vorrei spostare l'appuntamento di martedì pomeriggio. Posso venire mercoledì alle undici? Mercoledì alle undici è completo, ma c'è posto alle dodici e un quarto.",
        (
            ("Che cosa vuole fare la persona?", ("Spostare un appuntamento", "Annullare un viaggio", "Prenotare un albergo", "Cambiare lavoro"), "Spostare un appuntamento"),
            ("Quando era l'appuntamento?", ("Martedì pomeriggio", "Mercoledì mattina", "Lunedì sera", "Martedì mattina"), "Martedì pomeriggio"),
            ("Quale orario propone per primo?", ("Mercoledì alle undici", "Martedì alle undici", "Mercoledì alle dodici", "Giovedì alle undici"), "Mercoledì alle undici"),
            ("Quale orario è disponibile?", ("Le dodici e un quarto", "Le undici", "Le dieci e mezza", "Le tredici"), "Le dodici e un quarto"),
        ),
    ),
    (
        "Per arrivare al mercato attraversi la piazza e prenda la seconda strada a sinistra. Se vede la farmacia, è andato troppo avanti.",
        (
            ("Qual è la destinazione?", ("Il mercato", "La farmacia", "La stazione", "Il museo"), "Il mercato"),
            ("Che cosa bisogna attraversare?", ("La piazza", "Il ponte", "Il parco", "La stazione"), "La piazza"),
            ("Quale strada bisogna prendere?", ("La seconda a sinistra", "La prima a destra", "La seconda a destra", "Sempre dritto"), "La seconda a sinistra"),
            ("Che cosa indica di essere andati troppo avanti?", ("Vedere la farmacia", "Vedere il mercato", "Arrivare in piazza", "Trovare un ponte"), "Vedere la farmacia"),
        ),
    ),
)


def _insert_item(
    *,
    item_id: str,
    section_id: str,
    ordinal: int,
    item_kind: str,
    coverage_target: str,
    prompt: dict[str, object],
    solution: dict[str, object],
    media_ref: str | None = None,
    max_plays: int | None = None,
) -> None:
    op.get_bind().execute(
        sa.text(
            "INSERT INTO assessments.assessment_items "
            "(item_id,section_definition_id,ordinal,item_kind,answer_kind,correction_strategy,"
            "weight,difficulty_tier,coverage_targets,prompt_snapshot,solution_snapshot,media_ref,"
            "max_plays,defective,created_at) VALUES "
            "(CAST(:item AS uuid),CAST(:section AS uuid),:ordinal,:kind,'single_choice',"
            "'accepted_set',:weight,:tier,ARRAY[:coverage],CAST(:prompt AS jsonb),"
            "CAST(:solution AS jsonb),:media_ref,:max_plays,false,'2026-08-11T00:00:00Z')"
            " ON CONFLICT (item_id) DO NOTHING"
        ),
        {
            "item": item_id,
            "prompt": json.dumps(prompt, ensure_ascii=False),
            "solution": json.dumps(solution, ensure_ascii=False),
            "section": section_id,
            "ordinal": ordinal,
            "kind": item_kind,
            "weight": 1 / (16 if media_ref else 18),
            "tier": "lower_anchor" if ordinal <= 4 else "transfer" if ordinal > 14 else "current",
            "coverage": coverage_target,
            "media_ref": media_ref,
            "max_plays": max_plays,
        },
    )


def upgrade() -> None:
    statements = (
        """
        CREATE TABLE assessments.assessment_item_plays (
          play_id uuid PRIMARY KEY,
          assessment_run_id uuid NOT NULL REFERENCES assessments.assessment_runs(assessment_run_id) ON DELETE RESTRICT,
          item_id uuid NOT NULL REFERENCES assessments.assessment_items(item_id) ON DELETE RESTRICT,
          owner_account_id uuid NOT NULL REFERENCES identity.accounts(account_id) ON DELETE RESTRICT,
          idempotency_key varchar(255) NOT NULL,
          played_at timestamptz NOT NULL,
          UNIQUE (owner_account_id,assessment_run_id,item_id,idempotency_key)
        )
        """,
        """
        CREATE INDEX ix_assessment_item_plays_count
          ON assessments.assessment_item_plays(assessment_run_id,item_id,played_at)
        """,
        "ALTER TABLE assessments.assessment_item_plays ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE assessments.assessment_item_plays FORCE ROW LEVEL SECURITY",
        """
        CREATE POLICY assessment_item_plays_owner ON assessments.assessment_item_plays
          USING (owner_account_id=assessments.current_user_id())
          WITH CHECK (owner_account_id=assessments.current_user_id())
        """,
        """
        CREATE TRIGGER assessment_item_plays_append_only
          BEFORE UPDATE OR DELETE ON assessments.assessment_item_plays
          FOR EACH ROW EXECUTE FUNCTION assessments.guard_append_only()
        """,
        "GRANT SELECT,INSERT ON assessments.assessment_item_plays TO polyglot_runtime",
        "GRANT ALL PRIVILEGES ON assessments.assessment_item_plays TO polyglot_migration",
        "REVOKE ALL ON assessments.assessment_item_plays FROM PUBLIC",
        "ALTER TABLE assessments.assessment_item_plays OWNER TO polyglot_migration",
    )
    for statement in statements:
        op.execute(statement)

    op.execute(
        """
        INSERT INTO assessments.assessment_definition_revisions
          (assessment_revision_id,assessment_definition_id,revision_no,status,protocol_code,
           coverage_matrix,difficulty_profile,time_limit_ms,pause_policy,security_rules,
           rubric_revision,parallel_form_rules,protocol_fingerprint,created_at)
        SELECT '019feb32-0000-7000-8100-000000002001',assessment_definition_id,2,'published',
          protocol_code,coverage_matrix,difficulty_profile,time_limit_ms,pause_policy,security_rules,
          rubric_revision,parallel_form_rules,
          '94e6f218ebfb9e416c8d3185f99a01ad2f32cadc6e372ec47743d139a4ae5631',
          '2026-08-11T00:00:00Z'
        FROM assessments.assessment_definition_revisions
        WHERE assessment_revision_id='019feb32-0000-7000-8000-000000002001'
        ON CONFLICT (assessment_revision_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO assessments.assessment_definition_revisions
          (assessment_revision_id,assessment_definition_id,revision_no,status,protocol_code,
           coverage_matrix,difficulty_profile,time_limit_ms,pause_policy,security_rules,
           rubric_revision,parallel_form_rules,protocol_fingerprint,created_at)
        SELECT '019feb32-0000-7000-8100-000000002002',assessment_definition_id,2,'published',
          protocol_code,coverage_matrix,difficulty_profile,time_limit_ms,pause_policy,security_rules,
          rubric_revision,parallel_form_rules,
          '57d28919f21d761819b87d9cc07add77e4acd2bebc64feeb4848d49388678dd0',
          '2026-08-11T00:00:00Z'
        FROM assessments.assessment_definition_revisions
        WHERE assessment_revision_id='019feb32-0000-7000-8000-000000002002'
        ON CONFLICT (assessment_revision_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO assessments.assessment_forms
          (form_id,assessment_revision_id,form_code,status,current_band_weight,lower_anchor_weight,
           transfer_weight,calibration_uncertainty,media_cost,coverage_targets,
           required_capabilities,checksum,created_at)
        SELECT '019feb32-0000-7000-8100-000000003001',
          '019feb32-0000-7000-8100-000000002001','IT-READ-B','published',
          current_band_weight,lower_anchor_weight,transfer_weight,calibration_uncertainty,
          media_cost,coverage_targets,required_capabilities,
          '0cf2606d4dd80efad970f161429408a5ed834df9bb6ed4d169b194ea6b44ca04',
          '2026-08-11T00:00:00Z'
        FROM assessments.assessment_forms WHERE form_id='019feb32-0000-7000-8000-000000003001'
        ON CONFLICT (form_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO assessments.assessment_forms
          (form_id,assessment_revision_id,form_code,status,current_band_weight,lower_anchor_weight,
           transfer_weight,calibration_uncertainty,media_cost,coverage_targets,
           required_capabilities,checksum,created_at)
        SELECT '019feb32-0000-7000-8100-000000003002',
          '019feb32-0000-7000-8100-000000002002','IT-LISTEN-B','published',
          current_band_weight,lower_anchor_weight,transfer_weight,calibration_uncertainty,
          media_cost,coverage_targets,required_capabilities,
          '0ff37a71deec473ac0ecaf27d1223795efb49e46a25a3135f33ca227630c2a6f',
          '2026-08-11T00:00:00Z'
        FROM assessments.assessment_forms WHERE form_id='019feb32-0000-7000-8000-000000003002'
        ON CONFLICT (form_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO assessments.assessment_section_definitions
          (section_definition_id,form_id,ordinal,section_type,weight,title,instructions)
        VALUES
          ('019feb32-0000-7000-8100-000000004001','019feb32-0000-7000-8100-000000003001',
           1,'reading_comprehension',1,'Compréhension écrite','Lisez puis répondez sans aide externe.'),
          ('019feb32-0000-7000-8100-000000004002','019feb32-0000-7000-8100-000000003002',
           1,'listening_comprehension',1,'Compréhension orale','Écoutez chaque segment selon le nombre de lectures autorisé.')
        ON CONFLICT (section_definition_id) DO NOTHING
        """
    )

    ordinal = 1
    for title, body, questions in READING_GROUPS:
        for question, options, accepted in questions:
            _insert_item(
                item_id=f"019feb32-0000-7000-8101-{ordinal:012d}",
                section_id="019feb32-0000-7000-8100-000000004001",
                ordinal=ordinal,
                item_kind="single_choice",
                coverage_target=("inference" if ordinal % 3 == 0 else "literal" if ordinal % 3 == 1 else "register"),
                prompt={"title": title, "body": body, "question": question, "options": options},
                solution={"accepted": [accepted], "option_count": len(options)},
            )
            ordinal += 1

    ordinal = 1
    for audio_script, questions in LISTENING_GROUPS:
        for question, options, accepted in questions:
            _insert_item(
                item_id=f"019feb32-0000-7000-8102-{ordinal:012d}",
                section_id="019feb32-0000-7000-8100-000000004002",
                ordinal=ordinal,
                item_kind="listening_choice",
                coverage_target=("inference" if ordinal % 3 == 0 else "global" if ordinal % 3 == 1 else "detail"),
                prompt={
                    "title": f"Ascolto {ordinal}",
                    "question": question,
                    "options": options,
                    "transcript_hidden": True,
                },
                solution={
                    "accepted": [accepted],
                    "option_count": len(options),
                    "audio_script": audio_script,
                },
                media_ref=f"tts:it:assessment:listening:v2:{ordinal}",
                max_plays=2,
            )
            ordinal += 1

    op.execute(
        """
        UPDATE assessments.assessment_definitions SET
          current_revision_id=CASE modality
            WHEN 'reading' THEN '019feb32-0000-7000-8100-000000002001'::uuid
            WHEN 'listening' THEN '019feb32-0000-7000-8100-000000002002'::uuid
            ELSE current_revision_id END,
          version=CASE WHEN modality IN ('reading','listening')
            THEN GREATEST(version,2) ELSE version END,
          updated_at=CASE WHEN modality IN ('reading','listening')
            THEN '2026-08-11T00:00:00Z'::timestamptz ELSE updated_at END
        WHERE modality IN ('reading','listening')
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE assessments.assessment_definitions SET
          current_revision_id=CASE modality
            WHEN 'reading' THEN '019feb32-0000-7000-8000-000000002001'::uuid
            WHEN 'listening' THEN '019feb32-0000-7000-8000-000000002002'::uuid
            ELSE current_revision_id END
        WHERE modality IN ('reading','listening')
        """
    )
    op.execute("DROP TABLE assessments.assessment_item_plays")
