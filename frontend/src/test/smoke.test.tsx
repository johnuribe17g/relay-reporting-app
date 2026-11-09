import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

// Setup check only: the runner, jsdom, React and jest-dom matchers work inside the container.
test("smoke: jsdom renders a React element", () => {
  render(<p>run path ok</p>);
  expect(screen.getByText("run path ok")).toBeInTheDocument();
});
