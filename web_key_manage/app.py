#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SSH 公钥集中管理（Push，无 Ansible）
- DB: SQLite
- Web UI: 内置模板（无 block）
- 私钥：不落盘不入库，仅存服务端 session（Flask-Session filesystem）
- Push：Paramiko（SFTP + 原子替换）
"""

import os
import re
import base64
import hashlib
import tempfile
import secrets
from datetime import datetime

from flask import (
    Flask, request, jsonify, abort, redirect, url_for,
    render_template_string, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_session import Session
from sqlalchemy import UniqueConstraint
from sqlalchemy.exc import IntegrityError
from argon2 import PasswordHasher
import paramiko
from markupsafe import Markup  # 关键：用于包裹内层 HTML

# ========= 基本配置 =========
APP_SECRET = os.getenv("APP_SECRET", secrets.token_hex(32))
DB_PATH = os.getenv("DB_PATH", os.path.abspath("./sshcmdb.sqlite3"))

app = Flask(__name__)
app.config.update(
    SECRET_KEY=APP_SECRET,
    SQLALCHEMY_DATABASE_URI=f"sqlite:///{DB_PATH}",
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=os.path.abspath("./.flask_session"),
    SESSION_PERMANENT=False,
)
db = SQLAlchemy(app)
Session(app)
ph = PasswordHasher()

# ========= 数据模型 =========
class AppUser(db.Model):
    __tablename__ = "app_users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    pwd_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class People(db.Model):
    __tablename__ = "people"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    email = db.Column(db.String(256))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SSHKey(db.Model):
    __tablename__ = "ssh_keys"
    id = db.Column(db.Integer, primary_key=True)
    people_id = db.Column(db.Integer, db.ForeignKey("people.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    algo = db.Column(db.String(32), nullable=False)
    pubkey = db.Column(db.Text, nullable=False)
    fingerprint_sha256 = db.Column(db.String(128), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Server(db.Model):
    __tablename__ = "servers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), unique=True, nullable=False)
    host = db.Column(db.String(255), nullable=False)
    ssh_user = db.Column(db.String(64), nullable=False, default="root")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ServerKey(db.Model):
    __tablename__ = "server_keys"
    id = db.Column(db.Integer, primary_key=True)
    server_id = db.Column(db.Integer, db.ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    ssh_key_id = db.Column(db.Integer, db.ForeignKey("ssh_keys.id", ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint("server_id", "ssh_key_id", name="uq_server_key"),)

class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(64), nullable=False)
    detail = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

def log(action: str, detail: str):
    db.session.add(AuditLog(action=action, detail=detail))
    db.session.commit()

# ========= 工具函数 =========
def parse_pubkey_get_algo_and_b64(pubkey_line: str):
    line = pubkey_line.strip()
    parts = line.split()
    if len(parts) < 2:
        raise ValueError("无效的公钥格式（至少应包含算法 与 base64 内容）")
    algo = parts[0]
    b64 = parts[1]
    base64.b64decode(b64 + "==")
    return algo, b64

def calc_sha256_fingerprint(pubkey_line: str) -> str:
    _, b64 = parse_pubkey_get_algo_and_b64(pubkey_line)
    raw = base64.b64decode(b64 + "==")
    fp = base64.b64encode(hashlib.sha256(raw).digest()).decode("utf-8").rstrip("=")
    return f"SHA256:{fp}"

def parse_pubkey_from_any_line(line: str):
    """
    兼容 options 前缀的行：command="...",no-agent-forwarding ssh-ed25519 AAAA... comment...
    返回 (algo, b64, comment)；无效/注释行返 None
    """
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    toks = s.split()
    idx = None
    for i, t in enumerate(toks):
        if t.startswith("ssh-") or t.startswith("ecdsa-"):
            idx = i
            break
    if idx is None or idx + 1 >= len(toks):
        return None
    algo = toks[idx]; b64 = toks[idx + 1]
    try:
        base64.b64decode(b64 + "==")
    except Exception:
        return None
    comment = " ".join(toks[idx + 2:]) if len(toks) > idx + 2 else ""
    return algo, b64, comment

def fetch_remote_authorized_keys(server: 'Server') -> str:
    """用会话私钥 SSH 读取远端 ~user/.ssh/authorized_keys；不存在返回空串"""
    sk_pem, sk_passphrase = get_client_sk_or_raise()
    if not sk_pem:
        raise RuntimeError("当前会话没有私钥。请先在“会话私钥”里设置。")

    pkey = None; last_err = None
    for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            pkey = loader.from_private_key(io_stream_from_str(sk_pem), password=sk_passphrase); break
        except Exception as e:
            last_err = e
    if pkey is None:
        raise RuntimeError(f"无法解析私钥：{last_err}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(server.host, username=server.ssh_user, pkey=pkey,
                    timeout=20, allow_agent=False, look_for_keys=False,
                    banner_timeout=20, auth_timeout=20)
        home = remote_expanduser_home(ssh, server.ssh_user)
        path = f"{home}/.ssh/authorized_keys"
        cmd = f"bash -lc 'test -f {shq(path)} && cat {shq(path)} || true'"
        return run_ok(ssh, cmd)
    finally:
        ssh.close()

def remote_write_authorized_keys_via_ssh(server: 'Server', content: str):
    """通过 SSH heredoc 原子写入 authorized_keys（备份原文件）"""
    sk_pem, sk_passphrase = get_client_sk_or_raise()
    if not sk_pem:
        raise RuntimeError("当前会话没有私钥。请先在“会话私钥”里设置。")

    pkey = None; last_err = None
    for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            pkey = loader.from_private_key(io_stream_from_str(sk_pem), password=sk_passphrase); break
        except Exception as e:
            last_err = e
    if pkey is None:
        raise RuntimeError(f"无法解析私钥：{last_err}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(server.host, username=server.ssh_user, pkey=pkey,
                timeout=20, allow_agent=False, look_for_keys=False,
                banner_timeout=20, auth_timeout=20)

    try:
        home = remote_expanduser_home(ssh, server.ssh_user)
        ssh_dir = f"{home}/.ssh"
        file_path = f"{ssh_dir}/authorized_keys"
        tmp_path = f"{file_path}.cmdb.tmp"
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        bak_path = f"{file_path}.{ts}.bak"

        # 写 tmp（heredoc，单引号 EOF，内容原样）
        heredoc = f"""bash -lc '
