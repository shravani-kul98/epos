import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { displayTerm, recordTypeLabel, roleGuide } from "@/lib/terminology";

/**
 * Guard against internal vocabulary reaching the interface. Engine keys, build wording and model
 * names belong in developer documentation, never in a user-facing string.
 */

const SOURCE_ROOT = join(process.cwd(), "src");

/** Wording that must never appear inside a JSX text node or user-facing string literal. */
const FORBIDDEN = [
  "task_execution",
  "data_freshness",
  "risk_exposure",
  "dependency_status",
  "action_closure",
  "resource_capacity",
  "schedule_performance",
  "milestone_readiness",
  "data_completeness",
  "ownership_coverage",
  "source_reliability",
  "Version 1",
  "synthetic data",
  "synthetic dataset",
  "prototype",
  "no AI content",
  "GPT-4o",
  "gpt-4o",
  "AI-generated",
];

function sourceFiles(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory)) {
    const path = join(directory, entry);
    if (statSync(path).isDirectory()) {
      found.push(...sourceFiles(path));
    } else if (/\.tsx?$/.test(entry) && !/\.test\.tsx?$/.test(entry)) {
      found.push(path);
    }
  }
  return found;
}

describe("user-facing terminology", () => {
  it("keeps internal keys and build wording out of the interface", () => {
    const offenders: string[] = [];

    for (const file of sourceFiles(SOURCE_ROOT)) {
      // The terminology map itself must contain the internal keys in order to translate them.
      if (file.endsWith("terminology.ts")) continue;
      const contents = readFileSync(file, "utf8");
      for (const term of FORBIDDEN) {
        if (contents.includes(term)) {
          offenders.push(`${file.replace(SOURCE_ROOT, "src")} contains "${term}"`);
        }
      }
    }

    expect(offenders).toEqual([]);
  });

  it("translates every analysis factor key to its approved name", () => {
    expect(displayTerm("task_execution")).toBe("Task Delivery");
    expect(displayTerm("data_freshness")).toBe("Reporting Freshness");
    expect(displayTerm("risk_exposure")).toBe("Risk Management");
    expect(displayTerm("dependency_status")).toBe("Dependency Health");
    expect(displayTerm("action_closure")).toBe("Action Follow-Through");
    expect(displayTerm("resource_capacity")).toBe("Team Capacity");
    expect(displayTerm("schedule_performance")).toBe("Schedule Health");
    expect(displayTerm("milestone_readiness")).toBe("Milestone Readiness");
    expect(displayTerm("data_completeness")).toBe("Information Completeness");
    expect(displayTerm("ownership_coverage")).toBe("Accountability Coverage");
    expect(displayTerm("source_reliability")).toBe("Data Availability");
  });

  it("gives evidence records a readable type name", () => {
    expect(recordTypeLabel("change_request")).toBe("Change request");
    expect(recordTypeLabel("test_case")).toBe("Test case");
  });

  it("leaves ordinary wording untouched", () => {
    expect(displayTerm("Red")).toBe("Red");
    expect(displayTerm("In Progress")).toBe("In Progress");
  });

  it("describes every role in plain language without permission codes", () => {
    for (const role of [
      "executive",
      "engineer",
      "engineering_lead",
      "requirements_manager",
      "project_manager",
      "pmo_analyst",
      "administrator",
    ]) {
      const guide = roleGuide(role);
      expect(guide, `missing guide for ${role}`).toBeDefined();
      expect(guide?.can.length).toBeGreaterThan(0);
      for (const line of [...(guide?.can ?? []), ...(guide?.cannot ?? [])]) {
        expect(line).not.toMatch(/\.[a-z]+\b.*\bpermission|portfolio\.read|project\.create/);
      }
    }
  });
});
