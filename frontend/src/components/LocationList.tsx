import type { LocationRow } from "../api/types";

/** CP1b minimal: names as buttons, in the API's order. CP2 replaces it with the table. */
export function LocationList({
  locations,
  selected,
  onSelect,
}: {
  locations: LocationRow[];
  selected: string | null;
  onSelect: (location: string) => void;
}) {
  return (
    <ul>
      {locations.map((row) => (
        <li key={row.location}>
          <button
            type="button"
            aria-current={row.location === selected ? "true" : undefined}
            onClick={() => onSelect(row.location)}
          >
            {row.location}
          </button>
        </li>
      ))}
    </ul>
  );
}
