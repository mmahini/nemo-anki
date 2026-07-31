import { useTranslation } from "react-i18next";

import type { NounGender } from "../auth/api";
import { articleClass } from "../lib/article";

/**
 * Explains every article in a German sentence: the word, its true gender
 * (colour-coded), the article as used, the grammatical case, and why that case
 * applies. Populated by the "Colour genders" analysis.
 */
export default function CaseTable({ items }: { items: NounGender[] }) {
  const { t } = useTranslation();
  const rows = items.filter((n) => n.case || n.article);
  if (!rows.length) return null;
  return (
    <table className="casetable">
      <thead>
        <tr>
          <th>Word</th>
          <th>{t("cardEditor.articleColumn")}</th>
          <th>Case</th>
          <th>Why</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((n, i) => (
          <tr key={i}>
            <td className={`casetable__word ${articleClass(n.gender)}`}>{n.noun}</td>
            <td className={articleClass(n.gender)}>{n.article || "—"}</td>
            <td>{n.case && <span className={`casebadge casebadge--${n.case}`}>{n.case}</span>}</td>
            <td className="casetable__why">
              {n.trigger && <span className="trigger-word">{n.trigger}</span>}
              {n.trigger && n.reason ? " — " : ""}
              {n.reason}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
