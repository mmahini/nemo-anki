import type { Conjugation } from "../auth/api";
import SpeakButton from "./SpeakButton";

/** A verb card's conjugation table: one row per tense/situation, showing the
 * conjugated form (with audio) and its meaning. */
export default function ConjTable({ rows, lang }: { rows: Conjugation[]; lang: string }) {
  return (
    <table className="conjtable">
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            <th className="conjtable__tense">{r.tense}</th>
            <td className="conjtable__form">
              <span>{r.form}</span>
              <SpeakButton text={r.form} lang={lang} small title="Hear this form" />
            </td>
            <td className="conjtable__meaning" dir="auto">{r.meaning}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
