import { useId } from "react";
export function Field({
  label,
  value,
  onChange,
  nullable = false,
  help,
  min = 0,
  max,
  positive = false,
  integer = false,
  validationError,
}: {
  label: string;
  value: number | string | boolean | null;
  onChange: (value: number | string | boolean | null) => void;
  nullable?: boolean;
  help?: string;
  min?: number;
  max?: number;
  positive?: boolean;
  integer?: boolean;
  validationError?: string;
}) {
  const id = useId();
  const numeric = typeof value === "number" || value === null;
  const upper = max ?? (label.includes("0–1") ? 1 : undefined);
  const error = validationError || (
    numeric && value !== null &&
    (!Number.isFinite(value) || Number(value) < min ||
      (positive && Number(value) <= 0) ||
      (upper !== undefined && Number(value) > upper) ||
      (integer && !Number.isInteger(value)))
      ? `Inserisci ${integer ? "un numero intero" : "un numero"} ${positive ? "maggiore di zero" : `da ${min}`}${upper !== undefined ? ` e fino a ${upper}` : ""}.`
      : typeof value === "string" && !value.trim()
        ? "Inserisci un nome o un’etichetta."
        : ""
  );
  const describedBy = [help ? `${id}-help` : "", error ? `${id}-error` : ""].filter(Boolean).join(" ") || undefined;
  return (
    <div className="formField">
      <label htmlFor={id}>{label}</label>
      {typeof value === "boolean" ? (
        <input
          id={id}
          type="checkbox"
          aria-describedby={describedBy}
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
        />
      ) : (
        <input
          id={id}
          type={numeric ? "number" : "text"}
          min={numeric ? min : undefined}
          max={upper}
          step={integer ? 1 : "any"}
          aria-invalid={!!error}
          aria-describedby={describedBy}
          value={
            typeof value === "number" && !Number.isFinite(value)
              ? ""
              : (value ?? "")
          }
          onChange={(e) =>
            onChange(
              numeric
                ? e.target.value === ""
                  ? nullable
                    ? null
                    : NaN
                  : Number(e.target.value)
                : e.target.value,
            )
          }
        />
      )}{" "}
      {help && <small id={`${id}-help`} className="fieldHelp">{help}</small>}
      {error && (
        <small id={`${id}-error`} className="fieldError">
          {error}
        </small>
      )}
    </div>
  );
}

