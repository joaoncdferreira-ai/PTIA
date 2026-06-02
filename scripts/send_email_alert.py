import os
import sys
import json
from pathlib import Path
import urllib.request
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configurar PYTHONPATH
ROOT = Path(__file__).resolve().parents[1]

def send_via_smtp(to_email, subject, message):
    smtp_host = os.getenv("PTIA_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("PTIA_SMTP_PORT", "587"))
    smtp_user = os.getenv("PTIA_SMTP_USER", "")
    smtp_pass = os.getenv("PTIA_SMTP_PASS", "") # Deve ser uma App Password se for Gmail
    
    if not smtp_user or not smtp_pass:
        return False, "SMTP credentials missing in .env.local"
        
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Subject"] = subject
        
        msg.attach(MIMEText(message, "plain", "utf-8"))
        
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())
        server.quit()
        return True, "Email sent via SMTP successfully"
    except Exception as e:
        return False, f"SMTP Error: {str(e)}"

def send_via_web3forms(to_email, access_key, subject, message):
    url = "https://api.web3forms.com/submit"
    payload = {
        "access_key": access_key,
        "subject": subject,
        "from_name": "PTIA Co-Piloto",
        "email": to_email,
        "message": message
    }
    
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, 
            data=data, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15) as res:
            response = json.loads(res.read().decode("utf-8"))
            if response.get("success"):
                return True, "Email sent via Web3Forms successfully"
            else:
                return False, f"Web3Forms API Error: {response.get('message')}"
    except Exception as e:
        return False, f"Web3Forms Connection Error: {str(e)}"

def main():
    if len(sys.argv) < 3:
        print("Usage: python send_email_alert.py <Subject> <Message>")
        sys.exit(1)
        
    subject = sys.argv[1]
    message = sys.argv[2]
    
    # 1. Carregar .env.local se existir
    env_local = ROOT / ".env.local"
    if env_local.exists():
        for line in env_local.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()
                
    # 2. Carregar configuracao de alertas
    config_path = ROOT / "config" / "alert_config.json"
    to_email = os.getenv("PTIA_ALERT_EMAIL", "")
    web3forms_key = os.getenv("PTIA_WEB3FORMS_KEY", "")
    
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            to_email = to_email or config.get("to_email", "")
            web3forms_key = web3forms_key or config.get("web3forms_key", "")
        except Exception:
            pass
            
    if not to_email:
        print("Error: Recipient email address not configured. Please define PTIA_ALERT_EMAIL.")
        sys.exit(1)
        
    # 3. Tentar SMTP primeiro se configurado
    if os.getenv("PTIA_SMTP_USER") and os.getenv("PTIA_SMTP_PASS"):
        success, info = send_via_smtp(to_email, subject, message)
        print(info)
        if success:
            sys.exit(0)
            
    # 4. Caso contrario, usar Web3Forms se a chave existir
    if web3forms_key:
        success, info = send_via_web3forms(to_email, web3forms_key, subject, message)
        print(info)
        if success:
            sys.exit(0)
            
    print("Error: No valid email delivery method configured (SMTP or Web3Forms key).")
    sys.exit(1)

if __name__ == "__main__":
    main()