set -e
mkdir -p {shq(ssh_dir)} && chmod 700 {shq(ssh_dir)}
cat > {shq(tmp_path)} <<'CMDB_EOF'
{content.rstrip()}
CMDB_EOF
chmod 600 {shq(tmp_path)}
test -f {shq(file_path)} && cp -a {shq(file_path)} {shq(bak_path)} || true
mv -f {shq(tmp_path)} {shq(file_path)}
chmod 600 {shq(file_path)}
chown $(id -u):$(id -g) {shq(file_path)} {shq(ssh_dir)} || true
'"""
        run_ok(ssh, heredoc)
        return {"backup": bak_path}
    finally:
        ssh.close()

def db_lines_map_for_server(sid: int) -> dict:
    """
    返回 {fingerprint: line}，line 为将要写入 authorized_keys 的单行
    - 有原注释：保留整段注释
    - 无注释：用标题，末尾仍附指纹
    """
    q = db.session.query(SSHKey).join(ServerKey, ServerKey.ssh_key_id == SSHKey.id)\
        .filter(ServerKey.server_id == sid, SSHKey.is_active == True)\
        .order_by(SSHKey.id.asc())
    m = {}
    for k in q.all():
        parts = k.pubkey.strip().split()
        if len(parts) >= 2:
            algo, b64 = parts[0], parts[1]
            if len(parts) >= 3:
                comment = " ".join(parts[2:])
            else:
                comment = k.title or ""
            # 统一附上指纹便于排查
            comment = (comment + ("" if comment.endswith(k.fingerprint_sha256) else f":{k.fingerprint_sha256}")).strip()
            m[k.fingerprint_sha256] = f"{algo} {b64} {comment}".strip()
    return m

def require_login():
    if not session.get("uid"):
        abort(401, description="请先登录")

def current_user():
    uid = session.get("uid")
    return AppUser.query.get(uid) if uid else None

# ========= SSH Push =========
def push_authorized_keys_via_paramiko(server: 'Server', ak_content: str):
    sk_pem, sk_passphrase = get_client_sk_or_raise()
    if not sk_pem:
        raise RuntimeError("当前会话没有私钥。请先在页面右上角“会话私钥”里设置。")

    pkey = None
    last_err = None
    for loader in (paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey):
        try:
            pkey = loader.from_private_key(io_stream_from_str(sk_pem), password=sk_passphrase)
            break
        except Exception as e:
            last_err = e
            continue
    if pkey is None:
        raise RuntimeError(f"无法解析私钥：{last_err}")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(
            hostname=server.host, username=server.ssh_user, pkey=pkey,
            timeout=20, allow_agent=False, look_for_keys=False,
            banner_timeout=20, auth_timeout=20
        )
    except Exception as e:
        raise RuntimeError(f"SSH 连接失败：{e}")

    sftp = None
    try:
        sftp = ssh.open_sftp()
        remote_home = remote_expanduser_home(ssh, server.ssh_user)
        remote_ssh_dir = f"{remote_home}/.ssh"
        remote_file = f"{remote_ssh_dir}/authorized_keys"
        remote_tmp = f"{remote_file}.cmdb.tmp"
        ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        remote_bak = f"{remote_file}.{ts}.bak"

        run_ok(ssh, f"mkdir -p {shq(remote_ssh_dir)} && chmod 700 {shq(remote_ssh_dir)}")
        with sftp.file(remote_tmp, mode="w") as f:
            f.write(ak_content)
        run_ok(ssh, f"chmod 600 {shq(remote_tmp)}")

        cmd = f"""
set -e
test -f {shq(remote_file)} && cp -a {shq(remote_file)} {shq(remote_bak)} || true
mv -f {shq(remote_tmp)} {shq(remote_file)}
chmod 600 {shq(remote_file)}
chown $(id -u):$(id -g) {shq(remote_file)} {shq(remote_ssh_dir)} || true
"""
        run_ok(ssh, cmd)
        return {"backup": remote_bak}
    finally:
        try:
            if sftp: sftp.close()
        except Exception:
            pass
        ssh.close()

def io_stream_from_str(txt: str):
    import io
    return io.StringIO(txt)

