#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKS = {
    "IT": {
        "pack_revision_id": "019b0000-0000-7000-8000-000000000009",
        "target_language_tag": "it-IT",
        "support_language_tag": "fr-FR",
        "samples": {
            "script": ("Quel groupe se prononce avec un son dur ?", "casa", "cena"),
            "reading": ("Que signifie « Il treno parte alle otto » ?", "Le train part à huit heures", "Le train arrive à huit heures"),
            "listening": ("Écoutez puis choisissez le sens principal.", "Le train part à huit heures", "Le train est annulé"),
            "vocabulary": ("Que signifie « comunque » ?", "cependant / de toute façon", "seulement"),
            "grammar_functions": ("Complétez : Domani ___ prendere il treno.", "vado a", "sono"),
            "writing": ("Écrivez une demande polie pour faire répéter.", "Può ripetere, per favore?", ""),
            "interaction_repair": ("Vous n'avez pas compris. Que dites-vous ?", "Non ho capito, può ripetere?", "Ciao"),
            "pragmatics_register": ("Dans une boutique, quelle ouverture convient ?", "Buongiorno", "Ehi"),
        },
    },
    "JA": {
        "pack_revision_id": "019c0000-0000-7000-9000-000000000009",
        "target_language_tag": "ja-JP",
        "support_language_tag": "fr-FR",
        "samples": {
            "script": ("Quelle lecture correspond à あ ?", "a", "i"),
            "reading": ("Que signifie « えきはどこですか » ?", "Où est la gare ?", "Quel est ce train ?"),
            "listening": ("Écoutez puis choisissez le sens principal.", "Où est la gare ?", "Merci beaucoup"),
            "vocabulary": ("Que signifie « みず » ?", "eau", "riz"),
            "grammar_functions": ("Complétez la demande : みず___ください。", "を", "は"),
            "writing": ("Écrivez une salutation de journée.", "こんにちは", ""),
            "interaction_repair": ("Demandez de répéter.", "もういちどおねがいします", "ありがとう"),
            "pragmatics_register": ("Attirez poliment l'attention.", "すみません", "じゃあね"),
        },
    },
}


def build(code: str, source: dict[str, object]) -> dict[str, object]:
    items: list[dict[str, object]] = []
    samples = source["samples"]
    assert isinstance(samples, dict)
    ordinal = 1
    for skill, sample in samples.items():
        prompt, correct, distractor = sample
        for level in range(0, 9):
            namespace = 8100 if code == "IT" else 9100
            uid = f"019d0000-0000-7000-{namespace:04d}-{ordinal:012d}"
            variant_uid = f"019d0000-0000-7000-{namespace + 1:04d}-{ordinal:012d}"
            open_task = skill == "writing" and level >= 3
            items.append(
                {
                    "blueprint_revision_id": uid,
                    "variant_revision_id": variant_uid,
                    "variant_pool_id": f"{code.lower()}.{skill}.l{level}",
                    "primitive_ref": "free_text" if open_task else "single_choice",
                    "primary_skill_ref": skill,
                    "secondary_skill_refs": [],
                    "level": level,
                    "estimated_seconds": 55 if open_task else 30,
                    "scoring_kind": "structured_lm" if open_task else "deterministic",
                    "media_required": skill == "listening",
                    "payload": {
                        "prompt": prompt,
                        "response_kind": "text" if open_task else "single_choice",
                        "choices": [] if open_task else [correct, distractor],
                        "tts_text": correct if skill == "listening" else None,
                    },
                    "answer_key": None if open_task else {"value": correct},
                }
            )
            ordinal += 1
    return {
        "schema_version": 1,
        "pack_revision_id": source["pack_revision_id"],
        "target_language_tag": source["target_language_tag"],
        "support_language_tag": source["support_language_tag"],
        "items": items,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    mismatches: list[str] = []
    for code, source in PACKS.items():
        destination = ROOT / "fixtures" / "canonical" / f"FX-PLACEMENT-{code}" / "catalogue.json"
        rendered = json.dumps(build(code, source), ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not destination.exists() or destination.read_text() != rendered:
                mismatches.append(str(destination))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(rendered)
            manifest = {
                "id": f"FX-PLACEMENT-{code}",
                "kind": "positive",
                "expected_status": "accepted",
            }
            (destination.parent / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
    if mismatches:
        raise SystemExit("outdated placement fixtures: " + ", ".join(mismatches))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
