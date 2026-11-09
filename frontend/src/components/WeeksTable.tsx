import type { WeekPoint } from "../api/types";

/** The weekly totals in the order the API gave (oldest first); the selected week is marked, not computed. */
export function WeeksTable({ weeks }: { weeks: WeekPoint[] }) {
  return (
    <table aria-label="Weekly totals">
      <thead>
        <tr>
          <th scope="col">Week</th>
          <th scope="col">Total</th>
          <th scope="col">Calls</th>
          <th scope="col">Leads</th>
          <th scope="col">Appointments</th>
          <th scope="col">Role</th>
        </tr>
      </thead>
      <tbody>
        {weeks.map((point) => (
          <tr
            key={point.week}
            data-role={point.role}
            aria-current={point.role === "selected" ? "true" : undefined}
          >
            <td>{point.week}</td>
            <td>{point.total}</td>
            <td>{point.by_type.call_received}</td>
            <td>{point.by_type.lead_created}</td>
            <td>{point.by_type.appointment_set}</td>
            <td>{point.role === "selected" ? "Selected week" : "Baseline"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
