import { matchPath } from "react-router-dom";

export interface ShellRouteDefinition {
  path: string;
  title: string;
}

export const shellRoutes: readonly ShellRouteDefinition[] = [
  { path: "/today", title: "Aujourd'hui" },
  { path: "/learn", title: "Apprendre" },
  { path: "/learn/modules/:moduleId", title: "Détail du module" },
  { path: "/practice", title: "S'entraîner" },
  { path: "/practice/configure", title: "Configurer l'entraînement" },
  { path: "/sprints/:runId", title: "Séance en cours" },
  { path: "/vocabulary", title: "Vocabulaire" },
  { path: "/vocabulary/lists/:listId", title: "Liste de vocabulaire" },
  { path: "/vocabulary/senses/:senseId", title: "Détail du mot" },
  { path: "/progress", title: "Progression" },
  { path: "/progress/skills/:skillId", title: "Détail de la compétence" },
  { path: "/assess", title: "Évaluer" },
  { path: "/assess/:modality", title: "Protocole d'évaluation" },
  { path: "/assess/runs/:assessmentRunId", title: "Évaluation en cours" },
  { path: "/language-profile", title: "Profil de langue" },
  { path: "/settings", title: "Préférences" },
  { path: "/authoring", title: "Atelier" },
  { path: "/authoring/drafts", title: "Brouillons" },
  { path: "/authoring/tools", title: "Outils auteur" },
  { path: "/authoring/generate", title: "Génération" },
] as const;

export function getShellRouteTitle(pathname: string): string {
  return (
    shellRoutes.find(({ path }) => matchPath({ path, end: true }, pathname))?.title ??
    "Page introuvable"
  );
}
