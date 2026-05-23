"""
截图引擎单元测试 - 测试 clean_ansi、wrap_line、text_width、generate_screenshot
"""
import os
import pytest
import re
from unittest.mock import patch, Mock, MagicMock
from screenshot import (
    clean_ansi, text_width, wrap_line, generate_screenshot,
    FONT_SIZE, LINE_H, MARGIN_L, IMAGE_W,
    BG, FG, DIM, OK_COLOR, FAIL_COLOR, WARN_COLOR,
)


class TestCleanANSI:
    """测试 clean_ansi 函数"""

    def test_clean_simple_ansi_color(self):
        """测试移除简单ANSI颜色序列"""
        text = "\x1b[32mgreen text\x1b[0m"
        result = clean_ansi(text)
        assert result == "green text"

    def test_clean_complex_ansi(self):
        """测试移除复杂ANSI序列"""
        text = "\x1b[1;32;44mstyled\x1b[0m \x1b[1Kclear line\x1b[3Acursor up"
        result = clean_ansi(text)
        assert "styled" in result
        assert "clear line" in result
        assert "cursor up" in result
        assert "\x1b[" not in result

    def test_clean_cursor_movement(self):
        """测试移除光标移动序列"""
        text = "line1\x1b[2Aline2\x1b[1Dtext"
        result = clean_ansi(text)
        assert "line1" in result
        assert "text" in result
        assert "\x1b[" not in result

    def test_clean_carriage_return(self):
        """测试移除回车符"""
        text = "line1\r\nline2\rline3"
        result = clean_ansi(text)
        assert '\r' not in result
        assert 'line1' in result
        assert 'line2' in result

    def test_clean_empty_string(self):
        """测试空字符串"""
        result = clean_ansi('')
        assert result == ''

    def test_clean_no_ansi(self):
        """测试无ANSI序列的文本"""
        text = "plain text without any control characters"
        result = clean_ansi(text)
        assert result == text

    def test_clean_only_ansi(self):
        """测试纯ANSI序列"""
        text = "\x1b[32m\x1b[1;33m\x1b[0m"
        result = clean_ansi(text)
        assert result == ''

    def test_clean_multiline(self):
        """测试多行文本"""
        text = "\x1b[32mline1\x1b[0m\n\x1b[33mline2\x1b[0m\nline3"
        result = clean_ansi(text)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result


class TestTextWidth:
    """测试 text_width 函数"""

    def test_ascii(self):
        assert text_width("abc") == 3

    def test_cjk(self):
        assert text_width("中文") == 4

    def test_mixed(self):
        assert text_width("hello世界") == 5 + 4

    def test_empty(self):
        assert text_width("") == 0

    def test_emoji(self):
        w = text_width("😀")
        assert w >= 1


class TestWrapLine:
    """测试 wrap_line 函数"""

    def test_no_wrap(self):
        result = wrap_line("short", 10)
        assert result == ["short"]

    def test_simple_wrap(self):
        result = wrap_line("abcdefghij", 5)
        assert result == ["abcde", "fghij"]

    def test_cjk_wrap(self):
        result = wrap_line("中文测试文本", 4)
        assert len(result) >= 2

    def test_empty(self):
        result = wrap_line('', 10)
        assert result == []

    def test_whitespace_only(self):
        result = wrap_line('   ', 10)
        assert result == []


class TestGenerateScreenshot:
    """测试 generate_screenshot — mock Pillow 底层操作"""

    @patch('screenshot.ImageDraw.Draw')
    @patch('screenshot.ImageFont.truetype')
    @patch('screenshot.Image.open')
    @patch('screenshot.os.makedirs')
    def _run_screenshot_test(self, mock_makedirs, mock_img_open, mock_font, mock_draw, **kwargs):
        """执行截图测试的通用 helper"""
        # Mock the draw object to avoid real Pillow operations
        mock_draw_instance = Mock()
        mock_draw_instance.textbbox.return_value = (0, 0, 80, 14)
        mock_draw.return_value = mock_draw_instance

        # Default parameters
        params = dict(
            cmd_index=1, total=5,
            host_info='testuser@192.168.1.1',
            command='ls -la',
            output='total 8\ndrwxr-xr-x 2 user user 4096 May 1 10:00 .',
            exit_code=0, regex=None, regex_matched=None,
            duration=1.23, prompt='[testuser@host ~]$'
        )
        params.update(kwargs)

        result = generate_screenshot(**params)
        assert result is not None
        return result

    def test_generate_basic(self):
        """测试基本截图生成"""
        result = self._run_screenshot_test()
        assert result.startswith('/screenshots/')
        assert result.endswith('.png')

    def test_generate_with_regex_match(self):
        """测试带正则匹配的截图（成功）"""
        result = self._run_screenshot_test(
            cmd_index=1, total=1,
            host_info='root@server',
            command='cat /etc/passwd',
            output='root:x:0:0:root:/root:/bin/bash',
            exit_code=0, regex=r'root:.*', regex_matched=True,
            duration=0.5, prompt='root@server:~#'
        )
        assert result is not None

    def test_generate_with_regex_fail(self):
        """测试带正则匹配的截图（失败）"""
        result = self._run_screenshot_test(
            cmd_index=2, total=3,
            host_info='user@host',
            command='systemctl status firewalld',
            output='Unit firewalld.service could not be found.',
            exit_code=1, regex=r'Active: active', regex_matched=False,
            duration=2.0, prompt='user@host:~$'
        )
        assert result is not None

    def test_generate_empty_output(self):
        """测试空输出截图"""
        result = self._run_screenshot_test(output=None, duration=0.1, prompt='$')
        assert result is not None

    def test_generate_long_output(self):
        """测试长输出截图"""
        long_output = '\n'.join([f'line_{i:03d}' for i in range(100)])
        result = self._run_screenshot_test(
            command='find /', output=long_output, duration=5.0, prompt='$'
        )
        assert result is not None

    def test_generate_with_cjk(self):
        """测试中文字符截图"""
        result = self._run_screenshot_test(
            host_info='中文用户@服务器',
            command='echo 中文测试',
            output='这是中文输出内容，包含全角字符。',
            duration=0.3, prompt='中文用户@服务器:~$'
        )
        assert result is not None

    def test_generate_root_prompt(self):
        """测试root提示符截图"""
        result = self._run_screenshot_test(
            host_info='root@server',
            command='whoami',
            output='root',
            duration=0.2, prompt='root@server:~#'
        )
        assert result is not None

    def test_generate_nonzero_exit(self):
        """测试非零退出码截图"""
        result = self._run_screenshot_test(
            cmd_index=3, total=5,
            host_info='user@host',
            command='invalid_command',
            output='command not found',
            exit_code=127, duration=0.5, prompt='$'
        )
        assert result is not None