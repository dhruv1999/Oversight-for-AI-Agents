"""Make the README animation from the real corporate card example app.

    uv run python scripts/make_gif.py

Replays the sample morning one submission at a time, then has the approver answer what is left,
photographing the app's page after every step and adding a one line caption. Every frame is the
page the app itself renders at that moment. Needs Node with playwright, and Pillow.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "examples" / "corporate_card"
OUT = ROOT / "figures" / "card_app.gif"
WIDTH, HEIGHT, GIF_WIDTH = 1180, 1220, 900  # browser size, and the width of the finished GIF


def load_app():
    spec = importlib.util.spec_from_file_location("card_app", APP / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def caption(item: dict) -> str:
    amount = f"${item['amount']:,.2f}".replace(".00", "")
    what = f"{amount} {item['category'].lower()} from {item['employee'].split()[0]}"
    status = item["status"]
    if status == "Approved by the agent":
        return f"{what}: approved by the agent on its own"
    if status == "Approved after an automatic check":
        return f"{what}: approved after an automatic check"
    if status == "Approved by you":
        return f"{what}: sent to the approver, who approves"
    if status == "Rejected by you":
        return f"{what}: sent to the approver, who rejects"
    if item["check"].risk == "critical":
        return f"{what}: always waits for a person"
    return f"{what}: waits for the approver"


def main() -> None:
    app = load_app()
    submissions = json.loads((APP / "submissions.json").read_text(encoding="utf-8"))
    desk = app.Desk([])
    steps: list[tuple[str, str, int]] = [(desk.page(), "An AI expense agent starts processing the morning's card spend", 1600)]
    for s in submissions:
        desk.submit(s)
        steps.append((desk.page(), caption(desk.items[-1]), 1300))
    waiting = sorted((i for i, x in enumerate(desk.items) if x["status"] == "waiting"), key=lambda i: -desk.items[i]["amount"])
    for i in waiting:
        desk.decide(i, True)
        x = desk.items[i]
        steps.append((desk.page(), f"The approver approves the ${x['amount']:,.0f} {x['category'].lower()}", 1100))
    steps.append((desk.page(), "Small spend never reached the approver. Only the big requests did.", 3200))

    with tempfile.TemporaryDirectory() as tmp:
        shots = []
        for n, (html, _, _) in enumerate(steps):
            page = Path(tmp) / f"frame{n:02d}.html"
            page.write_text(html, encoding="utf-8")
            shots.append({"url": page.as_uri(), "out": str(Path(tmp) / f"frame{n:02d}.png"), "width": WIDTH, "height": HEIGHT, "clipHeight": HEIGHT})
        node_path = subprocess.run(["npm", "root", "-g"], capture_output=True, text=True, encoding="utf-8").stdout.strip()
        env = {**os.environ, "NODE_PATH": os.pathsep.join(p for p in (os.environ.get("NODE_PATH"), node_path) if p)}
        subprocess.run(["node", str(ROOT / "scripts" / "screenshot.cjs"), json.dumps(shots)], check=True, env=env)

        try:
            font = ImageFont.truetype(str(Path.home() / ".local/share/fonts/Inter-Variable.ttf"), 26)
            font.set_variation_by_name("SemiBold")
        except (OSError, ValueError):
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 24)
        frames, durations = [], []
        for (_, text, ms), shot in zip(steps, shots, strict=True):
            img = Image.open(shot["out"]).convert("RGB")
            img = img.resize((GIF_WIDTH, round(img.height * GIF_WIDTH / img.width)), Image.LANCZOS)
            bar = 64
            canvas = Image.new("RGB", (img.width, img.height + bar), "#1f2a44")
            canvas.paste(img, (0, bar))
            draw = ImageDraw.Draw(canvas)
            w = draw.textlength(text, font=font)
            draw.text(((img.width - w) / 2, bar / 2), text, font=font, fill="#ffffff", anchor="lm")
            frames.append(canvas.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
            durations.append(ms)
        frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB, {len(frames)} frames)")


if __name__ == "__main__":
    main()
