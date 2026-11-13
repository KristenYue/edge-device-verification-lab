from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 675
BACKGROUND = "#0d1117"
PANEL = "#161b22"
GREEN = "#3fb950"
BLUE = "#58a6ff"
MUTED = "#8b949e"
TEXT = "#f0f6fc"


def font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf"
    return ImageFont.truetype(name, size)


def frame(step: int, title: str, lines: list[tuple[str, str]]) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((45, 40, WIDTH - 45, HEIGHT - 40), radius=18, fill=PANEL)
    draw.ellipse((72, 65, 88, 81), fill="#ff5f56")
    draw.ellipse((98, 65, 114, 81), fill="#ffbd2e")
    draw.ellipse((124, 65, 140, 81), fill="#27c93f")
    draw.text(
        (165, 58),
        "edge-device validation / control protocol",
        font=font(22),
        fill=MUTED,
    )
    draw.text((75, 120), f"{step:02d}  {title}", font=font(34, bold=True), fill=TEXT)
    y = 190
    for prefix, value in lines:
        draw.text((90, y), prefix, font=font(24, bold=True), fill=BLUE)
        draw.text((330, y), value, font=font(24), fill=GREEN if "PASS" in value else TEXT)
        y += 55
    draw.text(
        (75, HEIGHT - 82),
        "protocol implementation — not production device-control",
        font=font(19),
        fill=MUTED,
    )
    draw.rounded_rectangle(
        (WIDTH - 230, HEIGHT - 92, WIDTH - 75, HEIGHT - 62), radius=12, fill="#21262d"
    )
    draw.rectangle((WIDTH - 220, HEIGHT - 84, WIDTH - 220 + step * 12, HEIGHT - 70), fill=GREEN)
    return image


def main() -> None:
    scenes = [
        (
            "Scope",
            [
                ("project", "virtual edge device"),
                ("boundary", "deterministic model, no real tool"),
            ],
        ),
        ("Build", [("C++17", "CMake + CTest PASS"), ("Python", "pytest + strict contracts")]),
        ("Communications", [("CONNECT", "OFFLINE -> ONLINE / LOCAL"), ("result", "connected")]),
        ("Control", [("request", "ONLINE / REMOTE"), ("guard", "remote command allowed")]),
        (
            "TaskProfile",
            [("REMOTE_COMMAND", "PROFILE DEMO-01"), ("validation", "boundaries + state PASS")],
        ),
        ("Start", [("REMOTE_COMMAND", "START"), ("event", "RUN_COMPLETE")]),
        (
            "Duplicate",
            [("request_id", "demo-start-1 replay"), ("idempotency", "one run PASS")],
        ),
        (
            "TCP framing",
            [("half packet", "reassembled PASS"), ("sticky packet", "2 messages PASS")],
        ),
        ("Alarm", [("fault", "INTERLOCK_OPEN"), ("alarm report", "ALARM-1001 PASS")]),
        ("Recovery", [("timeout", "retry with stable ID"), ("response", "cached replay PASS")]),
        (
            "Concurrency",
            [
                ("worker pool", "bounded queue + backpressure PASS"),
                ("duplicate START", "one execution PASS"),
            ],
        ),
        (
            "Smart Shelf",
            [("telemetry", "ordering + isolation PASS"), ("commands", "device authorization PASS")],
        ),
        ("Evidence", [("Python", "98 passed / 83.30% coverage"), ("C++", "CTest PASS")]),
        (
            "Traceability",
            [("requirements", "mapped to tests"), ("release", "qualified with limits")],
        ),
    ]
    frames = [frame(index, title, lines) for index, (title, lines) in enumerate(scenes, 1)]
    output = Path(__file__).resolve().parents[1] / "docs" / "assets" / "validation-demo.gif"
    output.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=5000, loop=0)
    print(output)


if __name__ == "__main__":
    main()




