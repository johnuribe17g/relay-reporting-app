import type { AccountOut } from "../api/types";

/** A demo stand-in for login (PLAN §1). */
export function AccountSwitcher({
  accounts,
  value,
  onChange,
}: {
  accounts: AccountOut[] | null;
  value: string;
  onChange: (id: string) => void;
}) {
  return (
    <label>
      Account (demo stand-in for login){" "}
      <select
        value={value}
        disabled={accounts === null}
        onChange={(event) => onChange(event.target.value)}
      >
        {value === "" && <option value="">Select an account</option>}
        {(accounts ?? []).map((a) => (
          <option key={a.id} value={String(a.id)}>
            {a.name} (#{a.id})
          </option>
        ))}
      </select>
    </label>
  );
}
