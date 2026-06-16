#!/usr/bin/env python3
import sys
import os
import json
import time
import hmac
import base64
import hashlib
import argparse
import tempfile
import subprocess
import threading
import urllib.request
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# GUI imports with fallback
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    import webbrowser
    HAS_GUI = True
except ImportError:
    HAS_GUI = False

# JWT helper methods
def base64url_decode(payload):
    rem = len(payload) % 4
    if rem > 0:
        payload += "=" * (4 - rem)
    return base64.urlsafe_b64decode(payload)

def verify_jwt(token, secret):
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False, "Invalid token format"
        header_b64, payload_b64, signature_b64 = parts
        
        signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
        expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        expected_sig_b64 = base64.urlsafe_b64encode(expected_sig).replace(b"=", b"").decode("utf-8")
        
        if not hmac.compare_digest(signature_b64, expected_sig_b64):
            return False, "Signature verification failed"
            
        payload_data = json.loads(base64url_decode(payload_b64).decode("utf-8"))
        
        # Check expiration
        exp = payload_data.get("exp")
        if exp and exp < time.time():
            return False, "Token expired"
            
        return True, payload_data
    except Exception as e:
        return False, str(e)

# Default configuration file path
CONFIG_FILE = "config.json"

def load_config():
    default_config = {
        "host": "127.0.0.1",
        "port": 8008,
        "secret": "change-this-secret",
        "main_app_url": "http://127.0.0.1:15001",
        "username": "admin",
        "password": "admin123",
        "server_id": None
    }
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            print(f"Created default configuration file: {CONFIG_FILE}")
        except Exception as e:
            print(f"Warning: Could not create default config file: {e}")
        return default_config
        
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        for k, v in default_config.items():
            if k not in config:
                config[k] = v
        return config
    except Exception as e:
        print(f"Error reading configuration file {CONFIG_FILE}: {e}. Using defaults.")
        return default_config

# HTTP Request helper using standard library
def api_request(url, method="GET", payload=None, token=None):
    try:
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Accept", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
        
        with urllib.request.urlopen(req, data=data, timeout=5) as response:
            res_data = response.read().decode("utf-8")
            if res_data:
                return response.status, json.loads(res_data)
            return response.status, None
    except urllib.error.HTTPError as e:
        try:
            err_data = e.read().decode("utf-8")
            err_json = json.loads(err_data)
            detail = err_json.get("detail", str(e))
        except:
            detail = str(e)
        return e.code, {"error": detail}
    except Exception as e:
        return 0, {"error": str(e)}

# Execution helpers
def run_command_normal(command, shell="powershell"):
    try:
        if shell == "powershell":
            import base64
            encoded_cmd = base64.b64encode(command.encode('utf-16-le')).decode('ascii')
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded_cmd],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
        else:
            if os.name == 'nt':
                # Windows-specific: Pass command as a raw string wrapped in outer quotes to prevent CMD from stripping internal quotes
                result = subprocess.run(
                    f'cmd.exe /c "{command}"',
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
            else:
                result = subprocess.run(
                    ["cmd", "/c", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace"
                )
        return result.returncode, result.stdout, result.stderr
    except Exception as e:
        return 1, "", str(e)

def run_command_elevated(command, shell="powershell"):
    fd, temp_path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    try:
        if shell == "powershell":
            ps_cmd = f"& {{ {command} }} > '{temp_path}' 2>&1"
            args = f"-NoProfile -ExecutionPolicy Bypass -Command \"Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command {ps_cmd}' -Verb RunAs -Wait -WindowStyle Hidden\""
            subprocess.run(["powershell", args], capture_output=True, text=True, encoding="utf-8")
        else:
            args = f"-NoProfile -ExecutionPolicy Bypass -Command \"Start-Process cmd -ArgumentList '/c {command} > \"\"{temp_path}\"\" 2>&1' -Verb RunAs -Wait -WindowStyle Hidden\""
            subprocess.run(["powershell", args], capture_output=True, text=True, encoding="utf-8")
        
        time.sleep(0.5)
        output = ""
        if os.path.exists(temp_path):
            with open(temp_path, "r", encoding="utf-8", errors="replace") as f:
                output = f.read()
            os.remove(temp_path)
        return 0, output, ""
    except Exception as e:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass
        return 1, "", str(e)

class AgentRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stdout.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), format%args))

    def do_POST(self):
        if self.path != "/execute":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return
            
        # Verify JWT
        auth_header = self.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"detail": "Missing or invalid Authorization header"}).encode("utf-8"))
            return
            
        token = auth_header.split(" ")[1]
        is_valid, claims = verify_jwt(token, self.server.secret)
        if not is_valid:
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"detail": f"Access forbidden: {claims}"}).encode("utf-8"))
            return

        # Parse request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")
            return
            
        command = data.get("command")
        shell = data.get("shell", "powershell")
        run_as_admin = data.get("run_as_admin", False)
        
        if not command:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Missing command field")
            return

        # Execute command
        if run_as_admin:
            exit_code, stdout, stderr = run_command_elevated(command, shell)
        else:
            exit_code, stdout, stderr = run_command_normal(command, shell)
            
        # Return results
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        response = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr
        }
        self.wfile.write(json.dumps(response).encode("utf-8"))

