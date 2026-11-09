/** Unknown event types are not counted in any total (D-16); the count is over the baseline window plus this week. */
export function DataQualityWarning({ count }: { count: number }) {
  return (
    <p role="note">
      Data quality: {count} event{count === 1 ? "" : "s"} of an unknown type in the baseline window plus
      this week. They are not counted in any total.
    </p>
  );
}
