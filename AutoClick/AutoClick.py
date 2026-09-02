import ctypes
from ctypes import wintypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

import keyboard
import pyautogui
import win32api
import win32con
import win32gui
import win32process

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
LAST_SESSION_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "last_session.json")
NUM_POINTS = 10
MAX_LEVEL = 4  # 0~4 共 5 级
DEFAULT_HOTKEYS = [f"ctrl+shift+{i if i < 10 else 0}" for i in range(1, NUM_POINTS + 1)]


class MacroCommand:
    def __init__(self, cmd_type, params=None, line_num=0, raw_text=""):
        self.cmd_type = cmd_type  # CLICK, CLICK_POINT, DELAY, LOOP_START, LOOP_END, DRAG, INPUT_TEXT, COMMENT
        self.params = params or {}
        self.line_num = line_num
        self.raw_text = raw_text


def safe_eval_expr(expr_str, scope_vars):
    """安全求值表达式/变量值 (支持 int, float, bool, str, 算术运算及变量查找)"""
    expr = expr_str.strip()
    # 大小写兼容处理 true/false/null
    expr_trans = re.sub(r"\btrue\b", "True", expr, flags=re.IGNORECASE)
    expr_trans = re.sub(r"\bfalse\b", "False", expr_trans, flags=re.IGNORECASE)
    expr_trans = re.sub(r"\bnull\b", "None", expr_trans, flags=re.IGNORECASE)

    safe_env = {
        "__builtins__": {},
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "True": True,
        "False": False,
        "None": None,
    }
    safe_env.update(scope_vars)

    try:
        return eval(expr_trans, safe_env)
    except Exception:
        if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
            return expr[1:-1]
        if expr in scope_vars:
            return scope_vars[expr]
        return expr


def safe_eval_cond(cond_str, scope_vars):
    """安全求值 If 条件表达式 (支持 ==, !=, >, <, >=, <=, and, or, not, 单变量真值判断)"""
    cond = cond_str.strip()
    if not cond:
        return False

    # 支持 = 单等号容错为 ==
    cond = re.sub(r"(?<![=!<>])=(?![=])", "==", cond)
    # 支持 !var -> not var
    cond = re.sub(r"!(?!=)", " not ", cond)

    cond_trans = re.sub(r"\btrue\b", "True", cond, flags=re.IGNORECASE)
    cond_trans = re.sub(r"\bfalse\b", "False", cond_trans, flags=re.IGNORECASE)
    cond_trans = re.sub(r"\bnull\b", "None", cond_trans, flags=re.IGNORECASE)

    safe_env = {
        "__builtins__": {},
        "int": int,
        "float": float,
        "str": str,
        "bool": bool,
        "True": True,
        "False": False,
        "None": None,
    }
    safe_env.update(scope_vars)

    try:
        return bool(eval(cond_trans, safe_env))
    except Exception:
        if cond in scope_vars:
            return bool(scope_vars[cond])
        return False


def strip_inline_comment(raw_line):
    """去除行尾注释 // ... (保留引号内的 //)"""
    in_quotes = False
    quote_char = None
    for i in range(len(raw_line) - 1):
        ch = raw_line[i]
        if ch in ['"', "'"]:
            if not in_quotes:
                in_quotes = True
                quote_char = ch
            elif quote_char == ch:
                in_quotes = False
        elif not in_quotes and (raw_line[i:i+2] == "//" or raw_line[i] == "#"):
            return raw_line[:i].strip()
    return raw_line.strip()


def split_macro_args(arg_str):
    """按逗号拆分宏参数列表，自动保护双引号/单引号/括号/中括号内部的逗号"""
    parts = []
    cur = ""
    in_quotes = False
    quote_char = ""
    nest_depth = 0
    for ch in arg_str:
        if ch in ['"', "'"]:
            if not in_quotes:
                in_quotes = True
                quote_char = ch
            elif quote_char == ch:
                in_quotes = False
            cur += ch
        elif not in_quotes:
            if ch in ['(', '[', '{']:
                nest_depth += 1
                cur += ch
            elif ch in [')', ']', '}']:
                nest_depth = max(0, nest_depth - 1)
                cur += ch
            elif ch == ',' and nest_depth == 0:
                parts.append(cur.strip())
                cur = ""
            else:
                cur += ch
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


