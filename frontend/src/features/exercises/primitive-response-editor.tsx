import type { AnswerKind, JsonValueInput } from "../../generated/model";
import type { PrimitiveResponse } from "./primitive-response";

type Contract = Record<string, JsonValueInput>;

interface Option {
  label: string;
  value: string;
}

function options(contract: Contract, key = "choices"): Option[] {
  const values = contract[key];
  if (!Array.isArray(values)) return [];
  return values.flatMap((item) => {
    if (typeof item === "string") return [{ label: item, value: item }];
    if (typeof item !== "object" || item === null || Array.isArray(item))
      return [];
    const value = item.value ?? item.id ?? item.key;
    const label = item.label ?? item.text ?? value;
    return typeof value === "string" && typeof label === "string"
      ? [{ label, value }]
      : [];
  });
}

function recordValue(value: PrimitiveResponse): Record<string, JsonValueInput> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : {};
}

function fieldValue(
  record: Record<string, JsonValueInput>,
  key: string,
): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function stringList(value: PrimitiveResponse): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function ChoiceEditor({ contract, kind, value, onChange }: EditorProps) {
  const available =
    kind === "self_grade"
      ? [
          { value: "again", label: "À revoir" },
          { value: "hard", label: "Difficile" },
          { value: "good", label: "Correct" },
          { value: "easy", label: "Facile" },
        ]
      : options(contract);
  return (
    <fieldset className="primitive-options">
      <legend>Choisissez une réponse</legend>
      {available.map((option) => (
        <label key={option.value}>
          <input
            checked={value === option.value}
            name="primitive-choice"
            type="radio"
            value={option.value}
            onChange={() => {
              onChange(option.value);
            }}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

function SelectionEditor({ contract, value, onChange }: EditorProps) {
  const selected = stringList(value);
  return (
    <fieldset className="primitive-options primitive-options--multiple">
      <legend>Sélectionnez toutes les réponses qui conviennent</legend>
      {options(contract).map((option) => (
        <label key={option.value}>
          <input
            checked={selected.includes(option.value)}
            type="checkbox"
            onChange={() => {
              onChange(
                selected.includes(option.value)
                  ? selected.filter((item) => item !== option.value)
                  : [...selected, option.value],
              );
            }}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

function SpanEditor({ contract, value, onChange }: EditorProps) {
  const segments = options(contract, "segments");
  const selected = Array.isArray(value)
    ? value.filter(
        (item): item is JsonValueInput[] =>
          Array.isArray(item) && item.length === 2,
      )
    : [];
  return (
    <fieldset className="primitive-options primitive-options--multiple">
      <legend>Repérez les segments demandés</legend>
      {segments.map((segment) => {
        const [startValue, endValue] = segment.value.split(":");
        const span = [Number(startValue), Number(endValue)];
        const checked = selected.some(
          (item) => item[0] === span[0] && item[1] === span[1],
        );
        return (
          <label key={segment.value}>
            <input
              checked={checked}
              type="checkbox"
              onChange={() => {
                onChange(
                  checked
                    ? selected.filter(
                        (item) => item[0] !== span[0] || item[1] !== span[1],
                      )
                    : [...selected, span],
                );
              }}
            />
            <span>{segment.label}</span>
          </label>
        );
      })}
    </fieldset>
  );
}

function MappingEditor({ contract, kind, value, onChange }: EditorProps) {
  const sources = options(contract, "items");
  const destinations = options(
    contract,
    kind === "grouping" ? "groups" : "matches",
  );
  const current = recordValue(value);
  const assignment = (source: string): string => {
    if (kind !== "grouping") return fieldValue(current, source);
    return (
      destinations.find((destination) => {
        const members = current[destination.value];
        return Array.isArray(members) && members.includes(source);
      })?.value ?? ""
    );
  };
  const assign = (source: string, destination: string) => {
    if (kind !== "grouping") {
      onChange({ ...current, [source]: destination });
      return;
    }
    const next = Object.fromEntries(
      destinations.map((group) => {
        const members = current[group.value];
        return [
          group.value,
          Array.isArray(members)
            ? members.filter((item) => item !== source)
            : [],
        ];
      }),
    );
    if (destination) {
      next[destination] = [...(next[destination] ?? []), source];
    }
    onChange(next);
  };
  return (
    <fieldset className="primitive-mapping">
      <legend>
        {kind === "grouping"
          ? "Classez chaque élément"
          : "Associez les éléments"}
      </legend>
      {sources.map((source) => (
        <label key={source.value}>
          <span>{source.label}</span>
          <select
            value={assignment(source.value)}
            onChange={(event) => {
              assign(source.value, event.target.value);
            }}
          >
            <option value="">Choisir…</option>
            {destinations.map((destination) => (
              <option key={destination.value} value={destination.value}>
                {destination.label}
              </option>
            ))}
          </select>
        </label>
      ))}
    </fieldset>
  );
}

function OrderEditor({ contract, value, onChange }: EditorProps) {
  const available = options(contract, "items");
  const ordered = stringList(value);
  const sequence =
    ordered.length > 0 ? ordered : available.map((item) => item.value);
  const labels = new Map(available.map((item) => [item.value, item.label]));
  function move(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= sequence.length) return;
    const next = [...sequence];
    const current = next[index];
    const displaced = next[target];
    if (current === undefined || displaced === undefined) return;
    next[index] = displaced;
    next[target] = current;
    onChange(next);
  }
  return (
    <fieldset className="primitive-order">
      <legend>Remettez les éléments dans l’ordre</legend>
      {sequence.map((item, index) => (
        <div key={`${item}-${index.toString()}`}>
          <span>{labels.get(item) ?? item}</span>
          <button
            aria-label={`Monter ${labels.get(item) ?? item}`}
            disabled={index === 0}
            type="button"
            onClick={() => {
              move(index, -1);
            }}
          >
            ↑
          </button>
          <button
            aria-label={`Descendre ${labels.get(item) ?? item}`}
            disabled={index === sequence.length - 1}
            type="button"
            onClick={() => {
              move(index, 1);
            }}
          >
            ↓
          </button>
        </div>
      ))}
    </fieldset>
  );
}

function CellsEditor({ contract, value, onChange }: EditorProps) {
  const cells = options(contract, "cells");
  const current = recordValue(value);
  return (
    <fieldset className="primitive-cells">
      <legend>Complétez chaque forme</legend>
      {cells.map((cell) => (
        <label key={cell.value}>
          <span>{cell.label}</span>
          <input
            autoComplete="off"
            value={fieldValue(current, cell.value)}
            onChange={(event) => {
              onChange({ ...current, [cell.value]: event.target.value });
            }}
          />
        </label>
      ))}
    </fieldset>
  );
}

function TokenEditor({ contract, value, onChange }: EditorProps) {
  const slots = options(contract, "slots");
  if (slots.length === 0) {
    return (
      <label className="answer-field">
        Mots manquants
        <input
          autoComplete="off"
          placeholder="Séparez les mots par une espace"
          value={stringList(value).join(" ")}
          onChange={(event) => {
            onChange(event.target.value.split(/\s+/u).filter(Boolean));
          }}
        />
      </label>
    );
  }
  const current = stringList(value);
  return (
    <fieldset className="primitive-cells">
      <legend>Complétez les blancs</legend>
      {slots.map((slot, index) => (
        <label key={slot.value}>
          <span>{slot.label}</span>
          <input
            autoComplete="off"
            value={current[index] ?? ""}
            onChange={(event) => {
              const next = [...current];
              next[index] = event.target.value;
              onChange(next);
            }}
          />
        </label>
      ))}
    </fieldset>
  );
}

interface EditorProps {
  contract: Contract;
  kind: AnswerKind;
  value: PrimitiveResponse;
  onChange: (value: PrimitiveResponse) => void;
}

export function PrimitiveResponseEditor(props: EditorProps) {
  const { kind, value, onChange } = props;
  if (
    kind === "single_choice" ||
    kind === "graded_choice" ||
    kind === "self_grade"
  ) {
    return <ChoiceEditor {...props} />;
  }
  if (kind === "selection") {
    return <SelectionEditor {...props} />;
  }
  if (kind === "spans") return <SpanEditor {...props} />;
  if (kind === "pairing" || kind === "grouping") {
    return <MappingEditor {...props} />;
  }
  if (kind === "ordered_items") return <OrderEditor {...props} />;
  if (kind === "cells") return <CellsEditor {...props} />;
  if (kind === "tokens") return <TokenEditor {...props} />;
  if (
    kind === "self_assessment" ||
    kind === "acknowledgement" ||
    kind === "no_answer"
  ) {
    return null;
  }
  return (
    <label className="answer-field">
      Votre réponse
      {kind === "short_text" ? (
        <input
          autoComplete="off"
          autoFocus
          maxLength={500}
          value={typeof value === "string" ? value : ""}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      ) : (
        <textarea
          autoFocus
          rows={kind === "audio_ref" ? 3 : 6}
          value={typeof value === "string" ? value : ""}
          onChange={(event) => {
            onChange(event.target.value);
          }}
        />
      )}
    </label>
  );
}
