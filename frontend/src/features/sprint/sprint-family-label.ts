import { languageWithDefiniteArticle } from "../../lib/language-display";

const familyLabels: Record<string, string> = {
  lexical_acquisition: "Vocabulaire du jour",
  vocabulary: "Vocabulaire du jour",
  recall_warmup: "Rappel actif",
  memory_review: "Rappels à échéance",
  grammar_toolbox: "Boîte grammaticale",
  transformation_gym: "Gym de transformation",
  gym: "Gym de transformation",
  listening: "Compréhension orale",
  shadowing: "Écoute et shadowing",
  guided_output: "Expression guidée",
  free_writing: "Expression écrite",
  delayed_recode: "Inversion J+1",
  reflection_close: "Bilan de séance",
};

export function sprintFamilyLabel(
  family: string,
  targetLanguageTag: string,
): string {
  if (family === "version_input" || family === "version") {
    return `Comprendre ${languageWithDefiniteArticle(targetLanguageTag)}`;
  }
  return familyLabels[family] ?? family;
}
