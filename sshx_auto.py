%%writefile /content/sshx_auto.py
import subprocess
import sys

def start_sshx():
    """一键启动 sshx 终极版"""
    print("🚀 正在启动 sshx 终极版...")
    result = subprocess.run([
        sys.executable, "-c", 
        """
import os
import signal
import subprocess
import sys
import time
import threading
import json
from pathlib import Path
from datetime import datetime, timedelta

# --- 配置文件 ---
CONFIG_FILE = Path.home() / '.config/sshx_colab.json'
CONFIG_FILE.parent.mkdir(exist_ok=True)

def load_config():
    default_config = {
        'last_session_info': {'link': '', 'expires_at': '2000-01-01T00:00:00Z'},
        'auto_renew_enabled': True,
        'auto_open_browser': False,
        'session_timeout_minutes': 50,
        'sshx_url': 'https://sshx.io/get',
        'expected_sha256': None
    }
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            default_config.update(saved)
        except: pass
    return default_config

def save_config(config):
    try: CONFIG_FILE.write_text(json.dumps(config, indent=2))
    except Exception as e: print(f'⚠️ 保存配置失败: {e}')

config = load_config()
SSHX_URL = config['sshx_url']
EXPECTED_SHA256 = config['expected_sha256']
AUTO_RENEW = config['auto_renew_enabled']
AUTO_OPEN_BROWSER = config['auto_open_browser']
SESSION_TIMEOUT_MINUTES = config['session_timeout_minutes']

INSTALL_DIR = Path('/tmp/sshx_launcher')
PID_FILE = INSTALL_DIR / 'sshx.pid'
LOG_FILE = INSTALL_DIR / 'sshx.log'

def log_message(msg):
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    full_msg = f'[{timestamp}] {msg}\\n'
    print(full_msg.strip())
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f: f.write(full_msg)

def copy_to_clipboard(text):
    try:
        from IPython.display import Javascript
        js_code = f\"\"\"
        navigator.clipboard.writeText('{text}').then(() => {{
            console.log('✅ 链接已复制到剪贴板');
        }}).catch(err => {{
            console.error('❌ 复制失败:', err);
        }});
        \"\"\"
        display(Javascript(js_code))
    except ImportError: print(f'📋 链接: {text}')

def open_in_browser(url):
    try:
        from IPython.display import HTML
        html_code = f'<a href=\"{url}\" target=\"_blank\">🔗 点击打开</a>'
        display(HTML(html_code))
    except ImportError: print(f'🌐 链接: {url}')

def is_process_running(pid):
    try: os.kill(pid, 0); return True
    except (ProcessLookupError, OSError): return False

def cleanup_previous_instances():
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if is_process_running(old_pid):
                log_message(f'⚠️ 清理旧实例 PID={old_pid}')
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(2)
                if is_process_running(old_pid): os.kill(old_pid, signal.SIGKILL)
            PID_FILE.unlink()
        except Exception as e: log_message(f'⚠️ 清理失败: {e}')

def download_and_verify_installer():
    installer_path = INSTALL_DIR / 'get_sshx.sh'
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    log_message('⬇️ 下载 sshx...')
    cmd = ['curl', '--retry', '5', '--retry-delay', '2', '-sSL', SSHX_URL, '-o', str(installer_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0: raise RuntimeError(f'下载失败: {result.stderr}')
    if EXPECTED_SHA256:
        import hashlib
        actual_hash = hashlib.sha256(installer_path.read_bytes()).hexdigest()
        if actual_hash != EXPECTED_SHA256: raise RuntimeError(f'校验失败!')
        log_message('✅ 校验通过!')
    installer_path.chmod(0o755)
    return installer_path

def launch_sshx_with_monitoring():
    try: installer_path = download_and_verify_installer()
    except Exception as e: log_message(f'❌ 下载失败: {e}'); return None, -1

    log_message('🚀 启动 sshx...')
    env = os.environ.copy()
    env['PATH'] = f'{INSTALL_DIR}:{env.get('PATH', '')}'
    process = subprocess.Popen([str(installer_path), 'run'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1, env=env)
    with open(PID_FILE, 'w') as f: f.write(str(process.pid))
    log_message(f'mPid={process.pid} 已记录')

    success_flag_found = False
    new_link = ''
    for line in iter(process.stdout.readline, ''):
        log_message(f'sshx 输出: {line.strip()}')
        if 'sshx.io/s/' in line and '#' in line:
            new_link = line.strip().split('Link: ')[-1] if 'Link:' in line else line.strip()
            log_message(f'🎉 成功获取: {new_link}')
            success_flag_found = True
            break
    return process, new_link if success_flag_found else None

def check_and_renew_session():
    global config
    last_info = config.get('last_session_info', {})
    expires_at_str = last_info.get('expires_at', '')
    try:
        from datetime import datetime, timedelta
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        now = datetime.now(expires_at.tzinfo)
        time_left = expires_at - now
        if time_left.total_seconds() < 60 * 5: return True
    except: pass
    return False

def main():
    global config
    log_message('=== 启动终极版 sshx ===')
    if AUTO_RENEW and check_and_renew_session():
        log_message('⏰ 自动续期...')
        cleanup_previous_instances()
        _, new_link = launch_sshx_with_monitoring()
        if new_link:
            expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            config['last_session_info'] = {'link': new_link, 'expires_at': expires_at.isoformat()}
            save_config(config)
            # ===== 🔗 强制显示链接 (新增) =====
            print('\\n' + '='*80)
            print('🔗 SSHx 会话已启动！请复制以下链接到浏览器打开：')
            print()
            print(f'🌐 链接: {new_link}')
            print()
            print('💡 重要提示：')
            print('   • 请在新标签页中打开此链接')
            print('   • 链接有效期 50 分钟，支持自动续期')
            print('   • 请勿刷新当前 Colab 页面')
            print('='*80)
            # ===== 结束新增 =====
            copy_to_clipboard(new_link)
            if AUTO_OPEN_BROWSER: open_in_browser(new_link)
        else: log_message('❌ 续期失败')
    else:
        cleanup_previous_instances()
        _, new_link = launch_sshx_with_monitoring()
        if new_link:
            expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            config['last_session_info'] = {'link': new_link, 'expires_at': expires_at.isoformat()}
            save_config(config)
            # ===== 🔗 强制显示链接 (新增) =====
            print('\\n' + '='*80)
            print('🎉 启动成功！')
            print('🔗 SSHx 会话已启动！请复制以下链接到浏览器打开：')
            print()
            print(f'🌐 链接: {new_link}')
            print()
            print('💡 重要提示：')
            print('   • 请在新标签页中打开此链接')
            print('   • 链接有效期 50 分钟，支持自动续期')
            print('   • 请勿刷新当前 Colab 页面')
            print('='*80)
            # ===== 结束新增 =====
            copy_to_clipboard(new_link)
            if AUTO_OPEN_BROWSER: open_in_browser(new_link)
        else: log_message('❌ 启动失败')

if __name__ == '__main__':
    try: main()
    except KeyboardInterrupt: log_message('🛑 中断')
    except Exception as e: log_message(f'💥 错误: {e}')
        """
    ])
    if result.returncode == 0:
        print("✅ sshx 已启动，请查看上方链接")
    else:
        print(f"❌ 启动失败，退出码: {result.returncode}")

# === 以后只需运行这一行即可启动 ===
start_sshx()