def shq(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"

def run_ok(ssh: paramiko.SSHClient, cmd: str):
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode("utf-8", "ignore")
    err = stderr.read().decode("utf-8", "ignore")
    rc = stdout.channel.recv_exit_status()
    if rc != 0:
        raise RuntimeError(f"远端命令失败 rc={rc} err={err.strip()}")
    return out

def get_client_sk_or_raise():
    """优先从请求表单读取浏览器会话注入的私钥；没有则报错"""
    sk_text = (request.form.get("sk_text") or "").strip()
    sk_pass = request.form.get("sk_passphrase") or None
    if not sk_text:
        raise RuntimeError("浏览器会话未携带私钥。请先在右上角“会话私钥”设置（仅存浏览器会话），再重试。")
    return sk_text, sk_pass

def remote_expanduser_home(ssh: paramiko.SSHClient, user: str) -> str:
    out = run_ok(ssh, f"bash -lc 'eval echo ~{user}'")
    return out.strip()

# ========= 模板 & 渲染 =========
TPL_BASE = """
<!doctype html>
<html lang="zh">
<head>
  <meta charset="utf-8"/>
  <title>SSH Key 管理</title>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <style>
    body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial; margin: 24px; }
    nav a { margin-right: 16px; }
    table { border-collapse: collapse; width: 100%; margin: 8px 0 24px; }
    th, td { border: 1px solid #ddd; padding: 8px; }
    th { background: #f8f8f8; text-align: left; }
    input[type=text], input[type=password], textarea { width: 100%; padding: 6px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .btn { display: inline-block; padding: 6px 12px; background: #2f6; border: 1px solid #2a5; text-decoration: none; color: #000; border-radius: 4px; }
    .btn-red { background: #f66; border-color: #e55; }
    .btn-blue { background: #8cf; border-color: #79b; }
    .flash { padding: 8px; background: #fffae6; margin: 8px 0; border: 1px solid #f0d; }
    .topbar { display:flex; align-items:center; gap:16px; margin-bottom:16px; }
    .topbar .right { margin-left:auto; }
    .muted { color:#666; }
    pre { white-space: pre-wrap; }
    .narrow { max-width: 560px; margin: 0 auto; }
  </style>
    <script>
    // —— 浏览器会话中的私钥 —— //
    function sk_has(){ return !!sessionStorage.getItem('sk_text'); }
    function sk_set(text, passphrase){
      sessionStorage.setItem('sk_text', text || '');
      sessionStorage.setItem('sk_passphrase', passphrase || '');
    }
    function sk_clear(){
      sessionStorage.removeItem('sk_text');
      sessionStorage.removeItem('sk_passphrase');
    }
    // 在需要私钥的表单提交前，把浏览器会话里的私钥注入为隐藏字段
    function sk_fill(form){
      var t = sessionStorage.getItem('sk_text') || '';
      var p = sessionStorage.getItem('sk_passphrase') || '';
      if(!t){ alert('浏览器会话中尚未设置私钥：请先在“会话私钥”页面设置。'); return false; }
      if(!form.querySelector('input[name="sk_text"]')){
        var it = document.createElement('input'); it.type='hidden'; it.name='sk_text'; it.value=t; form.appendChild(it);
        var ip = document.createElement('input'); ip.type='hidden'; ip.name='sk_passphrase'; ip.value=p; form.appendChild(ip);
      }
      return true;
    }
  </script>
</head>
<body>
  <div class="topbar">
    <nav>
      {% if me %}
        <a href="{{ url_for('index') }}">总览</a>
        <a href="{{ url_for('people_page') }}">人员</a>
        <a href="{{ url_for('keys_page') }}">公钥</a>
        <a href="{{ url_for('servers_page') }}">服务器</a>
        <a href="{{ url_for('bindings_page') }}">绑定</a>
      {% endif %}
    </nav>
    <div class="right">
      {% if me %}
        <span class="muted">当前用户：{{ me.username }}</span>
        &nbsp;|&nbsp;
        <a class="btn-blue" href="{{ url_for('session_key_page') }}">会话私钥</a>
        &nbsp;|&nbsp;
        <a class="btn" href="{{ url_for('logout') }}">退出</a>
      {% else %}
        <a class="btn-blue" href="{{ url_for('login_page') }}">登录</a>
      {% endif %}
    </div>
  </div>
  {% for msg in get_flashed_messages() %}
    <div class="flash">{{ msg }}</div>
  {% endfor %}
  {{ content|safe }}
</body>
</html>
"""

def render_page(content_tpl: str, **kwargs):
    """
    先用相同上下文渲染内层模板，再把结果作为 HTML 塞入基模板。
    避免 block/继承，也避免上下文丢失。
    """
    # 注：这里不依赖 context_processor，手动传入 kwargs（me 会由 context_processor 注入到外层）
    inner_html = render_template_string(content_tpl, **kwargs)
    return render_template_string(TPL_BASE, content=Markup(inner_html), **kwargs)

@app.context_processor
def inject_user():
    return {"me": current_user()}

# ========= 认证 =========
@app.route("/auth/init", methods=["POST"])
def auth_init():
    if AppUser.query.count() > 0:
        abort(400, "已初始化")
    data = request.get_json(force=True)
    username = data["username"].strip()
    password = data["password"]
    if not username or not password:
        abort(400, "缺少用户名或密码")
    u = AppUser(username=username, pwd_hash=ph.hash(password))
    db.session.add(u); db.session.commit()
    log("auth_init", f"user={username}")
    return jsonify({"ok": True})

@app.route("/auth/login", methods=["POST"])
def auth_login():
    data = request.get_json(force=True)
    username = data["username"].strip()
    password = data["password"]
    u = AppUser.query.filter_by(username=username).first()
    if not u: abort(401, "用户名或密码错误")
    try:
        ph.verify(u.pwd_hash, password)
    except Exception:
        abort(401, "用户名或密码错误")
    session["uid"] = u.id
    log("auth_login", f"user={username}")
    return jsonify({"ok": True})

@app.route("/logout")
def logout():
    session.clear()
    flash("已退出登录")
    return redirect(url_for("index"))

# ========= 页面 =========
@app.route("/")
def index():
    if not session.get("uid"):
        return redirect(url_for("login_page"))
    people_count = People.query.count()
    key_count = SSHKey.query.count()
    server_count = Server.query.count()
    sk_summary = "已设置" if session.get("ssh_private_key_text") else "未设置"
    return render_page("""
<h2>概览</h2>
<ul>
  <li>人员：{{ people_count }}</li>
  <li>公钥：{{ key_count }}</li>
  <li>服务器：{{ server_count }}</li>
  <li>会话私钥：{{ sk_summary }}</li>
</ul>
""", people_count=people_count, key_count=key_count, server_count=server_count, sk_summary=sk_summary)

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        act = request.form.get("act")
        if act == "init":
            if AppUser.query.count() > 0:
                flash("系统已初始化，请直接登录")
                return redirect(url_for("login_page"))
            username = request.form.get("username","").strip()
            password = request.form.get("password","")
            if not username or not password:
                flash("请输入用户名和密码")
            else:
                u = AppUser(username=username, pwd_hash=ph.hash(password))
                db.session.add(u); db.session.commit()
                flash("初始化成功，请登录")
                return redirect(url_for("login_page"))
        elif act == "login":
            username = request.form.get("username","").strip()
            password = request.form.get("password","")
            u = AppUser.query.filter_by(username=username).first()
            if not u:
                flash("用户名或密码错误")
            else:
                try:
                    ph.verify(u.pwd_hash, password)
                    session["uid"] = u.id
                    return redirect(url_for("index"))
                except Exception:
                    flash("用户名或密码错误")

    no_user = (AppUser.query.count() == 0)
    if no_user:
        return render_page("""
<div class="narrow">
  <h2>首次使用初始化管理员</h2>
  <form method="post">
    <input type="hidden" name="act" value="init"/>
    <p><label>用户名</label><br><input type="text" name="username"></p>
    <p><label>密码</label><br><input type="password" name="password"></p>
    <p><button class="btn-blue" type="submit">初始化</button></p>
  </form>
</div>
""")
    else:
        return render_page("""
<div class="narrow">
  <h2>登录</h2>
  <form method="post">
    <input type="hidden" name="act" value="login"/>
    <p><label>用户名</label><br><input type="text" name="username"></p>
    <p><label>密码</label><br><input type="password" name="password"></p>
    <p><button class="btn" type="submit">登录</button></p>
  </form>
</div>
""")

@app.route("/session-key", methods=["GET", "POST"])
def session_key_page():
    require_login()
    if request.method == "POST":
        act = request.form.get("act")
        if act == "set":
            text = request.form.get("keytext","").strip()
            passphrase = request.form.get("passphrase","")
            if not text and "keyfile" in request.files:
                f = request.files["keyfile"]; text = f.read().decode("utf-8", "ignore")
            if not text:
                flash("未提供私钥内容")
            else:
                session["ssh_private_key_text"] = text
                session["ssh_private_key_passphrase"] = passphrase
                flash("会话私钥已更新（仅保存于服务器会话，不持久化）")
                return redirect(url_for("session_key_page"))
        elif act == "clear":
            session.pop("ssh_private_key_text", None)
            session.pop("ssh_private_key_passphrase", None)
            flash("会话私钥已清除")
            return redirect(url_for("session_key_page"))

    has_key = False  # 状态由前端 JS 判断
    return render_page("""
<h2>会话私钥</h2>
<p class="muted">保存在<strong>浏览器会话</strong>（sessionStorage）中；不会写入服务器会话/数据库。关闭标签页或浏览器即清空。</p>

<form onsubmit="return sk_save(this)" enctype="multipart/form-data">
  <p><label>粘贴私钥文本（PEM）</label><br>
  <textarea name="keytext" rows="10" placeholder="-----BEGIN OPENSSH PRIVATE KEY----- ..."></textarea></p>
  <p><label>或上传私钥文件</label><br>
  <input type="file" name="keyfile" accept=".pem,.key,.txt" onchange="file_to_text(this)"/></p>
  <p><label>私钥口令（如有）</label><br>
  <input type="password" name="passphrase"/></p>
  <p>
    <button class="btn" type="submit">设置/替换（仅浏览器会话）</button>
    <button class="btn-red" onclick="return sk_clear_local()">清除当前私钥</button>
  </p>
</form>

<p><strong>状态：</strong><span id="sk-status">检测中...</span></p>

<script>
function file_to_text(inp){
  if(!inp.files || !inp.files[0]) return;
  var f = inp.files[0];
  var r = new FileReader();
  r.onload = function(){ document.querySelector('textarea[name="keytext"]').value = r.result; };
  r.readAsText(f);
}
function sk_save(f){
  var t = f.querySelector('textarea[name="keytext"]').value.trim();
  if(!t){ alert('请粘贴或选择私钥文件'); return false; }
  var p = f.querySelector('input[name="passphrase"]').value;
  sk_set(t, p);
  alert('会话私钥已保存在浏览器会话；关闭页面即清空。');
  update_status();
  return false; // 不提交到服务器
}
function sk_clear_local(){
  sk_clear();
  alert('已清除浏览器会话中的私钥');
  update_status();
  return false;
}
function update_status(){
  document.getElementById('sk-status').innerText = sk_has() ? '已设置（浏览器会话）' : '未设置';
}
update_status();
</script>
""")


# ========= 人员 / 公钥 =========
@app.route("/people", methods=["GET", "POST"])
def people_page():
    require_login()
    if request.method == "POST":
        act = request.form.get("act") or "add"
        if act == "add":
            name = request.form.get("name","").strip()
            email = request.form.get("email","").strip()
            if not name:
                flash("姓名必填", "err")
            else:
                p = People(name=name, email=email or None)
                db.session.add(p); db.session.commit()
                log("add_people", f"{p.id}:{p.name}")
                return redirect(url_for("people_page"))

        elif act == "update":
            pid = int(request.form.get("pid","0"))
            name = request.form.get("name","").strip()
            email = request.form.get("email","").strip()
            p = People.query.get(pid)
            if not p:
                flash("未找到该人员", "err")
            else:
                if not name:
                    flash("姓名必填", "err")
                else:
                    p.name = name
                    p.email = email or None
                    db.session.commit()
                    log("upd_people", f"{p.id}:{p.name}")
                    return redirect(url_for("people_page"))

        elif act == "delete":
            pid = int(request.form.get("pid","0"))
            p = People.query.get(pid)
            if not p:
                flash("未找到该人员", "err")
            else:
                has_keys = SSHKey.query.filter_by(people_id=pid).first()
                if has_keys:
                    flash("该人员仍有关联公钥，无法删除（请先删除/转移其公钥）", "err")
                else:
                    db.session.delete(p); db.session.commit()
                    log("del_people", f"{pid}")
                    flash("已删除", "ok")
                    return redirect(url_for("people_page"))

    rows = People.query.order_by(People.id.asc()).all()
    edit_id = request.args.get("edit", type=int)
    editing = People.query.get(edit_id) if edit_id else None

    return render_page("""
<h2>人员</h2>

{% if editing %}
<form method="post" class="row" style="border:1px solid #ddd;padding:12px;margin-bottom:16px">
  <input type="hidden" name="act" value="update"/>
  <input type="hidden" name="pid" value="{{ editing.id }}"/>
  <p><label>姓名</label><br><input type="text" name="name" value="{{ editing.name }}"/></p>
  <p><label>Email（可选）</label><br><input type="text" name="email" value="{{ editing.email or '' }}"/></p>
  <p><button class="btn" type="submit">保存修改</button></p>
  <p><a class="btn-blue" href="{{ url_for('people_page') }}">取消</a></p>
</form>
{% endif %}

<form method="post" class="row">
  <input type="hidden" name="act" value="add"/>
  <p><label>姓名</label><br><input type="text" name="name"/></p>
  <p><label>Email（可选）</label><br><input type="text" name="email"/></p>
  <p><button class="btn" type="submit">新增人员</button></p>
</form>

<table>
  <tr><th>ID</th><th>姓名</th><th>Email</th><th>创建时间</th><th>操作</th></tr>
  {% for r in rows %}
  <tr>
    <td>{{ r.id }}</td><td>{{ r.name }}</td><td>{{ r.email or "" }}</td><td>{{ r.created_at }}</td>
    <td>
      <a class="btn-blue" href="{{ url_for('people_page', edit=r.id) }}">编辑</a>
      <form method="post" style="display:inline" onsubmit="return confirm('确认删除该人员？');">
        <input type="hidden" name="act" value="delete"/>
        <input type="hidden" name="pid" value="{{ r.id }}"/>
        <button class="btn-red" type="submit">删除</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
""", rows=rows, editing=editing)

@app.route("/keys", methods=["GET", "POST"])
def keys_page():
    require_login()
    if request.method == "POST":
        act = request.form.get("act") or "add"

        if act == "add":
            people_id = int(request.form.get("people_id","0"))
            title = request.form.get("title","").strip()
            pubkey = request.form.get("pubkey","").strip()
            if not (people_id and pubkey):
                flash("请完整填写人员、公钥", "err")
            else:
                try:
                    parts = pubkey.strip().split()
                    algo, _ = parse_pubkey_get_algo_and_b64(pubkey)
                    fp = calc_sha256_fingerprint(pubkey)
                    has_comment = (len(parts) >= 3)
                    if not has_comment and not title:
                        person = People.query.get(people_id)
                        pname = (person.name if person else "user").replace(" ", "_")
                        title = f"{pname}-{algo}-{fp[-8:]}"
                        flash(f"已自动设置标题：{title}", "info")
                    k = SSHKey(people_id=people_id, title=title or "(auto)", algo=algo,
                               pubkey=pubkey, fingerprint_sha256=fp, is_active=True)
                    db.session.add(k); db.session.commit()
                    log("add_key", f"{k.id}:{fp}:{title or '(auto)'}")
                    return redirect(url_for("keys_page"))
                except Exception as e:
                    flash(f"公钥格式错误：{e}", "err")

        elif act == "update":
            kid = int(request.form.get("key_id","0"))
            title = request.form.get("title","").strip()
            pubkey = request.form.get("pubkey","").strip()
            k = SSHKey.query.get(kid)
            if not k:
                flash("未找到该公钥", "err")
            else:
                try:
                    # 若 pubkey 变化，重算 algo 与指纹，并检查唯一
                    if pubkey and pubkey.strip() != k.pubkey.strip():
                        algo, _ = parse_pubkey_get_algo_and_b64(pubkey)
                        fp = calc_sha256_fingerprint(pubkey)
                        exists = SSHKey.query.filter(SSHKey.fingerprint_sha256 == fp, SSHKey.id != kid).first()
                        if exists:
                            flash("该公钥（指纹）已存在，无法更新为重复值", "err")
                            return redirect(url_for("keys_page", edit=kid))
                        k.algo = algo
                        k.pubkey = pubkey
                        k.fingerprint_sha256 = fp
                    if title:
                        k.title = title
                    db.session.commit()
                    log("upd_key", f"{k.id}")
                    flash("公钥已更新", "ok")
                    return redirect(url_for("keys_page"))
                except Exception as e:
                    flash(f"更新失败：{e}", "err")

        elif act == "delete":
            kid = int(request.form.get("key_id","0"))
            k = SSHKey.query.get(kid)
            if not k:
                flash("未找到该公钥", "err")
            else:
                bound = ServerKey.query.filter_by(ssh_key_id=kid).first()
                if bound:
                    flash("该公钥仍绑定到服务器，无法删除（请先解绑）", "err")
                else:
                    db.session.delete(k); db.session.commit()
                    log("del_key", f"{kid}")
                    flash("已删除", "ok")
                    return redirect(url_for("keys_page"))

    keys = db.session.query(SSHKey, People.name).join(People, People.id==SSHKey.people_id)\
        .order_by(SSHKey.id.asc()).all()
    people = People.query.order_by(People.id.asc()).all()
    edit_id = request.args.get("edit", type=int)
    editing = SSHKey.query.get(edit_id) if edit_id else None

    return render_page("""
<h2>公钥</h2>

{% if editing %}
<form method="post" style="border:1px solid #ddd;padding:12px;margin-bottom:16px">
  <input type="hidden" name="act" value="update"/>
  <input type="hidden" name="key_id" value="{{ editing.id }}"/>
  <p><label>标题</label><br><input type="text" name="title" value="{{ editing.title }}"/></p>
  <p><label>公钥（单行）</label><br>
  <textarea name="pubkey" rows="4">{{ editing.pubkey }}</textarea></p>
  <p>
    <button class="btn" type="submit">保存修改</button>
    <a class="btn-blue" href="{{ url_for('keys_page') }}">取消</a>
  </p>
</form>
{% endif %}

<form method="post">
  <input type="hidden" name="act" value="add"/>
  <div class="row">
    <p>
      <label>人员</label><br>
      <select name="people_id">
        {% for p in people %}<option value="{{p.id}}">{{p.id}} - {{p.name}}</option>{% endfor %}
      </select>
    </p>
    <p><label>标题（可选；若公钥自带注释可留空）</label><br>
       <input type="text" name="title" placeholder="如 MacBook-2025"/></p>
  </div>
  <p><label>公钥（单行）</label><br>
  <textarea name="pubkey" rows="4" placeholder="ssh-ed25519 AAAAC3Nz... user@host"></textarea></p>
  <p><button class="btn" type="submit">新增公钥</button></p>
</form>

<table>
  <tr><th>ID</th><th>人员</th><th>标题</th><th>算法</th><th>指纹</th><th>状态</th><th>操作</th></tr>
  {% for k,pname in keys %}
  <tr>
    <td>{{ k.id }}</td>
    <td>{{ pname }}</td>
    <td>{{ k.title }}</td>
    <td>{{ k.algo }}</td>
    <td>{{ k.fingerprint_sha256 }}</td>
    <td>{{ 'active' if k.is_active else 'inactive' }}</td>
    <td>
      <a class="btn-blue" href="{{ url_for('keys_page', edit=k.id) }}">编辑</a>
      <form method="post" style="display:inline" onsubmit="return confirm('确认删除该公钥？');">
        <input type="hidden" name="act" value="delete"/>
        <input type="hidden" name="key_id" value="{{ k.id }}"/>
        <button class="btn-red" type="submit">删除</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
""", keys=keys, people=people, editing=editing)


# ========= 服务器 / 绑定 =========
@app.route("/servers", methods=["GET", "POST"])
def servers_page():
    require_login()
    if request.method == "POST":
        act = (request.form.get("act") or "add").strip()
        name = request.form.get("name", "").strip()
        host = request.form.get("host", "").strip()
        ssh_user = request.form.get("ssh_user", "").strip() or "root"

        if act == "add":
            if not (name and host):
                flash("请填写服务器名称与主机地址", "err")
                return redirect(url_for("servers_page"))

            # 先行校验，避免直接撞 UNIQUE
            if Server.query.filter_by(name=name).first():
                flash(f"服务器名称已存在：{name}", "err")
                return redirect(url_for("servers_page"))

            # 可选：主机重复给出提示（不改变库约束，仅提示）
            if Server.query.filter_by(host=host).first():
                flash(f"注意：主机 {host} 已存在，若确需重复可改名称区分。", "info")

            try:
                s = Server(name=name, host=host, ssh_user=ssh_user)
                db.session.add(s)
                db.session.commit()
                log("add_server", f"{s.id}:{s.name}@{s.host}")
                return redirect(url_for("servers_page"))
            except IntegrityError:
                db.session.rollback()
                flash(f"服务器名称已存在：{name}", "err")
                return redirect(url_for("servers_page"))
            except Exception as e:
                db.session.rollback()
                flash(f"新增服务器失败：{e}", "err")
                return redirect(url_for("servers_page"))

        elif act == "update":
            sid = int(request.form.get("sid", "0"))
            s = Server.query.get(sid)
            if not s:
                flash("未找到该服务器", "err")
                return redirect(url_for("servers_page"))
            if not (name and host):
                flash("请填写服务器名称与主机地址", "err")
                return redirect(url_for("servers_page", edit=sid))

            if Server.query.filter(Server.id != sid, Server.name == name).first():
                flash(f"服务器名称已存在：{name}", "err")
                return redirect(url_for("servers_page", edit=sid))
            if Server.query.filter(Server.id != sid, Server.host == host).first():
                flash(f"注意：主机 {host} 已存在，若确需重复可改名称区分。", "info")

            try:
                s.name = name
                s.host = host
                s.ssh_user = ssh_user
                db.session.commit()
                log("upd_server", f"{s.id}:{s.name}@{s.host}")
                flash("服务器已更新", "ok")
                return redirect(url_for("servers_page"))
            except Exception as e:
                db.session.rollback()
                flash(f"更新失败：{e}", "err")
                return redirect(url_for("servers_page", edit=sid))

        elif act == "delete":
            sid = int(request.form.get("sid", "0"))
            s = Server.query.get(sid)
            if not s:
                flash("未找到该服务器", "err")
                return redirect(url_for("servers_page"))
            try:
                ServerKey.query.filter_by(server_id=sid).delete()
                db.session.delete(s)
                db.session.commit()
                log("del_server", f"{sid}:{s.name}@{s.host}")
                flash("已删除", "ok")
            except Exception as e:
                db.session.rollback()
                flash(f"删除失败：{e}", "err")
            return redirect(url_for("servers_page"))

    rows = Server.query.order_by(Server.id.asc()).all()
    edit_id = request.args.get("edit", type=int)
    editing = Server.query.get(edit_id) if edit_id else None
    return render_page("""
<h2>服务器</h2>

{% if editing %}
<form method="post" class="row" style="border:1px solid #ddd;padding:12px;margin-bottom:16px">
  <input type="hidden" name="act" value="update"/>
  <input type="hidden" name="sid" value="{{ editing.id }}"/>
  <p><label>名称</label><br><input type="text" name="name" value="{{ editing.name }}"/></p>
  <p><label>主机（IP/域名）</label><br><input type="text" name="host" value="{{ editing.host }}"/></p>
  <p><label>SSH 用户</label><br><input type="text" name="ssh_user" value="{{ editing.ssh_user }}"/></p>
  <p><button class="btn" type="submit">保存修改</button></p>
  <p><a class="btn-blue" href="{{ url_for('servers_page') }}">取消</a></p>
</form>
{% endif %}

<form method="post" class="row">
  <input type="hidden" name="act" value="add"/>
  <p><label>名称</label><br><input type="text" name="name" placeholder="db-01"/></p>
  <p><label>主机（IP/域名）</label><br><input type="text" name="host" placeholder="10.0.0.23"/></p>
  <p><label>SSH 用户</label><br><input type="text" name="ssh_user" value="root"/></p>
  <p><button class="btn" type="submit">新增服务器</button></p>
</form>
<table>
  <tr><th>ID</th><th>名称</th><th>主机</th><th>SSH 用户</th><th>操作</th></tr>
  {% for r in rows %}
  <tr>
    <td>{{ r.id }}</td><td>{{ r.name }}</td><td>{{ r.host }}</td><td>{{ r.ssh_user }}</td>
    <td>
      <a class="btn-blue" href="{{ url_for('server_detail', sid=r.id) }}">详情</a>
      <a class="btn" href="{{ url_for('servers_page', edit=r.id) }}">编辑</a>
      <form method="post" style="display:inline" onsubmit="return confirm('确认删除该服务器？');">
        <input type="hidden" name="act" value="delete"/>
        <input type="hidden" name="sid" value="{{ r.id }}"/>
        <button class="btn-red" type="submit">删除</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
""", rows=rows, editing=editing)

@app.route("/bindings", methods=["GET", "POST"])
def bindings_page():
    require_login()
    if request.method == "POST":
        act = request.form.get("act")
        sid = int(request.form.get("server_id", "0"))

        if act == "attach":
            pid = int(request.form.get("people_id", "0"))
            s = Server.query.get(sid)
            p = People.query.get(pid)
            if not (s and p):
                flash("请选择有效的服务器与人员", "err")
                return redirect(url_for("bindings_page"))

            keys = SSHKey.query.filter_by(people_id=pid, is_active=True).all()
            if not keys:
                flash("该人员没有激活的公钥", "err")
                return redirect(url_for("bindings_page"))

            add_cnt, skip_cnt = 0, 0
            for k in keys:
                exist = ServerKey.query.filter_by(server_id=sid, ssh_key_id=k.id).first()
                if exist:
                    skip_cnt += 1
                else:
                    db.session.add(ServerKey(server_id=sid, ssh_key_id=k.id))
                    add_cnt += 1
            db.session.commit()
            log("attach_person_keys", f"sid={sid}, pid={pid}, add={add_cnt}, skip={skip_cnt}")
            flash(f"已绑定 {add_cnt} 把公钥（跳过重复 {skip_cnt}）", "ok")
            return redirect(url_for("bindings_page"))

        elif act == "detach":
            sid = int(request.form.get("server_id","0"))
            kid = int(request.form.get("key_id","0"))
            sk = ServerKey.query.filter_by(server_id=sid, ssh_key_id=kid).first()
            if sk:
                db.session.delete(sk); db.session.commit()
                log("detach_key", f"sid={sid}, kid={kid}")
                flash("已解绑", "ok")
            else:
                flash("未找到该绑定", "err")
            return redirect(url_for("bindings_page"))

    servers = Server.query.order_by(Server.id.asc()).all()
    people = People.query.order_by(People.id.asc()).all()

    # 展示当前绑定（携带人员名）
    binds = db.session.query(ServerKey, SSHKey, Server.name, SSHKey.title, People.name)\
        .join(SSHKey, SSHKey.id == ServerKey.ssh_key_id)\
        .join(Server, Server.id == ServerKey.server_id)\
        .join(People, People.id == SSHKey.people_id)\
        .order_by(ServerKey.server_id.asc(), SSHKey.id.asc()).all()

    return render_page("""
<h2>绑定</h2>
<form method="post" class="row">
  <input type="hidden" name="act" value="attach"/>
  <p><label>服务器</label><br>
     <select name="server_id">
      {% for s in servers %}<option value="{{s.id}}">{{s.id}} - {{s.name}}</option>{% endfor %}
     </select>
  </p>
  <p><label>人员</label><br>
     <select name="people_id">
      {% for p in people %}<option value="{{p.id}}">{{p.id}} - {{p.name}}</option>{% endfor %}
     </select>
  </p>
  <p><button class="btn" type="submit">绑定该人员的所有激活公钥</button></p>
</form>

<table>
  <tr><th>服务器</th><th>人员</th><th>公钥标题</th><th>操作</th></tr>
  {% for sk,k,sname,ktitle,pname in binds %}
  <tr>
    <td>{{ sname }}</td><td>{{ pname }}</td><td>{{ ktitle }}</td>
    <td>
      <form method="post" style="display:inline">
        <input type="hidden" name="act" value="detach"/>
        <input type="hidden" name="server_id" value="{{ sk.server_id }}"/>
        <input type="hidden" name="key_id" value="{{ sk.ssh_key_id }}"/>
        <button class="btn-red" type="submit">解绑</button>
      </form>
    </td>
  </tr>
  {% endfor %}
</table>
""", servers=servers, people=people, binds=binds)


@app.route("/server/<int:sid>")
def server_detail(sid: int):
    require_login()
    s = Server.query.get_or_404(sid)
    ak = build_authorized_keys_for_server(sid)
    binds = db.session.query(ServerKey, SSHKey).join(SSHKey, SSHKey.id==ServerKey.ssh_key_id)\
        .filter(ServerKey.server_id==sid, SSHKey.is_active==True).all()
    return render_page("""
<h2>服务器详情：{{ s.name }} ({{ s.host }})</h2>
<p>SSH 用户：{{ s.ssh_user }}</p>
<form method="post" action="{{ url_for('push_server', sid=s.id) }}" style="display:inline-block;margin-right:8px" onsubmit="return sk_fill(this)">
  <button class="btn" type="submit">合并下发 authorized_keys</button>
</form>

<form method="post" action="{{ url_for('server_inspect', sid=s.id) }}" style="display:inline-block" onsubmit="return sk_fill(this)">
  <input type="hidden" name="op" value="view"/>
  <button class="btn-blue" type="submit">读取目标 authorized_keys</button>
</form>

<h3>已绑定的公钥</h3>
<table>
  <tr><th>Key ID</th><th>标题</th><th>指纹</th></tr>
  {% for sk,k in binds %}
    <tr><td>{{ k.id }}</td><td>{{ k.title }}</td><td>{{ k.fingerprint_sha256 }}</td></tr>
  {% endfor %}
</table>

<h3>即将下发的 authorized_keys（预览）</h3>
<pre>{{ ak }}</pre>
""", s=s, binds=binds, ak=ak)

@app.route("/server/<int:sid>/inspect", methods=["GET", "POST"])
def server_inspect(sid: int):
    require_login()
    s = Server.query.get_or_404(sid)

    op = (request.form.get("op") or "").strip()
    # 只有 op=merge 或者真有勾选项(del_fp) 才执行“合并并下发”
    if request.method == "POST" and (op == "merge" or request.form.getlist("del_fp")):
        # 接收勾选要删除的指纹
        dels = set(request.form.getlist("del_fp"))
        try:
            remote = fetch_remote_authorized_keys(s)
        except Exception as e:
            flash(f"读取远端 authorized_keys 失败：{e}", "err")
            return redirect(url_for("server_detail", sid=sid))

        # 解析远端行（保留原顺序）
        remote_entries = []  # [(fp or None, line)]
        for line in remote.splitlines():
            p = parse_pubkey_from_any_line(line)
            if not p:
                remote_entries.append((None, line.strip()))
            else:
                fp = calc_sha256_fingerprint(f"{p[0]} {p[1]}")
                # 保留原注释行内容
                remote_entries.append((fp, f"{p[0]} {p[1]} {p[2]}".strip()))

        db_map = db_lines_map_for_server(sid)
        db_fps = set(db_map.keys())

        # 1) 先保留远端未知项（未勾选删除，且不在 db 管理范围）
        final_lines = []
        kept_unknown, removed, replaced, added = 0, 0, 0, 0
        for fp, line in remote_entries:
            if fp is None:
                final_lines.append(line);  # 注释/无效行原样保留
                continue
            if fp in dels:
                removed += 1
                continue
            if fp in db_fps:
                # 由系统管理，后面用系统行覆盖；这里先跳过
                continue
            final_lines.append(line); kept_unknown += 1

        # 2) 再加上系统管理的 key（覆盖远端同指纹）
        for fp, line in db_map.items():
            final_lines.append(line)
            if any(fp == e[0] for e in remote_entries):
                replaced += 1
            else:
                added += 1

        new_content = ("\n".join([l for l in final_lines if l.strip() != ""]) + "\n") if final_lines else ""

        try:
            info = remote_write_authorized_keys_via_ssh(s, new_content)
            flash(f"合并下发完成：新增 {added}，替换 {replaced}，删除 {removed}，保留未知 {kept_unknown}。备份：{info.get('backup')}", "ok")
        except Exception as e:
            flash(f"合并下发失败：{e}", "err")
        return redirect(url_for("server_detail", sid=sid))

    # GET：展示远端现状 + 匹配
    try:
        content = fetch_remote_authorized_keys(s)
    except Exception as e:
        flash(f"读取远端 authorized_keys 失败：{e}", "err")
        return redirect(url_for("server_detail", sid=sid))

    rows = []
    for line in content.splitlines():
        parsed = parse_pubkey_from_any_line(line)
        if not parsed:
            continue
        algo, b64, comment = parsed
        fp = calc_sha256_fingerprint(f"{algo} {b64}")
        key = SSHKey.query.filter_by(fingerprint_sha256=fp).first()
        person = People.query.get(key.people_id).name if key else ""
        title = key.title if key else ""
        rows.append({"algo": algo, "fingerprint": fp, "comment": comment, "person": person, "title": title, "known": bool(key)})

    return render_page("""
<h2>远端 authorized_keys（只读/可合并下发）：{{ s.name }} ({{ s.host }})</h2>
<p class="muted">勾选要“删除”的远端 key；提交后系统会合并：保留未勾选的未知项 + 覆盖/补齐系统管理的 key。</p>

<form method="post" onsubmit="return sk_fill(this)">
  <input type="hidden" name="op" value="merge"/>
<table>
  <tr><th>删除?</th><th>算法</th><th>指纹</th><th>远端注释</th><th>匹配人员</th><th>匹配 Key 标题</th></tr>
  {% for r in rows %}
  <tr>
    <td><input type="checkbox" name="del_fp" value="{{ r.fingerprint }}" {% if r.known %}{% endif %}></td>
    <td>{{ r.algo }}</td>
    <td>{{ r.fingerprint }}</td>
    <td>{{ r.comment }}</td>
    <td>{{ r.person or '未匹配' }}</td>
    <td>{{ r.title or '' }}</td>
  </tr>
  {% endfor %}
</table>
<p>
  <button class="btn" type="submit">合并并下发</button>  
  <a class="btn-blue" href="{{ url_for('server_detail', sid=s.id) }}">返回服务器详情</a>
</p>
</form>
""", s=s, rows=rows)

@app.route("/server/<int:sid>/push", methods=["POST"])
def push_server(sid: int):
    """合并下发：补齐系统管理 key，保留远端未知 key（不勾选删除时等价于此）"""
    require_login()
    s = Server.query.get_or_404(sid)

    try:
        remote = fetch_remote_authorized_keys(s)
    except Exception as e:
        flash(f"读取远端 authorized_keys 失败：{e}", "err")
        return redirect(url_for("server_detail", sid=sid))

    # 解析远端
    remote_entries = []
    for line in remote.splitlines():
        p = parse_pubkey_from_any_line(line)
        if not p:
            remote_entries.append((None, line.strip()))
        else:
            fp = calc_sha256_fingerprint(f"{p[0]} {p[1]}")
            remote_entries.append((fp, f"{p[0]} {p[1]} {p[2]}".strip()))

    db_map = db_lines_map_for_server(sid)
    db_fps = set(db_map.keys())

    # 合并：保留未知（非系统管理）+ 系统管理覆盖/补齐
    final_lines = []
    kept_unknown, replaced, added = 0, 0, 0
    for fp, line in remote_entries:
        if fp is None:
            final_lines.append(line); continue
        if fp in db_fps:
            continue
        final_lines.append(line); kept_unknown += 1

    for fp, line in db_map.items():
        final_lines.append(line)
        if any(fp == e[0] for e in remote_entries):
            replaced += 1
        else:
            added += 1

    new_content = ("\n".join([l for l in final_lines if l.strip() != ""]) + "\n") if final_lines else ""
    try:
        info = remote_write_authorized_keys_via_ssh(s, new_content)
        flash(f"合并下发完成：新增 {added}，替换 {replaced}，保留未知 {kept_unknown}。备份：{info.get('backup')}", "ok")
    except Exception as e:
        flash(f"Push 失败：{e}", "err")

    return redirect(url_for("server_detail", sid=sid))

# ========= 生成 authorized_keys =========
def build_authorized_keys_for_server(sid: int) -> str:
    q = db.session.query(SSHKey).join(ServerKey, ServerKey.ssh_key_id == SSHKey.id)\
        .filter(ServerKey.server_id == sid, SSHKey.is_active == True).order_by(SSHKey.id.asc())
    lines = []
    for k in q.all():
        parts = k.pubkey.strip().split()
        if len(parts) >= 2:
            algo, b64 = parts[0], parts[1]
            comment = parts[2] if len(parts) >= 3 else f"{k.title}"
            comment = f"{comment}:{k.fingerprint_sha256}"
            lines.append(f"{algo} {b64} {comment}")
    return "\n".join(lines) + ("\n" if lines else "")

# ========= 启动 =========
def ensure_dirs():
    os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)

with app.app_context():
    db.create_all()
ensure_dirs()

if __name__ == "__main__":
    # 开发期用 HTTP；生产请放到 Nginx 反代 TLS
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "15443")), debug=False)
