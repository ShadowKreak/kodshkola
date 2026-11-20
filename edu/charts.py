"""Серверная генерация SVG-графиков (без внешних библиотек)."""
from html import escape

from markupsafe import Markup


def line_chart(points, width=640, height=240, y_max=10):
    """points: список (подпись, значение). Значения 0..y_max."""
    if not points:
        return Markup('<div class="chart-empty">Пока нет оценок для графика</div>')
    pad_l, pad_r, pad_t, pad_b = 34, 16, 14, 34
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(points)
    xs = [pad_l + (w / 2 if n == 1 else i * w / (n - 1)) for i in range(n)]
    ys = [pad_t + h - (v / y_max) * h for _, v in points]
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="График оценок" preserveAspectRatio="xMidYMid meet">']
    for tick in range(0, y_max + 1, 2):
        y = pad_t + h - tick / y_max * h
        out.append(f'<line class="grid" x1="{pad_l}" x2="{width - pad_r}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(f'<text class="axis" x="{pad_l - 8}" y="{y + 4:.1f}" text-anchor="end">{tick}</text>')
    if n > 1:
        area = f"M{xs[0]:.1f},{pad_t + h} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in zip(xs, ys)) + f" L{xs[-1]:.1f},{pad_t + h} Z"
        out.append(f'<path class="area" d="{area}"/>')
        out.append('<polyline class="line" points="' + " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys)) + '"/>')
    step = max(1, n // 8)
    for i, ((label, val), x, y) in enumerate(zip(points, xs, ys)):
        out.append(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="4.5"><title>{escape(str(label))}: {val}</title></circle>')
        if i % step == 0 or i == n - 1:
            out.append(f'<text class="axis" x="{x:.1f}" y="{height - 12}" text-anchor="middle">{escape(str(label))}</text>')
    out.append("</svg>")
    return Markup("".join(out))


def bar_chart(labels, values, width=640, height=220):
    if not values or not any(values):
        return Markup('<div class="chart-empty">Пока нет проверенных работ</div>')
    pad_l, pad_r, pad_t, pad_b = 30, 10, 18, 30
    w, h = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(values)
    vmax = max(max(values), 1)
    slot = w / n
    bw = slot * 0.62
    out = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="Распределение оценок" preserveAspectRatio="xMidYMid meet">']
    out.append(f'<line class="grid" x1="{pad_l}" x2="{width - pad_r}" y1="{pad_t + h}" y2="{pad_t + h}"/>')
    for i, (lab, v) in enumerate(zip(labels, values)):
        bh = v / vmax * h
        x = pad_l + i * slot + (slot - bw) / 2
        y = pad_t + h - bh
        out.append(f'<rect class="cbar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="4"><title>Оценка {escape(str(lab))}: {v}</title></rect>')
        if v:
            out.append(f'<text class="axis val" x="{x + bw / 2:.1f}" y="{y - 5:.1f}" text-anchor="middle">{v}</text>')
        out.append(f'<text class="axis" x="{x + bw / 2:.1f}" y="{height - 10}" text-anchor="middle">{escape(str(lab))}</text>')
    out.append("</svg>")
    return Markup("".join(out))
