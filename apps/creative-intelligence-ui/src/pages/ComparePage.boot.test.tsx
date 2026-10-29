/// <reference types="vite/client" />
/** Exercise actual boot/state/apply statements without loading page/API/auth imports.
 * Option lists and ranking responses are synthetic boundaries, not integration proof.
 */
import * as React from "react";
import * as ts from "typescript";
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import source from "./ComparePage.tsx?raw";

const tree = ts.createSourceFile("ComparePage.tsx", source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const page = tree.statements.find((node): node is ts.FunctionDeclaration =>
  ts.isFunctionDeclaration(node) && node.name?.text === "ComparePage")!;
const states = page.body!.statements.filter((node) => ts.isVariableStatement(node)
  && node.declarationList.declarations.some((declaration) => {
    if (!ts.isArrayBindingPattern(declaration.name)) return false;
    const first = declaration.name.elements[0];
    return ts.isBindingElement(first)
      && ["mode", "picked", "campaignRank", "creativeRank", "booted"].includes(first.name.getText(tree));
  }));
if (states.length !== 5) throw new Error("Expected five original boot-related state declarations");
const declaration = (name: string) => page.body!.statements.find((node) => ts.isVariableStatement(node)
  && node.declarationList.declarations.some((item) => item.name.getText(tree) === name))!;
const effects = page.body!.statements.filter((node) => ts.isExpressionStatement(node)
  && ts.isCallExpression(node.expression) && node.expression.expression.getText(tree) === "useEffect"
  && node.getText(tree).includes("window.location.search"));
if (effects.length !== 1) throw new Error("Expected one ordinary comparison boot effect");
const numberHelper = tree.statements.find((node): node is ts.FunctionDeclaration =>
  ts.isFunctionDeclaration(node) && node.name?.text === "num")!;
const extracted = `const {useState,useEffect}=require("react");
${numberHelper.getText(tree)}
export function useOriginalBoot(campaignOptions,creativeOptions,runCampaigns,runCreatives) {
${states.map((node) => node.getText(tree)).join("\n")}
${declaration("rank").getText(tree)}
${effects[0].getText(tree)}
${declaration("apply").getText(tree)}
return {mode,picked,rank,booted,apply,setCreativeRank};
}`;
const compiled = ts.transpileModule(extracted, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
type CampaignOptions = { data: Record<string, { spend: number }> | null };
type CreativeOptions = { data: Array<{ creative_key: string }> | null };
type Run = (keys: string[], rank: string) => void;
type BootState = { mode: string; picked: string[]; rank: string; booted: boolean;
  apply: () => void; setCreativeRank: React.Dispatch<React.SetStateAction<string>> };
const extractedExports = {} as { useOriginalBoot: (campaigns: CampaignOptions, creatives: CreativeOptions,
  runCampaigns: Run, runCreatives: Run) => BootState };
// Only React is available to this exact-source excerpt; application imports are omitted.
new Function("require", "exports", compiled)((name: string) => {
  if (name !== "react") throw new Error(`Unexpected excerpt dependency: ${name}`);
  return React;
}, extractedExports);

afterEach(() => { cleanup(); window.history.replaceState({}, "", "/"); });
const campaigns: CampaignOptions = { data: { One: { spend: 20 }, Two: { spend: 10 } } };
const creatives: CreativeOptions = { data: ["A", "B", "C", "D"].map((creative_key) => ({ creative_key })) };
function mount(query: string, initialCampaigns = campaigns, initialCreatives = creatives) {
  window.history.replaceState({}, "", `/${query}`);
  const runCampaigns = vi.fn<Run>(), runCreatives = vi.fn<Run>();
  const hook = renderHook(({ campaignOptions, creativeOptions }) => extractedExports.useOriginalBoot(
    campaignOptions, creativeOptions, runCampaigns, runCreatives,
  ), { initialProps: { campaignOptions: initialCampaigns, creativeOptions: initialCreatives } });
  return { ...hook, runCampaigns, runCreatives };
}
function syntheticWinner(rank: string) {
  // Deliberately different CTR and ROAS leaders; this is an inert response fixture.
  const scores = { A: { ctr: 0.9, roas: 1 }, B: { ctr: 0.1, roas: 4 } };
  if (rank !== "ctr" && rank !== "roas") throw new Error("Unexpected fixture metric");
  return scores.A[rank] > scores.B[rank] ? "A" : "B";
}

describe("creative comparison boot rank", () => {
  it("requests the rank displayed by a valid creative deep link", () => {
    const hook = mount("?mode=creatives&creatives=A,B");
    expect(hook.result.current.mode).toBe("creatives");
    expect(hook.result.current.rank).toBe("roas");
    const [keys, requestedRank] = hook.runCreatives.mock.calls[0];
    expect(keys).toEqual(["A", "B"]);
    expect(requestedRank).toBe(hook.result.current.rank);
    expect(syntheticWinner(requestedRank)).toBe("B");
  });

  it("keeps the same rank and synthetic winner on Apply without changes", () => {
    const hook = mount("?mode=creatives&creatives=A,B");
    act(() => hook.result.current.apply());
    const [initial, applied] = hook.runCreatives.mock.calls;
    expect(initial).toEqual(applied);
    expect(syntheticWinner(initial[1])).toBe(syntheticWinner(applied[1]));
  });

  it("uses current rank state when delayed option lists become available", () => {
    const hook = mount("?mode=creatives&creatives=A,B", { data: null }, { data: null });
    expect(hook.runCreatives).not.toHaveBeenCalled();
    act(() => hook.result.current.setCreativeRank("cpa"));
    hook.rerender({ campaignOptions: campaigns, creativeOptions: creatives });
    expect(hook.result.current.rank).toBe("cpa");
    expect(hook.runCreatives).toHaveBeenCalledWith(["A", "B"], "cpa");
  });

  it("preserves all four valid linked selections", () => {
    const hook = mount("?mode=creatives&creatives=D,C,B,A");
    expect(hook.result.current.picked).toEqual(["D", "C", "B", "A"]);
    expect(hook.runCreatives.mock.calls[0][0]).toEqual(["D", "C", "B", "A"]);
  });

  it("retains incomplete-link behavior without running an invalid comparison", () => {
    const hook = mount("?mode=creatives&creatives=A,unknown");
    expect(hook.result.current.picked).toEqual(["A"]);
    expect(hook.runCreatives).not.toHaveBeenCalled();
  });

  it("does not rerun boot when option objects refresh after initialization", () => {
    const hook = mount("?mode=creatives&creatives=A,B");
    hook.rerender({ campaignOptions: { data: { ...campaigns.data } },
      creativeOptions: { data: [...creatives.data!] } });
    expect(hook.runCreatives).toHaveBeenCalledTimes(1);
  });

  it("preserves campaign-link default ranking", () => {
    const hook = mount("?mode=campaigns&campaigns=Two,One");
    expect(hook.result.current.mode).toBe("campaigns");
    expect(hook.result.current.rank).toBe("roas");
    expect(hook.runCampaigns).toHaveBeenCalledWith(["Two", "One"], "roas");
    expect(hook.runCreatives).not.toHaveBeenCalled();
  });

  it("preserves the no-link top-spend campaign boot", () => {
    const hook = mount("");
    expect(hook.runCampaigns).toHaveBeenCalledWith(["One", "Two"], "roas");
    expect(hook.result.current.picked).toEqual(["One", "Two"]);
  });
});
