import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PropagationWizardPanel } from "../components/guidance/PropagationWizardPanel";
import type { ArtifactIssue, PropagationPlan } from "./useArtifactIssues.types";

describe("PropagationWizardPanel", () => {
  const plan: PropagationPlan = {
    stale_stages: ["content_brief_reanchor", "optimal_questions"],
    invalidate_from: "content_brief_reanchor",
    cross_errors: ["seg_orphan not in manifest"],
    has_blocking: true,
  };

  it("renders stale stages and execute CTA when blocking", () => {
    const html = renderToStaticMarkup(
      createElement(PropagationWizardPanel, {
        plan,
        busy: false,
        onExecute: () => {},
      }),
    );
    expect(html).toContain("itr-propagation-wizard");
    expect(html).toContain("content_brief_reanchor");
    expect(html).toContain("Invalidate &amp; re-run from content brief reanchor");
  });

  it("renders nothing when plan is not blocking", () => {
    const html = renderToStaticMarkup(
      createElement(PropagationWizardPanel, {
        plan: { ...plan, has_blocking: false },
        busy: false,
        onExecute: () => {},
      }),
    );
    expect(html).toBe("");
  });
});

describe("useArtifactIssues recovery types", () => {
  it("accepts recovery_actions on issues", () => {
    const issue: ArtifactIssue = {
      id: "itr_1",
      stage_key: "segment_classification",
      kind: "overlap",
      severity: "critical",
      message: "overlap",
      status: "open",
      blocking: true,
      suggested_upstream_stage: "boundary_detection",
      recovery_actions: [
        { type: "apply_repair", label: "Apply auto-repair" },
        {
          type: "rerun_upstream",
          label: "Re-run boundary detection",
          stage: "boundary_detection",
        },
      ],
    };
    expect(issue.recovery_actions?.[1].type).toBe("rerun_upstream");
    expect(issue.suggested_upstream_stage).toBe("boundary_detection");
  });
});
