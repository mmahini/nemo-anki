import type { GrammarTable as GT } from "../auth/api";

export default function GrammarTable({ table }: { table: GT }) {
  const [hr, hc] = table.highlight ?? [-1, -1];
  return (
    <table className="gtable">
      {table.headers?.length > 0 && (
        <thead>
          <tr>
            {table.headers.map((h, i) => (
              <th key={i}>{h}</th>
            ))}
          </tr>
        </thead>
      )}
      <tbody>
        {table.rows.map((row, r) => (
          <tr key={r}>
            {row.map((cell, c) => (
              <td key={c} className={r === hr && c === hc ? "gtable__hl" : ""}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
