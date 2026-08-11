export function languageDisplayName(
  languageTag: string | null | undefined,
  interfaceLocale = "fr-FR",
): string {
  if (!languageTag) return "langue cible";
  try {
    const language = new Intl.Locale(languageTag).language;
    return (
      new Intl.DisplayNames([interfaceLocale], { type: "language" }).of(
        language,
      ) ?? languageTag
    );
  } catch {
    return languageTag;
  }
}

export function languageWithDefiniteArticle(languageTag: string): string {
  const name = languageDisplayName(languageTag);
  return /^[aeiouyhàâäéèêëîïôöùûü]/i.test(name)
    ? `l’${name}`
    : `le ${name}`;
}
