// Dynamic form renderer from JSON Schema properties. Author: Al Amin Ahamed.
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";

interface JsonSchemaFormProps {
  schema: Record<string, unknown>;
  value: Record<string, unknown>;
  onChange: (value: Record<string, unknown>) => void;
}

interface PropertySchema {
  type?: string;
  format?: string;
  enum?: string[];
  title?: string;
  description?: string;
}

function BooleanToggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onChange(!checked)}
      aria-checked={checked}
      role="switch"
      className={cn(
        "relative inline-flex h-4 w-7 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        checked ? "bg-success" : "bg-muted-foreground/40",
      )}
    >
      <span
        className={cn(
          "pointer-events-none block h-3 w-3 rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-3" : "translate-x-0",
        )}
      />
    </button>
  );
}

function RawJsonTextarea({
  value,
  onChange,
}: {
  value: Record<string, unknown>;
  onChange: (v: Record<string, unknown>) => void;
}) {
  const [raw, setRaw] = useState(() => JSON.stringify(value, null, 2));
  const [error, setError] = useState<string | null>(null);

  // Sync raw state when value changes externally (but only if not currently editing)
  useEffect(() => {
    try {
      if (JSON.stringify(JSON.parse(raw)) !== JSON.stringify(value)) {
        setRaw(JSON.stringify(value, null, 2));
      }
    } catch {
      // raw is invalid JSON — don't overwrite user edits
    }
  }, [value]); // eslint-disable-line react-hooks/exhaustive-deps

  function handleBlur() {
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      setError(null);
      onChange(parsed);
    } catch {
      setError("Invalid JSON — changes not saved");
    }
  }

  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium mb-1">
        Configuration (JSON)
      </label>
      <textarea
        className={cn(
          "w-full rounded border bg-background px-3 py-1.5 text-sm font-mono focus:outline-none focus:ring-1 focus:ring-ring min-h-[120px] resize-y",
          error ? "border-destructive" : "border-border",
        )}
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          setError(null);
        }}
        onBlur={handleBlur}
        spellCheck={false}
      />
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
    </div>
  );
}

function SchemaField({
  fieldKey,
  prop,
  required,
  value,
  onChange,
}: {
  fieldKey: string;
  prop: PropertySchema;
  required: boolean;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const label = (prop.title ?? fieldKey) + (required ? " *" : "");
  const inputClass =
    "w-full rounded border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring";

  function renderControl() {
    const { type, format, enum: enumValues } = prop;

    // Boolean toggle
    if (type === "boolean") {
      return (
        <div className="flex items-center gap-2 mt-1">
          <BooleanToggle
            checked={Boolean(value)}
            onChange={onChange}
          />
          <span className="text-sm text-muted-foreground">
            {Boolean(value) ? "Enabled" : "Disabled"}
          </span>
        </div>
      );
    }

    // Enum → select
    if (type === "string" && enumValues && enumValues.length > 0) {
      return (
        <select
          className={inputClass}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          {enumValues.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      );
    }

    // Password
    if (type === "string" && format === "password") {
      return (
        <input
          type="password"
          className={inputClass}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          autoComplete="new-password"
        />
      );
    }

    // URI
    if (type === "string" && format === "uri") {
      return (
        <input
          type="url"
          className={inputClass}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    }

    // Plain string
    if (type === "string") {
      return (
        <input
          type="text"
          className={inputClass}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        />
      );
    }

    // Number / integer
    if (type === "integer" || type === "number") {
      return (
        <input
          type="number"
          className={inputClass}
          value={value === undefined || value === null ? "" : String(value)}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "") {
              onChange(undefined);
            } else {
              onChange(type === "integer" ? parseInt(v, 10) : parseFloat(v));
            }
          }}
        />
      );
    }

    // Fallback: plain text
    return (
      <input
        type="text"
        className={inputClass}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }

  return (
    <div>
      {prop.type !== "boolean" && (
        <label className="block text-xs font-medium mb-1">{label}</label>
      )}
      {prop.type === "boolean" && (
        <label className="block text-xs font-medium">{label}</label>
      )}
      {renderControl()}
      {prop.description && (
        <p className="text-xs text-muted-foreground mt-0.5">{prop.description}</p>
      )}
    </div>
  );
}

export function JsonSchemaForm({ schema, value, onChange }: JsonSchemaFormProps) {
  const properties = schema.properties as Record<string, PropertySchema> | undefined;
  const requiredFields = new Set<string>(
    Array.isArray(schema.required) ? (schema.required as string[]) : [],
  );

  // No properties → raw JSON textarea fallback
  if (!properties || Object.keys(properties).length === 0) {
    return (
      <RawJsonTextarea
        value={value}
        onChange={onChange}
      />
    );
  }

  function handleFieldChange(key: string, fieldValue: unknown) {
    onChange({ ...value, [key]: fieldValue });
  }

  return (
    <div className="space-y-3">
      {Object.entries(properties).map(([key, prop]) => (
        <SchemaField
          key={key}
          fieldKey={key}
          prop={prop}
          required={requiredFields.has(key)}
          value={value[key]}
          onChange={(v) => handleFieldChange(key, v)}
        />
      ))}
    </div>
  );
}
