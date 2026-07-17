// 将 SCAN.GATE 图标 SVG 光栅化为多尺寸 PNG。
// 用法: node render.js
const fs = require("fs");
const path = require("path");
const { Resvg } = require("@resvg/resvg-js");

const DIR = __dirname;
const full = fs.readFileSync(path.join(DIR, "scan_gate_icon.svg"), "utf8");
const small = fs.readFileSync(path.join(DIR, "scan_gate_glyph_small.svg"), "utf8");

// 小尺寸(<=32)用简化字形，其余用完整图标
const sizes = [512, 256, 128, 64, 48, 32, 16];
const out = {};

for (const s of sizes) {
  const svg = s <= 32 ? small : full;
  const r = new Resvg(svg, {
    fitTo: { mode: "width", value: s },
    background: "rgba(0,0,0,0)",
  });
  const png = r.render().asPng();
  const fp = path.join(DIR, `icon_${s}.png`);
  fs.writeFileSync(fp, png);
  out[s] = fp;
  console.log(`rendered ${s}x${s} -> ${path.basename(fp)} (${png.length} bytes)`);
}

// 额外：512 主图（完整）另存一份便于预览
fs.copyFileSync(out[512], path.join(DIR, "scan_gate_icon_512.png"));
console.log("DONE");
