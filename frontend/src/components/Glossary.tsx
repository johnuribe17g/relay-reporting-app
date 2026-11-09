import type { Parameters } from "../api/types";
import { glossary } from "../format";

/** What the numbers mean, in the API's own parameters. Collapsed by default. */
export function Glossary({ parameters }: { parameters: Parameters }) {
  const g = glossary(parameters);
  return (
    <details>
      <summary>What do these numbers mean?</summary>
      <dl>
        <dt>Normal (median)</dt>
        <dd>{g.median}</dd>
        <dt>Normal range</dt>
        <dd>{g.range}</dd>
        <dt>Score (z)</dt>
        <dd>{g.z}</dd>
        <dt>Difference</dt>
        <dd>{g.diff}</dd>
        <dt>Too quiet</dt>
        <dd>{g.tooQuiet}</dd>
        <dt>Not enough history</dt>
        <dd>{g.notEnoughHistory}</dd>
      </dl>
    </details>
  );
}