# Scrollable Frame implementation for Service Cards
if HAS_GUI:
    class ScrollableFrame(tk.Frame):
        def __init__(self, container, *args, **kwargs):
            super().__init__(container, *args, **kwargs)
            self.canvas = tk.Canvas(self, bg=kwargs.get("bg", "#0f0f12"), bd=0, highlightthickness=0)
            self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
            self.scrollable_frame = tk.Frame(self.canvas, bg=kwargs.get("bg", "#0f0f12"))

            self.scrollable_frame.bind(
                "<Configure>",
                lambda e: self.canvas.configure(
                    scrollregion=self.canvas.bbox("all")
                )
            )

            self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
            
            # Stretch canvas to fill horizontal space
            self.canvas.bind('<Configure>', self._on_canvas_configure)
            self.canvas.configure(yscrollcommand=self.scrollbar.set)

            self.canvas.pack(side="left", fill="both", expand=True)
            self.scrollbar.pack(side="right", fill="y")
            
            # Mousewheel scrolling
            self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
            
        def _on_canvas_configure(self, event):
            self.canvas.itemconfig(self.canvas_window, width=event.width)
            
        def _on_mousewheel(self, event):
            if event.delta:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                if event.num == 4:
                    self.canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    self.canvas.yview_scroll(1, "units")

    # Custom Flat Hoverable Button
    class ModernButton(tk.Button):
        def __init__(self, parent, text, command, bg="#6366f1", fg="#f3f4f6", hover_bg="#4f46e5", active_bg="#4f46e5", **kwargs):
            font = kwargs.pop("font", ("Segoe UI", 10, "bold"))
            super().__init__(
                parent,
                text=text,
                command=command,
                bg=bg,
                fg=fg,
                activebackground=active_bg,
                activeforeground=fg,
                relief="flat",
                bd=0,
                cursor="hand2",
                font=font,
                padx=12,
                pady=6,
                **kwargs
            )
            self.bg = bg
            self.hover_bg = hover_bg
            self.bind("<Enter>", self.on_enter)
            self.bind("<Leave>", self.on_leave)
            
        def on_enter(self, event):
            if self["state"] != "disabled":
                self.configure(bg=self.hover_bg)
                
        def on_leave(self, event):
            if self["state"] != "disabled":
                self.configure(bg=self.bg)

    # Main GUI Class
    class AgentGUI:
        def __init__(self, root, config, server):
            self.root = root
            self.config = config
            self.server = server
            self._cached_token = None
            
            # Styling System (Dark Theme)
            self.BG_DARK = "#0f0f12"
            self.BG_CARD = "#18181f"
            self.BG_INPUT = "#24242d"
            self.FG_LIGHT = "#f3f4f6"
            self.FG_MUTED = "#9ca3af"
            self.ACCENT = "#6366f1"
            self.ACCENT_HOVER = "#4f46e5"
            self.COLOR_ONLINE = "#10b981"
            self.COLOR_OFFLINE = "#ef4444"
            self.COLOR_WARNING = "#f59e0b"
            self.BORDER_COLOR = "#2e2e38"
            
            self.root.title("Portal Console - Windows Agent")
            self.root.geometry("800x700")
            self.root.configure(bg=self.BG_DARK)
            self.root.minsize(750, 550)
            
            # Window Close Handler
            def on_close():
                try:
                    self.server.server_close()
                except:
                    pass
                self.root.destroy()
                sys.exit(0)
            self.root.protocol("WM_DELETE_WINDOW", on_close)
            
            # 1. Header Frame
            header_frame = tk.Frame(self.root, bg=self.BG_DARK, height=60)
            header_frame.pack(fill="x", side="top", padx=20, pady=(20, 5))
            
            # Title Badge & Info
            title_lbl = tk.Label(header_frame, text="PORTAL LOCAL HELPER", bg=self.BG_DARK, fg=self.ACCENT, font=("Segoe UI", 16, "bold"))
            title_lbl.pack(side="left")
            
            bind_info = f"http://{self.config['host']}:{self.config['port']}"
            info_lbl = tk.Label(header_frame, text=f"• Listening on {bind_info}", bg=self.BG_DARK, fg=self.FG_MUTED, font=("Segoe UI", 10))
            info_lbl.pack(side="left", padx=12, pady=(4, 0))
            
            # Open Portal Button
            open_btn = ModernButton(
                header_frame,
                text="Open Portal Console 🌐",
                command=self.open_portal_webpage,
                bg=self.BG_CARD,
                hover_bg=self.BORDER_COLOR
            )
            open_btn.pack(side="right")
            
            # 2. Navigation Tab Selector
            nav_frame = tk.Frame(self.root, bg=self.BG_DARK)
            nav_frame.pack(fill="x", side="top", padx=20, pady=5)
            
            self.btn_services_tab = tk.Button(
                nav_frame, text="Services", command=self.show_services_tab,
                bg=self.ACCENT, fg="#ffffff", font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=22, pady=8, cursor="hand2"
            )
            self.btn_services_tab.pack(side="left")
            
            self.btn_config_tab = tk.Button(
                nav_frame, text="Configuration", command=self.show_config_tab,
                bg=self.BG_CARD, fg=self.FG_MUTED, font=("Segoe UI", 10, "bold"), relief="flat", bd=0, padx=22, pady=8, cursor="hand2"
            )
            self.btn_config_tab.pack(side="left", padx=6)
            
            # Tab Divider
            divider = tk.Frame(self.root, bg=self.BORDER_COLOR, height=1)
            divider.pack(fill="x", padx=20, pady=(2, 10))
            
            # 3. Main Container Area
            self.main_container = tk.Frame(self.root, bg=self.BG_DARK)
            self.main_container.pack(fill="both", expand=True, padx=20, pady=5)
            
            # Create Tabs
            self.build_services_tab()
            self.build_config_tab()
            
            # Default tab
            self.show_services_tab()
            
            # Trigger initial fetch
            self.start_refresh_thread()

        def show_services_tab(self):
            self.btn_services_tab.configure(bg=self.ACCENT, fg="#ffffff")
            self.btn_config_tab.configure(bg=self.BG_CARD, fg=self.FG_MUTED)
            if hasattr(self, "config_tab_frame") and self.config_tab_frame:
                self.config_tab_frame.pack_forget()
            if hasattr(self, "services_tab_frame") and self.services_tab_frame:
                self.services_tab_frame.pack(fill="both", expand=True)

        def show_config_tab(self):
            self.btn_config_tab.configure(bg=self.ACCENT, fg="#ffffff")
            self.btn_services_tab.configure(bg=self.BG_CARD, fg=self.FG_MUTED)
            if hasattr(self, "services_tab_frame") and self.services_tab_frame:
                self.services_tab_frame.pack_forget()
            if hasattr(self, "config_tab_frame") and self.config_tab_frame:
                self.config_tab_frame.pack(fill="both", expand=True)

        # Tab 1: Services View
        def build_services_tab(self):
            self.services_tab_frame = tk.Frame(self.main_container, bg=self.BG_DARK)
            
            # Sub-header
            sub_header = tk.Frame(self.services_tab_frame, bg=self.BG_DARK)
            sub_header.pack(fill="x", side="top", pady=(0, 10))
            
            self.status_lbl = tk.Label(sub_header, text="Server status: Connected", bg=self.BG_DARK, fg=self.COLOR_ONLINE, font=("Segoe UI", 10, "bold"))
            self.status_lbl.pack(side="left", pady=5)
            
            self.refresh_btn = ModernButton(
                sub_header,
                text="Refresh List",
                command=self.start_refresh_thread,
                bg=self.BG_CARD,
                hover_bg=self.BORDER_COLOR,
                font=("Segoe UI", 9, "bold")
            )
            self.refresh_btn.pack(side="right")
            
            # Scrollable cards area
            self.scroll_frame = ScrollableFrame(self.services_tab_frame, bg=self.BG_DARK)
            self.scroll_frame.pack(fill="both", expand=True, pady=(0, 15))
            
            # Execution Logs Console at bottom
            console_frame = tk.Frame(
                self.services_tab_frame, 
                bg=self.BG_CARD, 
                bd=1, 
                relief="flat", 
                highlightbackground=self.BORDER_COLOR, 
                highlightcolor=self.BORDER_COLOR, 
                highlightthickness=1,
                height=180
            )
            console_frame.pack_propagate(False)
            console_frame.pack(fill="x", side="bottom")
            
            console_title = tk.Label(console_frame, text="Execution Logs & Console Output", bg=self.BG_CARD, fg=self.FG_LIGHT, font=("Segoe UI", 9, "bold"), anchor="w")
            console_title.pack(fill="x", padx=12, pady=6)
            
            # Scrollable Text Console
            text_scroll = tk.Scrollbar(console_frame)
            text_scroll.pack(side="right", fill="y")
            
            self.console_txt = tk.Text(console_frame, bg="#0b0b0e", fg="#a7f3d0", insertbackground="#f3f4f6", bd=0, font=("Consolas", 9), yscrollcommand=text_scroll.set)
            self.console_txt.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 12))
            text_scroll.config(command=self.console_txt.yview)
            self.console_txt.configure(state="disabled")

        # Tab 2: Configuration View
        def build_config_tab(self):
            self.config_tab_frame = tk.Frame(self.main_container, bg=self.BG_DARK)
            
            form_frame = tk.Frame(self.config_tab_frame, bg=self.BG_CARD, bd=1, relief="flat", highlightbackground=self.BORDER_COLOR, highlightcolor=self.BORDER_COLOR, highlightthickness=1)
            form_frame.pack(fill="both", expand=True, padx=5, pady=5)
            form_frame.columnconfigure(1, weight=1)
            
            fields = [
                ("Host (Bind Address):", "host", False),
                ("Port (Bind Port):", "port", False),
                ("JWT Shared Secret:", "secret", True),
                ("Portal Console URL:", "main_app_url", False),
                ("Portal Username:", "username", False),
                ("Portal Password:", "password", True),
                ("Server ID (Optional Filter):", "server_id", False),
            ]
            
            self.entries = {}
            for idx, (label_text, key, is_password) in enumerate(fields):
                lbl = tk.Label(form_frame, text=label_text, bg=self.BG_CARD, fg=self.FG_LIGHT, font=("Segoe UI", 10, "bold"), anchor="w")
                lbl.grid(row=idx, column=0, padx=20, pady=12, sticky="w")
                
                val = self.config.get(key)
                val_str = "" if val is None else str(val)
                
                entry_frame = tk.Frame(form_frame, bg=self.BG_CARD)
                entry_frame.grid(row=idx, column=1, padx=20, pady=12, sticky="ew")
                
                show_char = "*" if is_password else None
                entry = tk.Entry(entry_frame, bg=self.BG_INPUT, fg=self.FG_LIGHT, insertbackground=self.FG_LIGHT, relief="flat", bd=0, highlightbackground=self.BORDER_COLOR, highlightcolor=self.ACCENT, highlightthickness=1, font=("Segoe UI", 10), show=show_char)
                entry.insert(0, val_str)
                entry.pack(side="left", fill="x", expand=True)
                self.entries[key] = (entry, is_password)
                
                if is_password:
                    btn_show = tk.Button(
                        entry_frame, text="👁", bg=self.BG_CARD, fg=self.FG_MUTED, font=("Segoe UI", 10), relief="flat", bd=0, cursor="hand2", padx=5,
                        command=lambda e=entry: self.toggle_password_visibility(e)
                    )
                    btn_show.pack(side="right", padx=(6, 0))
                    
            btn_row = tk.Frame(self.config_tab_frame, bg=self.BG_DARK)
            btn_row.pack(pady=20)
            
            btn_cancel = ModernButton(
                btn_row,
                text="Cancel ✖",
                command=self.cancel_config_changes,
                bg=self.BG_CARD,
                hover_bg=self.BORDER_COLOR
            )
            btn_cancel.pack(side="left", padx=10)
            
            btn_save = ModernButton(
                btn_row,
                text="Save 💾",
                command=self.save_config_changes,
                bg=self.COLOR_ONLINE,
                hover_bg="#059669"
            )
            btn_save.pack(side="left", padx=10)
            
            btn_restart = ModernButton(
                btn_row,
                text="Restart 🔄",
                command=self.trigger_restart,
                bg=self.ACCENT,
                hover_bg=self.ACCENT_HOVER
            )
            btn_restart.pack(side="left", padx=10)

        def toggle_password_visibility(self, entry):
            if entry.cget("show") == "*":
                entry.configure(show="")
            else:
                entry.configure(show="*")

        def open_portal_webpage(self):
            main_url = self.config.get("main_app_url", "")
            if main_url:
                webbrowser.open(main_url)
            else:
                messagebox.showwarning("Warning", "Main App URL is not configured.")

        def log_message(self, msg):
            def append_log():
                self.console_txt.configure(state="normal")
                timestamp = time.strftime("[%Y-%m-%d %H:%M:%S] ")
                self.console_txt.insert("end", f"{timestamp}{msg}\n")
                self.console_txt.see("end")
                self.console_txt.configure(state="disabled")
            self.root.after(0, append_log)

        def get_auth_token(self):
            if self._cached_token:
                return self._cached_token
                
            main_url = self.config.get("main_app_url", "").rstrip("/")
            username = self.config.get("username", "")
            password = self.config.get("password", "")
            
            if not main_url or not username or not password:
                return None
                
            login_url = f"{main_url}/api/auth/login"
            login_payload = {"username": username, "password": password}
            
            status, res = api_request(login_url, "POST", login_payload)
            if status == 200 and isinstance(res, dict) and "access_token" in res:
                self._cached_token = res["access_token"]
                return self._cached_token
                
            return None

        # Fetch Projects Thread Management
        def start_refresh_thread(self):
            self.refresh_btn.configure(state="disabled", text="Refreshing...")
            threading.Thread(target=self.refresh_services_work, daemon=True).start()

        def refresh_services_work(self):
            detailed_projects = []
            error_msg = None
            try:
                token = self.get_auth_token()
                if not token:
                    error_msg = "Authentication failed. Validate username/password in Configuration tab."
                    self.root.after(0, self.update_services_ui, [], error_msg)
                    return
                    
                main_url = self.config.get("main_app_url", "").rstrip("/")
                server_id = self.config.get("server_id")
                
                projects_url = f"{main_url}/api/projects"
                if server_id:
                    projects_url += f"?server_id={server_id}"
                    
                status, projects = api_request(projects_url, "GET", token=token)
                if status != 200:
                    err_detail = projects.get("error", "HTTP error") if isinstance(projects, dict) else "HTTP error"
                    error_msg = f"Failed to list services: {err_detail} (HTTP {status})"
                    self.root.after(0, self.update_services_ui, [], error_msg)
                    return
                    
                # Load full details to fetch commands
                for proj in projects:
                    proj_id = proj["id"]
                    detail_url = f"{main_url}/api/projects/{proj_id}"
                    status_d, proj_detail = api_request(detail_url, "GET", token=token)
                    if status_d == 200:
                        detailed_projects.append(proj_detail)
                    else:
                        detailed_projects.append(proj)
                        
            except Exception as e:
                error_msg = f"Connection failed: {str(e)}"
                
            self.root.after(0, self.update_services_ui, detailed_projects, error_msg)

        def update_services_ui(self, detailed_projects, error_msg):
            self.refresh_btn.configure(state="normal", text="Refresh List")
            
            if error_msg:
                self.status_lbl.configure(text="Server status: Connection Offline", fg=self.COLOR_OFFLINE)
                self.log_message(f"Error refreshing service list: {error_msg}")
                # Don't show popup dialog every time to prevent disrupting the user experience, just output to logs
                return
                
            self.status_lbl.configure(text="Server status: Connected", fg=self.COLOR_ONLINE)
            
            # Clear old cards
            for widget in self.scroll_frame.scrollable_frame.winfo_children():
                widget.destroy()
                
            if not detailed_projects:
                lbl = tk.Label(self.scroll_frame.scrollable_frame, text="No local services found.", bg=self.BG_DARK, fg=self.FG_MUTED, font=("Segoe UI", 11, "italic"))
                lbl.pack(pady=50)
                return
                
            # Populate Cards
            for proj in detailed_projects:
                card = tk.Frame(
                    self.scroll_frame.scrollable_frame, bg=self.BG_CARD, bd=1, relief="flat",
                    highlightbackground=self.BORDER_COLOR, highlightcolor=self.BORDER_COLOR, highlightthickness=1
                )
                card.pack(fill="x", padx=15, pady=8)
                
                # Left side - Service Information
                info_frame = tk.Frame(card, bg=self.BG_CARD)
                info_frame.pack(side="left", fill="both", expand=True, padx=15, pady=12)
                
                # Name & Status Badge Row
                title_frame = tk.Frame(info_frame, bg=self.BG_CARD)
                title_frame.pack(fill="x", anchor="w")
                
                proj_name = proj.get("name", "Unnamed Service")
                lbl_name = tk.Label(title_frame, text=proj_name, bg=self.BG_CARD, fg=self.FG_LIGHT, font=("Segoe UI", 11, "bold"))
                lbl_name.pack(side="left")
                
                status_val = proj.get("current_status", "unknown")
                if status_val == "online":
                    status_color = self.COLOR_ONLINE
                elif status_val == "offline":
                    status_color = self.COLOR_OFFLINE
                else:
                    status_color = self.COLOR_WARNING
                    
                status_dot = tk.Label(title_frame, text="●", bg=self.BG_CARD, fg=status_color, font=("Segoe UI", 12))
                status_dot.pack(side="left", padx=(10, 3))
                
                status_text = tk.Label(title_frame, text=status_val.upper(), bg=self.BG_CARD, fg=status_color, font=("Segoe UI", 8, "bold"))
                status_text.pack(side="left")
                
                # Server metadata line
                server_info = proj.get("server", {})
                server_name = server_info.get("name", "Localhost")
                server_host = server_info.get("host", "127.0.0.1")
                lbl_server = tk.Label(info_frame, text=f"Host: {server_name} ({server_host})", bg=self.BG_CARD, fg=self.FG_MUTED, font=("Segoe UI", 9))
                lbl_server.pack(fill="x", anchor="w", pady=(2, 0))
                
                # Description
                desc = proj.get("description", "")
                if desc:
                    lbl_desc = tk.Label(info_frame, text=desc, bg=self.BG_CARD, fg=self.FG_MUTED, font=("Segoe UI", 9), wraplength=450, justify="left")
                    lbl_desc.pack(fill="x", anchor="w", pady=(4, 0))
                    
                # Right side - Actions
                btn_frame = tk.Frame(card, bg=self.BG_CARD)
                btn_frame.pack(side="right", fill="y", padx=15, pady=12)
                
                # Render buttons only if commands exist
                start_cmd = proj.get("start_cmd")
                if start_cmd:
                    start_btn = ModernButton(
                        btn_frame, text="Start", command=lambda p=proj: self.execute_service_action(p, "start"),
                        bg=self.COLOR_ONLINE, hover_bg="#059669"
                    )
                    start_btn.pack(side="left", padx=4)
                    
                stop_cmd = proj.get("stop_cmd")
                if stop_cmd:
                    stop_btn = ModernButton(
                        btn_frame, text="Stop", command=lambda p=proj: self.execute_service_action(p, "stop"),
                        bg=self.COLOR_OFFLINE, hover_bg="#dc2626"
                    )
                    stop_btn.pack(side="left", padx=4)
                    
                restart_cmd = proj.get("restart_cmd")
                if restart_cmd:
                    restart_btn = ModernButton(
                        btn_frame, text="Restart", command=lambda p=proj: self.execute_service_action(p, "restart"),
                        bg=self.ACCENT, hover_bg=self.ACCENT_HOVER
                    )
                    restart_btn.pack(side="left", padx=4)

        # Service Action Triggering
        def execute_service_action(self, project, action):
            proj_name = project.get("name", "Unnamed")
            cmd = project.get(f"{action}_cmd")
            if not cmd:
                self.log_message(f"[{proj_name}] Error: No {action} command configured.")
                return
                
            self.log_message(f"[{proj_name}] Triggered local {action.upper()} operation...")
            threading.Thread(target=self._run_action_thread, args=(project, action, cmd), daemon=True).start()

        def _run_action_thread(self, project, action, cmd):
            proj_name = project.get("name", "Unnamed")
            proj_id = project.get("id")
            
            admin_triggers = ["start-service", "stop-service", "restart-service", "net start", "net stop", "sc config"]
            run_as_admin = any(trigger in cmd.lower() for trigger in admin_triggers)
            
            shell = "powershell"
            if "cmd /c" in cmd or "cmd.exe /c" in cmd:
                shell = "cmd"
                
            if run_as_admin:
                self.log_message(f"[{proj_name}] Executing command as Administrator (shell={shell}): {cmd}")
                exit_code, stdout, stderr = run_command_elevated(cmd, shell)
            else:
                self.log_message(f"[{proj_name}] Executing command as normal user (shell={shell}): {cmd}")
                exit_code, stdout, stderr = run_command_normal(cmd, shell)
                
            self.log_message(
                f"[{proj_name}] Command exit code: {exit_code}\n"
                f"STDOUT:\n{stdout.strip() or '(none)'}\n"
                f"STDERR:\n{stderr.strip() or '(none)'}\n"
                f"=================================================="
            )
            
            # Sync server status
            token = self.get_auth_token()
            main_url = self.config.get("main_app_url", "").rstrip("/")
            if token and proj_id and main_url:
                sync_url = f"{main_url}/api/projects/sync-status"
                self.log_message(f"[{proj_name}] Syncing status to Portal Console server...")
                status, res = api_request(sync_url, "POST", {"project_ids": [proj_id]}, token=token)
                if status == 200:
                    self.log_message(f"[{proj_name}] Server status synchronized.")
                else:
                    self.log_message(f"[{proj_name}] Status sync failed with status {status}.")
                    
            # Refresh list to fetch updated status
            self.root.after(0, self.start_refresh_thread)

        # Configuration Action Handlers: Cancel, Save, and Restart
        def cancel_config_changes(self):
            # Revert inputs to loaded config values
            for key, (entry, _) in self.entries.items():
                val = self.config.get(key)
                val_str = "" if val is None else str(val)
                entry.delete(0, "end")
                entry.insert(0, val_str)
            self.log_message("Configuration changes canceled. Inputs reverted.")
            self.show_services_tab()

        def save_config_changes(self):
            new_config = {}
            for key, (entry, _) in self.entries.items():
                val = entry.get().strip()
                
                if key == "port":
                    try:
                        new_config[key] = int(val)
                    except ValueError:
                        messagebox.showerror("Error", "Port must be an integer.")
                        return
                elif key == "server_id":
                    if val:
                        try:
                            new_config[key] = int(val)
                        except ValueError:
                            messagebox.showerror("Error", "Server ID must be an integer or empty.")
                            return
                    else:
                        new_config[key] = None
                else:
                    new_config[key] = val
                    
            # Validations
            if not new_config["host"]:
                messagebox.showerror("Error", "Host bind address cannot be empty.")
                return
            if not new_config["secret"]:
                messagebox.showerror("Error", "JWT Secret cannot be empty.")
                return
            if not new_config["main_app_url"]:
                messagebox.showerror("Error", "Portal Console URL cannot be empty.")
                return
                
            # Write out to config.json
            try:
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(new_config, f, indent=4)
                
                # Update memory configuration
                self.config.update(new_config)
                # Clear cached auth token in case credentials changed
                self._cached_token = None
                
                self.log_message("Configuration saved successfully. Memory configuration updated. Note: Port/Host modifications require a restart to bind.")
                messagebox.showinfo("Success", "Configuration saved successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save configuration: {e}")

        def trigger_restart(self):
            if not messagebox.askyesno("Confirm Restart", "Are you sure you want to restart the agent process?"):
                return
                
            self.log_message("Initiating agent restart...")
            
            # Close HTTP socket to release port cleanly
            try:
                self.server.server_close()
            except:
                pass
                
            # Self-restart process
            try:
                os.execv(sys.executable, [sys.executable] + sys.argv)
            except:
                # Fallback: spawn new subprocess and exit parent
                subprocess.Popen([sys.executable] + sys.argv)
                sys.exit(0)

