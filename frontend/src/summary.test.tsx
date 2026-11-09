import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import type { SummaryOut } from "./api/types";
import App from "./App";
import a15Summary from "./test/fixtures/a15-summary-disabled.json";
import errInvalidWeek from "./test/fixtures/err-invalid-week.json";
import { held, installFetch, json, type MockFetch } from "./test/mockFetch";

// The summary card (plans/T5-ai-summary.md §2e, U1 to U7). The captured fixture is the real
// flag-off response; the other responses are clones with one changed field.
const SEARCH = "?account=15&week=2026-07-20";
const TEMPLATE = a15Summary as SummaryOut;
const FACT_LINES = TEMPLATE.text.split("\n");

function open(): void {
  window.history.pushState(null, "", `/${SEARCH}`);
}
const generate = (): Promise<HTMLElement> =>
  screen.findByRole("button", { name: /generate summary/i });
const summaryCalls = (mock: MockFetch) => mock.calls.filter((c) => c.path === "/api/summary");
const card = (): HTMLElement => screen.getByRole("region", { name: "AI summary" });

function ai(over: Partial<SummaryOut>): SummaryOut {
  return {
    ...structuredClone(TEMPLATE),
    source: "ai",
    reason: null,
    headline: "Site C is higher than usual.",
    ...over,
  };
}

describe("SummaryCard", () => {
  test("U1 the card and its button show with the flag off, and nothing is requested on load", async () => {
    const mock = installFetch();
    open();
    render(<App />);
    const button = await generate();
    expect(button.querySelector('[data-part="sparkle"]')).toHaveAttribute("aria-hidden", "true");
    await screen.findByText("Week of 2026-07-20");
    expect(summaryCalls(mock)).toHaveLength(0);
  });

  test("U2 a click POSTs the week and shows the template label and the fact lines", async () => {
    const mock = installFetch();
    open();
    render(<App />);
    await userEvent.click(await generate());
    const templateLabel = await screen.findByText("Template summary — disabled");
    expect(templateLabel.parentElement?.querySelector('[data-part="sparkle"]')).toBeNull();
    const calls = summaryCalls(mock);
    expect(calls).toHaveLength(1);
    expect(calls[0]).toMatchObject({
      method: "POST",
      account: "15",
      body: '{"week":"2026-07-20"}',
    });
    for (const line of FACT_LINES) expect(card()).toHaveTextContent(line, { normalizeWhitespace: true });
    expect(screen.getAllByText(FACT_LINES[1] as string)).toHaveLength(1);
    expect(card().querySelector('[data-part="headline"]')).toBeNull();
  });

  test("U3 an ai response from the mock is labeled a preview, with the headline before the lines", async () => {
    installFetch([(call) => (call.path === "/api/summary" ? json(ai({ provider: "mock" })) : undefined)]);
    open();
    render(<App />);
    await userEvent.click(await generate());
    const aiLabel = await screen.findByText("AI summary · preview (mock provider)");
    expect(aiLabel.parentElement?.querySelector('[data-part="sparkle"]')).not.toBeNull();
    expect(card()).not.toHaveTextContent("Template summary");
    const headline = card().querySelector('[data-part="headline"]') as HTMLElement;
    expect(headline).toHaveTextContent("Site C is higher than usual.");
    const firstLine = screen.getByText(FACT_LINES[0] as string);
    expect(headline.compareDocumentPosition(firstLine) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  test("U4 markup in the headline is shown as text, never as HTML", async () => {
    installFetch([
      (call) => (call.path === "/api/summary" ? json(ai({ headline: "<b>x</b> stands out." })) : undefined),
    ]);
    open();
    render(<App />);
    await userEvent.click(await generate());
    await screen.findByText("<b>x</b> stands out.");
    expect(card().querySelector("b")).toBeNull();
  });

  test.each([true, false])(
    "U6 a response for a superseded account is ignored (abort honored: %s)",
    async (honorAbort) => {
      const slow = held(honorAbort);
      installFetch([(call) => (call.path === "/api/summary" ? slow.handler(call) : undefined)]);
      open();
      render(<App />);
      await userEvent.click(await generate());
      await screen.findByText("Generating summary…");
      await userEvent.selectOptions(screen.getByLabelText(/^account \(demo/i), "6");
      await waitFor(() => expect(screen.getByLabelText(/^account \(demo/i)).toHaveValue("6"));
      await screen.findByRole("button", { name: /generate summary/i });
      slow.release(json(TEMPLATE));
      await new Promise((resolve) => setTimeout(resolve, 20));
      expect(screen.queryByText(/Template summary/)).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
      expect(screen.queryByText("Generating summary…")).toBeNull();
    },
  );

  test("U7a a 422 shows the error and no summary label or text", async () => {
    installFetch([
      (call) => (call.path === "/api/summary" ? json(errInvalidWeek, 422) : undefined),
    ]);
    open();
    render(<App />);
    await userEvent.click(await generate());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(errInvalidWeek.error.code);
    expect(alert).toHaveTextContent(errInvalidWeek.error.message);
    expect(card()).not.toHaveTextContent(/summary —|AI summary ·/);
    for (const line of FACT_LINES) expect(screen.queryByText(line)).toBeNull();
  });

  test("U7b a network failure shows network_error and no summary label or text", async () => {
    installFetch([
      (call) =>
        call.path === "/api/summary" ? Promise.reject(new TypeError("Failed to fetch")) : undefined,
    ]);
    open();
    render(<App />);
    await userEvent.click(await generate());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("network_error");
    expect(card()).not.toHaveTextContent(/summary —|AI summary ·/);
    for (const line of FACT_LINES) expect(screen.queryByText(line)).toBeNull();
  });
});
