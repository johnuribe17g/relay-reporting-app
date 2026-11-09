import type { LocationRow, Parameters } from "../api/types";
import { fmtBand, fmtDiff, fmtNum, fmtZ, glossary, reasonText, verdictLabel } from "../format";

/**
 * Rows exactly in the order the API gave (its ranking: judged by deviation, unjudged after). No sorting,
 * no grouping, no divider: a verdict is rendered as given, with its reason when it is not a judgement.
 */
export function LocationTable({
  locations,
  parameters,
  selected,
  onSelect,
}: {
  locations: LocationRow[];
  parameters: Parameters;
  selected: string | null;
  onSelect: (location: string) => void;
}) {
  const help = glossary(parameters);
  return (
    <table>
      <caption>Locations, in the order the API ranks them</caption>
      <thead>
        <tr>
          <th scope="col">Location</th>
          <th scope="col">Verdict</th>
          <th scope="col">This week</th>
          <th scope="col" title={help.median}>
            Normal (median)
          </th>
          <th scope="col" title={help.range}>
            Normal range
          </th>
          <th scope="col" title={help.z}>
            Score (z)
          </th>
          <th scope="col" title={help.diff}>
            Difference
          </th>
        </tr>
      </thead>
      <tbody>
        {locations.map((row) => {
          const reason = reasonText(row, parameters);
          return (
            <tr key={row.location} data-verdict={row.verdict}>
              <td>
                <button
                  type="button"
                  aria-current={row.location === selected ? "true" : undefined}
                  onClick={() => onSelect(row.location)}
                >
                  {row.location}
                </button>
              </td>
              <td>
                <span>{verdictLabel(row.verdict)}</span>
                {reason !== null && <small> {reason}</small>}
              </td>
              <td>{fmtNum(row.total)}</td>
              <td>{row.baseline === null ? "—" : fmtNum(row.baseline.median)}</td>
              <td>{row.baseline === null ? "—" : fmtBand(row.baseline)}</td>
              <td>{fmtZ(row.z)}</td>
              <td>{fmtDiff(row.diff)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