def main():
    config = load_config()
    
    parser = argparse.ArgumentParser(description="Portal Console - Windows Local Helper Agent")
    parser.add_argument("--port", type=int, default=config["port"], help="Port to listen on (default: 8008)")
    parser.add_argument("--host", default=config["host"], help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--secret", default=config["secret"], help="JWT shared secret key (must match main application's SECRET_KEY)")
    parser.add_argument("--no-gui", action="store_true", help="Run headlessly without showing the graphical user interface")
    
    args = parser.parse_args()
    
    # Override loaded config from arguments if provided
    config["port"] = args.port
    config["host"] = args.host
    config["secret"] = args.secret
    
    if config["secret"] == "change-this-secret":
        print("WARNING: You are using the default JWT secret. Please configure a secure secret key in config.json or via --secret!")
        
    print("==================================================")
    print("      Portal Console - Windows Helper Agent")
    print("==================================================")
    print(f"Binding to: http://{config['host']}:{config['port']}")
    print("JWT authentication is enabled.")
    
    # Store settings in server object so request handler can access it
    class CustomHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True  # Child threads terminate when parent exits
        def __init__(self, server_address, RequestHandlerClass, secret):
            super().__init__(server_address, RequestHandlerClass)
            self.secret = secret
            
    # Try starting HTTP Server
    try:
        server = CustomHTTPServer((config["host"], config["port"]), AgentRequestHandler, config["secret"])
    except Exception as e:
        print(f"FATAL: Failed to bind to socket {config['host']}:{config['port']}. Error: {e}")
        sys.exit(1)
        
    # Decide if we run GUI or Headless
    gui_mode = HAS_GUI and not args.no_gui
    
    if gui_mode:
        print("Running in GUI Mode...")
        # Start HTTP server on background daemon thread
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        
        # Initialize and run Tkinter mainloop on main thread
        root = tk.Tk()
        AgentGUI(root, config, server)
        try:
            root.mainloop()
        except KeyboardInterrupt:
            print("\nStopping Agent...")
            server.server_close()
            print("Agent stopped.")
    else:
        print("Running in Headless Mode...")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping Agent...")
            server.server_close()
            print("Agent stopped.")

if __name__ == "__main__":
    main()
