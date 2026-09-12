import { Field } from "./Field";
import type { DemoConfig } from "./types";
const fields: Record<string, [string, string]> = {
  confidence: ["Affidabilità minima del rilevamento (0–1)", "Scarta i rilevamenti meno sicuri. Un valore più alto riduce i rilevamenti accettati."],
  iou: ["Sovrapposizione consentita tra rilevamenti (0–1)", "Aiuta a eliminare riquadri duplicati sullo stesso oggetto. Un valore più basso elimina più sovrapposizioni."],
  image_size: ["Dimensione immagine per l’analisi (pixel)", "Numero intero da 32 a 4096. Una dimensione maggiore richiede più risorse di calcolo."],
  stationary_s: ["Tempo minimo di immobilità (secondi)", "Per quanto tempo il bagaglio deve restare fermo prima di essere considerato immobile."],
  unattended_s: ["Attesa prima dell’allarme bagaglio (secondi)", "Tempo senza sorveglianza necessario per segnalare un bagaglio immobile."],
  association_distance_norm: ["Distanza per riconoscere l’accompagnatore (0–1)", "Distanza massima iniziale tra persona e oggetto, come frazione della diagonale dell’immagine: 0,10 significa il 10%. Non è una distanza in metri."],
  association_confirm_s: ["Tempo per confermare l’accompagnatore (secondi)", "La persona deve restare vicina per questo tempo per essere associata al bagaglio o all’animale."],
  owner_distance_norm: ["Distanza massima dal proprietario (0–1)", "Oltre questa distanza il bagaglio può risultare non sorvegliato. Frazione della diagonale dell’immagine, non metri."],
  owner_missing_grace_s: ["Tolleranza se la persona non è visibile (secondi)", "Attesa prima di considerare assente una persona non più rilevata, ad esempio durante un’occlusione."],
  require_owner_association: ["Segnala solo dopo aver identificato una persona", "Se attivo, l’allarme richiede una precedente associazione con una persona. Se disattivo, può riguardare anche oggetti mai associati."],
  cooldown_s: ["Pausa minima tra due segnalazioni (secondi)", "Limita le segnalazioni ripetute per lo stesso evento. Non cambia il tempo necessario al primo allarme."],
  supervision_distance_norm: ["Distanza massima di sorveglianza (0–1)", "Oltre questa distanza dall’accompagnatore l’animale può risultare non sorvegliato. Frazione della diagonale dell’immagine, non metri."],
  unsupervised_s: ["Attesa prima dell’allarme animale (secondi)", "Tempo senza sorveglianza necessario per generare una segnalazione."],
};
const order = {
  model: ["confidence", "iou", "image_size"],
  luggage: ["require_owner_association", "association_distance_norm", "association_confirm_s", "owner_distance_norm", "owner_missing_grace_s", "stationary_s", "unattended_s", "cooldown_s"],
  animal: ["require_owner_association", "association_distance_norm", "association_confirm_s", "supervision_distance_norm", "owner_missing_grace_s", "unsupervised_s", "cooldown_s"],
};
export function TuningPanel({
  config,
  onChange,
}: {
  config: DemoConfig;
  onChange: (c: DemoConfig) => void;
}) {
  return (
    <section className="panel">
      <h2>Parametri dell’analisi</h2>
      <p>
        Le modifiche vengono applicate dopo il salvataggio e il riavvio
        dell’analisi.
      </p>
      <div className="tuningGrid">
        {(["model", "luggage", "animal"] as const).map((group) => (
          <fieldset key={group}>
            <legend>
              {group === "model"
                ? "Rilevamento AI"
                : group === "luggage"
                  ? "Bagagli incustoditi"
                  : "Animali non sorvegliati"}
            </legend>
            <p className="tuningIntro">{group === "model" ? "Regola la sensibilità generale del riconoscimento." : "Imposta prima l’associazione con la persona, poi l’attesa e la frequenza degli allarmi."}</p>
            {order[group].map((key) => {
              const value = (group === "model" ? config.model : config.analytics[group])[key];
              if (value === undefined) return null;
              return <Field
                key={key}
                label={fields[key][0]}
                help={fields[key][1]}
                min={key === "image_size" ? 32 : 0}
                max={key === "image_size" ? 4096 : key.endsWith("_norm") || ["confidence", "iou"].includes(key) ? 1 : undefined}
                integer={key === "image_size"}
                value={value}
                onChange={(next) => {
                  const copy = structuredClone(config);
                  if (group === "model") copy.model[key] = next as number;
                  else copy.analytics[group][key] = next as number | boolean;
                  onChange(copy);
                }}
              />;
            })}
          </fieldset>
        ))}
      </div>
    </section>
  );
}
