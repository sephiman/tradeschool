import { describe, expect, it } from "vitest";
import { assignPair, isComplete, unassignPair, usedRights } from "./matching";
import { moveItem } from "./ordering";

describe("matching pairing state machine", () => {
  it("assigns a right to a left", () => {
    expect(assignPair({}, "L1", "R1")).toEqual({ L1: "R1" });
  });

  it("reassigns: a left keeps only its most recent right", () => {
    let s = assignPair({}, "L1", "R1");
    s = assignPair(s, "L1", "R2");
    expect(s).toEqual({ L1: "R2" });
    expect(usedRights(s).has("R1")).toBe(false);
  });

  it("stays injective: assigning a used right moves it off its old left (steal)", () => {
    let s = assignPair({}, "L1", "R1");
    s = assignPair(s, "L2", "R2");
    s = assignPair(s, "L2", "R1"); // R1 was L1's; it moves to L2
    expect(s).toEqual({ L2: "R1" });
    expect("L1" in s).toBe(false);
  });

  it("unassigns a paired left, leaving the rest intact", () => {
    let s = assignPair({}, "L1", "R1");
    s = assignPair(s, "L2", "R2");
    expect(unassignPair(s, "L1")).toEqual({ L2: "R2" });
  });

  it("unassign is a no-op for an unpaired left", () => {
    const s = assignPair({}, "L1", "R1");
    expect(unassignPair(s, "LX")).toEqual({ L1: "R1" });
  });

  it("usedRights reflects exactly the consumed right ids", () => {
    let s = assignPair({}, "L1", "R1");
    s = assignPair(s, "L2", "R3");
    expect(usedRights(s)).toEqual(new Set(["R1", "R3"]));
  });

  it("is complete only when every left is paired", () => {
    const leftIds = ["L1", "L2"];
    expect(isComplete({}, leftIds)).toBe(false);
    expect(isComplete({ L1: "R1" }, leftIds)).toBe(false);
    expect(isComplete({ L1: "R1", L2: "R2" }, leftIds)).toBe(true);
  });

  it("is never complete with no lefts", () => {
    expect(isComplete({}, [])).toBe(false);
    expect(isComplete({ L1: "R1" }, [])).toBe(false);
  });

  it("never mutates the input map", () => {
    const original = { L1: "R1" };
    assignPair(original, "L2", "R2");
    unassignPair(original, "L1");
    expect(original).toEqual({ L1: "R1" });
  });
});

describe("ordering move logic", () => {
  it("moves an item up", () => {
    expect(moveItem(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
  });

  it("moves an item down", () => {
    expect(moveItem(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
  });

  it("is a no-op past the top edge", () => {
    expect(moveItem(["a", "b"], 0, -1)).toEqual(["a", "b"]);
  });

  it("is a no-op past the bottom edge", () => {
    expect(moveItem(["a", "b"], 1, 1)).toEqual(["a", "b"]);
  });

  it("never mutates the input array", () => {
    const arr = ["a", "b", "c"];
    moveItem(arr, 0, 1);
    expect(arr).toEqual(["a", "b", "c"]);
  });
});
