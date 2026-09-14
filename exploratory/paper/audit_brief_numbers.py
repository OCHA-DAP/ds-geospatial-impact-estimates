"""Audit: every numeric literal in the brief's prose must come from a key, a computed chunk,
or the allowlist below (dates, units, design parameters). Exit 1 on any other literal, so the
publish step fails loudly instead of shipping a hand-typed number.

Usage: python audit_brief_numbers.py [--strict]   (strict: parameters must be keys too)
"""
import re, sys, pathlib
QMD = pathlib.Path(__file__).parent / "manuscript_brief.qmd"
NUM = re.compile(r"(?<![\w/#.-])(?:\d{1,3}(?:,\d{3})+|\d+\.\d+|\d+)(?:%|\s?km²|\s?m\b|×)?")
# literals that are allowed to be typed: dates and times, radii and cell sizes (design choices),
# document structure numbers. Anything derived from data is NOT allowed here.
ALLOW = {r"^\d{4}$", r"^\d{1,2}$", r"^\d{1,2}:\d{2}$", r"^(10|20|30|50) m$", r"^0\.74 km²$", r"^0\.7 km²$", r"^0\.1 km²$", r"^5\.2 km²$", r"^5 km²$",
         r"^\d{1,2} m$", r"^95%$", r"^72$", r"^20$", r"^400$", r"^133$", r"^2,000$", r"^M7\.[25]$",
         r"^200$", r"^728$", r"^1\.0$"}  # 200 km swath, 728 round-2 volunteers (campaign metadata), probability 1.0
allow = [re.compile(p) for p in ALLOW]
strict = "--strict" in sys.argv
in_code = in_yaml = False; bad = []
for i, l in enumerate(QMD.read_text().split("\n"), 1):
    s = l.strip()
    if i == 1 and s == "---": in_yaml = True; continue
    if in_yaml:
        if s == "---": in_yaml = False
        continue
    if s.startswith("```"): in_code = not in_code; continue
    if in_code or s.startswith("|") or s.startswith("<!--") or s.startswith("#"): continue
    l2 = re.sub(r"`\{python\} N\[[^\]]+\]`", "«K»", l)
    l2 = re.sub(r"@(fig|tbl|sec|app)-[\w-]+|\]\([^)]*\)|\{#[^}]*\}", "", l2)
    for m in NUM.finditer(l2):
        v = m.group(0)
        if any(p.match(v) for p in allow) and not strict: continue
        bad.append((i, v, l2.strip()[:100]))
keys = len(set(re.findall(r'\{python\} N\["([^"]+)"\]', QMD.read_text())))
print(f"brief_numbers audit: {keys} distinct keys inline; {len(bad)} hand-typed numeric literals outside the allowlist")
for i, v, ctx in bad: print(f"  line {i:5d}  {v:>10s}  {ctx}")
sys.exit(1 if bad else 0)