def parse_macro_script(script_text):
    """按键脚本 DSL 解析器，将文本解析为可调度的 Command 指令列表 (支持全参数变量与表达式、If-Else 分支、/// 块注释)"""
    lines = script_text.splitlines()
    commands = []
    in_block_comment = False

    for idx, line in enumerate(lines, 1):
        raw = line.strip()
        if not raw:
            continue

        # 检查是否为块注释标记 /// (要求 /// 必须在行首，前面仅允许空格)
        if line.lstrip().startswith("///"):
            in_block_comment = not in_block_comment
            commands.append(MacroCommand("COMMENT", {"text": raw}, idx, raw))
            continue

        if in_block_comment:
            commands.append(MacroCommand("COMMENT", {"text": raw}, idx, raw))
            continue

        if raw.startswith("//") or raw.startswith("#"):
            commands.append(MacroCommand("COMMENT", {"text": raw}, idx, raw))
            continue

        raw = strip_inline_comment(raw)
        if not raw:
            continue

        # 检查行尾是否有独立的 } (如 ClickEx(...) } 或 Click(...) } )
        has_trailing_brace = False
        if raw.endswith("}") and raw != "}" and not raw.lower().startswith("loop") and not raw.lower().startswith("if") and not raw.lower().startswith("else"):
            raw = raw[:-1].strip()
            has_trailing_brace = True

        # 1. 组合行: } Else { 或 } Else 或 } else {
        m_close_else = re.match(r"^\}\s*else(?:\s*\{)?$", raw, re.IGNORECASE)
        if m_close_else:
            commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            commands.append(MacroCommand("ELSE", {}, idx, "Else {"))
            continue

        # 2. 独立 Else: Else { 或 Else
        m_else = re.match(r"^else(?:\s*\{)?$", raw, re.IGNORECASE)
        if m_else:
            commands.append(MacroCommand("ELSE", {}, idx, raw))
            continue

        # 3. If 条件语句 (同时支持单行 If 如 If (Tier == 2) RounfTime=101000 与多行块级 If)
        if raw.lower().startswith("if ") or raw.lower().startswith("if("):
            after_if = raw[2:].strip()
            cond_str = ""
            action_part = ""

            if after_if.startswith("("):
                depth = 0
                match_end = -1
                for ci, ch in enumerate(after_if):
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            match_end = ci
                            break
                if match_end != -1:
                    cond_str = after_if[1:match_end].strip()
                    action_part = after_if[match_end + 1:].strip()
                else:
                    cond_str = after_if.lstrip("(").rstrip("){").strip()
            else:
                if " then " in f" {after_if.lower()} ":
                    m_then = re.search(r"\bthen\b", after_if, re.IGNORECASE)
                    if m_then:
                        cond_str = after_if[:m_then.start()].strip()
                        action_part = after_if[m_then.end():].strip()
                elif "{" in after_if:
                    brace_pos = after_if.find("{")
                    cond_str = after_if[:brace_pos].strip()
                    action_part = after_if[brace_pos:].strip()
                else:
                    cond_str = after_if.strip()

            cond_str = cond_str.strip()
            if cond_str.startswith("(") and cond_str.endswith(")"):
                cond_str = cond_str[1:-1].strip()

            # 判断是否有单行跟随的动作 (单行 If)
            if action_part and action_part != "{" and action_part != "{":
                clean_act = action_part.strip()
                if clean_act.startswith("{") and clean_act.endswith("}"):
                    clean_act = clean_act[1:-1].strip()
                elif clean_act.startswith("{"):
                    clean_act = clean_act[1:].strip()

                if clean_act:
                    # 检查是否有单行 Else (例如: If (cond) act1 Else act2)
                    m_inline_else = re.search(r"\belse\b", clean_act, re.IGNORECASE)
                    if m_inline_else:
                        then_act = clean_act[:m_inline_else.start()].strip().rstrip("};")
                        else_act = clean_act[m_inline_else.end():].strip().strip("{}")
                        commands.append(MacroCommand("IF_START", {"condition": cond_str}, idx, f"If ({cond_str}) {{"))
                        if then_act:
                            sub_cmds = parse_macro_script(then_act)
                            commands.extend(sub_cmds)
                        commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
                        commands.append(MacroCommand("ELSE", {}, idx, "Else {"))
                        if else_act:
                            sub_cmds = parse_macro_script(else_act)
                            commands.extend(sub_cmds)
                        commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
                        continue
                    else:
                        # 单行 If 无 Else (如 If (Tier == 2) RounfTime=101000)
                        commands.append(MacroCommand("IF_START", {"condition": cond_str}, idx, f"If ({cond_str}) {{"))
                        sub_cmds = parse_macro_script(clean_act)
                        commands.extend(sub_cmds)
                        commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
                        continue

            # 多行块级 If
            commands.append(MacroCommand("IF_START", {"condition": cond_str}, idx, raw))
            continue

        # 4. Loop(5) { 或 Loop(rounds) {
        m_loop = re.match(r"^Loop\s*\(\s*(.*?)\s*\)\s*\{?$", raw, re.IGNORECASE)
        if m_loop:
            cnt_expr = m_loop.group(1).strip()
            try:
                cnt_val = int(cnt_expr)
            except ValueError:
                cnt_val = 1
            commands.append(MacroCommand("LOOP_START", {"count": cnt_val, "count_expr": cnt_expr}, idx, raw))
            continue

        # 5. 块结束标记: } 或 EndLoop 或 EndIf 或 Next (忽略大小写)
        if raw.lower() in ["}", "endloop", "endif", "next"]:
            commands.append(MacroCommand("BLOCK_END", {}, idx, raw))
            continue

        # 6. 变量定义/赋值: InTournament = 1 或 targetY = 283 或 Var X = 10
        m_assign = re.match(r"^(?:(?:var|set)\s+)?([a-zA-Z_]\w*)\s*=\s*(.+)$", raw, re.IGNORECASE)
        if m_assign and not raw.startswith("Click") and not raw.startswith("Timer") and not raw.startswith("Delay") and not raw.startswith("Drag") and not raw.startswith("Input"):
            var_name = m_assign.group(1).strip()
            var_expr = m_assign.group(2).strip()
            commands.append(MacroCommand("VAR_ASSIGN", {"name": var_name, "expr": var_expr}, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # ClickPoint(#1) 或 ClickPoint(1) 或 ClickPoint(#1, count)
        m_cp = re.match(r"^ClickPoint\s*\(\s*(.*?)\s*\)$", raw, re.IGNORECASE)
        if m_cp:
            cp_args = split_macro_args(m_cp.group(1))
            pt_idx_str = cp_args[0].lstrip("#") if len(cp_args) >= 1 else "1"
            cnt_str = cp_args[1] if len(cp_args) >= 2 else "1"
            try:
                pt_idx = int(pt_idx_str) - 1
            except ValueError:
                pt_idx = 0
            try:
                cnt_val = int(cnt_str)
            except ValueError:
                cnt_val = 1
            commands.append(MacroCommand("CLICK_POINT", {"index": pt_idx, "count": cnt_val, "index_expr": pt_idx_str, "count_expr": cnt_str}, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # ClickEx(level, x, y, delay, interval, count, "remark", timer_id) - 全参数支持变量与算术表达式
        m_cex = re.match(r"^ClickEx\s*\(\s*(.*?)\s*\)$", raw, re.IGNORECASE)
        if m_cex:
            parts = split_macro_args(m_cex.group(1))
            level_expr, x_expr, y_expr = "0", "0", "0"
            delay_expr, interval_expr, count_expr = "0.0", "0.5", "1"
            remark_expr, timer_id_expr = "", "0"

            if len(parts) >= 8:
                level_expr, x_expr, y_expr = parts[0], parts[1], parts[2]
                delay_expr, interval_expr, count_expr = parts[3], parts[4], parts[5]
                remark_expr, timer_id_expr = parts[6], parts[7]
            elif len(parts) == 7:
                level_expr, x_expr, y_expr = parts[0], parts[1], parts[2]
                delay_expr, interval_expr, count_expr = parts[3], parts[4], parts[5]
                remark_expr = parts[6]
            elif len(parts) == 6:
                level_expr, x_expr, y_expr = parts[0], parts[1], parts[2]
                delay_expr, interval_expr, count_expr = parts[3], parts[4], parts[5]
            elif len(parts) == 5:
                level_expr, x_expr, y_expr = parts[0], parts[1], parts[2]
                delay_expr, interval_expr = parts[3], parts[4]
            elif len(parts) == 4:
                level_expr, x_expr, y_expr = parts[0], parts[1], parts[2]
                delay_expr = parts[3]
            elif len(parts) == 3:
                if parts[2].startswith('"') or parts[2].startswith("'"):
                    x_expr, y_expr, remark_expr = parts[0], parts[1], parts[2]
                else:
                    level_expr, x_expr, y_expr = parts[0], parts[1], parts[2]
            elif len(parts) == 2:
                x_expr, y_expr = parts[0], parts[1]

            def _try_int(s, def_v=0):
                try:
                    return int(s)
                except Exception:
                    return def_v

            def _try_float(s, def_v=0.0):
                try:
                    return float(s)
                except Exception:
                    return def_v

            commands.append(MacroCommand("CLICK_EX", {
                "level": _try_int(level_expr, 0),
                "x": _try_int(x_expr, 0),
                "y": _try_int(y_expr, 0),
                "delay": _try_float(delay_expr, 0.0),
                "interval": _try_float(interval_expr, 0.5),
                "count": _try_int(count_expr, 1),
                "remark": remark_expr.strip("\"'"),
                "timer_id": _try_int(timer_id_expr, 0),
                "level_expr": level_expr,
                "x_expr": x_expr,
                "y_expr": y_expr,
                "delay_expr": delay_expr,
                "interval_expr": interval_expr,
                "count_expr": count_expr,
                "remark_expr": remark_expr,
                "timer_id_expr": timer_id_expr,
            }, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # TimerStart(1) / TimerReset(1) / Timer(1, start) / Timer(1)
        m_tstart = re.match(r"^(?:TimerStart|TimerReset)\s*\(\s*#?(\d+)\s*\)$", raw, re.IGNORECASE)
        if not m_tstart:
            m_tstart = re.match(r"^Timer\s*\(\s*#?(\d+)(?:\s*,\s*[\"']?(start|reset)[\"']?)?\s*\)$", raw, re.IGNORECASE)

        if m_tstart:
            tid = int(m_tstart.group(1))
            is_reset = raw.lower().startswith("timerreset") or (m_tstart.lastindex and m_tstart.lastindex >= 2 and (m_tstart.group(2) or "").lower() == "reset")
            cmd_type = "TIMER_RESET" if is_reset else "TIMER_START"
            commands.append(MacroCommand(cmd_type, {"id": tid}, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # TimerStop(1) / Timer(1, stop)
        m_tstop = re.match(r"^TimerStop\s*\(\s*#?(\d+)\s*\)$", raw, re.IGNORECASE)
        if not m_tstop:
            m_tstop = re.match(r"^Timer\s*\(\s*#?(\d+)\s*,\s*[\"']?stop[\"']?\s*\)$", raw, re.IGNORECASE)

        if m_tstop:
            tid = int(m_tstop.group(1))
            commands.append(MacroCommand("TIMER_STOP", {"id": tid}, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # Click(x, y) 或 Click(x, y, count) 或 Click(x, y, count, interval_ms)
        m_click = re.match(r"^Click\s*\(\s*(.*?)\s*\)$", raw, re.IGNORECASE)
        if m_click:
            parts = split_macro_args(m_click.group(1))
            x_expr = parts[0] if len(parts) >= 1 else "0"
            y_expr = parts[1] if len(parts) >= 2 else "0"
            cnt_expr = parts[2] if len(parts) >= 3 else "1"
            intv_expr = parts[3] if len(parts) >= 4 else "100"

            def _ti(s, d=0):
                try:
                    return int(s)
                except Exception:
                    return d

            commands.append(MacroCommand("CLICK", {
                "x": _ti(x_expr, 0),
                "y": _ti(y_expr, 0),
                "count": _ti(cnt_expr, 1),
                "interval_ms": _ti(intv_expr, 100),
                "x_expr": x_expr,
                "y_expr": y_expr,
                "count_expr": cnt_expr,
                "interval_ms_expr": intv_expr,
            }, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # Delay(1000) 或 Sleep(1000) 或 Delay(1.5s) 或 Delay(wait_time)
        m_delay = re.match(r"^(?:Delay|Sleep)\s*\(\s*(.*?)\s*\)$", raw, re.IGNORECASE)
        if m_delay:
            d_arg = m_delay.group(1).strip()
            delay_ms = 1000
            m_num = re.match(r"^([\d\.]+)(s|ms)?$", d_arg, re.IGNORECASE)
            if m_num:
                val = float(m_num.group(1))
                unit = (m_num.group(2) or "ms").lower()
                delay_ms = int(val * 1000) if unit == "s" else int(val)

            commands.append(MacroCommand("DELAY", {"delay_ms": delay_ms, "delay_expr": d_arg}, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # Drag(x1, y1, x2, y2, duration_ms) 或 Swipe(...)
        m_drag = re.match(r"^(?:Drag|Swipe)\s*\(\s*(.*?)\s*\)$", raw, re.IGNORECASE)
        if m_drag:
            parts = split_macro_args(m_drag.group(1))
            x1_expr = parts[0] if len(parts) >= 1 else "0"
            y1_expr = parts[1] if len(parts) >= 2 else "0"
            x2_expr = parts[2] if len(parts) >= 3 else "0"
            y2_expr = parts[3] if len(parts) >= 4 else "0"
            dur_expr = parts[4] if len(parts) >= 5 else "500"

            def _ti(s, d=0):
                try:
                    return int(s)
                except Exception:
                    return d

            commands.append(MacroCommand("DRAG", {
                "x1": _ti(x1_expr, 0),
                "y1": _ti(y1_expr, 0),
                "x2": _ti(x2_expr, 0),
                "y2": _ti(y2_expr, 0),
                "duration_ms": _ti(dur_expr, 500),
                "x1_expr": x1_expr,
                "y1_expr": y1_expr,
                "x2_expr": x2_expr,
                "y2_expr": y2_expr,
                "duration_ms_expr": dur_expr,
            }, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # Input("text") 或 InputText("text") 或 InputText(var_name)
        m_input = re.match(r"^(?:Input|InputText)\s*\(\s*(.*?)\s*\)$", raw, re.IGNORECASE)
        if m_input:
            text_expr = m_input.group(1).strip()
            text_val = text_expr.strip("\"'")
            commands.append(MacroCommand("INPUT_TEXT", {"text": text_val, "text_expr": text_expr}, idx, raw))
            if has_trailing_brace:
                commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))
            continue

        # 其它未识别行视作注释
        commands.append(MacroCommand("COMMENT", {"text": f"// {raw}"}, idx, raw))
        if has_trailing_brace:
            commands.append(MacroCommand("BLOCK_END", {}, idx, "}"))

    return commands


class ToolTip:
    """Tkinter 鼠标悬停提示框 (ToolTip) 类"""
    def __init__(self, widget, text, delay=300):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.id = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.delay, self.showtip)

    def unschedule(self):
        if self.id:
            self.widget.after_cancel(self.id)
            self.id = None

    def showtip(self, event=None):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 5
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify="left",
            background="#ffffe0",
            foreground="#2c3e50",
            relief="solid",
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=6,
            pady=4,
        )
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


def format_target_title_components(raw_title):
    """
    解析目标窗口字符串，返回 (pid_val, prog_name)。
    过滤清理 HWND 信息以及多重 PID 前缀。
    """
    raw_title = (raw_title or "").strip()
    if not raw_title or raw_title == "选择目标窗口...":
        return "", "未选择目标窗口"

    pid_val = ""
    pid_m = re.search(r"PID:(\d+)", raw_title)
    if pid_m:
        pid_val = pid_m.group(1)

    prog_name = raw_title
    while True:
        new_name = re.sub(r"^\[[^\]]+\]\s*", "", prog_name)
        if new_name == prog_name:
            break
        prog_name = new_name

    return pid_val, prog_name


def get_last_used_config():
    """获取上次使用的配置文件路径"""
    if os.path.exists(LAST_SESSION_FILE):
        try:
            with open(LAST_SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                filepath = data.get("last_config_file")
                if filepath and os.path.exists(filepath):
                    return filepath
        except Exception:
            pass
    return CONFIG_FILE


def save_last_used_config(filepath):
    """记录当前使用的配置文件路径，以便下次启动时默认加载"""
    try:
        with open(LAST_SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump({"last_config_file": os.path.abspath(filepath)}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def get_window_list():
    """获取系统当前可用的顶层窗口列表 [(hwnd, title)]"""
    windows = []

    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).strip()
            if title and title not in ["Program Manager"]:
                windows.append((hwnd, title))
        return True

    win32gui.EnumWindows(enum_cb, None)
    return windows


def post_background_click(hwnd, x, y):
    """向指定 HWND 发送后台鼠标点击消息 (x, y 为窗口内部相对坐标)"""
    if not win32gui.IsWindow(hwnd):
        return False

    client_x, client_y = int(x), int(y)
    lparam = win32api.MAKELONG(max(0, client_x), max(0, client_y))

    # 尝试寻找点位下的子窗口句柄 (应对特定嵌套控件/Chrome渲染面)
    try:
        screen_pt = win32gui.ClientToScreen(hwnd, (client_x, client_y))
        child_hwnd = win32gui.WindowFromPoint(screen_pt)
        target_h = child_hwnd if child_hwnd and win32gui.IsChild(hwnd, child_hwnd) else hwnd
        if target_h != hwnd:
            cx, cy = win32gui.ScreenToClient(target_h, screen_pt)
            lparam = win32api.MAKELONG(max(0, cx), max(0, cy))
    except Exception:
        target_h = hwnd

    win32gui.PostMessage(target_h, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lparam)
    time.sleep(0.015)
    win32gui.PostMessage(target_h, win32con.WM_LBUTTONUP, 0, lparam)
    return True


def detect_adb_ports_by_hwnd(hwnd):
    """通用算法：获取目标窗口进程在系统监听的 TCP 本地端口 (支持所有模拟器)"""
    if not hwnd or not win32gui.IsWindow(hwnd):
        return []

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if not pid:
            return []

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        out = subprocess.check_output("netstat -ano", shell=True, creationflags=flags, text=True, timeout=5)

        found_ports = []
        pid_str = str(pid)
        for line in out.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and parts[0].startswith("TCP") and parts[3] == "LISTENING" and parts[4] == pid_str:
                local_addr = parts[1]  # 例如 127.0.0.1:5556
                if ":" in local_addr:
                    port_str = local_addr.split(":")[-1]
                    try:
                        port = int(port_str)
                        if port not in found_ports:
                            found_ports.append(port)
                    except ValueError:
                        pass
        return found_ports
    except Exception:
        return []


class AutoClickerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AutoClick 自动点击器 v2.5 - 上次配置记忆版")
        self.root.geometry("1180x860")
        self.root.minsize(1100, 780)

        # 全局状态
        self.clicking = False
        self.click_thread = None
        self.state_lock = threading.Lock()
        self.is_dirty_point = False   # 10点位模式配置方案修改状态
        self.is_dirty_script = False  # 脚本宏模式代码文件修改状态
        self.current_config_file = CONFIG_FILE
        self.is_mini_mode = False  # 是否处于 Mini 面板模式

        # 配置初始化
        self.mode_var = tk.StringVar(value="foreground")  # 'foreground' or 'background'
        self._last_mode = "foreground"
        self.target_hwnd_var = tk.IntVar(value=0)
        self.target_title_var = tk.StringVar(value="选择目标窗口...")
        self.target_title_var.trace_add("write", lambda *args: self.update_mini_target_title())

        # 模拟器 ADB 增强模式变量
        self.adb_enabled_var = tk.BooleanVar(value=False)
        self.adb_device_var = tk.StringVar(value="")
        self.adb_custom_path_var = tk.StringVar(value="")

        # 模拟器窗口尺寸与双轨自适应基准 (自适应缩放与一键还原)
        self.target_window_size = [424, 901]
        self.base_render_size = [390, 867]
        self.base_adb_resolution = [540, 1200]

        # 置顶与窗口前台联动切换控制变量
        self.topmost_var = tk.BooleanVar(value=False)
        self.follow_target_var = tk.BooleanVar(value=True)

        # 10个点的配置数据框变量
        self.point_vars = []
        for i in range(NUM_POINTS):
            p_dict = {
                "enabled": tk.BooleanVar(value=False),
                "level": tk.IntVar(value=0),  # 0~4级挂载
                "remark": tk.StringVar(value=""),  # 备注说明
                "x": tk.StringVar(value="0"),
                "y": tk.StringVar(value="0"),
                "delay": tk.StringVar(value="0.0"),  # 上级触发后 Timer 置 0 的启动延迟(s)
                "interval": tk.StringVar(value="0.5"),  # 点击频率间隔(s)
                "count": tk.StringVar(value="1"),  # 每次 Timer 置 0 后点击次数 (0为无限制)
                "hotkey": tk.StringVar(value=DEFAULT_HOTKEYS[i]),
            }
            p_dict["enabled"].trace_add("write", lambda *args, idx=i: self.update_mini_point_button(idx))
            p_dict["remark"].trace_add("write", lambda *args, idx=i: self.update_mini_point_button(idx))
            self.point_vars.append(p_dict)

        # 脚本宏引擎全局状态
        self.script_running = False
        self.script_paused = False
        self.script_thread = None
        self.script_start_time = None
        self.click_start_time = None
        self.active_script_timers = {}  # {timer_id: start_monotonic_timestamp}
        self.script_variables = {}  # 脚本宏变量作用域 {var_name: value}
        self.is_recording = False
        self.record_thread = None
        self.current_script_file = ""
        self.scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
        os.makedirs(self.scripts_dir, exist_ok=True)
        self.script_file_var = tk.StringVar(value="")
        self._highlight_timer = None

        self.window_map = {}
        self.mini_point_widgets = []
        self.setup_ui()
        self.refresh_scripts_list()

        # 启动目标窗口前台联动检测与 Mini 面板计时器每秒刷新轮询
        self.root.after(300, self.check_target_foreground_loop)
        self.root.after(1000, self._update_macro_mini_timer_loop)

        # 默认自动加载上次使用的配置文件
        initial_config_file = get_last_used_config()
        self.load_config(initial_config_file)
        self.register_global_hotkeys()

        # 窗口关闭事件处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    @property
    def is_dirty(self):
        """兼容属性：任意模式有未保存改动即返回 True"""
        return self.is_dirty_point or self.is_dirty_script

    def _get_active_editor(self):
        """获取当前处于激活交互状态的脚本编辑器（Mini 模式下返回 mini_script_display，主面板下返回 script_editor）"""
        if getattr(self, "is_mini_mode", False) and hasattr(self, "mini_script_display"):
            return self.mini_script_display
        return getattr(self, "script_editor", None)

    def apply_syntax_highlight(self, widget=None):
        """对脚本编辑器中的注释等内容进行语法高亮 (支持 /// 块注释、// 与 # 单行注释及引号外行尾注释)"""
        widgets = [widget] if widget else [getattr(self, "script_editor", None), getattr(self, "mini_script_display", None)]
        for w in widgets:
            if not w:
                continue
            try:
                w.tag_configure("comment", foreground="#6a9955")  # VS Code 经典柔和高对比度注释绿
                w.tag_remove("comment", "1.0", tk.END)

                raw_text = w.get("1.0", tk.END)
                lines = raw_text.split("\n")
                in_block = False

                for idx, line in enumerate(lines, 1):
                    l_stripped = line.lstrip()
                    if in_block:
                        w.tag_add("comment", f"{idx}.0", f"{idx}.end")
                        if l_stripped.startswith("///"):
                            in_block = False
                    else:
                        if l_stripped.startswith("///"):
                            in_block = True
                            w.tag_add("comment", f"{idx}.0", f"{idx}.end")
                        elif l_stripped.startswith("//") or l_stripped.startswith("#"):
                            w.tag_add("comment", f"{idx}.0", f"{idx}.end")
                        else:
                            # 检查行内注释 (排除字符串内部的 // 或 #)
                            in_q = False
                            q_ch = None
                            for col in range(len(line)):
                                ch = line[col]
                                if ch in ['"', "'"]:
                                    if not in_q:
                                        in_q = True
                                        q_ch = ch
                                    elif q_ch == ch:
                                        in_q = False
                                elif not in_q:
                                    if line[col:col+2] == "//" or ch == "#":
                                        w.tag_add("comment", f"{idx}.{col}", f"{idx}.end")
                                        break
            except Exception:
                pass

    def trigger_syntax_highlight(self, widget=None):
        """防抖触发语法高亮"""
        if getattr(self, "_highlight_timer", None):
            try:
                self.root.after_cancel(self._highlight_timer)
            except Exception:
                pass
        self._highlight_timer = self.root.after(30, lambda: self.apply_syntax_highlight(widget))

    def _on_script_editor_change(self, event=None):
        """主面板编辑器内容变更回调"""
        self.mark_script_dirty()
        self.trigger_syntax_highlight(getattr(self, "script_editor", None))

    def _on_mini_editor_change(self, event=None):
        """Mini 面板编辑器内容变更回调"""
        self.mark_script_dirty()
        self.trigger_syntax_highlight(getattr(self, "mini_script_display", None))

    def update_window_title(self):
        """根据 Point 模式与 Script 模式各自的修改状态动态更新主窗口标题"""
        if self.is_mini_mode:
            self.update_mini_target_title()
            return

        cfg_name = os.path.basename(self.current_config_file)
        cfg_star = "*" if self.is_dirty_point else ""
        script_name = os.path.basename(self.current_script_file) if self.current_script_file else "未命名脚本.kms"
        script_star = "*" if self.is_dirty_script else ""

        self.root.title(f"AutoClick 自动点击器 v2.5 - [配置: {cfg_name}{cfg_star} | 脚本: {script_name}{script_star}]")

    def mark_point_dirty(self, *args):
        """标记 10点位配置模式 为已修改未保存"""
        self.is_dirty_point = True
        self.update_window_title()

    def mark_point_clean(self):
        """标记 10点位配置模式 改动已保存"""
        self.is_dirty_point = False
        self.update_window_title()

    def mark_script_dirty(self, *args):
        """标记 脚本宏模式 为已修改未保存"""
        self.is_dirty_script = True
        self.update_window_title()
        if hasattr(self, "lbl_mini_script_name"):
            script_name = self.script_file_var.get().strip() or "未选择脚本"
            self.lbl_mini_script_name.config(text=f"📜 {script_name}*")

    def mark_script_clean(self):
        """标记 脚本宏模式 改动已保存"""
        self.is_dirty_script = False
        self.update_window_title()
        if hasattr(self, "lbl_mini_script_name"):
            script_name = self.script_file_var.get().strip() or "未选择脚本"
            self.lbl_mini_script_name.config(text=f"📜 {script_name}")

    def mark_dirty(self, *args):
        """兼容原方法：标记 10点位配置模式 为已修改"""
        self.mark_point_dirty()

    def mark_clean(self):
        """兼容原方法：标记 10点位配置模式 为已保存"""
        self.mark_point_clean()

    def log_msg(self, msg):
        """向 GUI 日志框和状态栏同步输出带时间戳、已运行时长及 Timer 耗时 (秒) 的日志"""
        timestamp = time.strftime("%H:%M:%S")
        elapsed_sec = None

        if getattr(self, "script_running", False) and getattr(self, "script_start_time", None):
            elapsed_sec = int(time.monotonic() - self.script_start_time)
        elif getattr(self, "clicking", False) and getattr(self, "click_start_time", None):
            elapsed_sec = int(time.monotonic() - self.click_start_time)

        timer_part = ""
        if getattr(self, "script_running", False) and getattr(self, "active_script_timers", None):
            active_items = sorted(self.active_script_timers.items(), key=lambda x: x[0])[:3]
            if active_items:
                now = time.monotonic()
                t_strs = []
                for tid, start_t in active_items:
                    t_dur = int(now - start_t)
                    t_strs.append(f"T{tid}:{t_dur}s")
                timer_part = " | " + " | ".join(t_strs)

        if elapsed_sec is not None:
            full_line = f"[{timestamp} | {elapsed_sec}s{timer_part}] {msg}\n"
        else:
            full_line = f"[{timestamp}] {msg}\n"

        def update_gui():
            self.status_var.set(msg)
            if hasattr(self, "log_text"):
                self.log_text.insert(tk.END, full_line)
                if self.auto_scroll_var.get():
                    self.log_text.see(tk.END)

        self.root.after(0, update_gui)

    def clear_log(self):
        """清空日志输出框"""
        if hasattr(self, "log_text"):
            self.log_text.delete("1.0", tk.END)
            self.status_var.set("日志控制台已清空。")

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # 主界面容器 Frame (包含原有的全部全功能面板)
        self.main_frame = ttk.Frame(self.root)
        self.main_frame.pack(fill="both", expand=True)

        # 头部面板 (控制模式 & 目标窗口 & ADB设置)
        top_frame = ttk.LabelFrame(self.main_frame, text="控制面板 & 模式选择 & 目标窗口", padding=10)
        top_frame.pack(fill="x", padx=10, pady=5)

        # 模式切换栏 (最右侧包含 Mini 面板切换按钮)
        mode_inner = ttk.Frame(top_frame)
        mode_inner.pack(fill="x", pady=2)
        ttk.Label(mode_inner, text="点击模式:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)
        ttk.Radiobutton(
            mode_inner,
            text="前台全局模式 (全局绝对坐标，物理鼠标点击)",
            variable=self.mode_var,
            value="foreground",
            command=self.on_mode_changed,
        ).pack(side="left", padx=10)
        ttk.Radiobutton(
            mode_inner,
            text="后台窗口模式 (窗口相对坐标，移动窗口不影响静默点击)",
            variable=self.mode_var,
            value="background",
            command=self.on_mode_changed,
        ).pack(side="left", padx=10)

        # 模拟器增强 (ADB) 勾选框
        self.chk_adb = ttk.Checkbutton(
            mode_inner,
            text="⚡ 模拟器增强 (ADB模式)",
            variable=self.adb_enabled_var,
            command=self.on_adb_toggled,
        )
        self.chk_adb.pack(side="left", padx=15)

        # 模式通用共享：右侧 Mini 面板切换按钮
        tk.Button(
            mode_inner,
            text="📱 Mini面板",
            bg="#8e44ad",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            activebackground="#9b59b6",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=8,
            pady=1,
            command=self.switch_to_mini_panel,
        ).pack(side="right", padx=5)

        # 目标窗口选择面板 (放在进程框顶部)
        win_frame = ttk.Frame(top_frame)
        win_frame.pack(fill="x", pady=5)
        ttk.Label(win_frame, text="目标窗口:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)

        self.win_cb = ttk.Combobox(win_frame, width=50, state="readonly")
        self.win_cb.pack(side="left", padx=5, fill="x", expand=True)
        self.win_cb.bind("<<ComboboxSelected>>", self.on_window_selected)

        ttk.Button(win_frame, text="🔄 刷新窗口", command=self.refresh_window_list).pack(side="left", padx=3)
        ttk.Button(win_frame, text="🎯 瞄准锁定窗口", command=self.pick_target_window).pack(side="left", padx=3)
        ttk.Button(win_frame, text="📐 还原窗口尺寸", command=self.restore_target_window_size).pack(side="left", padx=3)

        # 模拟器 ADB 参数配置面板 (放在目标窗口下方)
        adb_frame = ttk.Frame(top_frame)
        adb_frame.pack(fill="x", pady=3)

        ttk.Label(adb_frame, text="ADB设备:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)
        self.adb_dev_cb = ttk.Combobox(adb_frame, textvariable=self.adb_device_var, width=22, state="readonly")
        self.adb_dev_cb.pack(side="left", padx=3)

        ttk.Button(adb_frame, text="🔄 刷新设备", command=self.refresh_adb_devices).pack(side="left", padx=3)
        ttk.Button(adb_frame, text="🔗 手动连接端口", command=self.connect_adb_port).pack(side="left", padx=3)
        ttk.Button(adb_frame, text="⚡ 测试ADB点击", command=self.test_adb_connection).pack(side="left", padx=3)

        ttk.Label(adb_frame, text="自定义ADB路径:").pack(side="left", padx=(15, 3))
        ent_adb_path = ttk.Entry(adb_frame, textvariable=self.adb_custom_path_var, width=24)
        ent_adb_path.pack(side="left", padx=3)
        ent_adb_path.bind("<KeyRelease>", lambda e: self.mark_dirty())
        ttk.Button(adb_frame, text="📁 浏览...", command=self.browse_adb_path).pack(side="left", padx=3)

        # ==================== 选项卡 Notebook 容器 ====================
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.pack(fill="x", padx=10, pady=5)

        # Tab 1: 10组坐标点配置面板 (Point Mode)
        tab_points = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_points, text="  🎯 10组点位模式 (Point Mode)  ")

        # 1. Point Mode 配置方案文件管理栏 (行 1)
        cfg_bar = ttk.Frame(tab_points)
        cfg_bar.pack(fill="x", padx=5, pady=(2, 3))
        ttk.Label(cfg_bar, text="当前方案:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)

        self.lbl_cfg_file = ttk.Label(cfg_bar, text=os.path.basename(self.current_config_file), foreground="#2980b9", font=("Segoe UI", 9, "bold"))
        self.lbl_cfg_file.pack(side="left", padx=5)

        ttk.Button(cfg_bar, text="💾 保存配置", command=self.save_config).pack(side="left", padx=3)
        ttk.Button(cfg_bar, text="📁 另存为...", command=self.save_config_as).pack(side="left", padx=3)
        ttk.Button(cfg_bar, text="📂 加载配置文件...", command=self.open_config_file).pack(side="left", padx=3)

        # 2. Point Mode 专属主操作控制按钮栏 (行 2: 开始点击/停止点击/全部启用/全部禁用)
        point_ctrl_bar = ttk.Frame(tab_points)
        point_ctrl_bar.pack(fill="x", padx=5, pady=(3, 5))

        self.btn_start = tk.Button(
            point_ctrl_bar,
            text="▶ 开始点击 (Ctrl+Shift+S)",
            bg="#2ecc71",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            command=self.start_clicking,
        )
        self.btn_start.pack(side="left", padx=(0, 4), expand=True, fill="x")

        self.btn_stop = tk.Button(
            point_ctrl_bar,
            text="⏹ 停止点击 (Ctrl+Shift+Q)",
            bg="#e74c3c",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            state="disabled",
            command=self.stop_clicking,
        )
        self.btn_stop.pack(side="left", padx=4, expand=True, fill="x")

        ttk.Button(point_ctrl_bar, text="☑ 全部启用", command=lambda: self.set_all_enabled(True)).pack(
            side="left", padx=3
        )
        ttk.Button(point_ctrl_bar, text="☒ 全部禁用", command=lambda: self.set_all_enabled(False)).pack(
            side="left", padx=3
        )

        # 坐标点配置表格区域 (高度固定，不跟随窗口拉长)
        points_frame = ttk.LabelFrame(tab_points, text="10组坐标点详细配置", padding=10)
        points_frame.pack(fill="x", padx=5, pady=2)

        # 表头：包含备注列与加宽的挂载关系列 (34 字符宽，1.5倍扩充)
        headers = ["启用", "层级", "点位及挂载关系 (1.5倍加宽)", "备注说明", "录入快捷键", "拾取坐标", "X 坐标", "Y 坐标", "启动延迟(s)", "点击间隔(s)", "次数(0无限)", "测试"]
        widths = [4, 5, 34, 12, 13, 8, 7, 7, 10, 10, 9, 7]
        header_frame = ttk.Frame(points_frame)
        header_frame.pack(fill="x", pady=2)

        for col, (h, w) in enumerate(zip(headers, widths)):
            lbl = ttk.Label(header_frame, text=h, width=w, anchor="center", font=("Segoe UI", 9, "bold"))
            lbl.pack(side="left", padx=2)

        # 分割线
        ttk.Separator(points_frame, orient="horizontal").pack(fill="x", pady=3)

        # 10 行表单容器
        self.rows_container = ttk.Frame(points_frame)
        self.rows_container.pack(fill="both", expand=True)

        self.point_labels = []

        for i in range(NUM_POINTS):
            row = ttk.Frame(self.rows_container)
            row.pack(fill="x", pady=2)

            p_vars = self.point_vars[i]

            # 1. 启用 Checkbox
            chk = ttk.Checkbutton(
                row, variable=p_vars["enabled"], command=self.mark_dirty, width=3
            )
            chk.pack(side="left", padx=3)

            # 2. 层级调整按钮 (← 升级, → 降级)
            lvl_frame = ttk.Frame(row, width=45)
            lvl_frame.pack(side="left", padx=1)
            btn_up = ttk.Button(lvl_frame, text="←", width=2, command=lambda idx=i: self.change_level(idx, -1))
            btn_up.pack(side="left", padx=1)
            btn_down = ttk.Button(lvl_frame, text="→", width=2, command=lambda idx=i: self.change_level(idx, 1))
            btn_down.pack(side="left", padx=1)

            # 3. 序号及挂载树形 Label (扩大到 34 宽)
            lbl_num = ttk.Label(row, text="", width=34, anchor="w", font=("Consolas", 9))
            lbl_num.pack(side="left", padx=2)
            self.point_labels.append(lbl_num)

            # 4. 备注说明 Entry
            ent_rem = ttk.Entry(row, textvariable=p_vars["remark"], width=12, justify="center")
            ent_rem.pack(side="left", padx=2)
            ent_rem.bind("<KeyRelease>", lambda e: self.mark_dirty())

            # 5. 快捷键 Entry
            ent_hk = ttk.Entry(row, textvariable=p_vars["hotkey"], width=13, justify="center")
            ent_hk.pack(side="left", padx=2)
            ent_hk.bind("<FocusOut>", lambda e: self.register_global_hotkeys())

            # 6. 拾取按钮
            btn_pick = ttk.Button(
                row, text="📍 拾取", width=8, command=lambda idx=i: self.pick_coordinate(idx)
            )
            btn_pick.pack(side="left", padx=2)

            # 7. X 坐标
            ent_x = ttk.Entry(row, textvariable=p_vars["x"], width=7, justify="center")
            ent_x.pack(side="left", padx=2)
            ent_x.bind("<KeyRelease>", lambda e: self.mark_dirty())

            # 8. Y 坐标
            ent_y = ttk.Entry(row, textvariable=p_vars["y"], width=7, justify="center")
            ent_y.pack(side="left", padx=2)
            ent_y.bind("<KeyRelease>", lambda e: self.mark_dirty())

            # 9. 启动延迟 (s)
            ent_delay = ttk.Entry(row, textvariable=p_vars["delay"], width=10, justify="center")
            ent_delay.pack(side="left", padx=2)
            ent_delay.bind("<KeyRelease>", lambda e: self.mark_dirty())

            # 10. 点击间隔 (s)
            ent_int = ttk.Entry(row, textvariable=p_vars["interval"], width=10, justify="center")
            ent_int.pack(side="left", padx=2)
            ent_int.bind("<KeyRelease>", lambda e: self.mark_dirty())

            # 11. 点击次数
            ent_cnt = ttk.Entry(row, textvariable=p_vars["count"], width=9, justify="center")
            ent_cnt.pack(side="left", padx=2)
            ent_cnt.bind("<KeyRelease>", lambda e: self.mark_dirty())

            # 12. 测试按钮
            btn_test = ttk.Button(
                row, text="⚡ 测试", width=7, command=lambda idx=i: self.test_single_click(idx)
            )
            btn_test.pack(side="left", padx=2)

        # Tab 2: 脚本宏模式面板
        tab_script = ttk.Frame(self.notebook, padding=5)
        self.notebook.add(tab_script, text="  📜 脚本宏模式 (Macro Scripting)  ")

        # 1. 脚本文件管理工具栏 (行 1)
        script_file_bar = ttk.Frame(tab_script)
        script_file_bar.pack(fill="x", pady=(2, 3))

        ttk.Label(script_file_bar, text="脚本方案:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)
        self.script_cb = ttk.Combobox(script_file_bar, textvariable=self.script_file_var, width=28)
        self.script_cb.pack(side="left", padx=3)
        self.script_cb.bind("<<ComboboxSelected>>", self.on_script_selected)

        ttk.Button(script_file_bar, text="📂 打开...", command=self.open_script_file).pack(side="left", padx=2)
        ttk.Button(script_file_bar, text="💾 保存", command=self.save_script_file).pack(side="left", padx=2)
        ttk.Button(script_file_bar, text="📁 另存为...", command=self.save_script_as).pack(side="left", padx=2)
        ttk.Button(script_file_bar, text="📥 导入JSON方案", command=self.import_json_config_to_script).pack(side="left", padx=2)

        # 2. 脚本运行与录制控制工具栏 (单独独占行 2，避免任何挤压与遮挡)
        script_exec_bar = ttk.Frame(tab_script)
        script_exec_bar.pack(fill="x", pady=(3, 5))

        self.btn_run_script = tk.Button(
            script_exec_bar,
            text="▶ 运行脚本 (Ctrl+Shift+R)",
            bg="#2ecc71",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            command=self.start_macro_script,
        )
        self.btn_run_script.pack(side="left", padx=(0, 2), expand=True, fill="x")

        self.btn_run_from_line = tk.Button(
            script_exec_bar,
            text="⏯ 从当前行运行 (Ctrl+Shift+F)",
            bg="#16a085",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            command=lambda: self.start_macro_script(start_from_current_line=True),
        )
        self.btn_run_from_line.pack(side="left", padx=2, expand=True, fill="x")

        self.btn_pause_script = tk.Button(
            script_exec_bar,
            text="⏸ 暂停脚本 (Ctrl+Shift+P)",
            bg="#7f8c8d",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            state="disabled",
            command=self.toggle_pause_macro_script,
        )
        self.btn_pause_script.pack(side="left", padx=2, expand=True, fill="x")

        self.btn_stop_script = tk.Button(
            script_exec_bar,
            text="⏹ 停止脚本 (Ctrl+Shift+E)",
            bg="#7f8c8d",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            state="disabled",
            command=self.stop_macro_script,
        )
        self.btn_stop_script.pack(side="left", padx=2, expand=True, fill="x")

        self.btn_record_script = tk.Button(
            script_exec_bar,
            text="🔴 开始录制 (Ctrl+Alt+R)",
            bg="#8e44ad",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            command=self.toggle_script_recording,
        )
        self.btn_record_script.pack(side="left", padx=(2, 0), expand=True, fill="x")

        # 2. 快速代码 Snippets 插入工具栏 (带有鼠标悬停说明 ToolTip)
        snippet_bar = ttk.LabelFrame(tab_script, text="按键指令快速插入 Snippets", padding=5)
        snippet_bar.pack(fill="x", pady=2)

        snippets_info = [
            ("[🎯 拾取坐标]", self.pick_script_coordinate,
             "【拾取坐标】倒计时 2 秒拾取鼠标屏幕/模拟器相对坐标。\n若当前行空白插入 Click(x, y)，若在已有指令行中则填入 x, y"),
            ("[+ ❓ If-Else 条件]", lambda: self.insert_script_snippet("If (InTournament == 1) {\n    Click(100, 200)\n} Else {\n    Click(300, 400)\n}\n"),
             "【If-Else 条件分支】格式: If (条件表达式) { ... } Else { ... }\n支持变量判定(如 InTournament == 1 或 InTournament == True)，根据逻辑选择分支。"),
            ("[+ 🏷️ 变量赋值]", lambda: self.insert_script_snippet("InTournament = 1\n"),
             "【变量赋值】格式: 变量名 = 值\n支持整型 (1)、布尔值 (True/False)、字符串等。"),
            ("[+ ClickEx 点位]", lambda: self.insert_script_snippet('ClickEx(0, 368, 22, 0.0, 900.0, 0, "右上菜单")\n'),
             "【ClickEx 点位】格式: ClickEx(层级, X, Y, 启动延迟, 点击间隔, 次数, 备注, [TimerID])\n支持多级 Timer 级联挂载及绑定计时器编号。"),
            ("[+ 点击坐标]", lambda: self.insert_script_snippet("Click(300, 400)\n"),
             "【点击坐标】格式: Click(X, Y, [点击次数], [间隔毫秒])\n在指定坐标执行基础点击操作。"),
            ("[+ ⏱️ TimerStart]", lambda: self.insert_script_snippet("TimerStart(1)\n"),
             "【启动/重置 Timer】格式: TimerStart(ID) 或 Timer(ID, 'start')\n启动/重置指定编号的 Timer 独立计时器，在 Log 与 Mini 面板显示耗时。"),
            ("[+ ⏹️ TimerStop]", lambda: self.insert_script_snippet("TimerStop(1)\n"),
             "【停止 Timer】格式: TimerStop(ID) 或 Timer(ID, 'stop')\n停止指定编号的 Timer 独立计时器。"),
            ("[+ 关联点位]", lambda: self.insert_script_snippet("ClickPoint(#1)\n"),
             "【关联点位】格式: ClickPoint(#N)\n触发主界面 10 组点位模式中第 N 个坐标点位的点击动作。"),
            ("[+ 延时等待]", lambda: self.insert_script_snippet("Delay(1000)\n"),
             "【延时等待】格式: Delay(毫秒) 或 Sleep(毫秒/s)\n暂停当前脚本执行指定的毫秒数。"),
            ("[+ 循环区间]", lambda: self.insert_script_snippet("Loop(5) {\n    Click(300, 400)\n    Delay(500)\n}\n"),
             "【循环区间】格式: Loop(N) { ... }\n将大括号内部的指令重复执行 N 次。"),
            ("[+ 轨迹拖拽]", lambda: self.insert_script_snippet("Drag(300, 600, 300, 200, 500)\n"),
             "【轨迹拖拽】格式: Drag(起点X, 起点Y, 终点X, 终点Y, 持续毫秒)\n模拟按住鼠标从起点拖拽/滑动至终点。"),
            ("[+ 文本输入]", lambda: self.insert_script_snippet('Input("Hello")\n'),
             "【文本输入】格式: Input('内容')\n发送模拟器/键盘文本字符输入指令。"),
            ("[+ 单行注释]", lambda: self.insert_script_snippet("// 说明注释...\n"),
             "【单行注释】格式: // 说明内容\n单行代码注释，运行时忽略执行。"),
            ("[+ 块注释 ///]", lambda: self.insert_script_snippet("///\n// 注释块内容...\n///\n"),
             "【块注释】格式: /// ... ///\n使用 /// 开始与结束块注释，首行与尾行以 /// 开头，内部指令均不执行。"),
        ]

        for text, cmd, tip in snippets_info:
            btn = ttk.Button(snippet_bar, text=text, command=cmd)
            btn.pack(side="left", padx=2)
            ToolTip(btn, tip)

        # 3. 按键脚本编辑器
        editor_frame = ttk.LabelFrame(tab_script, text="按键脚本代码编辑器 (QuickMacro DSL)", padding=5)
        editor_frame.pack(fill="both", expand=True, pady=2)

        editor_container = ttk.Frame(editor_frame)
        editor_container.pack(fill="both", expand=True)

        self.script_editor = tk.Text(
            editor_container,
            height=10,
            wrap="none",
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#dcdcdc",
            insertbackground="white",
            undo=True,
        )
        self.script_editor.pack(side="left", fill="both", expand=True)
        self.script_editor.bind("<KeyRelease>", self._on_script_editor_change)
        self.script_editor.bind("<Control-s>", lambda e: (self.save_script_file(), "break")[1])
        self.script_editor.bind("<Control-S>", lambda e: (self.save_script_file(), "break")[1])

        ed_scroll_y = ttk.Scrollbar(editor_container, command=self.script_editor.yview)
        ed_scroll_y.pack(side="right", fill="y")
        self.script_editor.config(yscrollcommand=ed_scroll_y.set)

        # 编辑器右键上下文菜单
        self.script_editor_menu = tk.Menu(self.script_editor, tearoff=0)
        self.script_editor_menu.add_command(
            label="🎯 倒计时 2 秒拾取坐标并填入",
            command=self.pick_script_coordinate,
        )
        self.script_editor_menu.add_separator()
        self.script_editor_menu.add_command(
            label="▶ 从开头运行脚本 (Ctrl+Shift+R)",
            command=self.start_macro_script,
        )
        self.script_editor_menu.add_command(
            label="⏯ 从当前行开始运行 (Ctrl+Shift+F)",
            command=lambda: self.start_macro_script(start_from_current_line=True),
        )
        self.script_editor_menu.add_separator()
        self.script_editor_menu.add_command(
            label="⏸ 暂停 / 继续脚本 (Ctrl+Shift+P)",
            command=self.toggle_pause_macro_script,
        )
        self.script_editor_menu.add_command(
            label="⏹ 停止脚本 (Ctrl+Shift+E)",
            command=self.stop_macro_script,
        )
        self.script_editor_menu.add_separator()
        self.script_editor_menu.add_command(
            label="💾 保存脚本 (Ctrl+S)",
            command=self.save_script_file,
        )
        self.script_editor_menu.add_separator()
        self.script_editor_menu.add_command(
            label="⏱️ 插入 TimerStart(1)",
            command=lambda: self.insert_script_snippet("TimerStart(1)\n"),
        )
        self.script_editor_menu.add_command(
            label="⏹️ 插入 TimerStop(1)",
            command=lambda: self.insert_script_snippet("TimerStop(1)\n"),
        )
        self.script_editor_menu.add_separator()
        self.script_editor_menu.add_command(
            label="✂ 剪切",
            command=lambda: self._get_active_editor().event_generate("<<Cut>>") if self._get_active_editor() else None,
        )
        self.script_editor_menu.add_command(
            label="📋 复制",
            command=lambda: self._get_active_editor().event_generate("<<Copy>>") if self._get_active_editor() else None,
        )
        self.script_editor_menu.add_command(
            label="📌 粘贴",
            command=lambda: self._get_active_editor().event_generate("<<Paste>>") if self._get_active_editor() else None,
        )

        def show_editor_context_menu(event):
            self.script_editor_menu.tk_popup(event.x_root, event.y_root)

        self.script_editor.bind("<Button-3>", show_editor_context_menu)

        # 实时运行日志控制台区域 (界面下方，跟随窗口垂直拉长)
        log_frame = ttk.LabelFrame(self.main_frame, text="运行日志控制台 (Real-time Execution Log)", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        log_ctrl_bar = ttk.Frame(log_frame)
        log_ctrl_bar.pack(fill="x", pady=2)

        self.auto_scroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_ctrl_bar, text="☑ 自动滚动", variable=self.auto_scroll_var).pack(side="left", padx=5)
        ttk.Button(log_ctrl_bar, text="🧹 清空日志", command=self.clear_log).pack(side="left", padx=5)

        log_container = ttk.Frame(log_frame)
        log_container.pack(fill="both", expand=True, pady=2)

        self.log_text = tk.Text(
            log_container, height=7, wrap="word", font=("Consolas", 9), bg="#1e1e1e", fg="#dcdcdc"
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(log_container, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scrollbar.set)

        # 底部状态栏
        self.status_var = tk.StringVar(value="就绪。可以使用上方日志控制台查看实时自动点击触发与排期细节。")
        status_bar = ttk.Label(
            self.main_frame, textvariable=self.status_var, relief="sunken", anchor="w", padding=5
        )
        status_bar.pack(fill="x", side="bottom")

        # ==================== 构建 Mini 面板 (默认隐藏) ====================
        self.mini_frame = ttk.Frame(self.root)

        # 1. Mini 面板顶部栏：无遮挡控制工具栏
        mini_top = ttk.Frame(self.mini_frame, padding=(6, 4, 6, 2))
        mini_top.pack(fill="x", side="top")

        lbl_mini_badge = ttk.Label(
            mini_top,
            text="⚡ Mini 控制台",
            font=("Segoe UI", 9, "bold"),
            foreground="#2980b9",
            anchor="w",
        )
        lbl_mini_badge.pack(side="left", fill="x", expand=True)

        btn_to_main = tk.Button(
            mini_top,
            text="🖥️ 主面板",
            bg="#2980b9",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#3498db",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=5,
            pady=1,
            command=self.switch_to_main_panel,
        )
        btn_to_main.pack(side="right", padx=(3, 0))

        self.btn_restore = tk.Button(
            mini_top,
            text="📐 还原",
            bg="#34495e",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#2c3e50",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=4,
            pady=1,
            command=self.restore_target_window_size,
        )
        self.btn_restore.pack(side="right", padx=(3, 3))

        self.btn_follow = tk.Button(
            mini_top,
            text="🔗 已联动",
            bg="#27ae60",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#2ecc71",
            activeforeground="white",
            relief="sunken",
            bd=1,
            padx=4,
            pady=1,
            command=self.toggle_follow_target,
        )
        self.btn_follow.pack(side="right", padx=(3, 3))

        self.btn_topmost = tk.Button(
            mini_top,
            text="📌 置顶",
            bg="#7f8c8d",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#f39c12",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=4,
            pady=1,
            command=self.toggle_topmost,
        )
        self.btn_topmost.pack(side="right", padx=(3, 3))

        ttk.Separator(self.mini_frame, orient="horizontal").pack(fill="x", pady=2)

        # 2. Mini 面板内容区：网格布局实现等比自动缩放 (左侧 10 个按钮 weight=1，右侧控制按钮 minsize=115 固定等宽)
        mini_content = ttk.Frame(self.mini_frame, padding=6)
        mini_content.pack(fill="both", expand=True)

        mini_content.columnconfigure(0, weight=1)
        mini_content.columnconfigure(1, weight=0, minsize=115)
        mini_content.rowconfigure(0, weight=1)

        # 左侧 10 个自动点击点位按钮
        mini_left = ttk.Frame(mini_content)
        mini_left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        grid_frame = ttk.Frame(mini_left)
        grid_frame.pack(fill="both", expand=True)

        for col in range(2):
            grid_frame.columnconfigure(col, weight=1)
        for row_idx in range(5):
            grid_frame.rowconfigure(row_idx, weight=1)

        self.mini_point_widgets = []
        for i in range(NUM_POINTS):
            r = i // 2
            c = i % 2

            btn_frame = tk.Frame(
                grid_frame,
                relief="raised",
                bd=2,
                padx=3,
                pady=2,
                cursor="hand2"
            )
            btn_frame.grid(row=r, column=c, padx=2, pady=2, sticky="nsew")

            canvas = tk.Canvas(btn_frame, width=9, height=9, highlightthickness=0, bg="#f0f0f0")
            canvas.pack(side="left", padx=(3, 2))
            oval = canvas.create_oval(1, 1, 8, 8, fill="#95a5a6", outline="")

            lbl_text = tk.Label(
                btn_frame,
                text=f"#{i+1}",
                font=("Segoe UI", 9, "bold"),
                bg="#f0f0f0",
                fg="#555555",
                anchor="w"
            )
            lbl_text.pack(side="left", padx=(1, 2), fill="x", expand=True)

            handler = lambda e, idx=i: self.toggle_point_enabled(idx)
            btn_frame.bind("<Button-1>", handler)
            canvas.bind("<Button-1>", handler)
            lbl_text.bind("<Button-1>", handler)

            self.mini_point_widgets.append({
                "frame": btn_frame,
                "canvas": canvas,
                "oval": oval,
                "label": lbl_text,
            })

        # 右侧上下排列的开始/停止点击按钮 (固定宽度与网格比例)
        mini_right = ttk.Frame(mini_content)
        mini_right.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
        mini_right.rowconfigure(0, weight=1)
        mini_right.rowconfigure(1, weight=1)
        mini_right.columnconfigure(0, weight=1)

        self.btn_mini_start = tk.Button(
            mini_right,
            text="▶ 开始\nCtrl+Shift+S",
            bg="#2ecc71",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            activebackground="#27ae60",
            activeforeground="white",
            relief="raised",
            bd=1,
            command=self.start_clicking,
        )
        self.btn_mini_start.grid(row=0, column=0, sticky="nsew", pady=(0, 2))

        self.btn_mini_stop = tk.Button(
            mini_right,
            text="⏹ 停止\nCtrl+Shift+Q",
            bg="#e74c3c",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            activebackground="#c0392b",
            activeforeground="white",
            relief="raised",
            bd=1,
            state="disabled",
            command=self.stop_clicking,
        )
        self.btn_mini_stop.grid(row=1, column=0, sticky="nsew", pady=(2, 0))

        # ==================== 构建 脚本宏模式 Mini 面板 (默认隐藏) ====================
        self.macro_mini_frame = ttk.Frame(self.root)

        # 1. 顶部无遮挡控制栏
        macro_mini_top = ttk.Frame(self.macro_mini_frame, padding=(6, 4, 6, 2))
        macro_mini_top.pack(fill="x", side="top")

        self.lbl_macro_mini_badge = ttk.Label(
            macro_mini_top,
            text="📜 脚本宏 Mini 面板",
            font=("Segoe UI", 9, "bold"),
            foreground="#8e44ad",
            anchor="w",
        )
        self.lbl_macro_mini_badge.pack(side="left", fill="x", expand=True)

        btn_macro_to_main = tk.Button(
            macro_mini_top,
            text="🖥️ 主面板",
            bg="#2980b9",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#3498db",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=5,
            pady=1,
            command=self.switch_to_main_panel,
        )
        btn_macro_to_main.pack(side="right", padx=(3, 0))

        self.btn_macro_restore = tk.Button(
            macro_mini_top,
            text="📐 还原",
            bg="#34495e",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#2c3e50",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=4,
            pady=1,
            command=self.restore_target_window_size,
        )
        self.btn_macro_restore.pack(side="right", padx=(3, 3))

        self.btn_macro_follow = tk.Button(
            macro_mini_top,
            text="🔗 已联动",
            bg="#27ae60",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#2ecc71",
            activeforeground="white",
            relief="sunken",
            bd=1,
            padx=4,
            pady=1,
            command=self.toggle_follow_target,
        )
        self.btn_macro_follow.pack(side="right", padx=(3, 3))

        self.btn_macro_topmost = tk.Button(
            macro_mini_top,
            text="📌 置顶",
            bg="#7f8c8d",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#f39c12",
            activeforeground="white",
            relief="raised",
            bd=1,
            padx=4,
            pady=1,
            command=self.toggle_topmost,
        )
        self.btn_macro_topmost.pack(side="right", padx=(3, 3))

        ttk.Separator(self.macro_mini_frame, orient="horizontal").pack(fill="x", pady=2)

        # 2. 脚本宏 Mini 面板内容区 (网格布局：左侧脚本展示/载入 weight=1，右侧控制按钮 minsize=115 固定等宽)
        macro_mini_content = ttk.Frame(self.macro_mini_frame, padding=6)
        macro_mini_content.pack(fill="both", expand=True)

        macro_mini_content.columnconfigure(0, weight=1)
        macro_mini_content.columnconfigure(1, weight=0, minsize=115)
        macro_mini_content.rowconfigure(0, weight=1)

        # 左侧容器
        macro_mini_left = ttk.Frame(macro_mini_content)
        macro_mini_left.grid(row=0, column=0, sticky="nsew", padx=(0, 4))

        # 顶行：脚本文件名 + 💾 保存 + 📂 载入 按钮
        macro_mini_top_line = ttk.Frame(macro_mini_left)
        macro_mini_top_line.pack(fill="x", pady=(0, 4))

        self.lbl_mini_script_name = ttk.Label(
            macro_mini_top_line,
            text="📜 未选择脚本",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.lbl_mini_script_name.pack(side="left", fill="x", expand=True, padx=(2, 5))

        btn_mini_save_script = ttk.Button(
            macro_mini_top_line,
            text="💾 保存",
            width=6,
            command=self.save_script_file,
        )
        btn_mini_save_script.pack(side="right", padx=(2, 0))
        ToolTip(btn_mini_save_script, "【保存当前脚本】(Ctrl+S)")

        btn_mini_load_script = ttk.Button(
            macro_mini_top_line,
            text="📂 载入",
            width=6,
            command=self.open_script_file_from_mini,
        )
        btn_mini_load_script.pack(side="right", padx=(2, 2))
        ToolTip(btn_mini_load_script, "【载入脚本文件】")

        # 下方可下拉缩放的可编辑 Text 代码展示/编辑框
        macro_mini_code_frame = ttk.Frame(macro_mini_left)
        macro_mini_code_frame.pack(fill="both", expand=True)

        self.mini_script_display = tk.Text(
            macro_mini_code_frame,
            wrap="none",
            font=("Consolas", 9),
            bg="#1e1e1e",
            fg="#dcdcdc",
            insertbackground="white",
            undo=True,
            state="normal",
            bd=1,
            relief="solid",
            width=10,
            height=5,
        )
        self.mini_script_display.pack(side="left", fill="both", expand=True)

        mini_code_scroll = ttk.Scrollbar(macro_mini_code_frame, command=self.mini_script_display.yview)
        mini_code_scroll.pack(side="right", fill="y")
        self.mini_script_display.config(yscrollcommand=mini_code_scroll.set)

        self.mini_script_display.bind("<KeyRelease>", self._on_mini_editor_change)
        self.mini_script_display.bind("<Control-s>", lambda e: (self.save_script_file(), "break")[1])
        self.mini_script_display.bind("<Control-S>", lambda e: (self.save_script_file(), "break")[1])
        self.mini_script_display.bind("<Button-3>", show_editor_context_menu)

        # 右侧：启动 / 暂停 / 从当前行 / 停止控制按钮 (网格均匀分布，右侧固定 115px 宽度)
        macro_mini_right = ttk.Frame(macro_mini_content)
        macro_mini_right.grid(row=0, column=1, sticky="nsew", padx=(2, 0))

        for r in range(4):
            macro_mini_right.rowconfigure(r, weight=1)
        macro_mini_right.columnconfigure(0, weight=1)

        self.btn_macro_mini_start = tk.Button(
            macro_mini_right,
            text="▶ 从头启动\nCtrl+Shift+R",
            bg="#2ecc71",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#27ae60",
            activeforeground="white",
            relief="raised",
            bd=1,
            pady=1,
            command=self.start_macro_script,
        )
        self.btn_macro_mini_start.grid(row=0, column=0, sticky="nsew", pady=1)

        self.btn_macro_mini_start_line = tk.Button(
            macro_mini_right,
            text="⏯ 从当前行\nCtrl+Shift+F",
            bg="#16a085",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#1abc9c",
            activeforeground="white",
            relief="raised",
            bd=1,
            pady=1,
            command=lambda: self.start_macro_script(start_from_current_line=True),
        )
        self.btn_macro_mini_start_line.grid(row=1, column=0, sticky="nsew", pady=1)

        self.btn_macro_mini_pause = tk.Button(
            macro_mini_right,
            text="⏸ 暂停脚本\nCtrl+Shift+P",
            bg="#7f8c8d",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#f39c12",
            activeforeground="white",
            relief="raised",
            bd=1,
            pady=1,
            state="disabled",
            command=self.toggle_pause_macro_script,
        )
        self.btn_macro_mini_pause.grid(row=2, column=0, sticky="nsew", pady=1)

        self.btn_macro_mini_stop = tk.Button(
            macro_mini_right,
            text="⏹ 停止运行\nCtrl+Shift+E",
            bg="#7f8c8d",
            fg="white",
            font=("Segoe UI", 8, "bold"),
            activebackground="#c0392b",
            activeforeground="white",
            relief="raised",
            bd=1,
            pady=1,
            state="disabled",
            command=self.stop_macro_script,
        )
        self.btn_macro_mini_stop.grid(row=3, column=0, sticky="nsew", pady=1)

    def toggle_topmost(self):
        """切换 Mini 面板窗口置顶状态"""
        curr = not self.topmost_var.get()
        self.topmost_var.set(curr)
        self.apply_topmost_ui()
        self.mark_dirty()

    def apply_topmost_ui(self):
        """更新置顶状态与按钮视觉表现"""
        is_top = self.topmost_var.get()
        self.root.attributes("-topmost", is_top)
        for btn in [getattr(self, "btn_topmost", None), getattr(self, "btn_macro_topmost", None)]:
            if btn:
                if is_top:
                    btn.config(text="📌 已置顶", bg="#e67e22", relief="sunken")
                else:
                    btn.config(text="📌 置顶", bg="#7f8c8d", relief="raised")

    def toggle_follow_target(self):
        """切换目标窗口前台联动切换状态"""
        curr = not self.follow_target_var.get()
        self.follow_target_var.set(curr)
        self.apply_follow_target_ui()
        if curr and getattr(self, "is_mini_mode", False):
            self.align_mini_to_target_bottom()
        self.mark_dirty()

    def apply_follow_target_ui(self):
        """更新联动状态与按钮视觉表现"""
        is_follow = self.follow_target_var.get()
        for btn in [getattr(self, "btn_follow", None), getattr(self, "btn_macro_follow", None)]:
            if btn:
                if is_follow:
                    btn.config(text="🔗 已联动", bg="#27ae60", relief="sunken")
                else:
                    btn.config(text="🔗 联动", bg="#7f8c8d", relief="raised")
        self.update_window_ownership()

    def update_window_ownership(self):
        """设置目标窗口为 Mini 面板的 Win32 HWNDPARENT，实现 Windows 原生窗口 Z-Order 联动/跟随"""
        try:
            if getattr(self, "is_mini_mode", False) and self.follow_target_var.get():
                target_hwnd = self.target_hwnd_var.get()
                if target_hwnd and win32gui.IsWindow(target_hwnd):
                    my_hwnd = self.root.winfo_id()
                    root_my = win32gui.GetAncestor(my_hwnd, win32con.GA_ROOT) or my_hwnd
                    root_target = win32gui.GetAncestor(target_hwnd, win32con.GA_ROOT) or target_hwnd
                    if root_my != root_target:
                        win32gui.SetWindowLong(root_my, win32con.GWL_HWNDPARENT, root_target)
        except Exception:
            pass

    def check_target_foreground_loop(self):
        """轮询目标窗口前台状态：智能动态前台联动 (状态变化时才触发，避免多实例竞争引发标题栏闪烁)"""
        try:
            if getattr(self, "is_mini_mode", False):
                # 若用户手动勾选了“全局置顶”，强制保持全局置顶
                if self.topmost_var.get():
                    if not getattr(self, "_current_topmost_state", False):
                        self.root.attributes("-topmost", True)
                        self._current_topmost_state = True
                elif self.follow_target_var.get():
                    target_hwnd = self.target_hwnd_var.get()
                    if target_hwnd and win32gui.IsWindow(target_hwnd):
                        fg_hwnd = win32gui.GetForegroundWindow()
                        if fg_hwnd and win32gui.IsWindow(fg_hwnd):
                            my_hwnd = self.root.winfo_id()
                            root_my = win32gui.GetAncestor(my_hwnd, win32con.GA_ROOT) or my_hwnd

                            # 如果当前获得焦点的是当前 Mini 面板本身，保持现有置顶状态不变
                            if fg_hwnd != my_hwnd and fg_hwnd != root_my:
                                root_fg = win32gui.GetAncestor(fg_hwnd, win32con.GA_ROOT) or fg_hwnd
                                root_target = win32gui.GetAncestor(target_hwnd, win32con.GA_ROOT) or target_hwnd

                                try:
                                    _, target_pid = win32process.GetWindowThreadProcessId(target_hwnd)
                                    _, fg_pid = win32process.GetWindowThreadProcessId(fg_hwnd)
                                except Exception:
                                    target_pid = 0
                                    fg_pid = -1

                                fg_title = win32gui.GetWindowText(fg_hwnd)

                                # 判定切到前台的是否为绑定的模拟器，或者协同运行的另一个 AutoClick 实例
                                is_target_active = (
                                    fg_hwnd == target_hwnd
                                    or root_fg == root_target
                                    or (target_pid > 0 and fg_pid == target_pid)
                                    or ("AutoClick" in fg_title)
                                )

                                # 仅在状态真正发生跃变时才调用 attributes("-topmost")，彻底避免频繁重绘导致标题栏闪烁
                                last_active = getattr(self, "_last_target_active_state", None)
                                if is_target_active != last_active:
                                    self._last_target_active_state = is_target_active
                                    if is_target_active:
                                        self.root.attributes("-topmost", True)
                                        self._current_topmost_state = True
                                    else:
                                        self.root.attributes("-topmost", False)
                                        self._current_topmost_state = False
        except Exception:
            pass

        self.root.after(300, self.check_target_foreground_loop)

    def toggle_point_enabled(self, index):
        """Mini 面板点击按钮切换对应点位的启用/禁用状态"""
        curr = self.point_vars[index]["enabled"].get()
        self.point_vars[index]["enabled"].set(not curr)
        self.update_mini_point_button(index)
        self.mark_dirty()

    def sync_macro_mini_display(self):
        """同步宏脚本 Mini 面板上的当前脚本文件名与代码编辑框"""
        if not hasattr(self, "mini_script_display"):
            return

        file_name = self.script_file_var.get().strip() or "未选择脚本"
        star = "*" if self.is_dirty_script else ""
        if hasattr(self, "lbl_mini_script_name"):
            self.lbl_mini_script_name.config(text=f"📜 {file_name}{star}")

        code_text = ""
        if hasattr(self, "script_editor"):
            code_text = self.script_editor.get("1.0", tk.END)

        self.mini_script_display.delete("1.0", tk.END)
        self.mini_script_display.insert("1.0", code_text)
        self.apply_syntax_highlight(self.mini_script_display)

    def open_script_file_from_mini(self):
        """从 Macro Mini 面板载入脚本文件"""
        self.open_script_file()
        self.sync_macro_mini_display()

    def update_mini_point_button(self, index):
        """同步更新指定点位在 Mini 面板上的按钮样式（凹陷/弹起，亮灯/灭灯）与文字"""
        if not hasattr(self, "mini_point_widgets") or index >= len(self.mini_point_widgets):
            return

        enabled = self.point_vars[index]["enabled"].get()
        remark = self.point_vars[index]["remark"].get().strip()
        display_text = f"#{index + 1} {remark}" if remark else f"#{index + 1}"

        w = self.mini_point_widgets[index]
        w["label"].config(text=display_text)

        if enabled:
            # 启用工作状态：被按下去 (sunken)，亮起小绿灯
            w["frame"].config(relief="sunken", bg="#dcdcdc")
            w["label"].config(bg="#dcdcdc", fg="#111111")
            w["canvas"].config(bg="#dcdcdc")
            w["canvas"].itemconfig(w["oval"], fill="#2ecc71")
        else:
            # 未启用状态：弹起的按钮 (raised)，灯不亮
            w["frame"].config(relief="raised", bg="#f0f0f0")
            w["label"].config(bg="#f0f0f0", fg="#555555")
            w["canvas"].config(bg="#f0f0f0")
            w["canvas"].itemconfig(w["oval"], fill="#95a5a6")

    def update_mini_target_title(self, *args):
        """实时查询 target_hwnd 真实进程信息并更新 Mini 面板标题，确保 100% 所见即所得"""
        hwnd = self.target_hwnd_var.get()
        if hwnd and win32gui.IsWindow(hwnd):
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                raw_title = win32gui.GetWindowText(hwnd)
                _, prog_name = format_target_title_components(raw_title)
                title_str = f"AutoClick Mini - [PID:{pid}] {prog_name}"
            except Exception:
                title_str = f"AutoClick Mini - [HWND:{hwnd}]"
        else:
            title_str = "AutoClick Mini - [⚠️未绑定有效目标]"

        if getattr(self, "is_mini_mode", False):
            self.root.title(title_str)

    def align_mini_to_target_bottom(self):
        """将 Mini 面板自动吸附/粘连到当前绑定的目标窗口正下方（支持点位模式与脚本模式、多显示器、副屏负坐标与高分屏）"""
        try:
            target_hwnd = self.target_hwnd_var.get()

            # 1. 严格基于用户选中的 target_hwnd 校验，严禁自动猜测并串台重置用户绑定的窗口！
            if not target_hwnd or not win32gui.IsWindow(target_hwnd) or win32gui.IsIconic(target_hwnd):
                selected_title = self.win_cb.get() if hasattr(self, "win_cb") else ""
                if hasattr(self, "window_map") and selected_title in self.window_map:
                    target_hwnd = self.window_map[selected_title]
                else:
                    return False

            if not target_hwnd or not win32gui.IsWindow(target_hwnd) or win32gui.IsIconic(target_hwnd):
                return False

            root_target = win32gui.GetAncestor(target_hwnd, win32con.GA_ROOT) or target_hwnd

            # 2. 获取目标窗口真实的物理像素边界 (通过 DWM 获得剔除透明阴影的真实物理窗口区域)
            t_rect = wintypes.RECT()
            DWMWA_EXTENDED_FRAME_BOUNDS = 9
            try:
                res = ctypes.windll.dwmapi.DwmGetWindowAttribute(
                    wintypes.HWND(root_target),
                    wintypes.DWORD(DWMWA_EXTENDED_FRAME_BOUNDS),
                    ctypes.byref(t_rect),
                    ctypes.sizeof(t_rect)
                )
                if res == 0:
                    t_left, t_top, t_right, t_bottom = t_rect.left, t_rect.top, t_rect.right, t_rect.bottom
                else:
                    t_left, t_top, t_right, t_bottom = win32gui.GetWindowRect(root_target)
            except Exception:
                t_left, t_top, t_right, t_bottom = win32gui.GetWindowRect(root_target)

            if t_right <= t_left or t_bottom <= t_top or t_left <= -10000:
                return False

            # 3. 获取目标窗口所在显示器的专属可用工作区 (Work Area, 已扣除任务栏，支持副屏负坐标)
            try:
                h_monitor = win32api.MonitorFromWindow(root_target, win32con.MONITOR_DEFAULTTONEAREST)
                mon_info = win32api.GetMonitorInfo(h_monitor)
                work_left, work_top, work_right, work_bottom = mon_info["Work"]
            except Exception:
                work_left = 0
                work_top = 0
                work_right = win32api.GetSystemMetrics(win32con.SM_CXSCREEN)
                work_bottom = win32api.GetSystemMetrics(win32con.SM_CYSCREEN)

            mini_w, mini_h = 415, 255

            # 4. 计算 X 轴：优先与目标窗口左对齐；若右侧超出该屏幕工作区，则向左贴齐该显示器工作区右边缘
            pos_x = max(work_left, min(t_left, work_right - mini_w))

            # 5. 计算 Y 轴：优先紧贴目标窗口下方 (t_bottom)
            # 若窗口底部空间不足以放下 Mini 面板，则贴靠在当前显示器的工作区底部
            pos_y = max(work_top, min(t_bottom, work_bottom - mini_h))

            # 6. 更新 Tkinter 几何位置并调用 Win32 SetWindowPos 实现跨屏无缝精确定位
            self.root.update_idletasks()
            self.root.geometry(f"{mini_w}x{mini_h}+{pos_x}+{pos_y}")

            try:
                my_hwnd = self.root.winfo_id()
                root_my = win32gui.GetAncestor(my_hwnd, win32con.GA_ROOT) or my_hwnd
                if root_my and win32gui.IsWindow(root_my):
                    win32gui.SetWindowPos(
                        root_my,
                        0,
                        pos_x,
                        pos_y,
                        mini_w,
                        mini_h,
                        win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
                    )
            except Exception:
                pass

            return True
        except Exception:
            pass
        return False

    def switch_to_mini_panel(self):
        """切换到 Mini 面板界面 (根据当前激活的 Notebook Tab 自动决定显示 10点位 Mini 面板还是 脚本宏 Mini 面板)"""
        self.is_mini_mode = True
        self.main_frame.pack_forget()

        current_tab = self.notebook.index(self.notebook.select()) if hasattr(self, "notebook") else 0

        if current_tab == 1:
            # 切换至 脚本宏模式 Mini 面板
            if hasattr(self, "mini_frame"):
                self.mini_frame.pack_forget()
            if hasattr(self, "macro_mini_frame"):
                self.macro_mini_frame.pack(fill="both", expand=True)
            self.sync_macro_mini_display()
        else:
            # 切换至 10 组点位模式 Mini 面板
            if hasattr(self, "macro_mini_frame"):
                self.macro_mini_frame.pack_forget()
            if hasattr(self, "mini_frame"):
                self.mini_frame.pack(fill="both", expand=True)
            for i in range(NUM_POINTS):
                self.update_mini_point_button(i)

        self.root.minsize(360, 220)
        self.apply_topmost_ui()
        self.apply_follow_target_ui()
        self.update_mini_target_title()

        # 在所有 UI 结构与 Win32 父子关系建立完毕后，最后执行吸附粘连定位
        if not self.align_mini_to_target_bottom():
            self.root.geometry("415x255")

    def switch_to_main_panel(self):
        """切换回全功能主面板界面"""
        self.is_mini_mode = False
        if hasattr(self, "mini_script_display") and hasattr(self, "script_editor"):
            content = self.mini_script_display.get("1.0", tk.END)
            self.script_editor.delete("1.0", tk.END)
            self.script_editor.insert("1.0", content)
            self.apply_syntax_highlight(self.script_editor)
        if hasattr(self, "mini_frame"):
            self.mini_frame.pack_forget()
        if hasattr(self, "macro_mini_frame"):
            self.macro_mini_frame.pack_forget()
        self.main_frame.pack(fill="both", expand=True)
        self.root.minsize(1100, 780)
        self.root.geometry("1180x860")
        self.update_window_title()

    def resolve_hierarchy(self):
        """解析 10 个坐标点的多级挂载父子关系"""
        parents = [None] * NUM_POINTS
        children = {i: [] for i in range(NUM_POINTS)}

        for i in range(NUM_POINTS):
            lvl = self.point_vars[i]["level"].get()
            parent_idx = None

            if lvl > 0:
                for prev in range(i - 1, -1, -1):
                    if self.point_vars[prev]["level"].get() == lvl - 1:
                        parent_idx = prev
                        break

                if parent_idx is None:
                    lvl = 0
                    self.point_vars[i]["level"].set(0)

            parents[i] = parent_idx
            if parent_idx is not None:
                children[parent_idx].append(i)

        return parents, children

    def update_hierarchy_ui(self):
        """更新 UI 缩进与挂载关系文本显示 (已加宽 1.5 倍)"""
        parents, _ = self.resolve_hierarchy()

        for i in range(NUM_POINTS):
            lvl = self.point_vars[i]["level"].get()
            parent_idx = parents[i]

            indent = "  " * lvl
            prefix = "└─ " if lvl > 0 else ""

            if lvl == 0:
                text = f"[L0 主点] #{i + 1:02d}"
            else:
                text = f"{indent}{prefix}[L{lvl} 挂载于#{parent_idx + 1:02d}] #{i + 1:02d}"

            self.point_labels[i].config(text=text)

    def change_level(self, index, delta):
        """调整点位的挂载层级 (delta: -1 升级 / +1 降级)"""
        current_lvl = self.point_vars[index]["level"].get()
        new_lvl = current_lvl + delta

        if new_lvl < 0:
            new_lvl = 0
        if new_lvl > MAX_LEVEL:
            new_lvl = MAX_LEVEL

        if delta > 0 and index > 0:
            prev_lvl = self.point_vars[index - 1]["level"].get()
            if new_lvl > prev_lvl + 1:
                new_lvl = prev_lvl + 1

        if index == 0:
            new_lvl = 0

        self.point_vars[index]["level"].set(new_lvl)
        self.update_hierarchy_ui()
        self.mark_dirty()

    def on_mode_changed(self):
        """模式切换时智能自动转换坐标体系 (前台屏幕绝对坐标 <-> 后台模拟器视口相对坐标)"""
        new_mode = self.mode_var.get()
        old_mode = self._last_mode
        self._last_mode = new_mode

        hwnd = self.target_hwnd_var.get()

        if old_mode != new_mode and hwnd and win32gui.IsWindow(hwnd):
            render_hwnd, cl_w, cl_h, _, _ = self.get_emulator_render_info(hwnd)
            converted_count = 0
            for i in range(NUM_POINTS):
                p_vars = self.point_vars[i]
                try:
                    x = int(p_vars["x"].get())
                    y = int(p_vars["y"].get())
                except ValueError:
                    continue

                if x == 0 and y == 0:
                    continue

                if old_mode == "foreground" and new_mode == "background":
                    cx, cy = win32gui.ScreenToClient(render_hwnd, (x, y))
                    p_vars["x"].set(str(cx))
                    p_vars["y"].set(str(cy))
                    converted_count += 1
                elif old_mode == "background" and new_mode == "foreground":
                    sx, sy = win32gui.ClientToScreen(render_hwnd, (x, y))
                    p_vars["x"].set(str(sx))
                    p_vars["y"].set(str(sy))
                    converted_count += 1

            if converted_count > 0:
                if new_mode == "background":
                    self.log_msg(f"🔄 已自动将 {converted_count} 组坐标从 [屏幕绝对坐标] 转换为 [模拟器视口相对坐标 ({cl_w}x{cl_h})]")
                else:
                    self.log_msg(f"🔄 已自动将 {converted_count} 组坐标从 [模拟器视口相对坐标] 转换为 [屏幕绝对坐标]")

        self.mark_dirty()

    def refresh_window_list(self):
        """刷新窗口下拉菜单，并精准同步当前选中的目标窗口"""
        windows = get_window_list()
        self.window_map = {}
        for hwnd, title in windows:
            try:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                key = f"[PID:{pid} | HWND:{hwnd}] {title}"
            except Exception:
                key = f"[HWND:{hwnd}] {title}"
            self.window_map[key] = hwnd

        values = list(self.window_map.keys())
        self.win_cb["values"] = values

        current_hwnd = self.target_hwnd_var.get()
        current_title = self.target_title_var.get().strip()

        found_key = None

        # 1. 优先依据 HWND 精确匹配当前活跃窗口
        if current_hwnd and win32gui.IsWindow(current_hwnd):
            for name, hwnd in self.window_map.items():
                if hwnd == current_hwnd:
                    found_key = name
                    break

        # 2. 若 HWND 改变 (例如进程/模拟器重启)，严格匹配完整标题；若存在多个同名实例，严禁随意猜测！
        if not found_key and current_title and current_title != "选择目标窗口...":
            # 先精确全字匹配 (含特定标识)
            for name, hwnd in self.window_map.items():
                if current_title == name:
                    found_key = name
                    self.target_hwnd_var.set(hwnd)
                    break

            if not found_key:
                _, saved_prog = format_target_title_components(current_title)
                if saved_prog and saved_prog != "未选择目标窗口":
                    matches = []
                    for name, hwnd in self.window_map.items():
                        _, name_prog = format_target_title_components(name)
                        if saved_prog == name_prog or saved_prog in name:
                            matches.append((name, hwnd))

                    if len(matches) == 1:
                        # 仅在有且仅有唯一一个同名实例时才自动重连
                        found_key, target_h = matches[0]
                        self.target_hwnd_var.set(target_h)
                    elif len(matches) > 1:
                        # 检测到多个同名模拟器实例，严禁随意绑定第一个！清空 HWND 并提示用户手动选择
                        self.target_hwnd_var.set(0)
                        found_key = None
                        self.log_msg(f"⚠️ 检测到系统中运行了 {len(matches)} 个同名模拟器窗口！为确保安全防止串台，请在下拉列表中手动选择具体要绑定的实例。")

        # 3. 匹配成功则同步更新下拉框与 target_title_var，保证主面板与 Mini 面板完全一致
        if found_key:
            self.win_cb.set(found_key)
            self.target_title_var.set(found_key)
        else:
            if current_hwnd and not win32gui.IsWindow(current_hwnd):
                self.target_hwnd_var.set(0)
            if current_title and current_title != "选择目标窗口...":
                self.win_cb.set(current_title)
            else:
                self.win_cb.set("选择目标窗口...")
                self.target_title_var.set("选择目标窗口...")

        self.update_mini_target_title()

        self.log_msg(f"窗口列表已更新，找到 {len(values)} 个活动窗口。")

    def on_window_selected(self, event):
        selected = self.win_cb.get()
        if selected in self.window_map:
            hwnd = self.window_map[selected]
            self.target_hwnd_var.set(hwnd)
            self.target_title_var.set(selected)
            self.mark_dirty()
            if self.adb_enabled_var.get():
                self.refresh_adb_devices()

    def pick_target_window(self):
        """鼠标拾取窗口句柄"""
        self.log_msg("请在 3 秒内将鼠标悬停在目标窗口上方...")
        self.root.update()

        def delayed_pick():
            time.sleep(3)
            x, y = pyautogui.position()
            hwnd = win32gui.WindowFromPoint((x, y))
            root_hwnd = win32gui.GetAncestor(hwnd, win32con.GA_ROOT)
            if root_hwnd:
                hwnd = root_hwnd

            title = win32gui.GetWindowText(hwnd)
            self.root.after(
                0,
                lambda: self._set_target_window_picked(hwnd, title),
            )

        threading.Thread(target=delayed_pick, daemon=True).start()

    def _set_target_window_picked(self, hwnd, title):
        self.target_hwnd_var.set(hwnd)
        pid_val, clean_title = format_target_title_components(title)
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if pid:
                pid_val = str(pid)
        except Exception:
            pass

        if pid_val:
            display_name = f"[PID:{pid_val} | HWND:{hwnd}] {clean_title}"
        else:
            display_name = f"[HWND:{hwnd}] {clean_title}"

        self.win_cb.set(display_name)
        self.window_map[display_name] = hwnd
        self.target_title_var.set(display_name)
        self.update_mini_target_title()
        self.update_window_ownership()
        self.mark_dirty()
        self.log_msg(f"已锁定目标窗口: {display_name}")
        if self.adb_enabled_var.get():
            self.refresh_adb_devices()

    def pick_coordinate(self, index):
        """倒计时拾取坐标"""
        self.log_msg(f"请在 2 秒内将鼠标放置在点位 #{index + 1} 目标位置...")
        self.root.update()

        def do_pick():
            time.sleep(2)
            x, y = pyautogui.position()
            self.root.after(0, lambda: self._update_point_coord(index, x, y))

        threading.Thread(target=do_pick, daemon=True).start()

    def record_current_position(self, index):
        """通过快捷键实时录入当前鼠标坐标"""
        x, y = pyautogui.position()
        self.root.after(0, lambda: self._update_point_coord(index, x, y))

    def _update_point_coord(self, index, screen_x, screen_y):
        mode = self.mode_var.get()
        hwnd = self.target_hwnd_var.get()
        is_adb = self.adb_enabled_var.get()

        if hwnd and win32gui.IsWindow(hwnd):
            render_hwnd, cl_w, cl_h, offset_x, offset_y = self.get_emulator_render_info(hwnd)
            if cl_w > 50 and cl_h > 50:
                self.base_render_size = [cl_w, cl_h]
            try:
                rect = win32gui.GetWindowRect(hwnd)
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                if w > 100 and h > 100:
                    self.target_window_size = [w, h]
            except Exception:
                pass

            cx, cy = win32gui.ScreenToClient(render_hwnd, (screen_x, screen_y))
            norm_x = max(0.0, min(1.0, cx / max(1, cl_w)))
            norm_y = max(0.0, min(1.0, cy / max(1, cl_h)))

            if is_adb:
                device = self.adb_device_var.get().strip()
                wm_w, wm_h = self.get_adb_screen_resolution(device)
                if wm_w <= 0 or wm_h <= 0:
                    wm_w, wm_h = getattr(self, "base_adb_resolution", [540, 1200])
                real_adb_w = wm_h if (cl_w > cl_h) != (wm_w > wm_h) else wm_w
                real_adb_h = wm_w if (cl_w > cl_h) != (wm_w > wm_h) else wm_h
                final_x, final_y = int(norm_x * real_adb_w), int(norm_y * real_adb_h)
                coord_desc = f"[ADB 内部物理坐标: ({final_x}, {final_y}) | 比例: {norm_x*100:.1f}%, {norm_y*100:.1f}%]"
            elif mode == "background":
                final_x, final_y = cx, cy
                coord_desc = f"[模拟器视口相对坐标: ({final_x}, {final_y}) | 比例: {norm_x*100:.1f}%, {norm_y*100:.1f}%]"
            else:
                final_x, final_y = screen_x, screen_y
                coord_desc = f"[屏幕绝对坐标: ({final_x}, {final_y})]"
        else:
            final_x, final_y = screen_x, screen_y
            coord_desc = f"[屏幕绝对坐标: ({final_x}, {final_y})]"

        p_vars = self.point_vars[index]
        p_vars["x"].set(str(final_x))
        p_vars["y"].set(str(final_y))
        p_vars["enabled"].set(True)
        self.mark_dirty()
        self.log_msg(f"已自动录入点位 #{index + 1} {coord_desc}")

    def log_auto_click(self, point_idx, current_cnt, max_cnt):
        """在 UI 状态栏与日志框实时显示自动点击日志"""
        p_vars = self.point_vars[point_idx]
        lvl = p_vars["level"].get()
        rem = p_vars["remark"].get().strip()
        rem_str = f" ({rem})" if rem else ""
        cnt_str = f" [{current_cnt}/{max_cnt}次]" if max_cnt > 0 else ""

        msg = f"⚡ [自动运行] 点击点位 #{point_idx + 1}{rem_str} (L{lvl}){cnt_str}"
        self.log_msg(msg)

    def on_adb_toggled(self):
        """模拟器增强 (ADB模式) 切换逻辑与点位坐标智能等比换算"""
        self.mark_dirty()
        is_adb = self.adb_enabled_var.get()
        hwnd = self.target_hwnd_var.get()

        if is_adb:
            self.log_msg("⚡ 已开启 [模拟器增强 (ADB后台模式)]！点击指令将通过 ADB 底层触控直接发送至模拟器。")
            self.refresh_adb_devices()
            if hwnd and win32gui.IsWindow(hwnd):
                render_hwnd, cl_w, cl_h, _, _ = self.get_emulator_render_info(hwnd)
                device = self.adb_device_var.get().strip()
                wm_w, wm_h = self.get_adb_screen_resolution(device)
                if wm_w <= 0 or wm_h <= 0:
                    wm_w, wm_h = getattr(self, "base_adb_resolution", [540, 1200])
                if wm_w > 0 and wm_h > 0 and cl_w > 0 and cl_h > 0:
                    real_adb_w = wm_h if (cl_w > cl_h) != (wm_w > wm_h) else wm_w
                    real_adb_h = wm_w if (cl_w > cl_h) != (wm_w > wm_h) else wm_h
                    cnt = 0
                    for i in range(NUM_POINTS):
                        p_vars = self.point_vars[i]
                        try:
                            x, y = int(p_vars["x"].get()), int(p_vars["y"].get())
                        except ValueError:
                            continue
                        if x == 0 and y == 0:
                            continue
                        # 如果坐标看起来还是视口相对坐标 (<= cl_w, cl_h)
                        if x <= cl_w * 1.1 and y <= cl_h * 1.1:
                            nx = x / max(1, cl_w)
                            ny = y / max(1, cl_h)
                            p_vars["x"].set(str(int(nx * real_adb_w)))
                            p_vars["y"].set(str(int(ny * real_adb_h)))
                            cnt += 1
                    if cnt > 0:
                        self.log_msg(f"⚡ 已自动将 {cnt} 组点位坐标等比转换为 [ADB 内部物理坐标 ({real_adb_w}x{real_adb_h})]")
        else:
            self.log_msg("已关闭 [模拟器增强 (ADB后台模式)]，恢复使用标准 Windows 消息。")
            if hwnd and win32gui.IsWindow(hwnd):
                render_hwnd, cl_w, cl_h, _, _ = self.get_emulator_render_info(hwnd)
                device = self.adb_device_var.get().strip()
                wm_w, wm_h = self.get_adb_screen_resolution(device)
                if wm_w <= 0 or wm_h <= 0:
                    wm_w, wm_h = getattr(self, "base_adb_resolution", [540, 1200])
                if wm_w > 0 and wm_h > 0 and cl_w > 0 and cl_h > 0:
                    real_adb_w = wm_h if (cl_w > cl_h) != (wm_w > wm_h) else wm_w
                    real_adb_h = wm_w if (cl_w > cl_h) != (wm_w > wm_h) else wm_h
                    cnt = 0
                    for i in range(NUM_POINTS):
                        p_vars = self.point_vars[i]
                        try:
                            x, y = int(p_vars["x"].get()), int(p_vars["y"].get())
                        except ValueError:
                            continue
                        if x == 0 and y == 0:
                            continue
                        # 如果坐标看起来是 ADB 内部坐标 (> cl_w 或 > cl_h)
                        if x > cl_w * 1.1 or y > cl_h * 1.1:
                            nx = x / max(1, real_adb_w)
                            ny = y / max(1, real_adb_h)
                            p_vars["x"].set(str(int(nx * cl_w)))
                            p_vars["y"].set(str(int(ny * cl_h)))
                            cnt += 1
                    if cnt > 0:
                        self.log_msg(f"🔄 已自动将 {cnt} 组点位坐标等比转换为 [模拟器视口相对坐标 ({cl_w}x{cl_h})]")

    def get_adb_path(self):
        """优先使用程序所在目录下的独立 ADB 工具，保证全功能兼容与免冲突"""
        custom_path = self.adb_custom_path_var.get().strip()
        if custom_path and os.path.exists(custom_path):
            return custom_path

        # 1. 优先调用本程序目录下的 adb/adb.exe 或 adb.exe
        base_dir = os.path.dirname(os.path.abspath(__file__))
        local_candidates = [
            os.path.join(base_dir, "adb", "adb.exe"),
            os.path.join(base_dir, "adb.exe"),
        ]
        for p in local_candidates:
            if os.path.exists(p):
                return p

        # 2. 尝试系统 PATH 中的 adb
        try:
            res = shutil.which("adb")
            if res:
                return res
        except Exception:
            pass

        return None

    def refresh_adb_devices(self):
        """精准依据选中窗口 PID 匹配连接对应的 ADB 模拟器端口"""
        adb_bin = self.get_adb_path()
        if not adb_bin:
            self.log_msg("⚠️ 刷新失败：未找到可用的 ADB 工具 (请确认 adb/ 目录是否存在)")
            self.adb_dev_cb["values"] = []
            return []

        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

        # 1. 依据目标窗口进程 PID 查找其监听的 TCP 本地端口
        hwnd = self.target_hwnd_var.get()
        pid_ports = []
        if hwnd and win32gui.IsWindow(hwnd):
            pid_ports = detect_adb_ports_by_hwnd(hwnd)
            if pid_ports:
                self.log_msg(f"🔍 锁定当前窗口进程对应的 ADB 监听端口: {pid_ports}")
                for port in pid_ports:
                    try:
                        subprocess.run(
                            [adb_bin, "connect", f"127.0.0.1:{port}"],
                            creationflags=flags,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=3.0
                        )
                    except Exception:
                        pass

        # 尝试常用模拟器 ADB 端口补救连接 (如 5555, 5565)
        for default_port in [5555, 5565]:
            if default_port not in pid_ports:
                try:
                    subprocess.run(
                        [adb_bin, "connect", f"127.0.0.1:{default_port}"],
                        creationflags=flags,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=1.0
                    )
                except Exception:
                    pass

        # 2. 查询系统当前已连接的 ADB 设备
        try:
            out = subprocess.check_output(
                [adb_bin, "devices"],
                creationflags=flags,
                text=True,
                timeout=5
            )
            devices = []
            for line in out.splitlines():
                line = line.strip()
                if line and not line.startswith("List of") and "device" in line and not line.startswith("*"):
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "device":
                        devices.append(parts[0])

            # 3. 校验设备响应并进行 PID 专属匹配
            valid_devices = []
            for d in devices:
                try:
                    res_ping = subprocess.run(
                        [adb_bin, "-s", d, "shell", "echo", "ok"],
                        creationflags=flags,
                        capture_output=True,
                        text=True,
                        timeout=1.5
                    )
                    if res_ping.returncode == 0 and "ok" in res_ping.stdout:
                        valid_devices.append(d)
                except Exception:
                    pass

            if not valid_devices:
                valid_devices = devices

            # 4. 精准分配属于当前进程 PID 的 ADB 设备
            matched_dev = None
            matched_list = []

            if pid_ports:
                for p in pid_ports:
                    p_str = str(p)
                    console_port_str = str(p - 1)
                    for d in valid_devices:
                        if f":{p_str}" in d or f"-{p_str}" in d or f"-{console_port_str}" in d:
                            if d not in matched_list:
                                matched_list.append(d)

                # 优先挑选 IP:Port 形式（如 127.0.0.1:5555 / 127.0.0.1:5565），避免使用模糊的 emulator-5554
                ip_ports = [d for d in matched_list if ":" in d]
                if ip_ports:
                    matched_dev = ip_ports[0]
                elif matched_list:
                    matched_dev = matched_list[0]

            # 仅在下拉框中显示当前窗口 PID 锁定的 ADB 设备 (不把其它无关设备的 ADB 混入下拉框)
            if matched_list:
                final_dropdown_list = matched_list
            else:
                final_dropdown_list = valid_devices

            self.adb_dev_cb["values"] = final_dropdown_list

            hwnd = self.target_hwnd_var.get()
            target_pid = 0
            if hwnd and win32gui.IsWindow(hwnd):
                try:
                    _, target_pid = win32process.GetWindowThreadProcessId(hwnd)
                except Exception:
                    pass

            if matched_dev:
                self.adb_device_var.set(matched_dev)
                self.log_msg(f"✅ [ADB 锁定] 成功将目标窗口 [PID:{target_pid}] 100% 精准绑定到 ADB 设备: [{matched_dev}]")
            elif len(final_dropdown_list) == 1:
                self.adb_device_var.set(final_dropdown_list[0])
                self.log_msg(f"✅ [ADB 唯一设备] 绑定 ADB 设备: [{final_dropdown_list[0]}]")
            elif len(final_dropdown_list) > 1:
                # 存在多个 ADB 设备且无法根据 PID 唯一确定时，严禁随意绑定第一个！必须置空并由用户选择！
                self.adb_device_var.set("")
                self.log_msg(f"⚠️ [ADB 防串台拦截] 检测到多个在线 ADB 设备 ({', '.join(final_dropdown_list)})，未找到与当前窗口 PID:{target_pid} 唯一匹配的端口。为防串台，请在 ADB 设备下拉框中手动指定！")
            else:
                self.adb_device_var.set("")
                self.log_msg("⚠️ 未检测到可正常响应的 ADB 设备。请确认模拟器「设置 -> 高级」中已开启「Android 调试桥 (ADB)」。")

            return final_dropdown_list
        except Exception as e:
            self.log_msg(f"❌ 获取 ADB 设备列表出错: {e}")
            return []

    def connect_adb_port(self):
        """手动连接 ADB 端口 (例如 127.0.0.1:5555)"""
        target = simpledialog.askstring(
            "连接 ADB 设备",
            "请输入 ADB 目标 IP 与端口 (如 127.0.0.1:5555 或 127.0.0.1:5565):",
            initialvalue="127.0.0.1:5555"
        )
        if target:
            adb_bin = self.get_adb_path()
            if not adb_bin:
                messagebox.showerror("错误", "未找到 ADB 可执行文件！")
                return
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                out = subprocess.check_output(
                    [adb_bin, "connect", target.strip()],
                    creationflags=flags,
                    text=True,
                    timeout=5
                )
                self.log_msg(f"🔗 ADB 连接响应: {out.strip()}")
                self.refresh_adb_devices()
            except Exception as e:
                messagebox.showerror("连接失败", f"无法连接至 {target}: {e}")

    def browse_adb_path(self):
        """选择自定义 adb.exe / HD-Adb.exe"""
        filepath = filedialog.askopenfilename(
            title="选择 ADB 可执行文件",
            filetypes=[("可执行程序", "*.exe"), ("所有文件", "*.*")],
        )
        if filepath:
            self.adb_custom_path_var.set(filepath)
            self.mark_dirty()
            self.refresh_adb_devices()

    def get_adb_screen_resolution(self, device):
        """获取并缓存模拟器内部 Android 物理分辨率 (wm size)"""
        if not hasattr(self, "_res_cache"):
            self._res_cache = {}
        if device in self._res_cache:
            return self._res_cache[device]

        adb_bin = self.get_adb_path()
        if not adb_bin:
            return (0, 0)

        cmd = [adb_bin]
        if device:
            cmd.extend(["-s", device])
        cmd.extend(["shell", "wm", "size"])

        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            out = subprocess.check_output(cmd, creationflags=flags, text=True, timeout=3)
            m = re.search(r"(\d+)x(\d+)", out)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                self._res_cache[device] = (w, h)
                return (w, h)
        except Exception:
            pass
        return (0, 0)

    def get_emulator_render_info(self, hwnd):
        """
        获取模拟器游戏画面的 Viewport 子窗口句柄与物理尺寸。
        自动精确定位并消除 BlueStacks / 雷电 / MuMu 等模拟器的顶部标题栏 (约38px) 与侧边栏偏移。
        返回: (render_hwnd, cl_w, cl_h, offset_x, offset_y)
        """
        if not hwnd or not win32gui.IsWindow(hwnd):
            return hwnd, 0, 0, 0, 0

        render_hwnd = hwnd
        children = []

        def enum_cb(ch, _):
            if win32gui.IsWindowVisible(ch):
                try:
                    _, _, cw, ch_h = win32gui.GetClientRect(ch)
                    if cw > 50 and ch_h > 50:
                        cls_name = win32gui.GetClassName(ch)
                        children.append((ch, cls_name, cw, ch_h))
                except Exception:
                    pass
            return True

        try:
            win32gui.EnumChildWindows(hwnd, enum_cb, None)
        except Exception:
            pass

        known_render_classes = [
            "renderwindow",
            "inputinteropwindow",
            "subwin",
            "nemurender",
            "sdl_app",
            "bluestacksapp",
        ]

        found_child = False
        for ch, cls_name, cw, ch_h in children:
            cls_lower = cls_name.lower()
            for kw in known_render_classes:
                if kw in cls_lower:
                    render_hwnd = ch
                    found_child = True
                    break
            if found_child:
                break

        if not found_child and children:
            try:
                _, _, top_w, top_h = win32gui.GetClientRect(hwnd)
                top_area = top_w * top_h
                best_ch = hwnd
                best_area = 0
                for ch, cls_name, cw, ch_h in children:
                    area = cw * ch_h
                    if 0.3 * top_area <= area < 0.98 * top_area:
                        if area > best_area:
                            best_area = area
                            best_ch = ch
                if best_ch != hwnd:
                    render_hwnd = best_ch
                    found_child = True
            except Exception:
                pass

        try:
            _, _, cl_w, cl_h = win32gui.GetClientRect(render_hwnd)
        except Exception:
            cl_w, cl_h = 0, 0

        offset_x, offset_y = 0, 0
        if render_hwnd != hwnd:
            try:
                r_screen = win32gui.ClientToScreen(render_hwnd, (0, 0))
                offset_pt = win32gui.ScreenToClient(hwnd, r_screen)
                offset_x, offset_y = offset_pt[0], offset_pt[1]
            except Exception:
                pass
        else:
            # 备用方案：如果未抓到独立 Viewport 窗口，针对 BlueStacks/雷电/MuMu 进行外框高度与侧栏补偿
            title_text = win32gui.GetWindowText(hwnd).lower()
            cls_text = win32gui.GetClassName(hwnd).lower()
            if any(kw in title_text or kw in cls_text for kw in ["bluestacks", "ldplayer", "dnplayer", "mumu", "nemu"]):
                offset_y = 38
                offset_x = 0
                cl_h = max(1, cl_h - 38)
                cl_w = max(1, cl_w - 38)

        return render_hwnd, cl_w, cl_h, offset_x, offset_y

    def restore_target_window_size(self):
        """将当前绑定的目标模拟器窗口还原为配置中指定的标准尺寸 (默认 424x901)"""
        target_hwnd = self.target_hwnd_var.get()
        if not target_hwnd or not win32gui.IsWindow(target_hwnd):
            messagebox.showwarning("提示", "请先选择或锁定有效的目标窗口！")
            return

        root_target = win32gui.GetAncestor(target_hwnd, win32con.GA_ROOT) or target_hwnd

        target_w, target_h = getattr(self, "target_window_size", [424, 901])
        if target_w <= 0 or target_h <= 0:
            target_w, target_h = 424, 901

        try:
            rect = win32gui.GetWindowRect(root_target)
            pos_x, pos_y = rect[0], rect[1]
            win32gui.SetWindowPos(
                root_target,
                0,
                pos_x,
                pos_y,
                target_w,
                target_h,
                win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW
            )
            render_hwnd, cl_w, cl_h, _, _ = self.get_emulator_render_info(root_target)
            self.log_msg(f"📐 已将目标窗口尺寸还原为标准大小: {target_w}x{target_h} (视口画布: {cl_w}x{cl_h})")
            if getattr(self, "is_mini_mode", False):
                self.root.after(100, self.align_mini_to_target_bottom)
        except Exception as e:
            self.log_msg(f"❌ 还原窗口尺寸失败: {e}")

    def calculate_scaled_coords(self, x, y, hwnd=None, mode=None):
        """
        双轨坐标自适应换算引擎：
        根据基准录制视口尺寸 (base_render_size) 或 Android 内部物理分辨率 (base_adb_resolution)，
        自适应换算当前目标窗口与当前模式下的实际点击坐标与归一化百分比。
        返回: (target_x, target_y, norm_x, norm_y, render_hwnd)
        """
        if hwnd is None:
            hwnd = self.target_hwnd_var.get()
        if mode is None:
            mode = self.mode_var.get()
        is_adb = self.adb_enabled_var.get()

        render_hwnd, cl_w, cl_h, offset_x, offset_y = self.get_emulator_render_info(hwnd)
        base_w, base_h = getattr(self, "base_render_size", [390, 867])
        if base_w <= 0 or base_h <= 0:
            base_w, base_h = max(1, cl_w) if cl_w > 0 else 390, max(1, cl_h) if cl_h > 0 else 867

        if is_adb:
            adb_base_w, adb_base_h = getattr(self, "base_adb_resolution", [540, 1200])
            if adb_base_w <= 0 or adb_base_h <= 0:
                adb_base_w, adb_base_h = 540, 1200

            # 智能判断传入坐标是基于视口尺寸还是 ADB 内部物理分辨率
            if x <= base_w * 1.08 and y <= base_h * 1.08:
                norm_x = max(0.0, min(1.0, x / max(1, base_w)))
                norm_y = max(0.0, min(1.0, y / max(1, base_h)))
            else:
                norm_x = max(0.0, min(1.0, x / max(1, adb_base_w)))
                norm_y = max(0.0, min(1.0, y / max(1, adb_base_h)))

            device = self.adb_device_var.get().strip()
            wm_w, wm_h = self.get_adb_screen_resolution(device)
            if wm_w <= 0 or wm_h <= 0:
                wm_w, wm_h = adb_base_w, adb_base_h

            is_win_landscape = cl_w > cl_h
            is_adb_landscape = wm_w > wm_h
            if is_win_landscape != is_adb_landscape:
                real_adb_w, real_adb_h = wm_h, wm_w
            else:
                real_adb_w, real_adb_h = wm_w, wm_h

            target_x = int(norm_x * real_adb_w)
            target_y = int(norm_y * real_adb_h)
            return target_x, target_y, norm_x, norm_y, render_hwnd

        elif mode == "background":
            norm_x = max(0.0, min(1.0, x / max(1, base_w)))
            norm_y = max(0.0, min(1.0, y / max(1, base_h)))
            cur_w = max(1, cl_w) if cl_w > 0 else base_w
            cur_h = max(1, cl_h) if cl_h > 0 else base_h
            target_x = int(norm_x * cur_w)
            target_y = int(norm_y * cur_h)
            return target_x, target_y, norm_x, norm_y, render_hwnd

        else:
            # 前台模式
            if hwnd and win32gui.IsWindow(hwnd):
                norm_x = max(0.0, min(1.0, x / max(1, base_w)))
                norm_y = max(0.0, min(1.0, y / max(1, base_h)))
                cur_w = max(1, cl_w) if cl_w > 0 else base_w
                cur_h = max(1, cl_h) if cl_h > 0 else base_h
                vx = int(norm_x * cur_w)
                vy = int(norm_y * cur_h)
                try:
                    screen_pt = win32gui.ClientToScreen(render_hwnd, (vx, vy))
                    target_x, target_y = screen_pt[0], screen_pt[1]
                except Exception:
                    target_x, target_y = x, y
            else:
                target_x, target_y = x, y
                norm_x, norm_y = 0.0, 0.0
            return target_x, target_y, norm_x, norm_y, render_hwnd

    def dispatch_click(self, x, y, hwnd=None):
        """统一底层点击击发器 (支持自适应缩放与三大模式调度)"""
        if hwnd is None:
            hwnd = self.target_hwnd_var.get()
        mode = self.mode_var.get()
        is_adb = self.adb_enabled_var.get()

        target_x, target_y, norm_x, norm_y, render_h = self.calculate_scaled_coords(x, y, hwnd, mode)

        if is_adb:
            return self.execute_adb_click(target_x, target_y, direct_adb=True)
        elif mode == "foreground":
            pyautogui.click(target_x, target_y)
            return True
        else:
            if render_h and win32gui.IsWindow(render_h):
                return post_background_click(render_h, target_x, target_y)
            elif hwnd and win32gui.IsWindow(hwnd):
                return post_background_click(hwnd, target_x, target_y)
            return False

    def execute_adb_click(self, x, y, direct_adb=False):
        """使用 ADB 向模拟器发送带适度长按延时的 input 触控指令 (精准计算画布偏移与坐标映射)"""
        adb_bin = self.get_adb_path()
        if not adb_bin:
            self.log_msg("❌ [ADB] 未找到 ADB 可执行文件！")
            return False

        device = self.adb_device_var.get().strip()
        if not device:
            devs = self.refresh_adb_devices()
            if len(devs) == 1:
                device = devs[0]
            elif len(devs) > 1:
                self.log_msg(f"❌ [ADB 保护] 检测到多个在线 ADB 设备 ({', '.join(devs)})，但未明确指定目标设备！为防串台误操作，已阻止发送。请在 ADB 设置中选择对应设备。")
                return False
            else:
                self.log_msg("❌ [ADB] 未选择且未找到匹配的 ADB 设备！")
                return False

        if direct_adb:
            target_x, target_y = int(x), int(y)
        else:
            hwnd = self.target_hwnd_var.get()
            target_x, target_y, norm_x, norm_y, _ = self.calculate_scaled_coords(x, y, hwnd, mode="background")
            self.log_msg(f"⚡ [ADB 自适应映射] 坐标({x},{y}) -> 比例({norm_x*100:.1f}%, {norm_y*100:.1f}%) -> 物理触控({target_x}, {target_y})")

        # 使用 input swipe 按住 80 毫秒 (模拟真实手指点击，解决部分游戏 input tap 太快被过滤的问题)
        cmd = [adb_bin]
        if device:
            cmd.extend(["-s", device])
        cmd.extend(["shell", "input", "swipe", str(target_x), str(target_y), str(target_x), str(target_y), "80"])

        try:
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            res = subprocess.run(cmd, creationflags=flags, capture_output=True, text=True, timeout=3)
            if res.returncode != 0:
                err_info = (res.stderr or res.stdout or f"退出码 {res.returncode}").strip()
                if "error: closed" in err_info or "offline" in err_info or "not found" in err_info:
                    self.log_msg(f"❌ [ADB错误] 设备 [{device}] 点击失败: {err_info}")
                    self.log_msg("💡 建议排查：1. 在 BlueStacks 设置 -> 高级 中确认开启「Android 调试桥 (ADB)」；2. 确认设备未处于离线状态。")
                else:
                    self.log_msg(f"❌ [ADB] 执行触控指令失败: {err_info}")
                return False
            return True
        except Exception as e:
            self.log_msg(f"❌ [ADB] 点击命令执行异常: {e}")
            return False

    def test_adb_connection(self):
        """测试 ADB 点击功能 (点击模拟器中央屏幕)"""
        if not self.adb_enabled_var.get():
            messagebox.showinfo("提示", "请先勾选开启 [模拟器增强 (ADB模式)]。")
            return

        is_valid, hwnd, real_pid, real_title = self.verify_target_consistency(caller_name="ADB点击测试")
        if not is_valid:
            return

        adb_bin = self.get_adb_path()
        if not adb_bin:
            messagebox.showerror("错误", "未检测到 ADB 可执行文件！\n请确保安装了 BlueStacks 或手动指定 adb.exe 路径。")
            return

        device = self.adb_device_var.get().strip()
        wm_w, wm_h = self.get_adb_screen_resolution(device)
        if wm_w <= 0 or wm_h <= 0:
            wm_w, wm_h = getattr(self, "base_adb_resolution", [540, 1200])

        center_x, center_y = max(10, wm_w // 2), max(10, wm_h // 2)

        if self.execute_adb_click(center_x, center_y, direct_adb=True):
            self.log_msg(f"⚡ [ADB 点击测试成功] 已向设备 [{device}] 屏幕中央物理坐标 ({center_x}, {center_y}) 发送触控指令！")
        else:
            self.log_msg("❌ [ADB 点击测试失败] 发送点击失败。")

    def execute_click(self, point_idx, mode=None, hwnd=None):
        """执行指定点位的实际点击动作，返回 bool 结果"""
        p_vars = self.point_vars[point_idx]
        try:
            x = int(p_vars["x"].get())
            y = int(p_vars["y"].get())
        except ValueError:
            return False

        return self.dispatch_click(x, y, hwnd)

    def test_single_click(self, index):
        """测试单次点击"""
        try:
            x = int(self.point_vars[index]["x"].get())
            y = int(self.point_vars[index]["y"].get())
        except ValueError:
            messagebox.showwarning("提示", f"点位 #{index + 1} 坐标格式不正确！")
            return

        mode = self.mode_var.get()
        is_adb = self.adb_enabled_var.get()
        hwnd = self.target_hwnd_var.get()

        # 强制进行 100% 目标一致性预飞核验
        if mode == "background" or is_adb:
            is_valid, hwnd, _, _ = self.verify_target_consistency(caller_name=f"点位#{index+1}测试点击")
            if not is_valid:
                return

        success = self.execute_click(index, mode, hwnd)
        lvl = self.point_vars[index]["level"].get()
        rem = self.point_vars[index]["remark"].get().strip()
        rem_str = f" ({rem})" if rem else ""
        mode_desc = "ADB模式" if is_adb else ("前台" if mode == "foreground" else "后台")

        target_x, target_y, norm_x, norm_y, _ = self.calculate_scaled_coords(x, y, hwnd, mode)
        scale_info = f" -> 实际击发 ({target_x}, {target_y}) [比例 {norm_x*100:.1f}%, {norm_y*100:.1f}%]"

        if success:
            self.log_msg(f"⚡ [{mode_desc}测试击发] 点位 #{index + 1}{rem_str} (L{lvl}) | 原始坐标 ({x}, {y}){scale_info}")
        else:
            self.log_msg(f"❌ [{mode_desc}测试失败] 点位 #{index + 1}{rem_str} (L{lvl}) 点击未能送达模拟器！")

    def execute_macro_drag(self, x1, y1, x2, y2, duration_ms):
        """执行宏脚本中的轨迹拖拽/滑动指令 (精准自适应模拟器画布与分辨率)"""
        hwnd = self.target_hwnd_var.get()
        mode = self.mode_var.get()
        is_adb = self.adb_enabled_var.get()

        tx1, ty1, _, _, render_hwnd = self.calculate_scaled_coords(x1, y1, hwnd, mode)
        tx2, ty2, _, _, _ = self.calculate_scaled_coords(x2, y2, hwnd, mode)

        if is_adb:
            adb_bin = self.get_adb_path()
            device = self.adb_device_var.get().strip()
            if not adb_bin or not device:
                self.log_msg("❌ [Macro Drag] ADB 未就绪或未选择设备！")
                return False

            cmd = [adb_bin, "-s", device, "shell", "input", "swipe", str(tx1), str(ty1), str(tx2), str(ty2), str(duration_ms)]
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                res = subprocess.run(cmd, creationflags=flags, capture_output=True, text=True, timeout=5)
                return res.returncode == 0
            except Exception:
                return False

        elif mode == "foreground":
            try:
                pyautogui.moveTo(tx1, ty1)
                pyautogui.dragTo(tx2, ty2, duration=max(0.1, duration_ms / 1000.0))
                return True
            except Exception:
                return False
        else:
            if not render_hwnd or not win32gui.IsWindow(render_hwnd):
                if not hwnd or not win32gui.IsWindow(hwnd):
                    return False
                render_hwnd = hwnd
            lp1 = win32api.MAKELONG(max(0, tx1), max(0, ty1))
            lp2 = win32api.MAKELONG(max(0, tx2), max(0, ty2))
            win32gui.PostMessage(render_hwnd, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lp1)
            steps = 5
            for s in range(1, steps + 1):
                ix = int(tx1 + (tx2 - tx1) * (s / steps))
                iy = int(ty1 + (ty2 - ty1) * (s / steps))
                win32gui.PostMessage(render_hwnd, win32con.WM_MOUSEMOVE, win32con.MK_LBUTTON, win32api.MAKELONG(max(0, ix), max(0, iy)))
                time.sleep(duration_ms / (1000.0 * steps))
            win32gui.PostMessage(render_hwnd, win32con.WM_LBUTTONUP, 0, lp2)
            return True

    def execute_macro_input(self, text):
        """执行宏脚本中的字符/文本输入指令"""
        hwnd = self.target_hwnd_var.get()
        mode = self.mode_var.get()
        is_adb = self.adb_enabled_var.get()

        if is_adb:
            adb_bin = self.get_adb_path()
            device = self.adb_device_var.get().strip()
            if not adb_bin or not device:
                self.log_msg("❌ [Macro Input] ADB 未就绪！")
                return False

            escaped_text = text.replace(" ", "%s").replace("&", "\\&").replace("<", "\\<").replace(">", "\\>")
            cmd = [adb_bin, "-s", device, "shell", "input", "text", escaped_text]
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                res = subprocess.run(cmd, creationflags=flags, capture_output=True, text=True, timeout=5)
                return res.returncode == 0
            except Exception:
                return False
        elif mode == "foreground":
            try:
                keyboard.write(text)
                return True
            except Exception:
                return False
        else:
            if not hwnd or not win32gui.IsWindow(hwnd):
                return False
            for char in text:
                win32gui.SendMessage(hwnd, win32con.WM_CHAR, ord(char), 0)
                time.sleep(0.02)
            return True

    def get_current_editor_line(self):
        """获取当前激活编辑器光标或选中区所在行 (1-based)"""
        try:
            active_ed = self._get_active_editor()
            if not active_ed:
                return 1
            if active_ed.tag_ranges("sel"):
                sel_start = active_ed.index("sel.first")
                return int(sel_start.split(".")[0])
            cursor_pos = active_ed.index("insert")
            return int(cursor_pos.split(".")[0])
        except Exception:
            return 1

    def update_script_ui_states(self):
        """统一同步更新主界面与 Mini 面板中脚本控制按钮的状态、颜色与文本"""
        if not self.script_running:
            if hasattr(self, "btn_run_script"):
                self.btn_run_script.config(state="normal", bg="#2ecc71")
            if hasattr(self, "btn_run_from_line"):
                self.btn_run_from_line.config(state="normal", bg="#16a085")
            if hasattr(self, "btn_pause_script"):
                self.btn_pause_script.config(state="disabled", text="⏸ 暂停脚本 (Ctrl+Shift+P)", bg="#7f8c8d")
            if hasattr(self, "btn_stop_script"):
                self.btn_stop_script.config(state="disabled", bg="#7f8c8d")

            if hasattr(self, "btn_macro_mini_start"):
                self.btn_macro_mini_start.config(state="normal", bg="#2ecc71")
            if hasattr(self, "btn_macro_mini_start_line"):
                self.btn_macro_mini_start_line.config(state="normal", bg="#16a085")
            if hasattr(self, "btn_macro_mini_pause"):
                self.btn_macro_mini_pause.config(state="disabled", text="⏸ 暂停脚本\nCtrl+Shift+P", bg="#7f8c8d")
            if hasattr(self, "btn_macro_mini_stop"):
                self.btn_macro_mini_stop.config(state="disabled", bg="#7f8c8d")

        elif not self.script_paused:
            if hasattr(self, "btn_run_script"):
                self.btn_run_script.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_run_from_line"):
                self.btn_run_from_line.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_pause_script"):
                self.btn_pause_script.config(state="normal", text="⏸ 暂停脚本 (Ctrl+Shift+P)", bg="#f39c12")
            if hasattr(self, "btn_stop_script"):
                self.btn_stop_script.config(state="normal", bg="#e74c3c")

            if hasattr(self, "btn_macro_mini_start"):
                self.btn_macro_mini_start.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_macro_mini_start_line"):
                self.btn_macro_mini_start_line.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_macro_mini_pause"):
                self.btn_macro_mini_pause.config(state="normal", text="⏸ 暂停脚本\nCtrl+Shift+P", bg="#f39c12")
            if hasattr(self, "btn_macro_mini_stop"):
                self.btn_macro_mini_stop.config(state="normal", bg="#e74c3c")

        else:
            if hasattr(self, "btn_run_script"):
                self.btn_run_script.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_run_from_line"):
                self.btn_run_from_line.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_pause_script"):
                self.btn_pause_script.config(state="normal", text="▶ 继续脚本 (Ctrl+Shift+P)", bg="#27ae60")
            if hasattr(self, "btn_stop_script"):
                self.btn_stop_script.config(state="normal", bg="#e74c3c")

            if hasattr(self, "btn_macro_mini_start"):
                self.btn_macro_mini_start.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_macro_mini_start_line"):
                self.btn_macro_mini_start_line.config(state="disabled", bg="#7f8c8d")
            if hasattr(self, "btn_macro_mini_pause"):
                self.btn_macro_mini_pause.config(state="normal", text="▶ 继续脚本\nCtrl+Shift+P", bg="#27ae60")
            if hasattr(self, "btn_macro_mini_stop"):
                self.btn_macro_mini_stop.config(state="normal", bg="#e74c3c")

        self.update_macro_mini_timer_display()

    def update_macro_mini_timer_display(self):
        """更新 脚本宏 Mini 面板左上角显示的运行时间与 3 个 Timer 耗时"""
        if not hasattr(self, "lbl_macro_mini_badge"):
            return

        if getattr(self, "script_running", False):
            now = time.monotonic()
            elapsed_sec = int(now - getattr(self, "script_start_time", now))

            active_items = sorted(self.active_script_timers.items(), key=lambda x: x[0])[:3]
            t_strs = []
            for tid, start_t in active_items:
                t_dur = int(now - start_t)
                t_strs.append(f"T{tid}:{t_dur}s")

            timer_part = (" | " + " ".join(t_strs)) if t_strs else ""

            if getattr(self, "script_paused", False):
                disp_text = f"⏸️ {elapsed_sec}s{timer_part}"
                fg_color = "#e67e22"
            else:
                disp_text = f"⏱️ {elapsed_sec}s{timer_part}"
                fg_color = "#27ae60"

            self.lbl_macro_mini_badge.config(text=disp_text, foreground=fg_color)
        else:
            self.lbl_macro_mini_badge.config(text="📜 脚本宏 Mini 面板", foreground="#8e44ad")

    def _update_macro_mini_timer_loop(self):
        """每秒刷新一次脚本宏 Mini 面板时间显示"""
        try:
            self.update_macro_mini_timer_display()
        except Exception:
            pass
        self.root.after(1000, self._update_macro_mini_timer_loop)

    def toggle_pause_macro_script(self):
        """切换按键脚本宏的暂停与继续状态"""
        if not self.script_running:
            return
        self.script_paused = not self.script_paused
        if self.script_paused:
            self.log_msg("⏸ [脚本宏] 脚本运行已暂停。")
        else:
            self.log_msg("▶ [脚本宏] 脚本恢复运行。")
        self.root.after(0, self.update_script_ui_states)

    def verify_target_consistency(self, caller_name="操作"):
        """
        启动前强制进行 100% 目标一致性预飞核验 (Pre-Flight Consistency Verification)。
        核验要求：
        1. target_hwnd 必须为操作系统中真实存在且有效的窗口。
        2. UI 界面上显示的标题/PID 必须与 target_hwnd 在 Windows 内核中实时的 PID/标题 100% 吻合。
        3. 若开启 ADB 模式，所选 ADB 设备端口必须属于该窗口 PID (若检测到属于其他模拟器实例或未选择，直接拦截报错)。
        返回值：(is_valid: bool, target_hwnd: int, real_pid: int, real_title: str)
        """
        target_hwnd = self.target_hwnd_var.get()
        if not target_hwnd or not win32gui.IsWindow(target_hwnd):
            selected = self.win_cb.get() if hasattr(self, "win_cb") else ""
            if selected in self.window_map:
                target_hwnd = self.window_map[selected]
                self.target_hwnd_var.set(target_hwnd)
            else:
                err_msg = f"❌ [安全拦截: 目标未绑定] 当前未绑定有效的目标窗口，已强制终止 {caller_name}！请在下拉框中选择要操作的目标模拟器窗口。"
                self.log_msg(err_msg)
                messagebox.showerror("未绑定目标窗口", f"当前未绑定有效的目标窗口！\n\n为确保数据安全，已终止 {caller_name}。\n请先在窗口下拉菜单中明确选择目标窗口。")
                return False, 0, 0, ""

        # 1. 查询目标窗口当前在操作系统中的实时 PID 与标题
        try:
            _, real_pid = win32process.GetWindowThreadProcessId(target_hwnd)
            real_title = win32gui.GetWindowText(target_hwnd)
        except Exception as e:
            err_msg = f"❌ [安全拦截: 获取进程信息失败] 无法获取句柄 HWND:{target_hwnd} 的实时系统信息: {e}"
            self.log_msg(err_msg)
            messagebox.showerror("目标窗口失效", f"目标窗口已失效或无权访问！\n\n{err_msg}")
            return False, 0, 0, ""

        # 2. 校验界面显示内容与真实操作系统目标的一致性
        ui_selected = self.win_cb.get() if hasattr(self, "win_cb") else ""
        ui_pid, ui_prog = format_target_title_components(ui_selected)
        if ui_pid and str(real_pid) != str(ui_pid):
            err_msg = (
                f"❌ [致命安全拦截: 界面与实际目标 PID 不一致！]\n"
                f"界面显示目标: PID:{ui_pid} ({ui_prog})\n"
                f"实际绑定目标: [PID:{real_pid} | HWND:{target_hwnd}] {real_title}\n"
                f"检测到显示与底层目标不一致，为保护您的游戏数据安全，程序已强制终止本次{caller_name}！\n"
                f"请点击 [🔄 刷新窗口] 并重新选择目标。"
            )
            self.log_msg(err_msg)
            messagebox.showerror("目标不一致 - 安全拦截", err_msg)
            return False, 0, 0, ""

        # 3. 校验 ADB 模式下 ADB 端口与当前窗口 PID 的一致性
        if self.adb_enabled_var.get():
            adb_device = self.adb_device_var.get().strip()
            if not adb_device:
                err_msg = f"❌ [安全拦截: ADB 未指定设备] 已开启 ADB 模式，但未指定具体 ADB 设备！为防串台，已终止{caller_name}。请在 ADB 设置中选择对应设备。"
                self.log_msg(err_msg)
                messagebox.showerror("ADB 未指定设备", err_msg)
                return False, 0, 0, ""

            # 探测当前 PID 所监听的端口
            pid_ports = detect_adb_ports_by_hwnd(target_hwnd)
            if pid_ports:
                matched_port = any(
                    f":{p}" in adb_device or f"-{p}" in adb_device or f"-{p-1}" in adb_device
                    for p in pid_ports
                )
                if not matched_port:
                    err_msg = (
                        f"❌ [致命安全拦截: ADB 设备与当前窗口 PID 不匹配！]\n"
                        f"当前目标窗口: [PID:{real_pid}] {real_title} (该实例监听端口: {pid_ports})\n"
                        f"当前 ADB 设备绑定为: [{adb_device}] (属于其他模拟器实例！)\n"
                        f"为防止串台误操作其他游戏实例，程序已强制终止本次{caller_name}！\n"
                        f"请在 ADB 设备下拉框中选择正确的端口 (包含 {pid_ports})。"
                    )
                    self.log_msg(err_msg)
                    messagebox.showerror("ADB 串台安全拦截", err_msg)
                    return False, 0, 0, ""

        # 4. 全部核验通过，记录确信一致性日志
        mode_name = "ADB增强" if self.adb_enabled_var.get() else ("前台" if self.mode_var.get() == "foreground" else "后台")
        adb_str = f" | ADB设备: [{self.adb_device_var.get().strip()}]" if self.adb_enabled_var.get() else ""
        self.log_msg(f"✅ [预飞核验 100% 通过] 界面显示与底层发送目标完全一致: [PID:{real_pid} | HWND:{target_hwnd}] {real_title} (方式: {mode_name}{adb_str})")
        return True, target_hwnd, real_pid, real_title

    def start_macro_script(self, start_from_current_line=False):
        """启动按键脚本宏解析调度线程"""
        if self.script_running:
            return

        active_ed = self._get_active_editor()
        script_code = active_ed.get("1.0", tk.END).strip() if active_ed else ""
        if not script_code:
            messagebox.showwarning("提示", "当前脚本文本为空，请输入或录制脚本！")
            return

        # 若在 Mini 模式下，将最新内容同步至主面板 script_editor
        if active_ed != getattr(self, "script_editor", None) and hasattr(self, "script_editor"):
            full_text = active_ed.get("1.0", tk.END)
            self.script_editor.delete("1.0", tk.END)
            self.script_editor.insert("1.0", full_text)
            self.apply_syntax_highlight(self.script_editor)

        commands = parse_macro_script(script_code)
        if not commands:
            messagebox.showwarning("提示", "无法解析脚本指令，请检查脚本语法！")
            return

        start_pc = 0
        if start_from_current_line:
            target_line = self.get_current_editor_line()
            found = False
            for idx, cmd in enumerate(commands):
                if cmd.line_num >= target_line:
                    start_pc = idx
                    found = True
                    break
            if not found:
                start_pc = 0

        # 强制进行 100% 目标一致性预飞核验
        is_valid, target_hwnd, real_pid, real_title = self.verify_target_consistency(caller_name="脚本宏运行")
        if not is_valid:
            return

        self.script_running = True
        self.script_paused = False
        self.script_start_time = time.monotonic()
        self.active_script_timers.clear()
        self.script_variables = {}
        self.root.after(0, self.update_script_ui_states)

        if start_pc > 0:
            self.log_msg(f"📜 [脚本宏] 从第 {commands[start_pc].line_num} 行 (指令 #{start_pc + 1}: {commands[start_pc].raw_text}) 开始启动脚本 (共 {len(commands)} 条指令)...")
        else:
            self.log_msg(f"📜 [脚本宏] 启动执行，共解析出 {len(commands)} 条指令...")

        def macro_loop():
            block_stack = []
            loop_pairs = {}
            if_jump = {}
            if_branch_end_jump = {}

            # 构建循环与 If-Else 两趟扫描跳转表
            for i, cmd in enumerate(commands):
                ctype = cmd.cmd_type
                if ctype == "LOOP_START":
                    block_stack.append(("LOOP", i))
                elif ctype == "IF_START":
                    block_stack.append(("IF", i))
                elif ctype == "ELSE":
                    if block_stack and block_stack[-1][0] == "IF_CLOSED":
                        entry = block_stack.pop()
                        if_idx, if_end_pc = entry[1], entry[2]
                        if_jump[if_idx] = i + 1
                        block_stack.append(("ELSE", i, if_idx, if_end_pc))
                    elif block_stack and block_stack[-1][0] == "IF":
                        entry = block_stack.pop()
                        if_idx = entry[1]
                        if_jump[if_idx] = i + 1
                        block_stack.append(("ELSE", i, if_idx, i))
                elif ctype in ["BLOCK_END", "LOOP_END"]:
                    if block_stack:
                        entry = block_stack.pop()
                        b_type = entry[0]
                        if b_type == "LOOP":
                            loop_start_pc = entry[1]
                            loop_pairs[loop_start_pc] = i
                            loop_pairs[i] = loop_start_pc
                        elif b_type == "IF":
                            if_idx = entry[1]
                            if_jump[if_idx] = i + 1
                            block_stack.append(("IF_CLOSED", if_idx, i))
                        elif b_type == "ELSE":
                            else_idx, if_idx, if_end_pc = entry[1], entry[2], entry[3]
                            if_branch_end_jump[if_end_pc] = i + 1

            loop_counters = {}
            pc = start_pc
            n = len(commands)

            while pc < n and self.script_running:
                while self.script_running and self.script_paused:
                    p_start = time.monotonic()
                    time.sleep(0.05)
                    p_dur = time.monotonic() - p_start
                    if p_dur > 0 and hasattr(self, "active_script_timers"):
                        for tid in list(self.active_script_timers.keys()):
                            self.active_script_timers[tid] += p_dur

                if not self.script_running:
                    break

                cmd = commands[pc]
                ctype = cmd.cmd_type
                params = cmd.params

                if ctype == "COMMENT":
                    pc += 1
                    continue

                elif ctype == "VAR_ASSIGN":
                    v_name = params["name"]
                    v_expr = params["expr"]
                    val = safe_eval_expr(v_expr, self.script_variables)
                    self.script_variables[v_name] = val
                    self.log_msg(f"📝 [脚本行#{cmd.line_num}] 变量赋值: {v_name} = {val}")

                elif ctype == "IF_START":
                    cond_str = params["condition"]
                    cond_res = safe_eval_cond(cond_str, self.script_variables)
                    cond_desc = "真 (进入 IF 分支)" if cond_res else "假 (跳过 IF 分支)"
                    self.log_msg(f"🔀 [脚本行#{cmd.line_num}] 条件判断 If ({cond_str}) -> {cond_desc}")
                    if not cond_res:
                        pc = if_jump.get(pc, pc + 1)
                        continue

                elif ctype == "ELSE":
                    # 正常从 IF 执行完落入时跳过 ELSE，或直接顺延
                    pass

                elif ctype == "TIMER_START":
                    tid = params.get("id", 1)
                    self.active_script_timers[tid] = time.monotonic()
                    self.log_msg(f"⏱️ [脚本行#{cmd.line_num}] 启动 Timer #{tid}")

                elif ctype == "TIMER_RESET":
                    tid = params.get("id", 1)
                    self.active_script_timers[tid] = time.monotonic()
                    self.log_msg(f"⏱️ [脚本行#{cmd.line_num}] 重置 Timer #{tid}")

                elif ctype == "TIMER_STOP":
                    tid = params.get("id", 1)
                    if tid in self.active_script_timers:
                        dur = int(time.monotonic() - self.active_script_timers[tid])
                        del self.active_script_timers[tid]
                        self.log_msg(f"⏹️ [脚本行#{cmd.line_num}] 停止 Timer #{tid} (用时 {dur}s)")
                    else:
                        self.log_msg(f"⏹️ [脚本行#{cmd.line_num}] 停止 Timer #{tid}")

                elif ctype == "DELAY":
                    d_expr = params.get("delay_expr", str(params.get("delay_ms", 1000)))
                    if isinstance(d_expr, str) and d_expr.endswith("s") and not d_expr.endswith("ms"):
                        try:
                            val = float(safe_eval_expr(d_expr[:-1], self.script_variables))
                            delay_ms = int(val * 1000)
                        except Exception:
                            delay_ms = 1000
                    else:
                        try:
                            delay_ms = int(safe_eval_expr(str(d_expr), self.script_variables))
                        except Exception:
                            delay_ms = 1000

                    end_t = time.monotonic() + (delay_ms / 1000.0)
                    self.log_msg(f"⏱ [脚本行#{cmd.line_num}] 延时等待 {delay_ms}ms...")
                    while time.monotonic() < end_t and self.script_running:
                        if self.script_paused:
                            p_start = time.monotonic()
                            while self.script_running and self.script_paused:
                                time.sleep(0.05)
                            p_dur = time.monotonic() - p_start
                            end_t += p_dur
                            for tid in list(self.active_script_timers.keys()):
                                self.active_script_timers[tid] += p_dur
                        time.sleep(0.01)

                elif ctype == "CLICK":
                    try:
                        x = int(safe_eval_expr(str(params.get("x_expr", params["x"])), self.script_variables))
                        y = int(safe_eval_expr(str(params.get("y_expr", params["y"])), self.script_variables))
                        cnt = int(safe_eval_expr(str(params.get("count_expr", params.get("count", 1))), self.script_variables))
                        raw_intv = safe_eval_expr(str(params.get("interval_ms_expr", params.get("interval_ms", 100))), self.script_variables)
                        interval = float(raw_intv) / 1000.0
                    except Exception as e:
                        self.log_msg(f"⚠️ [脚本行#{cmd.line_num}] Click 参数计算异常: {e}")
                        x, y, cnt, interval = params.get("x", 0), params.get("y", 0), 1, 0.1

                    for c_idx in range(cnt):
                        if not self.script_running:
                            break
                        while self.script_running and self.script_paused:
                            time.sleep(0.05)
                        self.dispatch_click(x, y, hwnd)
                        self.log_msg(f"⚡ [脚本行#{cmd.line_num}] 点击坐标 ({x}, {y}) [{c_idx+1}/{cnt}]")
                        if c_idx < cnt - 1:
                            end_intv = time.monotonic() + interval
                            while time.monotonic() < end_intv and self.script_running:
                                if self.script_paused:
                                    p_start = time.monotonic()
                                    while self.script_running and self.script_paused:
                                        time.sleep(0.05)
                                    p_dur = time.monotonic() - p_start
                                    end_intv += p_dur
                                    for tid in list(self.active_script_timers.keys()):
                                        self.active_script_timers[tid] += p_dur
                                time.sleep(0.01)

                elif ctype == "CLICK_POINT":
                    try:
                        pt_idx = int(safe_eval_expr(str(params.get("index_expr", params["index"])), self.script_variables))
                        cnt = int(safe_eval_expr(str(params.get("count_expr", params.get("count", 1))), self.script_variables))
                    except Exception:
                        pt_idx, cnt = params.get("index", 0), 1

                    if 0 <= pt_idx < NUM_POINTS:
                        for c_idx in range(cnt):
                            if not self.script_running:
                                break
                            while self.script_running and self.script_paused:
                                time.sleep(0.05)
                            self.execute_click(pt_idx, self.mode_var.get(), self.target_hwnd_var.get())
                            rem = self.point_vars[pt_idx]["remark"].get().strip()
                            self.log_msg(f"⚡ [脚本行#{cmd.line_num}] 触发关联点位 #{pt_idx+1} ({rem}) [{c_idx+1}/{cnt}]")
                            time.sleep(0.1)

                elif ctype == "DRAG":
                    try:
                        x1 = int(safe_eval_expr(str(params.get("x1_expr", params["x1"])), self.script_variables))
                        y1 = int(safe_eval_expr(str(params.get("y1_expr", params["y1"])), self.script_variables))
                        x2 = int(safe_eval_expr(str(params.get("x2_expr", params["x2"])), self.script_variables))
                        y2 = int(safe_eval_expr(str(params.get("y2_expr", params["y2"])), self.script_variables))
                        dur = int(safe_eval_expr(str(params.get("duration_ms_expr", params.get("duration_ms", 500))), self.script_variables))
                    except Exception:
                        x1, y1, x2, y2, dur = params.get("x1", 0), params.get("y1", 0), params.get("x2", 0), params.get("y2", 0), 500

                    self.log_msg(f"🖐️ [脚本行#{cmd.line_num}] 拖拽轨迹 ({x1},{y1}) -> ({x2},{y2}) [{dur}ms]")
                    self.execute_macro_drag(x1, y1, x2, y2, dur)

                elif ctype == "CLICK_EX":
                    # 智能提取包含在条件分支 (If-Else) 中的完整 ClickEx 树状调度块 (自动求值参数表达式)
                    click_ex_block, next_pc = self.collect_click_ex_block_with_flow(commands, pc)

                    has_hierarchy = any(c.params["level"] > 0 or c.params["interval"] >= 5.0 for c in click_ex_block)

                    if len(click_ex_block) > 1 and has_hierarchy:
                        self.log_msg(f"⚡ [脚本行#{cmd.line_num}] 启动 ClickEx 多级 Timer 级联调度引擎 (包含 {len(click_ex_block)} 个级联点位)...")
                        self.execute_click_ex_hierarchy_block(click_ex_block)
                        pc = next_pc
                        continue
                    else:
                        try:
                            lvl = int(safe_eval_expr(str(params.get("level_expr", params.get("level", 0))), self.script_variables))
                            x = int(safe_eval_expr(str(params.get("x_expr", params.get("x", 0))), self.script_variables))
                            y = int(safe_eval_expr(str(params.get("y_expr", params.get("y", 0))), self.script_variables))
                            delay = float(safe_eval_expr(str(params.get("delay_expr", params.get("delay", 0.0))), self.script_variables))
                            interval = float(safe_eval_expr(str(params.get("interval_expr", params.get("interval", 0.5))), self.script_variables))
                            cnt = int(safe_eval_expr(str(params.get("count_expr", params.get("count", 1))), self.script_variables))
                            rem = str(safe_eval_expr(str(params.get("remark_expr", params.get("remark", ""))), self.script_variables)).strip("\"'")
                            timer_id = int(safe_eval_expr(str(params.get("timer_id_expr", params.get("timer_id", 0))), self.script_variables))
                        except Exception:
                            lvl, x, y, delay, interval, cnt, rem, timer_id = 0, 0, 0, 0.0, 0.5, 1, "", 0

                        rem_str = f" ({rem})" if rem else ""

                        if timer_id > 0:
                            self.active_script_timers[timer_id] = time.monotonic()

                        if lvl > 0:
                            self.log_msg(f"⚡ [脚本行#{cmd.line_num}] ClickEx L{lvl}{rem_str} (上级视作为真，直接运行)...")

                        if delay > 0:
                            self.log_msg(f"⏱ [脚本行#{cmd.line_num}] ClickEx L{lvl}{rem_str} 启动延迟 {delay}s...")
                            end_t = time.monotonic() + delay
                            while time.monotonic() < end_t and self.script_running:
                                if self.script_paused:
                                    p_start = time.monotonic()
                                    while self.script_running and self.script_paused:
                                        time.sleep(0.05)
                                    p_dur = time.monotonic() - p_start
                                    end_t += p_dur
                                    for tid in list(self.active_script_timers.keys()):
                                        self.active_script_timers[tid] += p_dur
                                time.sleep(0.01)

                        if cnt <= 0:
                            cnt = 1

                        for c_idx in range(cnt):
                            if not self.script_running:
                                break
                            while self.script_running and self.script_paused:
                                time.sleep(0.05)
                            self.dispatch_click(x, y, hwnd)
                            self.log_msg(f"⚡ [脚本行#{cmd.line_num}] ClickEx L{lvl}{rem_str} 点击 ({x}, {y}) [{c_idx+1}/{cnt}]")
                            if c_idx < cnt - 1:
                                end_intv = time.monotonic() + interval
                                while time.monotonic() < end_intv and self.script_running:
                                    if self.script_paused:
                                        p_start = time.monotonic()
                                        while self.script_running and self.script_paused:
                                            time.sleep(0.05)
                                        p_dur = time.monotonic() - p_start
                                        end_intv += p_dur
                                        for tid in list(self.active_script_timers.keys()):
                                            self.active_script_timers[tid] += p_dur
                                    time.sleep(0.01)

                elif ctype == "INPUT_TEXT":
                    txt_expr = params.get("text_expr", params.get("text", ""))
                    txt = str(safe_eval_expr(str(txt_expr), self.script_variables)).strip("\"'")
                    self.log_msg(f"⌨️ [脚本行#{cmd.line_num}] 输入文本: \"{txt}\"")
                    self.execute_macro_input(txt)

                elif ctype == "LOOP_START":
                    if "count_expr" in params:
                        try:
                            cnt = int(safe_eval_expr(str(params["count_expr"]), self.script_variables))
                        except Exception:
                            cnt = params.get("count", 1)
                    else:
                        cnt = params.get("count", 1)

                    if pc not in loop_counters:
                        loop_counters[pc] = cnt

                    if loop_counters[pc] > 0:
                        self.log_msg(f"🔄 [脚本行#{cmd.line_num}] 进入循环区间 (剩余 {loop_counters[pc]} 次)")
                    else:
                        if pc in loop_pairs:
                            pc = loop_pairs[pc]
                            if loop_pairs[pc] in loop_counters:
                                del loop_counters[loop_pairs[pc]]
                            pc += 1
                            continue

                elif ctype in ["BLOCK_END", "LOOP_END"]:
                    # 1. 检查是否为循环块末尾
                    if pc in loop_pairs and loop_pairs[pc] < pc:
                        start_idx = loop_pairs[pc]
                        if start_idx in loop_counters:
                            loop_counters[start_idx] -= 1
                            if loop_counters[start_idx] > 0:
                                pc = start_idx + 1
                                continue
                            else:
                                del loop_counters[start_idx]
                    # 2. 检查是否为 IF 块末尾（且存在 ELSE 分支，执行完 IF 后跳过 ELSE 块）
                    if pc in if_branch_end_jump:
                        pc = if_branch_end_jump[pc]
                        continue

                pc += 1

            self.script_running = False
            self.script_paused = False
            self.script_start_time = None
            self.active_script_timers.clear()
            self.root.after(0, self.update_script_ui_states)
            self.log_msg("⏹ [脚本宏] 脚本运行已结束。")

        self.script_thread = threading.Thread(target=macro_loop, daemon=True)
        self.script_thread.start()

    def collect_click_ex_block_with_flow(self, commands, start_pc):
        """从 start_pc 开始，智能跨越 IF/ELSE 条件分支，提取出当前激活生效的 ClickEx 级联集合，并返回 (resolved_block, next_pc)"""
        n = len(commands)
        resolved_block = []

        block_stack = []
        if_jump = {}
        if_branch_end_jump = {}

        for i in range(start_pc, n):
            cmd = commands[i]
            ctype = cmd.cmd_type
            if ctype == "IF_START":
                block_stack.append(("IF", i))
            elif ctype == "ELSE":
                if block_stack and block_stack[-1][0] == "IF_CLOSED":
                    entry = block_stack.pop()
                    if_idx, if_end_pc = entry[1], entry[2]
                    if_jump[if_idx] = i + 1
                    block_stack.append(("ELSE", i, if_idx, if_end_pc))
                elif block_stack and block_stack[-1][0] == "IF":
                    entry = block_stack.pop()
                    if_idx = entry[1]
                    if_jump[if_idx] = i + 1
                    block_stack.append(("ELSE", i, if_idx, i))
            elif ctype in ["BLOCK_END", "LOOP_END"]:
                if block_stack:
                    entry = block_stack.pop()
                    b_type = entry[0]
                    if b_type == "IF":
                        if_idx = entry[1]
                        if_jump[if_idx] = i + 1
                        block_stack.append(("IF_CLOSED", if_idx, i))
                    elif b_type == "ELSE":
                        else_idx, if_idx, if_end_pc = entry[1], entry[2], entry[3]
                        if_branch_end_jump[if_end_pc] = i + 1

        pc = start_pc
        while pc < n:
            cmd = commands[pc]
            ctype = cmd.cmd_type
            if ctype == "CLICK_EX":
                eval_p = dict(cmd.params)
                for f_name, typ, def_v in [
                    ("level", int, 0),
                    ("x", int, 0),
                    ("y", int, 0),
                    ("delay", float, 0.0),
                    ("interval", float, 0.5),
                    ("count", int, 1),
                    ("timer_id", int, 0)
                ]:
                    expr_k = f"{f_name}_expr"
                    if expr_k in cmd.params:
                        try:
                            eval_p[f_name] = typ(safe_eval_expr(str(cmd.params[expr_k]), self.script_variables))
                        except Exception:
                            eval_p[f_name] = def_v
                if "remark_expr" in cmd.params:
                    try:
                        eval_p["remark"] = str(safe_eval_expr(str(cmd.params["remark_expr"]), self.script_variables)).strip("\"'")
                    except Exception:
                        pass
                resolved_block.append(MacroCommand("CLICK_EX", eval_p, cmd.line_num, cmd.raw_text))
                pc += 1
            elif ctype == "COMMENT":
                pc += 1
            elif ctype == "VAR_ASSIGN":
                val = safe_eval_expr(cmd.params["expr"], self.script_variables)
                self.script_variables[cmd.params["name"]] = val
                pc += 1
            elif ctype == "IF_START":
                cond_res = safe_eval_cond(cmd.params["condition"], self.script_variables)
                cond_desc = "真 (纳入分支)" if cond_res else "假 (跳过分支)"
                self.log_msg(f"🔀 [脚本行#{cmd.line_num}] 级联条件判断 If ({cmd.params['condition']}) -> {cond_desc}")
                if not cond_res:
                    pc = if_jump.get(pc, pc + 1)
                else:
                    pc += 1
            elif ctype == "BLOCK_END":
                if pc in if_branch_end_jump:
                    pc = if_branch_end_jump[pc]
                else:
                    pc += 1
            elif ctype == "ELSE":
                pc += 1
            else:
                # 遇到其它动作指令（如常规 Click, Delay, Drag），说明 ClickEx 树状结构结束
                break

        return resolved_block, pc

    def execute_click_ex_hierarchy_block(self, block_cmds):
        """运行 ClickEx 多级点位集合的双 Timer 级联调度引擎"""
        num_b = len(block_cmds)
        parents = [None] * num_b
        children = {i: [] for i in range(num_b)}

        for i in range(num_b):
            lvl = block_cmds[i].params["level"]
            parent_idx = None
            if lvl > 0:
                for prev in range(i - 1, -1, -1):
                    if block_cmds[prev].params["level"] == lvl - 1:
                        parent_idx = prev
                        break
            parents[i] = parent_idx
            if parent_idx is not None:
                children[parent_idx].append(i)

        def get_all_descendants(root_idx):
            desc = []
            stack = list(children[root_idx])
            while stack:
                curr = stack.pop()
                desc.append(curr)
                stack.extend(children[curr])
            return desc

        next_l0_cycle_times = [0.0] * num_b
        next_periodic_times = [0.0] * num_b
        active_state = [False] * num_b
        executed_counts = [0] * num_b
        scheduled_resets = []

        start_t = time.monotonic()
        for i in range(num_b):
            if parents[i] is None:
                if block_cmds[i].params["level"] == 0:
                    next_l0_cycle_times[i] = start_t
                else:
                    delay = max(0.0, block_cmds[i].params["delay"])
                    scheduled_resets.append((start_t + delay, i))
                    rem = block_cmds[i].params["remark"]
                    rem_str = f" ({rem})" if rem else ""
                    lvl = block_cmds[i].params["level"]
                    self.log_msg(f" ⏱ [ClickEx 排期] #{i+1}{rem_str} (L{lvl}, 上级视作为真) 将在 {delay} 秒后触发...")

        mode = self.mode_var.get()
        hwnd = self.target_hwnd_var.get()
        is_adb = self.adb_enabled_var.get()

        while self.script_running:
            if self.script_paused:
                p_start = time.monotonic()
                while self.script_running and self.script_paused:
                    time.sleep(0.05)
                p_dur = time.monotonic() - p_start
                if p_dur > 0:
                    for k in range(num_b):
                        next_l0_cycle_times[k] += p_dur
                        next_periodic_times[k] += p_dur
                    scheduled_resets = [(t + p_dur, c_idx) for (t, c_idx) in scheduled_resets]
                    for tid in list(self.active_script_timers.keys()):
                        self.active_script_timers[tid] += p_dur

            now = time.monotonic()

            for i in range(num_b):
                p = block_cmds[i].params
                if parents[i] is not None or p["level"] != 0:
                    continue
                interval = max(0.1, p["interval"])
                if now >= next_l0_cycle_times[i]:
                    next_l0_cycle_times[i] = now + interval
                    executed_counts[i] = 0
                    max_cnt = p["count"]
                    rem = p["remark"]
                    rem_str = f" ({rem})" if rem else ""
                    if p.get("timer_id"):
                        self.active_script_timers[p["timer_id"]] = now

                    if max_cnt <= 0 or executed_counts[i] < max_cnt:
                        self.dispatch_click(p["x"], p["y"], hwnd)
                        executed_counts[i] += 1
                        self.log_msg(f"▶ [ClickEx L0] 触发 #{i+1}{rem_str} (周期 {interval}s)")

                    # 当 L0 开启新周期时，递归停止并重置名下所有子孙节点的周期状态及排期（防止前一周期的无限点击干扰）
                    for d_idx in get_all_descendants(i):
                        active_state[d_idx] = False
                        executed_counts[d_idx] = 0
                        for item in scheduled_resets[:]:
                            if item[1] == d_idx:
                                scheduled_resets.remove(item)

                    for c_idx in children[i]:
                        delay = max(0.0, block_cmds[c_idx].params["delay"])
                        scheduled_resets.append((now + delay, c_idx))
                        c_rem = block_cmds[c_idx].params["remark"]
                        c_rem_str = f" ({c_rem})" if c_rem else ""
                        self.log_msg(f" ⏱ [ClickEx 排期] #{c_idx+1}{c_rem_str} 将在 {delay} 秒后触发...")

            executed_resets = []
            for item in scheduled_resets[:]:
                reset_t, c_idx = item
                if now >= reset_t:
                    p = block_cmds[c_idx].params
                    active_state[c_idx] = True
                    executed_counts[c_idx] = 0
                    max_cnt = p["count"]
                    rem = p["remark"]
                    rem_str = f" ({rem})" if rem else ""
                    lvl = p["level"]

                    if max_cnt <= 0 or executed_counts[c_idx] < max_cnt:
                        self.dispatch_click(p["x"], p["y"], hwnd)
                        executed_counts[c_idx] += 1
                        if p.get("timer_id"):
                            self.active_script_timers[p["timer_id"]] = now
                        self.log_msg(f" ⚡ [ClickEx 挂载] #{c_idx+1}{rem_str} (L{lvl})")

                    c_interval = max(0.1, p["interval"])
                    next_periodic_times[c_idx] = now + c_interval

                    # 当子节点被触发时，递归停止并重置名下所有更深层孙节点的周期状态及排期
                    for sd_idx in get_all_descendants(c_idx):
                        active_state[sd_idx] = False
                        executed_counts[sd_idx] = 0
                        for old_item in scheduled_resets[:]:
                            if old_item[1] == sd_idx:
                                scheduled_resets.remove(old_item)

                    for gc_idx in children[c_idx]:
                        gc_delay = max(0.0, block_cmds[gc_idx].params["delay"])
                        scheduled_resets.append((now + gc_delay, gc_idx))

                    executed_resets.append(item)

            for item in executed_resets:
                if item in scheduled_resets:
                    scheduled_resets.remove(item)

            for i in range(num_b):
                p = block_cmds[i].params
                if active_state[i] and now >= next_periodic_times[i]:
                    interval = max(0.1, p["interval"])
                    max_cnt = p["count"]
                    if max_cnt <= 0 or executed_counts[i] < max_cnt:
                        self.dispatch_click(p["x"], p["y"], hwnd)
                        executed_counts[i] += 1
                        rem = p["remark"]
                        rem_str = f" ({rem})" if rem else ""
                        self.log_msg(f" ⚡ [ClickEx 周期] #{i+1}{rem_str} (L{p['level']})")
                        next_periodic_times[i] = now + interval
                    else:
                        active_state[i] = False

            root_nodes_finished = all(
                block_cmds[i].params["count"] > 0 and executed_counts[i] >= block_cmds[i].params["count"]
                for i in range(num_b) if parents[i] is None
            )
            children_finished = not scheduled_resets and not any(active_state)
            if root_nodes_finished and children_finished:
                self.log_msg(f"⚡ [ClickEx 级联组] 多级 Timer 调度集合已本轮执行完成，继续执行后续脚本指令...")
                break

            time.sleep(0.02)

    def import_json_config_to_script(self):
        """将 10 组点位方案或选择的 JSON 方案一键导入转写为 ClickEx 脚本代码"""
        res = messagebox.askyesnocancel("导入方案", "选择导入来源：\n\n[是]：导入当前主界面已配置的 10 组点位方案\n[否]：选择外部 .json 文件导入\n[取消]：取消操作")
        points_data = []

        if res is True:
            for i in range(NUM_POINTS):
                p_vars = self.point_vars[i]
                if p_vars["enabled"].get():
                    points_data.append({
                        "id": i + 1,
                        "enabled": True,
                        "level": p_vars["level"].get(),
                        "remark": p_vars["remark"].get(),
                        "x": p_vars["x"].get(),
                        "y": p_vars["y"].get(),
                        "delay": p_vars["delay"].get(),
                        "interval": p_vars["interval"].get(),
                        "count": p_vars["count"].get(),
                    })
        elif res is False:
            filepath = filedialog.askopenfilename(
                title="选择 JSON 配置方案文件",
                initialdir=os.path.dirname(self.current_config_file),
                filetypes=[("JSON 配置文件", "*.json"), ("所有文件", "*.*")],
            )
            if filepath and os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                        points_data = cfg.get("points", [])
                except Exception as e:
                    messagebox.showerror("错误", f"读取配置文件失败: {e}")
                    return
            else:
                return
        else:
            return

        if not points_data:
            messagebox.showinfo("提示", "未找到开启的点位配置！")
            return

        lines = ["// ==================== 一键转换导入的 10组级联 Timer 点位方案 ===================="]
        for p in points_data:
            if not p.get("enabled", True):
                continue
            lvl = int(p.get("level", 0))
            x = int(p.get("x", 0))
            y = int(p.get("y", 0))
            delay = float(p.get("delay", 0.0))
            interval = float(p.get("interval", 0.5))
            count = int(p.get("count", 1))
            remark = (p.get("remark") or "").strip()

            indent = "    " * lvl
            line = f'{indent}ClickEx({lvl}, {x}, {y}, {delay:.1f}, {interval:.1f}, {count}, "{remark}")'
            lines.append(line)

        lines.append("// ====================================================================\n")
        code = "\n".join(lines)
        self.insert_script_snippet(code)
        self.log_msg(f"✅ 已将 {len(points_data)} 组多级点位成功导入为 ClickEx 代码！")

    def stop_macro_script(self):
        """停止按键脚本宏运行与录制"""
        self.script_running = False
        self.script_paused = False
        self.script_start_time = None
        if hasattr(self, "active_script_timers"):
            self.active_script_timers.clear()
        if self.is_recording:
            self.toggle_script_recording()
        self.root.after(0, self.update_script_ui_states)
        self.log_msg("⏹ [脚本宏] 已发送中断信号，停止脚本运行。")

    def toggle_script_recording(self):
        """切换目标窗口操作录制器 (开始 / 停止录制)"""
        if not self.is_recording:
            hwnd = self.target_hwnd_var.get()
            if not hwnd or not win32gui.IsWindow(hwnd):
                messagebox.showwarning("提示", "录制前请先锁定选择有效的目标模拟器窗口！")
                return

            self.is_recording = True
            self.btn_record_script.config(text="⏹ 停止录制 (Recording...)", bg="#e74c3c")
            self.log_msg("🔴 [脚本录制器] 已启动操作录制！请在模拟器窗口内进行点击、拖拽等操作...")

            def record_loop():
                last_time = time.monotonic()
                is_down = False
                down_time = 0
                down_pt = (0, 0)

                while self.is_recording:
                    time.sleep(0.015)
                    btn_state = win32api.GetAsyncKeyState(win32con.VK_LBUTTON)
                    currently_down = (btn_state & 0x8000) != 0

                    hwnd_target = self.target_hwnd_var.get()
                    if hwnd_target and win32gui.IsWindow(hwnd_target):
                        render_hwnd, _, _, _, _ = self.get_emulator_render_info(hwnd_target)
                    else:
                        render_hwnd = 0

                    if currently_down and not is_down:
                        is_down = True
                        down_time = time.monotonic()
                        down_pt = win32api.GetCursorPos()

                        idle_ms = int((down_time - last_time) * 1000)
                        if idle_ms >= 200:
                            self.root.after(0, lambda ms=idle_ms: self.insert_script_snippet(f"Delay({ms})\n"))

                    elif not currently_down and is_down:
                        is_down = False
                        up_time = time.monotonic()
                        up_pt = win32api.GetCursorPos()
                        dur_ms = max(50, int((up_time - down_time) * 1000))

                        if render_hwnd and win32gui.IsWindow(render_hwnd):
                            try:
                                r_pt1 = win32gui.ScreenToClient(render_hwnd, down_pt)
                                r_pt2 = win32gui.ScreenToClient(render_hwnd, up_pt)
                                rx1, ry1 = max(0, r_pt1[0]), max(0, r_pt1[1])
                                rx2, ry2 = max(0, r_pt2[0]), max(0, r_pt2[1])
                            except Exception:
                                rx1, ry1 = down_pt[0], down_pt[1]
                                rx2, ry2 = up_pt[0], up_pt[1]
                        else:
                            rx1, ry1 = down_pt[0], down_pt[1]
                            rx2, ry2 = up_pt[0], up_pt[1]

                        import math
                        dist = math.hypot(up_pt[0] - down_pt[0], up_pt[1] - down_pt[1])
                        if dist < 8:
                            self.root.after(0, lambda x=rx1, y=ry1: self.insert_script_snippet(f"Click({x}, {y})\n"))
                        else:
                            self.root.after(0, lambda x1=rx1, y1=ry1, x2=rx2, y2=ry2, d=dur_ms: self.insert_script_snippet(f"Drag({x1}, {y1}, {x2}, {y2}, {d})\n"))

                        last_time = up_time

            self.record_thread = threading.Thread(target=record_loop, daemon=True)
            self.record_thread.start()
        else:
            self.is_recording = False
            self.btn_record_script.config(text="🔴 开始录制 (Ctrl+Alt+R)", bg="#8e44ad")
            self.log_msg("⏹ [脚本录制器] 已结束操作录制，脚本已自动生成至编辑器中！")

    def insert_script_snippet(self, snippet_text):
        """向当前活动的脚本编辑器插入代码片段"""
        active_ed = self._get_active_editor()
        if active_ed:
            active_ed.insert(tk.INSERT, snippet_text)
            active_ed.see(tk.INSERT)
            self.mark_script_dirty()
            self.trigger_syntax_highlight(active_ed)

    def pick_script_coordinate(self):
        """倒计时 2 秒拾取屏幕/模拟器坐标并自动填入当前脚本编辑器中"""
        self.log_msg("🎯 请在 2 秒内将鼠标放置到目标位置以获取坐标...")

        def do_pick():
            time.sleep(2)
            screen_x, screen_y = pyautogui.position()
            mode = self.mode_var.get()
            hwnd = self.target_hwnd_var.get()

            if mode == "background" and hwnd and win32gui.IsWindow(hwnd):
                try:
                    render_hwnd, _, _, _, _ = self.get_emulator_render_info(hwnd)
                    final_x, final_y = win32gui.ScreenToClient(render_hwnd, (screen_x, screen_y))
                except Exception:
                    final_x, final_y = screen_x, screen_y
            else:
                final_x, final_y = screen_x, screen_y

            self.root.after(0, lambda: self._insert_picked_coord(final_x, final_y))

        threading.Thread(target=do_pick, daemon=True).start()

    def _insert_picked_coord(self, x, y):
        """将拾取到的坐标 (x, y) 智能插入当前脚本编辑器中"""
        active_ed = self._get_active_editor()
        if not active_ed:
            return

        try:
            line_text = active_ed.get("insert linestart", "insert lineend").strip()
            if not line_text:
                snippet = f"Click({x}, {y})\n"
            else:
                snippet = f"{x}, {y}"
        except Exception:
            snippet = f"{x}, {y}"

        self.insert_script_snippet(snippet)
        self.log_msg(f"🎯 成功拾取坐标并填入脚本编辑器: ({x}, {y})")

    def refresh_scripts_list(self):
        """刷新 scripts/ 目录下的按键脚本列表下拉框"""
        if not os.path.exists(self.scripts_dir):
            os.makedirs(self.scripts_dir, exist_ok=True)

        files = [f for f in os.listdir(self.scripts_dir) if f.endswith(".kms") or f.endswith(".txt")]
        files.sort()

        if hasattr(self, "script_cb"):
            self.script_cb["values"] = files
            if files and not self.script_file_var.get():
                self.script_file_var.set(files[0])
                self.load_script_content(os.path.join(self.scripts_dir, files[0]))

    def check_save_script_changes(self):
        """如果当前脚本宏代码有未保存修改，询问用户是否保存"""
        if self.is_dirty_script:
            script_name = os.path.basename(self.current_script_file) if self.current_script_file else "未命名脚本.kms"
            res = messagebox.askyesnocancel("保存确认", f"当前脚本代码 [{script_name}] 存在未保存的修改！\n\n是否在切换/加载前保存修改？")
            if res is True:
                return self.save_script_file()
            elif res is False:
                return True
            else:
                return False
        return True

    def on_script_selected(self, event):
        sel_name = self.script_file_var.get().strip()
        if sel_name:
            full_p = os.path.join(self.scripts_dir, sel_name)
            if os.path.exists(full_p) and full_p != self.current_script_file:
                if not self.check_save_script_changes():
                    return
                self.load_script_content(full_p)

    def load_script_content(self, filepath):
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                if hasattr(self, "script_editor"):
                    self.script_editor.delete("1.0", tk.END)
                    self.script_editor.insert("1.0", content)
                    self.apply_syntax_highlight(self.script_editor)
                if hasattr(self, "mini_script_display"):
                    self.mini_script_display.delete("1.0", tk.END)
                    self.mini_script_display.insert("1.0", content)
                    self.apply_syntax_highlight(self.mini_script_display)
                self.current_script_file = filepath
                self.script_file_var.set(os.path.basename(filepath))
                self.mark_script_clean()
                self.log_msg(f"已自动载入脚本文件: {os.path.basename(filepath)}")
            except Exception as e:
                self.log_msg(f"❌ 载入脚本文件失败: {e}")

    def open_script_file(self):
        if not self.check_save_script_changes():
            return
        filepath = filedialog.askopenfilename(
            title="选择按键脚本文件",
            initialdir=self.scripts_dir,
            filetypes=[("AutoClick 脚本 (*.kms)", "*.kms"), ("文本文件 (*.txt)", "*.txt"), ("所有文件", "*.*")],
        )
        if filepath:
            self.load_script_content(filepath)

    def save_script_file(self, target_file=None):
        if not target_file:
            if self.current_script_file:
                target_file = self.current_script_file
            else:
                target_file = os.path.join(self.scripts_dir, "default_macro.kms")

        active_ed = self._get_active_editor()
        if active_ed:
            content = active_ed.get("1.0", tk.END)
            try:
                with open(target_file, "w", encoding="utf-8") as f:
                    f.write(content)
                self.current_script_file = target_file
                self.script_file_var.set(os.path.basename(target_file))

                # 双向同步至另一个编辑器
                other_ed = getattr(self, "mini_script_display", None) if active_ed == getattr(self, "script_editor", None) else getattr(self, "script_editor", None)
                if other_ed and other_ed != active_ed:
                    other_ed.delete("1.0", tk.END)
                    other_ed.insert("1.0", content)
                    self.apply_syntax_highlight(other_ed)
                self.apply_syntax_highlight(active_ed)

                self.refresh_scripts_list()
                self.mark_script_clean()
                self.log_msg(f"按键脚本已成功保存至: {os.path.basename(target_file)}")
                return True
            except Exception as e:
                messagebox.showerror("错误", f"保存脚本文件失败: {e}")
                return False
        return False

    def save_script_as(self):
        filepath = filedialog.asksaveasfilename(
            title="另存为按键脚本",
            initialdir=self.scripts_dir,
            initialfile="my_script.kms",
            defaultextension=".kms",
            filetypes=[("AutoClick 脚本 (*.kms)", "*.kms"), ("所有文件", "*.*")],
        )
        if filepath:
            self.save_script_file(target_file=filepath)

    def set_all_enabled(self, enabled):
        for p_vars in self.point_vars:
            p_vars["enabled"].set(enabled)
        self.mark_dirty()

    def register_global_hotkeys(self):
        """注册/更新全局快捷键"""
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

        try:
            keyboard.add_hotkey("ctrl+shift+s", self.start_clicking)
            keyboard.add_hotkey("ctrl+shift+q", self.stop_clicking)
            keyboard.add_hotkey("ctrl+shift+r", self.start_macro_script)
            keyboard.add_hotkey("ctrl+shift+f", lambda: self.start_macro_script(start_from_current_line=True))
            keyboard.add_hotkey("ctrl+shift+p", self.toggle_pause_macro_script)
            keyboard.add_hotkey("ctrl+shift+e", self.stop_macro_script)
            keyboard.add_hotkey("ctrl+alt+r", self.toggle_script_recording)
        except Exception as e:
            print(f"热键绑定失败: {e}")

        for i in range(NUM_POINTS):
            hk = self.point_vars[i]["hotkey"].get().strip().lower()
            if hk:
                try:
                    keyboard.add_hotkey(hk, lambda idx=i: self.record_current_position(idx))
                except Exception:
                    pass

        self.mark_dirty()

    def auto_click_loop(self):
        """支持点击次数限制与双 Timer 级联调度的自动点击主循环线程"""
        next_l0_cycle_times = [0.0] * NUM_POINTS
        next_periodic_times = [0.0] * NUM_POINTS
        active_state = [False] * NUM_POINTS
        executed_counts = [0] * NUM_POINTS  # 当前 Timer 周期内已执行点击次数
        scheduled_resets = []  # [(timer_zero_timestamp, child_idx)]

        start_time = time.monotonic()

        # 初始化 Level 0 节点
        for i in range(NUM_POINTS):
            if self.point_vars[i]["level"].get() == 0 and self.point_vars[i]["enabled"].get():
                next_l0_cycle_times[i] = start_time

        while True:
            with self.state_lock:
                if not self.clicking:
                    break

            now = time.monotonic()
            mode = self.mode_var.get()
            hwnd = self.target_hwnd_var.get()

            # 解析当前父子层级结构
            parents, children = self.resolve_hierarchy()

            def get_all_descendants(root_idx):
                desc = []
                stack = list(children[root_idx])
                while stack:
                    curr = stack.pop()
                    desc.append(curr)
                    stack.extend(children[curr])
                return desc

            # 1. 检查 Level 0 主节点的周期触发
            for i in range(NUM_POINTS):
                p_vars = self.point_vars[i]
                if not p_vars["enabled"].get() or p_vars["level"].get() != 0:
                    continue

                try:
                    interval = float(p_vars["interval"].get())
                except ValueError:
                    interval = 0.5
                if interval <= 0:
                    interval = 0.1

                if now >= next_l0_cycle_times[i]:
                    # L0 主节点进入下一周期，重置计数器
                    next_l0_cycle_times[i] = now + interval
                    executed_counts[i] = 0

                    try:
                        max_cnt = int(p_vars["count"].get())
                    except ValueError:
                        max_cnt = 1

                    rem = p_vars["remark"].get().strip()
                    rem_str = f" ({rem})" if rem else ""

                    if max_cnt <= 0 or executed_counts[i] < max_cnt:
                        self.execute_click(i, mode, hwnd)
                        executed_counts[i] += 1
                        cnt_info = f" [{executed_counts[i]}/{max_cnt}次]" if max_cnt > 0 else ""
                        self.log_msg(f"▶ [L0主节点] 触发点位 #{i+1}{rem_str}{cnt_info} (周期 {interval}s)")

                    # 当 L0 开启新周期时，递归停止并重置名下所有子孙节点的周期状态及排期
                    for d_idx in get_all_descendants(i):
                        active_state[d_idx] = False
                        executed_counts[d_idx] = 0
                        for item in scheduled_resets[:]:
                            if item[1] == d_idx:
                                scheduled_resets.remove(item)

                    # 通知并为直属 L1 子节点排期 Timer 置 0
                    for child_idx in children[i]:
                        if self.point_vars[child_idx]["enabled"].get():
                            try:
                                delay = float(self.point_vars[child_idx]["delay"].get())
                            except ValueError:
                                delay = 0.0

                            scheduled_resets.append((now + max(0.0, delay), child_idx))
                            c_rem = self.point_vars[child_idx]["remark"].get().strip()
                            c_rem_str = f" ({c_rem})" if c_rem else ""
                            self.log_msg(f" ⏱ [排期挂载] 点位 #{child_idx+1}{c_rem_str} 将在 {delay} 秒后触发...")

            # 2. 处理挂载节点 (L1~L4) 的 Timer 置 0 启动排期
            executed_resets = []
            for item in scheduled_resets[:]:
                reset_time, child_idx = item
                if now >= reset_time:
                    p_vars = self.point_vars[child_idx]
                    if p_vars["enabled"].get():
                        # 该子节点 Timer 置 0，重置已被执行点击次数！
                        active_state[child_idx] = True
                        executed_counts[child_idx] = 0

                        try:
                            max_cnt = int(p_vars["count"].get())
                        except ValueError:
                            max_cnt = 1

                        rem = p_vars["remark"].get().strip()
                        rem_str = f" ({rem})" if rem else ""
                        lvl = p_vars["level"].get()

                        if max_cnt <= 0 or executed_counts[child_idx] < max_cnt:
                            self.execute_click(child_idx, mode, hwnd)
                            executed_counts[child_idx] += 1
                            cnt_info = f" [{executed_counts[child_idx]}/{max_cnt}次]" if max_cnt > 0 else ""
                            self.log_msg(f" ⚡ [挂载触发] 点位 #{child_idx+1}{rem_str} (L{lvl}){cnt_info}")

                        # 设置下一次周期点击时间
                        try:
                            c_interval = float(p_vars["interval"].get())
                        except ValueError:
                            c_interval = 0.5
                        if c_interval <= 0:
                            c_interval = 0.1

                        next_periodic_times[child_idx] = now + c_interval

                        # 当子节点被触发时，递归停止并重置名下所有更深层孙节点的周期状态及排期
                        for sd_idx in get_all_descendants(child_idx):
                            active_state[sd_idx] = False
                            executed_counts[sd_idx] = 0
                            for old_item in scheduled_resets[:]:
                                if old_item[1] == sd_idx:
                                    scheduled_resets.remove(old_item)

                        # 递归为直属 L+1 孙节点排期 Timer 置 0
                        for gc_idx in children[child_idx]:
                            if self.point_vars[gc_idx]["enabled"].get():
                                try:
                                    gc_delay = float(self.point_vars[gc_idx]["delay"].get())
                                except ValueError:
                                    gc_delay = 0.0

                                scheduled_resets.append((now + max(0.0, gc_delay), gc_idx))
                                gc_rem = self.point_vars[gc_idx]["remark"].get().strip()
                                gc_rem_str = f" ({gc_rem})" if gc_rem else ""
                                self.log_msg(f"   ⏱ [递归排期] 点位 #{gc_idx+1}{gc_rem_str} 将在 {gc_delay} 秒后触发...")

                    executed_resets.append(item)

            for item in executed_resets:
                if item in scheduled_resets:
                    scheduled_resets.remove(item)

            # 3. 检查激活中的节点在 Timer 置 0 后的后续周期点击 (受点击次数限制)
            for i in range(NUM_POINTS):
                p_vars = self.point_vars[i]
                if not p_vars["enabled"].get() or p_vars["level"].get() == 0:
                    continue

                if active_state[i] and now >= next_periodic_times[i]:
                    try:
                        interval = float(p_vars["interval"].get())
                    except ValueError:
                        interval = 0.5
                    if interval <= 0:
                        interval = 0.1

                    try:
                        max_cnt = int(p_vars["count"].get())
                    except ValueError:
                        max_cnt = 1

                    # 检查点击次数限制
                    if max_cnt <= 0 or executed_counts[i] < max_cnt:
                        self.execute_click(i, mode, hwnd)
                        executed_counts[i] += 1
                        rem = p_vars["remark"].get().strip()
                        rem_str = f" ({rem})" if rem else ""
                        lvl = p_vars["level"].get()
                        cnt_info = f" [{executed_counts[i]}/{max_cnt}次]" if max_cnt > 0 else ""
                        self.log_msg(f" ⚡ [周期重复] 点位 #{i+1}{rem_str} (L{lvl}){cnt_info}")

                        next_periodic_times[i] = now + interval
                    else:
                        # 已达限制，关闭该节点的周期重复标志
                        active_state[i] = False

            time.sleep(0.01)

    def start_clicking(self):
        # 强制进行 100% 目标一致性预飞核验
        if self.mode_var.get() == "background" or self.adb_enabled_var.get():
            is_valid, _, _, _ = self.verify_target_consistency(caller_name="自动点击运行")
            if not is_valid:
                return

        with self.state_lock:
            if self.clicking:
                return
            self.clicking = True
            self.click_start_time = time.monotonic()

        self.btn_start.config(state="disabled", bg="#7f8c8d")
        self.btn_stop.config(state="normal", bg="#e74c3c")
        if hasattr(self, "btn_mini_start"):
            self.btn_mini_start.config(state="disabled", bg="#7f8c8d")
            self.btn_mini_stop.config(state="normal", bg="#e74c3c")
        self.log_msg("▶▶ 自动点击引擎已启动 (多级级联与双Timer模式)")

        self.click_thread = threading.Thread(target=self.auto_click_loop, daemon=True)
        self.click_thread.start()

    def stop_clicking(self):
        with self.state_lock:
            if not self.clicking:
                return
            self.clicking = False
            self.click_start_time = None

        self.btn_start.config(state="normal", bg="#2ecc71")
        self.btn_stop.config(state="disabled", bg="#e74c3c")
        if hasattr(self, "btn_mini_start"):
            self.btn_mini_start.config(state="normal", bg="#2ecc71")
            self.btn_mini_stop.config(state="disabled", bg="#e74c3c")
        self.log_msg("⏹ 自动点击引擎已停止。")

    def save_config(self, target_file=None):
        """保存配置至当前或指定的 .json 方案文件"""
        if not target_file:
            target_file = self.current_config_file

        target_hwnd = self.target_hwnd_var.get()
        if target_hwnd and win32gui.IsWindow(target_hwnd):
            try:
                rect = win32gui.GetWindowRect(target_hwnd)
                w, h = rect[2] - rect[0], rect[3] - rect[1]
                if w > 100 and h > 100:
                    self.target_window_size = [w, h]
                _, cl_w, cl_h, _, _ = self.get_emulator_render_info(target_hwnd)
                if cl_w > 50 and cl_h > 50:
                    self.base_render_size = [cl_w, cl_h]
            except Exception:
                pass

        config = {
            "mode": self.mode_var.get(),
            "target_hwnd": self.target_hwnd_var.get(),
            "target_title": self.target_title_var.get(),
            "window_size": getattr(self, "target_window_size", [424, 901]),
            "base_render_size": getattr(self, "base_render_size", [390, 867]),
            "base_adb_resolution": getattr(self, "base_adb_resolution", [540, 1200]),
            "adb_enabled": self.adb_enabled_var.get(),
            "adb_device": self.adb_device_var.get(),
            "adb_custom_path": self.adb_custom_path_var.get(),
            "topmost": self.topmost_var.get(),
            "follow_target": self.follow_target_var.get(),
            "points": [],
        }

        for i in range(NUM_POINTS):
            p_vars = self.point_vars[i]
            config["points"].append({
                "id": i + 1,
                "enabled": p_vars["enabled"].get(),
                "level": p_vars["level"].get(),
                "remark": p_vars["remark"].get(),
                "x": p_vars["x"].get(),
                "y": p_vars["y"].get(),
                "delay": p_vars["delay"].get(),
                "interval": p_vars["interval"].get(),
                "count": p_vars["count"].get(),
                "hotkey": p_vars["hotkey"].get(),
            })

        try:
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            self.current_config_file = target_file
            save_last_used_config(target_file)
            self.lbl_cfg_file.config(text=os.path.basename(target_file))
            self.mark_clean()
            self.log_msg(f"配置方案已成功保存至: {os.path.basename(target_file)}")
            return True
        except Exception as e:
            messagebox.showerror("错误", f"保存配置文件失败: {e}")
            return False

    def save_config_as(self):
        """配置方案“另存为...”"""
        filepath = filedialog.asksaveasfilename(
            title="另存为配置方案",
            initialdir=os.path.dirname(self.current_config_file),
            initialfile="my_autoclick_config.json",
            defaultextension=".json",
            filetypes=[("JSON 配置文件", "*.json"), ("所有文件", "*.*")],
        )
        if filepath:
            self.save_config(target_file=filepath)

    def check_save_point_changes(self):
        """如果当前 10点位配置方案有未保存修改，询问用户是否保存"""
        if self.is_dirty_point:
            cfg_name = os.path.basename(self.current_config_file)
            res = messagebox.askyesnocancel("保存确认", f"点位模式配置方案 [{cfg_name}] 存在未保存的修改！\n\n是否在切换/加载前保存修改？")
            if res is True:
                return self.save_config()
            elif res is False:
                return True
            else:
                return False
        return True

    def open_config_file(self):
        """加载已有的配置文件方案"""
        if not self.check_save_point_changes():
            return

        filepath = filedialog.askopenfilename(
            title="加载配置方案文件",
            initialdir=os.path.dirname(self.current_config_file),
            filetypes=[("JSON 配置文件", "*.json"), ("所有文件", "*.*")],
        )
        if filepath:
            self.load_config(filepath)

    def load_config(self, filepath):
        """从指定的 .json 文件读取配置"""
        if not os.path.exists(filepath):
            self.update_hierarchy_ui()
            self.refresh_window_list()
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config = json.load(f)

            mode = config.get("mode", "foreground")
            self.mode_var.set(mode)
            self._last_mode = mode
            self.target_hwnd_var.set(config.get("target_hwnd", 0))
            self.target_title_var.set(config.get("target_title", ""))

            self.target_window_size = config.get("window_size", [424, 901])
            self.base_render_size = config.get("base_render_size", [390, 867])
            self.base_adb_resolution = config.get("base_adb_resolution", [540, 1200])

            self.adb_enabled_var.set(config.get("adb_enabled", False))
            self.adb_device_var.set(config.get("adb_device", ""))
            self.adb_custom_path_var.set(config.get("adb_custom_path", ""))
            if self.adb_enabled_var.get():
                self.refresh_adb_devices()

            self.topmost_var.set(config.get("topmost", False))
            self.follow_target_var.set(config.get("follow_target", True))
            self.apply_topmost_ui()
            self.apply_follow_target_ui()

            points_data = config.get("points", [])
            for i in range(min(NUM_POINTS, len(points_data))):
                p_data = points_data[i]
                p_vars = self.point_vars[i]
                p_vars["enabled"].set(p_data.get("enabled", False))
                p_vars["level"].set(p_data.get("level", 0))
                p_vars["remark"].set(p_data.get("remark", ""))
                p_vars["x"].set(str(p_data.get("x", "0")))
                p_vars["y"].set(str(p_data.get("y", "0")))
                p_vars["delay"].set(str(p_data.get("delay", "0.0")))
                p_vars["interval"].set(str(p_data.get("interval", "0.5")))
                p_vars["count"].set(str(p_data.get("count", "1")))
                p_vars["hotkey"].set(p_data.get("hotkey", DEFAULT_HOTKEYS[i]))

            self.current_config_file = filepath
            save_last_used_config(filepath)
            self.lbl_cfg_file.config(text=os.path.basename(filepath))
            self.update_hierarchy_ui()
            self.refresh_window_list()
            self.mark_point_clean()
            self.log_msg(f"成功加载配置方案: {os.path.basename(filepath)}")
        except Exception as e:
            messagebox.showerror("错误", f"加载配置文件出错: {e}")
            self.update_hierarchy_ui()
            self.refresh_window_list()

    def on_closing(self):
        """退出程序前的保存询问机制（分别针对 10点位配置模式 与 脚本宏模式 独立提问检测）"""
        # 1. 检查 10点位配置方案 (Point Mode)
        if self.is_dirty_point:
            cfg_name = os.path.basename(self.current_config_file)
            ans = messagebox.askyesnocancel("退出确认 (Point Mode)", f"点位模式配置方案 [{cfg_name}] 存在未保存的修改！\n\n是否在退出前保存该配置方案？")
            if ans is True:
                if not self.save_config():
                    return  # 保存失败或取消另存，放弃退出
            elif ans is None:
                return  # 用户选择“取消”，中止退出流程

        # 2. 检查 脚本宏模式代码 (Script Mode)
        if self.is_dirty_script:
            script_name = os.path.basename(self.current_script_file) if self.current_script_file else "未命名脚本.kms"
            ans = messagebox.askyesnocancel("退出确认 (Script Mode)", f"脚本宏代码文件 [{script_name}] 存在未保存的修改！\n\n是否在退出前保存该脚本？")
            if ans is True:
                if not self.save_script_file():
                    return  # 保存失败或取消另存，放弃退出
            elif ans is None:
                return  # 用户选择“取消”，中止退出流程

        self.stop_clicking()
        try:
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    app = AutoClickerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
