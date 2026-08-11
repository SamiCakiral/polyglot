const knownModules: Record<
  string,
  { description: string; title: string }
> = {
  "IT-FIRST-AUTONOMOUS-EXCHANGE": {
    description:
      "Entrer en contact, obtenir quelque chose et réparer un échange simple.",
    title: "Premiers échanges autonomes",
  },
};

function sentence(value: string): string {
  const trimmed = value.trim().replace(/[.!?]+$/, "");
  if (!trimmed) return "Module d'apprentissage";
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
}

export function modulePresentation(moduleCode: string, intention: string) {
  const known = knownModules[moduleCode];
  if (known) return known;
  const title = sentence(intention);
  return { description: `${title}.`, title };
}
