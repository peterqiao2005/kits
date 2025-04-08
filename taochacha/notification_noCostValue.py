import psycopg2
import smtplib
from configparser import ConfigParser
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

def load_config(file='config.ini'):
    config = ConfigParser()
    config.read(file)
    return config

def send_email(smtp_server, smtp_port, account, password, receiver_str, subject, html_body):
    receiver_list = [r.strip() for r in receiver_str.split(',') if r.strip()]

    msg = MIMEMultipart('alternative')
    msg['From'] = account
    msg['To'] = ", ".join(receiver_list)
    msg['Subject'] = Header(subject, 'utf-8')

    msg.attach(MIMEText(html_body, 'html', 'utf-8'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(account, password)
        server.sendmail(account, receiver_list, msg.as_string())
        print(f"✅ 邮件发送成功，已发送给：{', '.join(receiver_list)}")

def generate_html_table(data):
    html = """
    <html>
      <body>
        <p>以下机器的 <b>cost</b> 字段为 0 或 NULL，请尽快处理：</p>
        <table border="1" cellpadding="5" cellspacing="0">
          <tr><th>ID</th><th>Name</th><th>Host</th><th>Model</th><th>Cost</th></tr>
    """
    for row in data:
        id_, name, ip, model, cost = row
        html += f"<tr><td>{id_}</td><td>{name}</td><td>{ip}</td><td>{model}</td><td>{cost}</td></tr>\n"
    html += "</table></body></html>"
    return html

def check_database_and_notify():
    config = load_config()

    db_cfg = config['database']
    email_cfg = config['email']

    try:
        conn = psycopg2.connect(
            host=db_cfg['host'],
            port=db_cfg.getint('port'),
            dbname=db_cfg['dbname'],
            user=db_cfg['user'],
            password=db_cfg['password']
        )
        cur = conn.cursor()
        cur.execute("""
                SELECT id, name, ip, model, cost FROM machine_info 
                WHERE (name IS NOT NULL AND NAME <> '')
                AND (cost IS NULL OR cost = 0)
            """)
        rows = cur.fetchall()

        if rows:
            html_body = generate_html_table(rows)
            send_email(
                smtp_server=email_cfg['smtp_server'],
                smtp_port=email_cfg.getint('smtp_port'),
                account=email_cfg['email_account'],
                password=email_cfg['email_password'],
                receiver_str=email_cfg['email_receiver'],
                subject='机器信息提醒：存在未设置成本项',
                html_body=html_body
            )
        else:
            print("✅ 所有机器的 cost 字段已正确设置")
        cur.close()
        conn.close()
    except Exception as e:
        print("❌ 检查失败:", e)

if __name__ == '__main__':
    check_database_and_notify()
