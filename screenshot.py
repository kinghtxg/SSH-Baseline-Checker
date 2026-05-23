"""
截图引擎 - V4 真实shell风格
保留对方原始提示符，不做强制替换
"""
import os
import re
from PIL import Image, ImageDraw, ImageFont

FONT_SIZE = 14
LINE_H = 20
MARGIN_L = 16
IMAGE_W = 960


_FONT_CACHE = None


def get_font():
    """获取字体（优先使用支持中文的等宽或 CJK 字体）"""
    global _FONT_CACHE
    if _FONT_CACHE is not None:
        return _FONT_CACHE

    candidates = [
        # Windows: 微软雅黑（中文支持最好）
        'C:/Windows/Fonts/msyh.ttc',
        'C:/Windows/Fonts/msyhbd.ttc',
        # Windows: 等线（等宽 + CJK）
        'C:/Windows/Fonts/Deng.ttf',
        # Windows: Consolas + NSimSun 回退
        'C:/Windows/Fonts/consola.ttf',
        # Linux
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansMono-Regular.ttf',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                _FONT_CACHE = ImageFont.truetype(p, FONT_SIZE)
                return _FONT_CACHE
            except Exception:
                continue
    # 最终回退
    _FONT_CACHE = ImageFont.load_default()
    return _FONT_CACHE


def text_width(text, font=None):
    """计算视觉宽度（优先使用字体实际度量）"""
    if font and hasattr(font, 'getbbox'):
        # Pillow 9.2+: 使用 getbbox 精确测量
        try:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0]
        except Exception:
            pass
    # 回退：粗略估算，CJK 字符约占 1.8~2 倍等宽
    w = 0
    for ch in text:
        w += 2 if ord(ch) > 127 else 1
    return w


def wrap_line(line, max_w, font=None):
    """按视觉宽度换行"""
    if text_width(line, font) <= max_w:
        return [line] if line.strip() else []
    result = []
    cur = ''
    cur_w = 0
    for ch in line:
        cw = text_width(ch, font)
        if cur_w + cw > max_w:
            result.append(cur)
            cur = ch
            cur_w = cw
        else:
            cur += ch
            cur_w += cw
    if cur:
        result.append(cur)
    return result


def clean_ansi(text):
    """去除ANSI转义序列（覆盖 CSI / OSC / 其他控制序列）"""
    # CSI 序列: ESC [ 参数(数字;?等) 终止字母  (如 m/K/h/l/A-G 等)
    text = re.sub(r'\x1b\[[0-9;?]*[a-zA-Z]', '', text)
    # OSC 序列: ESC ] ... BEL(\x07) 或 ST(\x1b\\)
    text = re.sub(r'\x1b\].*?(\x07|\x1b\\)', '', text)
    # 其他 escape 序列 (如 ESC ( B 等字符集选择)
    text = re.sub(r'\x1b[^\[\]]', '', text)
    return text.replace('\r', '')


# 颜色配置
BG = (0, 0, 0)              # 黑底
FG = (220, 220, 220)        # 文字灰白
PROMPT_USER = (100, 200, 255)   # 用户名蓝色
PROMPT_HOST = (100, 255, 100)   # 主机名绿色
PROMPT_PATH = (255, 220, 100)   # 路径黄色
PROMPT_SYMBOL = (255, 255, 255) # $/# 白色
HEADER_BG = (30, 30, 30)
HEADER_FG = (150, 150, 150)
OK_COLOR = (50, 200, 50)
FAIL_COLOR = (220, 50, 50)
WARN_COLOR = (255, 180, 50)
DIM = (80, 80, 80)


