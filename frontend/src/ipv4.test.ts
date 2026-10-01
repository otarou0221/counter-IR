import { describe, expect, it } from "vitest";
import {
  ipv4ValidationError,
  isValidIpv4,
  joinIpv4,
  normalizeIpv4Octet,
  splitIpv4,
} from "./ipv4";

describe("IPv4 input", () => {
  it("splits and joins the four octets", () => {
    expect(splitIpv4("192.168.100.50")).toEqual(["192", "168", "100", "50"]);
    expect(joinIpv4(["192", "168", "", ""])).toBe("192.168..");
    expect(joinIpv4(["", "", "", ""])).toBe("");
  });

  it("keeps only three numeric digits and removes leading zeroes", () => {
    expect(normalizeIpv4Octet("00a7")).toBe("7");
    expect(normalizeIpv4Octet("1234")).toBe("123");
  });

  it.each(["0.0.0.0", "192.168.100.50", "255.255.255.255"])(
    "accepts a canonical IPv4 address: %s",
    (value) => expect(isValidIpv4(value)).toBe(true),
  );

  it.each(["", "abc", "192.168.1", "192.168.1.256", "192.168.001.1", "-1.2.3.4"])(
    "rejects an invalid IPv4 address: %s",
    (value) => expect(ipv4ValidationError(value)).toBeDefined(),
  );
});
