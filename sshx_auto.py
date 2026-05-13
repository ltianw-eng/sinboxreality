import os
import signal
import subprocess
import sys
import time
import threading
import json
from pathlib import Path
from datetime import datetime, timedelta

# 🔧 配置文件路径
CONFIG_FILE = Path.home() / ".config/sshx_colab.json"
CONFIG_FILE.parent.mkdir(exist_ok=True)

def load_config():
    """加载持久化配置"""
    default_config = {
        "last_session_info": {"link": "", "expires_at": "2000-01-01T00:00:00Z"},
        "auto_renew_enabled": True,
        "auto_open_browser": False,
        "session_timeout_minutes": 50,  # 预防性提前 10 分钟续期
        "sshx_url": "https://sshx.io/get",
        "expected_sha256": None  # 如需校验，填入官方 SHA256
    }
    if CONFIG_FILE.exists():
        try:
            saved = json.loads(CONFIG_FILE.read_text())
            default_config.update(saved)
        except:
            pass  # 忽略损坏的配置文件
    return default_config

def save_config(config):
    """保存配置到文件"""
    try:
        CONFIG_FILE.write_text(json.dumps(config, indent=2))
    except Exception as e:
        print(f"⚠️ 保存配置失败: {e}")

# 加载配置
config = load_config()

# 🔧 配置项
SSHX_URL = config["sshx_url"]
EXPECTED_SHA256 = config["expected_sha256"]
AUTO_RENEW = config["auto_renew_enabled"]
AUTO_OPEN_BROWSER = config["auto_open_browser"]
SESSION_TIMEOUT_MINUTES = config["session_timeout_minutes"]

# 路径配置
INSTALL_DIR = Path("/tmp/sshx_launcher")
PID_FILE = INSTALL_DIR / "sshx.pid"
LOG_FILE = INSTALL_DIR / "sshx.log"
LAST_LINK_FILE = INSTALL_DIR / "last_link.txt"

def log_message(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}\n"
    print(full_msg.strip())
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(full_msg)

def copy_to_clipboard(text):
    """尝试复制文本到剪贴板（通过 JavaScript）"""
    try:
        from IPython.display import Javascript
        # 注入 JS 来复制到剪贴板
        js_code = f"""
        navigator.clipboard.writeText('{text}').then(() => {{
            console.log('✅ 链接已复制到剪贴板');
        }}).catch(err => {{
            console.error('❌ 复制失败:', err);
        }});
        """
        display(Javascript(js_code))
    except ImportError:
        print(f"📋 链接已生成: {text} (无法自动复制，请手动 Ctrl+C)")

def open_in_browser(url):
    """尝试在浏览器中打开 URL"""
    try:
        from IPython.display import HTML
        html_code = f'<a href="{url}" target="_blank">🔗 点击此处打开链接</a>'
        display(HTML(html_code))
    except ImportError:
        print(f"🌐 浏览器链接: {url}")

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False

def cleanup_previous_instances():
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if is_process_running(old_pid):
                log_message(f"⚠️ 发现旧实例 PID={old_pid}，正在终止...")
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(2)
                if is_process_running(old_pid):
                    os.kill(old_pid, signal.SIGKILL)
            PID_FILE.unlink()
        except (ValueError, ProcessLookupError, PermissionError) as e:
            log_message(f"⚠️ 清理旧实例失败: {e}")

def download_and_verify_installer():
    installer_path = INSTALL_DIR / "get_sshx.sh"
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    
    log_message("⬇️ 开始下载 sshx 安装脚本...")
    cmd = ["curl", "--retry", "5", "--retry-delay", "2", "-sSL", SSHX_URL, "-o", str(installer_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"下载失败: {result.stderr}")

    if EXPECTED_SHA256:
        import hashlib
        actual_hash = hashlib.sha256(installer_path.read_bytes()).hexdigest()
        if actual_hash != EXPECTED_SHA256:
            raise RuntimeError(f"校验失败! 期望: {EXPECTED_SHA256}, 实际: {actual_hash}")
        log_message("✅ 安装脚本校验通过!")

    installer_path.chmod(0o755)
    return installer_path

def launch_sshx_with_monitoring():
    try:
        installer_path = download_and_verify_installer()
    except Exception as e:
        log_message(f"❌ 下载/校验失败: {e}")
        return None, -1

    log_message("🚀 启动 sshx 实例...")
    
    env = os.environ.copy()
    env["PATH"] = f"{INSTALL_DIR}:{env.get('PATH', '')}"

    process = subprocess.Popen(
        [str(installer_path), "run"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        env=env
    )

    with open(PID_FILE, "w") as f:
        f.write(str(process.pid))
    log_message(f"mPid={process.pid} 已记录")

    success_flag_found = False
    new_link = ""
    for line in iter(process.stdout.readline, ""):
        log_message(f"sshx 输出: {line.strip()}")
        if "sshx.io/s/" in line and "#" in line:
            new_link = line.strip().split("Link: ")[-1] if "Link:" in line else line.strip()
            log_message(f"🎉 成功获取新链接: {new_link}")
            success_flag_found = True
            break  # 找到链接后立即停止读取

    # 非阻塞：不等待进程结束，直接返回
    return process, new_link if success_flag_found else None

def check_and_renew_session():
    """检查会话是否即将过期，如是则自动续期"""
    global config
    last_info = config.get("last_session_info", {})
    expires_at_str = last_info.get("expires_at", "")
    
    try:
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        now = datetime.now(expires_at.tzinfo)
        time_left = expires_at - now
        
        if time_left.total_seconds() < 60 * 5:  # 少于 5 分钟则续期
            log_message(f"⏰ 会话即将过期 ({time_left})，开始自动续期...")
            return True
    except:
        pass  # 解析时间失败，忽略
    return False

def main():
    global config
    log_message("=== 启动终极版 Colab sshx ===")
    
    # 检查是否需要续期
    if AUTO_RENEW and check_and_renew_session():
        cleanup_previous_instances()
        _, new_link = launch_sshx_with_monitoring()
        if new_link:
            # 更新配置
            expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            config["last_session_info"] = {"link": new_link, "expires_at": expires_at.isoformat()}
            save_config(config)
            
            print("\n" + "="*50)
            print("🔗 新链接已生成并自动复制！")
            print(f"🌐 链接: {new_link}")
            print(f"⏰ 有效期至: {expires_at.strftime('%Y-%m-%d %H:%M:%S')} (本地时间)")
            print("="*50)
            
            copy_to_clipboard(new_link)
            if AUTO_OPEN_BROWSER:
                open_in_browser(new_link)
        else:
            log_message("❌ 自动续期失败")
    else:
        # 正常启动流程
        cleanup_previous_instances()
        _, new_link = launch_sshx_with_monitoring()
        if new_link:
            expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
            config["last_session_info"] = {"link": new_link, "expires_at": expires_at.isoformat()}
            save_config(config)
            
            print("\n" + "="*50)
            print("🎉 sshx 启动成功！")
            print(f"🔗 链接: {new_link}")
            print(f"⏰ 有效期至: {expires_at.strftime('%Y-%m-%d %H:%M:%S')} (本地时间)")
            print("💡 如需修改配置，编辑 ~/.config/sshx_colab.json")
            print("="*50)
            
            copy_to_clipboard(new_link)
            if AUTO_OPEN_BROWSER:
                open_in_browser(new_link)
        else:
            log_message("❌ sshx 启动失败")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("🛑 用户中断")
    except Exception as e:
        log_message(f"💥 错误: {e}")