def generate_screenshot(cmd_index, total, host_info, command, output,
                        exit_code, regex, regex_matched, duration,
                        prompt=None, save_dir='static/screenshots'):
    """
    生成真实终端风格截图
    prompt: 对方的实际shell提示符，如 [kinght@VM-0-9-tencentos ~]$
    """
    font = get_font()
    output_clean = clean_ansi(output or '')
    lines = output_clean.split('\n') if output_clean else ['(无输出)']

    # 计算高度
    max_c = IMAGE_W - MARGIN_L * 2  # 可用像素宽度
    content_lines = 0
    for ln in lines:
        ws = wrap_line(ln, max_c, font)
        content_lines += max(len(ws), 1)

    footer = 3 + (1 if regex else 0)
    total_l = 2 + content_lines + footer  # header + prompt/cmd + output + sep + status
    img_h = 46 + total_l * LINE_H + 12
    img_h = max(img_h, 280)

    img = Image.new('RGB', (IMAGE_W, img_h), BG)
    draw = ImageDraw.Draw(img)

    y = 0
    # 顶部信息栏
    draw.rectangle([(0, 0), (IMAGE_W, 38)], fill=HEADER_BG)
    draw.text((MARGIN_L, 8), f"[{cmd_index}/{total}]", font=font, fill=HEADER_FG)
    draw.text((IMAGE_W // 2 - 60, 8), host_info, font=font, fill=HEADER_FG)
    tw = draw.textbbox((0, 0), f"{duration:.2f}s", font=font)
    draw.text((IMAGE_W - MARGIN_L - (tw[2] - tw[0]), 8), f"{duration:.2f}s", font=font, fill=HEADER_FG)

    y = 46

    # 提示符 + 命令（使用对方真实提示符）
    display_prompt = prompt or '$'

    # 解析提示符颜色：尝试分割用户名@主机:路径$ 的格式
    # 简单处理：如果包含@符号，给不同部分上色
    px = MARGIN_L
    if '@' in display_prompt and ('$' in display_prompt or '#' in display_prompt):
        # 尝试解析 [user@host path]$ 格式
        parts = re.split(r'([@:\[\]\s\$#])', display_prompt)
        colors_cycle = [PROMPT_USER, (150, 150, 150), PROMPT_HOST, (150, 150, 150), PROMPT_PATH, PROMPT_SYMBOL]
        ci = 0
        for part in parts:
            if not part:
                continue
            color = PROMPT_SYMBOL if part in '$#' else colors_cycle[min(ci, len(colors_cycle) - 1)]
            if part not in '@:[] $#\n\r':
                ci = min(ci + 1, len(colors_cycle) - 1)
            draw.text((px, y), part, font=font, fill=color)
            bw = draw.textbbox((0, 0), part, font=font)
            px += bw[2] - bw[0]
    else:
        draw.text((px, y), display_prompt, font=font, fill=PROMPT_SYMBOL)
        bw = draw.textbbox((0, 0), display_prompt, font=font)
        px += bw[2] - bw[0]

    # 命令用绿色
    draw.text((px + 4, y), command, font=font, fill=(144, 238, 144))
    y += LINE_H

    # 分隔线
    dash_w = draw.textbbox((0, 0), '-', font=font)[2] or 8
    line_chars = (IMAGE_W - MARGIN_L * 2) // dash_w
    draw.text((MARGIN_L, y), '-' * line_chars, font=font, fill=DIM)
    y += LINE_H

    # 输出内容
    for ln in lines:
        if not ln.strip():
            y += LINE_H // 2
            continue
        ws = wrap_line(ln, max_c, font)
        for chunk in ws:
            draw.text((MARGIN_L, y), chunk, font=font, fill=FG)
            y += LINE_H

    y += LINE_H // 2

    # 底部分隔线
    draw.text((MARGIN_L, y), '-' * line_chars, font=font, fill=DIM)
    y += LINE_H

    # 正则匹配
    if regex:
        rd = regex[:50] + '...' if len(regex) > 50 else regex
        if regex_matched:
            draw.text((MARGIN_L, y), f"[OK] regex matched /{rd}/", font=font, fill=OK_COLOR)
        else:
            draw.text((MARGIN_L, y), f"[FAIL] regex no match /{rd}/", font=font, fill=WARN_COLOR)
        y += LINE_H

    # 退出码
    if exit_code == 0:
        draw.text((MARGIN_L, y), f"[EXIT 0] OK", font=font, fill=OK_COLOR)
    else:
        draw.text((MARGIN_L, y), f"[EXIT {exit_code}] FAILED", font=font, fill=FAIL_COLOR)

    # 保存
    os.makedirs(save_dir, exist_ok=True)
    safe = re.sub(r'[^\w\-]', '_', command)[:40]
    fn = f"cmd_{cmd_index}_{int(duration * 1000)}_{safe}.png"
    fp = os.path.join(save_dir, fn)
    img.save(fp, 'PNG')
    return f'/screenshots/{fn}'
