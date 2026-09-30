"""Append the latest games snapshot, with every arm's answers, to docs/GAMES-LOG.md (the committed audit trail).

    .venv/bin/python log_day.py
"""

from __future__ import annotations

import glob
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).parent
LOG = ROOT / "docs" / "GAMES-LOG.md"


def main() -> None:
    snap_path = sorted(p for p in (ROOT / "runs").glob("games-2*.json") if not p.stem.endswith("resolved"))[-1]
    snap = json.loads(snap_path.read_text())
    stamp = snap["stamp"]
    if f"games-{stamp}" in LOG.read_text():
        print(f"{stamp} already logged")
        return
    jev = [json.loads(Path(f).read_text())["answers"] for f in sorted(glob.glob(str(ROOT / "runs" / f"jev-games-{stamp}-run*.json")))]
    oj_files = glob.glob(str(ROOT / "runs" / f"openjev-games-{stamp}-run1.json"))
    oj = json.loads(Path(oj_files[0]).read_text())["answers"] if oj_files else {}
    rows = ["| Start (UTC) | League | Game (A vs B) | Market P(A) | Jev P(A) | Jev spread | openjev P(A) | Jev favours |",
            "|---|---|---|---|---|---|---|---|"]
    for g in snap["games"]:
        pj = statistics.mean(r[g["id"]]["p_a"] for r in jev)
        sp = statistics.mean(r[g["id"]]["spread"] for r in jev)
        po = f"{oj[g['id']]['p_a']:.3f}" if g["id"] in oj else "-"
        rows.append(f"| {g['starts'][5:16].replace('T', ' ')} | {g['league']} | {g['team_a']} vs {g['team_b']} | {g['price']:.3f} | "
                    f"{pj:.3f} | {sp:.2f} | {po} | {g['team_a'] if pj > 0.5 else g['team_b']} |")
    first = snap["games"][0]["starts"][:16] if snap["games"] else "-"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## {snap['fetched_at'][:16]} UTC — snapshot games-{stamp}, {len(snap['games'])} games; "
                 f"answered before the first start ({first} UTC)\n\n" + "\n".join(rows) + "\n")
    print(f"logged {stamp}: {len(snap['games'])} games")


if __name__ == "__main__":
    main()
