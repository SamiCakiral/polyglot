import { Download, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useActiveProfile } from "../../app/profile-state";
import { useSession } from "../../app/session-context";
import {
  ErrorRegion,
  NoProfile,
  PageHeader,
  StatusPill,
} from "../../components/product-ui";
import {
  deleteLanguageProfile,
  requestExport,
  updateUserPreferences,
} from "../../generated/polyglot";
import { commandFetch, responseProblem } from "../../lib/api";

export function SettingsPage() {
  const session = useSession();
  const { activeProfile } = useActiveProfile();
  const navigate = useNavigate();
  const [minutes, setMinutes] = useState(
    session.preferences.preferred_sprint_minutes,
  );
  const [reducedMotion, setReducedMotion] = useState(
    Boolean(session.preferences.accessibility_preferences.reduced_motion),
  );
  const [manualAudio, setManualAudio] = useState(
    session.preferences.media_preferences.autoplay_audio !== true,
  );
  const [deleteConfirmation, setDeleteConfirmation] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  if (!activeProfile) return <NoProfile />;
  const profile = activeProfile;

  async function save() {
    setBusy(true);
    setError("");
    setNotice("");
    const response = await updateUserPreferences(
      {
        accessibility_preferences: {
          schema_version: 1,
          reduced_motion: reducedMotion,
        },
        interface_locale: "fr-FR",
        media_preferences: { schema_version: 1, autoplay_audio: !manualAudio },
        preferred_sprint_minutes: minutes,
        timezone: session.preferences.timezone,
      },
      commandFetch(session, session.preferences.version),
    );
    const problem = responseProblem(response);
    if (problem) setError(problem);
    else if (response.status === 200) setNotice("Préférences enregistrées.");
    setBusy(false);
  }

  async function exportData() {
    setBusy(true);
    setError("");
    setNotice("");
    const response = await requestExport(
      profile.profile_id,
      {
        requested_at: new Date().toISOString(),
        scope: {
          format: "json",
          include: ["profile", "word_bank", "memory", "attempts", "progress"],
        },
      },
      commandFetch(session),
    );
    const problem = responseProblem(response);
    if (problem) setError(problem);
    else if (response.status === 202)
      setNotice(`Export demandé. Référence : ${response.data.resource_id}`);
    setBusy(false);
  }

  async function deleteProfile() {
    if (deleteConfirmation !== "SUPPRIMER") return;
    setBusy(true);
    setError("");
    const response = await deleteLanguageProfile(
      profile.profile_id,
      commandFetch(session, profile.version),
    );
    const problem = responseProblem(response);
    if (problem) {
      setError(problem);
      setBusy(false);
      return;
    }
    localStorage.removeItem("polyglot.active-profile");
    localStorage.removeItem("polyglot.active-run");
    void navigate("/language-profile");
  }

  return (
    <div className="page-flow page-flow--narrow">
      <PageHeader
        eyebrow="Compte"
        title="Préférences"
        description="Réglages d'interface, de rythme, de médias et gestion de vos données."
      />
      <section className="settings-form">
        <label>
          Durée préférée
          <select
            value={minutes}
            onChange={(event) => {
              setMinutes(Number(event.target.value));
            }}
          >
            <option value={10}>10 minutes</option>
            <option value={20}>20 minutes</option>
            <option value={30}>30 minutes</option>
            <option value={45}>45 minutes</option>
            <option value={60}>60 minutes</option>
          </select>
        </label>
        <label>
          Langue de l'interface
          <select value="fr-FR" disabled>
            <option value="fr-FR">Français</option>
          </select>
        </label>
        <label className="choice-row">
          <input
            checked={reducedMotion}
            type="checkbox"
            onChange={(event) => {
              setReducedMotion(event.target.checked);
            }}
          />
          <span>Réduire les animations</span>
        </label>
        <label className="choice-row">
          <input
            checked={manualAudio}
            type="checkbox"
            onChange={(event) => {
              setManualAudio(event.target.checked);
            }}
          />
          <span>Lire l'audio uniquement sur action</span>
        </label>
        {error ? <ErrorRegion message={error} /> : null}
        {notice ? (
          <p className="success-notice" role="status">
            {notice}
          </p>
        ) : null}
        <button disabled={busy} type="button" onClick={() => void save()}>
          <Save aria-hidden="true" size={18} /> Enregistrer
        </button>
      </section>
      <section className="data-management">
        <div>
          <p className="eyebrow">Portabilité</p>
          <h2>Exporter mes données</h2>
          <p>
            Prépare un export JSON de votre profil, de la Word Bank, de la
            mémoire, des productions et de la progression.
          </p>
        </div>
        <button
          className="secondary-button"
          disabled={busy}
          type="button"
          onClick={() => void exportData()}
        >
          <Download aria-hidden="true" size={18} /> Demander l'export
        </button>
      </section>
      <section className="danger-zone">
        <div>
          <p className="eyebrow">Zone sensible</p>
          <h2>Supprimer ce profil de langue</h2>
          <p>
            La demande place le profil en suppression et lance le cycle de purge
            contrôlé.
          </p>
        </div>
        <StatusPill tone="warn">Action irréversible</StatusPill>
        <label>
          Écrivez SUPPRIMER pour confirmer
          <input
            value={deleteConfirmation}
            onChange={(event) => {
              setDeleteConfirmation(event.target.value);
            }}
          />
        </label>
        <button
          className="danger-button"
          disabled={busy || deleteConfirmation !== "SUPPRIMER"}
          type="button"
          onClick={() => void deleteProfile()}
        >
          <Trash2 aria-hidden="true" size={18} /> Demander la suppression
        </button>
      </section>
    </div>
  );
}
