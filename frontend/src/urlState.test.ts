import { describe, expect, test } from "vitest";

import { buildUrl, nextOnAccount, nextOnLocation, nextOnWeek, parseUrl } from "./urlState";

describe("urlState (plan §2a)", () => {
  test("P1 parses account, week and an encoded location", () => {
    expect(parseUrl("?account=15&week=2026-07-20&location=Site%20C")).toEqual({
      account: "15",
      week: "2026-07-20",
      location: "Site C",
    });
  });

  test("P2 empty search and empty values are absent", () => {
    const none = { account: null, week: null, location: null };
    expect(parseUrl("")).toEqual(none);
    expect(parseUrl("?account=&week=")).toEqual(none);
  });

  test("P3 a plus sign in the query is a space", () => {
    expect(parseUrl("?location=Site+C").location).toBe("Site C");
  });

  test("P4 builds in the order account, week, location", () => {
    expect(buildUrl({ account: "15", week: "2026-07-20", location: "Site C" })).toBe(
      "?account=15&week=2026-07-20&location=Site+C",
    );
  });

  test("P5 omits nulls; all null gives an empty string", () => {
    expect(buildUrl({ account: "15", week: null, location: null })).toBe("?account=15");
    expect(buildUrl({ account: null, week: null, location: null })).toBe("");
  });

  test("P6 reserved characters round trip", () => {
    // '+' is 0x2B -> %2B; '&' is 0x26 -> %26; '=' is 0x3D -> %3D
    const plus = buildUrl({ account: null, week: null, location: "A+B" });
    expect(plus).toBe("?location=A%2BB");
    expect(parseUrl(plus).location).toBe("A+B");

    const amp = buildUrl({ account: null, week: null, location: "A&B=1" });
    expect(amp).toBe("?location=A%26B%3D1");
    expect(parseUrl(amp).location).toBe("A&B=1");
  });

  test("P7 unknown parameters are not kept", () => {
    const state = parseUrl("?account=15&utm=x");
    expect(buildUrl(state)).toBe("?account=15");
  });

  test("P8 transitions", () => {
    const state = { account: "15", week: "2026-07-20", location: "Site C" };
    expect(nextOnAccount(state, "6")).toEqual({ account: "6", week: null, location: null });
    expect(nextOnWeek(state, "2026-06-01")).toEqual({
      account: "15",
      week: "2026-06-01",
      location: "Site C",
    });
    expect(nextOnLocation(state, "Site A")).toEqual({
      account: "15",
      week: "2026-07-20",
      location: "Site A",
    });
  });
});
