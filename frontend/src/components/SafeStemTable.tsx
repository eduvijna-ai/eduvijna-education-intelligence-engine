type Props = {
  headers: string[]
  rows: string[][]
  caption: string
}

/** Fixture-authored table only — cells are plain text, no HTML injection. */
export function SafeStemTable({ headers, rows, caption }: Props) {
  return (
    <table className="data-table stem-table">
      <caption>{caption}</caption>
      <thead>
        <tr>
          {headers.map((h) => (
            <th key={h} scope="col">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, ri) => (
          <tr key={ri}>
            {row.map((cell, ci) => (
              <td key={ci}>{cell}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}