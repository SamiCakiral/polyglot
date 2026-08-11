import { Languages } from "lucide-react";
import { type SyntheticEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useAuthenticateSession, useRegisterAccount } from "../../generated/polyglot";
import { commandFetch, responseProblem } from "../../lib/api";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const navigate = useNavigate();
  const authenticate = useAuthenticateSession({ fetch: commandFetch() });
  const register = useRegisterAccount({ fetch: commandFetch() });
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const isRegister = mode === "register";
  const pending = authenticate.isPending || register.isPending;

  async function submit(event: SyntheticEvent<HTMLFormElement, SubmitEvent>) {
    event.preventDefault();
    setError("");
    const credentials = { identifier, password, provider_type: "local_password" as const };

    if (isRegister) {
      const registration = await register.mutateAsync({ data: credentials });
      const registrationError = responseProblem(registration);
      if (registrationError) {
        setError(registrationError);
        return;
      }
    }

    const session = await authenticate.mutateAsync({ data: credentials });
    const sessionError = responseProblem(session);
    if (sessionError) {
      setError(sessionError);
      return;
    }
    void navigate("/language-profile", { replace: true });
  }

  return (
    <main className="auth-layout">
      <section className="auth-intro">
        <div className="brand-mark"><Languages aria-hidden="true" size={22} /> Polyglot</div>
        <p className="eyebrow">Français vers italien</p>
        <h1>Une pratique courte, reliée à ce que vous apprenez vraiment.</h1>
        <p>Vocabulaire rencontré, structures grammaticales, productions et progrès restent liés dans un même parcours.</p>
        <blockquote lang="it">“Un passo alla volta, ma ogni giorno.”</blockquote>
      </section>
      <section className="auth-form-region">
        <form className="auth-form" onSubmit={(event) => void submit(event)}>
          <div>
            <p className="eyebrow">{isRegister ? "Nouveau parcours" : "Bon retour"}</p>
            <h2>{isRegister ? "Créer un compte" : "Se connecter"}</h2>
          </div>
          <label>Adresse e-mail<input autoComplete="email" name="email" required type="email" value={identifier} onChange={(event) => { setIdentifier(event.target.value); }} /></label>
          <label>Mot de passe<input autoComplete={isRegister ? "new-password" : "current-password"} minLength={12} name="password" required type="password" value={password} onChange={(event) => { setPassword(event.target.value); }} /></label>
          {error ? <p className="form-error" role="alert">{error}</p> : null}
          <button disabled={pending} type="submit">{pending ? "Patientez..." : isRegister ? "Créer mon espace" : "Ouvrir mon espace"}</button>
          <p className="auth-switch">{isRegister ? "Vous avez déjà un compte ?" : "Première visite ?"} <Link to={isRegister ? "/login" : "/register"}>{isRegister ? "Se connecter" : "Créer un compte"}</Link></p>
        </form>
      </section>
    </main>
  );
}
