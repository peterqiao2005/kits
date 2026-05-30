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
from http.server import HTTPServer, BaseHTTPRequestHandler

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
        "main_app_url": "http://127.0.0.1:8000"
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

# Execution helpers
def run_command_normal(command, shell="powershell"):
    try:
        if shell == "powershell":
            # For powershell execution, run in non-profile bypass mode
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
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
            # powershell -Command ...
            # We redirect standard output and error to the temp file inside the elevated execution block.
            ps_cmd = f"& {{ {command} }} > '{temp_path}' 2>&1"
            # Note: inside windows, we can run powershell Start-Process with RunAs
            # -Wait prevents the window from returning before command completes.
            # -WindowStyle Hidden keeps the window from flashing.
            args = f"-NoProfile -ExecutionPolicy Bypass -Command \"Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -Command {ps_cmd}' -Verb RunAs -Wait -WindowStyle Hidden\""
            subprocess.run(["powershell", args], capture_output=True, text=True, encoding="utf-8")
        else:
            # cmd
            # We escape quotes properly for cmd redirection.
            args = f"-NoProfile -ExecutionPolicy Bypass -Command \"Start-Process cmd -ArgumentList '/c {command} > \"\"{temp_path}\"\" 2>&1' -Verb RunAs -Wait -WindowStyle Hidden\""
            subprocess.run(["powershell", args], capture_output=True, text=True, encoding="utf-8")
        
        # Read the file
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

def main():
    config = load_config()
    
    parser = argparse.ArgumentParser(description="Portal Console - Windows Local Helper Agent")
    parser.add_argument("--port", type=int, default=config["port"], help="Port to listen on (default: 8008)")
    parser.add_argument("--host", default=config["host"], help="Host address to bind (default: 127.0.0.1)")
    parser.add_argument("--secret", default=config["secret"], help="JWT shared secret key (must match main application's SECRET_KEY)")
    
    args = parser.parse_args()
    
    if args.secret == "change-this-secret":
        print("WARNING: You are using the default JWT secret. Please configure a secure secret key in config.json or via --secret!")
    
    print("==================================================")
    print("      Portal Console - Windows Helper Agent")
    print("==================================================")
    print(f"Binding to: http://{args.host}:{args.port}")
    print("JWT authentication is enabled.")
    print("Running... Press Ctrl+C to stop.")
    
    # Store settings in server object so request handler can access it
    class CustomHTTPServer(HTTPServer):
        def __init__(self, server_address, RequestHandlerClass, secret):
            super().__init__(server_address, RequestHandlerClass)
            self.secret = secret
            
    server = CustomHTTPServer((args.host, args.port), AgentRequestHandler, args.secret)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Agent...")
        server.server_close()
        print("Agent stopped.")

if __name__ == "__main__":
    main()
