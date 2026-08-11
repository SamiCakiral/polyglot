import {
  Navigate,
  createBrowserRouter,
  createMemoryRouter,
  type RouteObject,
} from "react-router-dom";
import { AuthPage } from "../features/auth/auth-page";
import {
  AssessPage,
  AssessmentProtocolPage,
  AssessmentRunPage,
} from "../features/assess/assess-page";
import { LearnPage, ModuleDetailPage } from "../features/learn/learn-page";
import {
  PracticePage,
  PracticeRunPage,
} from "../features/practice/practice-page";
import {
  ProgressPage,
  ProgressSkillDetailPage,
} from "../features/progress/progress-page";
import { LanguageProfilePage } from "../features/profile/profile-page";
import { SettingsPage } from "../features/settings/settings-page";
import { SprintPage } from "../features/sprint/sprint-page";
import { TodayPage } from "../features/today/today-page";
import {
  VocabularyListDetailPage,
  VocabularyPage,
  VocabularySenseDetailPage,
} from "../features/vocabulary/vocabulary-page";
import {
  AuthoringPage,
  AuthoringToolsPage,
  DraftsPage,
  GenerationPage,
} from "../features/authoring/authoring-page";
import { shellRoutes } from "./navigation";
import { ProtectedFocus, ProtectedShell } from "./protected-routes";
import { RouteErrorBoundary } from "./route-error-boundary";
import { NotFoundRoute } from "./shell-route";

const routeElements: Record<string, React.ReactNode> = {
  "/today": <TodayPage />,
  "/learn": <LearnPage />,
  "/learn/modules/:moduleId": <ModuleDetailPage />,
  "/practice": <PracticePage />,
  "/practice/configure": <PracticePage />,
  "/vocabulary": <VocabularyPage />,
  "/vocabulary/lists/:listId": <VocabularyListDetailPage />,
  "/vocabulary/senses/:senseId": <VocabularySenseDetailPage />,
  "/progress": <ProgressPage />,
  "/progress/skills/:skillId": <ProgressSkillDetailPage />,
  "/assess": <AssessPage />,
  "/assess/:modality": <AssessmentProtocolPage />,
  "/language-profile": <LanguageProfilePage />,
  "/settings": <SettingsPage />,
  "/authoring": <AuthoringPage />,
  "/authoring/drafts": <DraftsPage />,
  "/authoring/tools": <AuthoringToolsPage />,
  "/authoring/generate": <GenerationPage />,
};

const routes: RouteObject[] = [
  {
    path: "/login",
    element: <AuthPage mode="login" />,
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/register",
    element: <AuthPage mode="register" />,
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/sprints/:runId",
    element: (
      <ProtectedFocus>
        <SprintPage />
      </ProtectedFocus>
    ),
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/practice/runs/:practiceRunId",
    element: (
      <ProtectedFocus>
        <PracticeRunPage />
      </ProtectedFocus>
    ),
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/assess/runs/:assessmentRunId",
    element: (
      <ProtectedFocus>
        <AssessmentRunPage />
      </ProtectedFocus>
    ),
    errorElement: <RouteErrorBoundary />,
  },
  {
    path: "/",
    element: <ProtectedShell />,
    errorElement: <RouteErrorBoundary />,
    children: [
      { index: true, element: <Navigate replace to="/today" /> },
      ...shellRoutes
        .filter(
          ({ path }) =>
            !["/sprints/:runId", "/assess/runs/:assessmentRunId"].includes(
              path,
            ),
        )
        .map(({ path }) => ({
          path,
          element: routeElements[path] ?? <NotFoundRoute />,
        })),
      { path: "*", element: <NotFoundRoute /> },
    ],
  },
];

export function createAppRouter(initialEntries?: string[]) {
  if (initialEntries) {
    return createMemoryRouter(routes, { initialEntries });
  }

  return createBrowserRouter(routes);
}
