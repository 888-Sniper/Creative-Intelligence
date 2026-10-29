import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import ts from "typescript";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render } from "@testing-library/react";
import { TrendChart } from "./charts";
vi.mock("@/i18n", () => ({ useLocale: () => ({ locale: "en", t: (key) => key }) }));
afterEach(cleanup);
// Compile only the local trend projection, not the page's imports, requests or hooks.
// Keeping the source expressions makes this fail if the page regroups daily values again.
const path = resolve(process.cwd(), "src/pages/DashboardPage.tsx");
const source = ts.createSourceFile(path, readFileSync(path, "utf8"), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
const helpers = source.statements.filter((node) => ts.isFunctionDeclaration(node) && ["num", "downsample"].includes(node.name?.text ?? ""));
const declarations = new Map();
function collect(node) {
    if (ts.isVariableStatement(node)) {
        for (const declaration of node.declarationList.declarations) {
            if (ts.isIdentifier(declaration.name) && ["trend", "trendSeries"].includes(declaration.name.text)) {
                if (declarations.has(declaration.name.text))
                    throw new Error("Ambiguous trend projection");
                declarations.set(declaration.name.text, node);
            }
        }
    }
    ts.forEachChild(node, collect);
}
collect(source);
if (declarations.size !== 2 || !helpers.some((n) => n.name?.text === "num")) {
    throw new Error("Expected local trend projection is missing");
}
const excerpt = `${helpers.map((node) => node.getText(source)).join("\n")}
function project(daily, leftMetric, rightMetric) {
  const useMemo = (read) => read();
  const leftLabel = leftMetric, rightLabel = rightMetric;
  ${declarations.get("trend").getText(source)}
  ${declarations.get("trendSeries").getText(source)}
  return { trend, trendSeries };
}
project;`;
const javascript = ts.transpileModule(excerpt, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const project = runInNewContext(javascript, {}, { timeout: 1000 });
function days(count) {
    return Array.from({ length: count }, (_, i) => ({
        date: new Date(Date.UTC(2026, 0, i + 1)).toISOString().slice(0, 10),
        impressions: 100, clicks: 10, spend: 5, conversions: 2, revenue: 15,
    }));
}
describe("Dashboard daily trend semantics", () => {
    it("keeps a constant 31-day period flat instead of halving its last value", () => {
        const input = days(31);
        const result = project(input, "impressions", "clicks");
        expect(result.trend).toHaveLength(31);
        expect(result.trendSeries[0].points).toEqual(Array(31).fill(100));
        expect(result.trendSeries[1].points).toEqual(Array(31).fill(10));
        expect(result.trend[30].date).toBe("2026-01-31");
    });
    it.each([0, 1, 16, 17])("retains all %i reported days around the former limit", (count) => {
        const input = days(count);
        expect(project(input, "spend", "revenue").trend).toEqual(input);
    });
    it("retains daily values and dates in longer synthetic periods", () => {
        for (const count of [90, 366, 730]) {
            const input = days(count);
            const result = project(input, "spend", "conversions");
            expect(result.trend).toEqual(input);
            expect(result.trendSeries[0].points).toEqual(Array(count).fill(5));
            expect(result.trendSeries[1].points).toEqual(Array(count).fill(2));
        }
    });
    it("keeps a one-day spike attached to its actual day", () => {
        const input = days(31);
        input[16] = { ...input[16], impressions: 900, spend: 0 };
        const result = project(input, "impressions", "spend");
        expect(result.trend[16].date).toBe("2026-01-17");
        expect(result.trendSeries[0].points[16]).toBe(900);
        expect(result.trendSeries[1].points[16]).toBe(0);
        expect(result.trendSeries[0].points.filter((n) => n === 100)).toHaveLength(30);
    });
    it("does not combine missing calendar dates or reorder supplied observations", () => {
        const input = days(20).filter((_, i) => i !== 3 && i !== 9).reverse();
        expect(project(input, "clicks", "revenue").trend).toEqual(input);
    });
    it("projects each selected metric without replacing day values with totals", () => {
        const input = days(31).map((day, i) => ({ ...day,
            impressions: 100 + i, clicks: 10 + i, spend: 5.25 + i,
            conversions: i, revenue: 15.5 + i,
        }));
        const metrics = ["impressions", "clicks", "spend", "conversions", "revenue"];
        for (const metric of metrics) {
            const result = project(input, metric, metric);
            expect(result.trendSeries[0].points).toEqual(input.map((d) => d[metric]));
            expect(result.trendSeries[1].points).toEqual(input.map((d) => d[metric]));
            expect(result.trendSeries[1].axis).toBe("right");
        }
    });
    it("does not mutate frozen input days", () => {
        const input = Object.freeze(days(31).map((day) => Object.freeze(day)));
        project(input, "spend", "revenue");
        expect(input).toEqual(days(31));
    });
    it("keeps an absent daily response empty", () => {
        for (const input of [null, undefined]) {
            const result = project(input, "impressions", "clicks");
            expect(result.trend).toEqual([]);
            expect(result.trendSeries.map((s) => s.points)).toEqual([[], []]);
        }
    });
    it("does not carry old observations into a different daily input", () => {
        project(days(31), "spend", "revenue");
        expect(project(days(2), "spend", "revenue").trend).toEqual(days(2));
        expect(project([], "spend", "revenue").trend).toEqual([]);
    });
    it("passes every reported day through the real shared chart", () => {
        const result = project(days(31), "impressions", "clicks");
        const view = render(<TrendChart series={result.trendSeries} labels={result.trend.map((d) => d.date)}/>);
        const strokes = view.container.querySelectorAll('path[fill="none"]');
        expect(strokes).toHaveLength(2);
        for (const stroke of strokes) {
            expect(stroke.getAttribute("d")?.match(/L/g)).toHaveLength(30);
        }
        expect(view.container.querySelectorAll("svg text").length).toBeLessThan(31);
        expect(view.container.innerHTML).not.toMatch(/NaN|Infinity/);
    });
});
