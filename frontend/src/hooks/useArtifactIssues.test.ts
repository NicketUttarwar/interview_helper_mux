import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PropagationWizardPanel } from "../components/guidance/PropagationWizardPanel";
import type { ArtifactIssue, PropagationPlan } from "./useArtifactIssues.types";

describe("PropagationWizardPanel", () => {
  const plan: PropagationPlan = {
    from_stage: "source_topology_build",
    stale_stages: ["content_context", "narrative_arc_plan"],
    stage_labels: {
      content_context: "Story brief & strategic moat",
      narrative_arc_plan: "Five-act narrative plan",
    },
    change_hint: "Topology or pickup eligibility changed",
    tbiy_affected: true,
    invalidate_from: "content_context",
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
    expect(html).toContain("Story brief &amp; strategic moat");
    expect(html).toContain("itr-propagation-tbiy-hint");
    expect(html).toContain("Invalidate &amp; re-run from Story brief &amp; strategic moat");
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
