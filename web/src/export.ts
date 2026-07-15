// Client-side Excel export (ADR-0011): builds the same styled workbook the server's
// /api/export.xlsx produced (README + adm1/2/3 sheets), from platinum artifacts —
// values/export-adm{level}.parquet (numbers precomputed in the pipeline, identical to
// the server's) + meta/export_meta.json (glossary/source blurbs from the same
// constants). This module is dynamically imported on click so exceljs stays out of
// the main bundle.
import ExcelJS from "exceljs";
import { asyncBufferFromUrl, parquetReadObjects } from "hyparquet";

// Deterministic column order per level (mirrors gie.serving.load_export's SELECT).
const COLS = (level: number) => [
  ...Array.from({ length: level }, (_, i) => `adm${i + 1}_name`),
  "unit_id", "source", "total_buildings", "analysed_buildings",
  "pct_buildings_covered", "damaged", "damage_fraction",
  "analysed_area_km2", "unit_area_km2", "area_coverage_fraction",
];
const PCT = new Set(["pct_buildings_covered", "damage_fraction", "area_coverage_fraction"]);

// Styling constants — 1:1 with the openpyxl version (gie.serving.export_workbook).
const GREEN = "FF55B284";
const BAND = "FFEAF4EE";
const HAIR = { style: "thin" as const, color: { argb: "FFD3D3D3" } };
const BORDER = { top: HAIR, left: HAIR, bottom: HAIR, right: HAIR };
const fill = (argb: string) => ({ type: "pattern" as const, pattern: "solid" as const, fgColor: { argb } });

export async function downloadExport(tok: any): Promise<void> {
  const base = `${tok.base_url}/${tok.platinum_dir}`;
  const meta = await fetch(`${base}/meta/export_meta.json?${tok.sas}`).then((r) => r.json());

  const wb = new ExcelJS.Workbook();

  // --- README ------------------------------------------------------------------
  const rm = wb.addWorksheet("README", { views: [{ showGridLines: false }] });
  rm.getCell("A1").value = "Venezuela Earthquake — Building Damage Exposure by Admin Unit";
  rm.getCell("A1").font = { bold: true, size: 22, color: { argb: "FF3E8F6B" } };
  rm.getCell("A2").value =
    "Multi-source — " + meta.subtitle_sources.join(", ") + " — buildings & damage by OCHA COD admin 1 / 2 / 3";
  rm.getCell("A2").font = { italic: true, size: 13, color: { argb: "FF333333" } };
  const tier = tok.platinum_dir === "platinum-prod" ? "prod" : "staging";
  rm.getCell("A3").value =
    `OCHA Centre for Humanitarian Data  ·  activation EMSR884  ·  generated ${new Date().toISOString().slice(0, 10)}  ·  ${tier}`;
  rm.getCell("A3").font = { size: 10, color: { argb: "FF888888" } };
  rm.getCell("A5").value = "Columns — meaning & derivation";
  rm.getCell("A5").font = { bold: true, size: 12, color: { argb: "FFFFFFFF" } };
  rm.getCell("A5").fill = fill(GREEN);
  rm.getCell("B5").fill = fill(GREEN);
  rm.getCell("A6").value = "Column";
  rm.getCell("B6").value = "How it is derived";
  for (const c of ["A6", "B6"]) {
    const cell = rm.getCell(c);
    cell.font = { bold: true, color: { argb: "FFFFFFFF" }, size: 11 };
    cell.fill = fill(GREEN);
    cell.alignment = { vertical: "middle", indent: 1 };
    cell.border = BORDER;
  }
  meta.glossary.forEach(([col, desc]: [string, string], j: number) => {
    const i = j + 7;
    rm.getCell(`A${i}`).value = col;
    rm.getCell(`B${i}`).value = desc;
    rm.getCell(`A${i}`).font = { bold: true, color: { argb: "FF333333" } };
    rm.getCell(`B${i}`).font = { color: { argb: "FF333333" } };
    for (const c of [`A${i}`, `B${i}`]) {
      const cell = rm.getCell(c);
      cell.alignment = { vertical: "top", wrapText: true };
      cell.border = BORDER;
      if (i % 2 === 0) cell.fill = fill(BAND);
    }
    rm.getRow(i).height = Math.max(16, 15 * (Math.floor(desc.length / 88) + 1));
  });
  rm.getColumn("A").width = 30;
  rm.getColumn("B").width = 92;

  // --- adm1/2/3 data sheets ------------------------------------------------------
  // fetch all three levels in parallel before building
  const levelRows = await Promise.all(
    [1, 2, 3].map(async (level) =>
      (await parquetReadObjects({
        file: await asyncBufferFromUrl({ url: `${base}/values/export-adm${level}.parquet?${tok.sas}` }),
      })) as any[],
    ),
  );
  for (const level of [1, 2, 3]) {
    const rows = levelRows[level - 1];
    const cols = COLS(level);
    const ws = wb.addWorksheet(`adm${level}`, {
      views: [{ state: "frozen", ySplit: 1, showGridLines: false }],
    });
    ws.addRow(cols);
    for (const r of rows) ws.addRow(cols.map((c) => (r[c] == null || Number.isNaN(r[c]) ? null : r[c])));
    const head = ws.getRow(1);
    head.height = 30;
    head.eachCell((cell) => {
      cell.fill = fill(GREEN);
      cell.font = { bold: true, color: { argb: "FFFFFFFF" }, size: 11 };
      cell.alignment = { horizontal: "center", vertical: "middle", wrapText: true };
      cell.border = BORDER;
    });
    ws.autoFilter = { from: { row: 1, column: 1 }, to: { row: rows.length + 1, column: cols.length } };
    cols.forEach((name, i) => {
      const col = ws.getColumn(i + 1);
      col.width = Math.max(name.length + 2, name === "unit_id" || name === "source" ? 22 : 14);
      if (name !== "source" && !name.includes("name") && name !== "unit_id")
        // column-level format (one style op instead of one per cell); the header cell
        // is text, so the numeric format has no visible effect on it
        col.numFmt = PCT.has(name) ? "0.0%" : name.endsWith("km2") ? "0.00" : "#,##0";
    });
    for (let r = 2; r <= rows.length + 1; r++)
      if (r % 2 === 0) ws.getRow(r).eachCell({ includeEmpty: true }, (cell) => (cell.fill = fill(BAND)));
  }

  const buf = await wb.xlsx.writeBuffer();
  const url = URL.createObjectURL(
    new Blob([buf], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "ven_earthquake_damage_compilation_by_admin.xlsx";
  a.click();
  URL.revokeObjectURL(url);
}
