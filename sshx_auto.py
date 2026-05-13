import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# 🔧 配置区域（可根据需要调整）
SSHX_URL = "https://sshx.io/get"
SSHX_BINARY_NAME = "sshx"
INSTALL_DIR = Path("/tmp/sshx_launcher")
PID_FILE = INSTALL_DIR / "sshx.pid"
LOG_FILE = INSTALL_DIR / "sshx.log"

# 🔒 官方校验哈希（2024-05-13 最新版参考值，请务必核对官方发布页更新）
# 可从 https://github.com/sshx/sshx/releases 获取最新 SHA256
EXPECTED_SHA256 = None  # 👉 建议：填入真实哈希值以启用校验；设为 None 则跳过
# 示例（请勿直接使用，需替换为最新）：
# EXPECTED_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"  # 空文件示例，非真实值

def log_message(msg):
    """记录日志并打印到控制台 —— 已修复目录未创建问题"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    full_msg = f"[{timestamp}] {msg}\n"
    print(full_msg.strip())
    
    # ✅ 关键修复：确保日志目录存在（即使在首次调用时也安全）
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(full_msg)
    except Exception as e:
        # 即使日志写入失败，也不应中断主流程（降级处理）
        print(f"⚠️ 日志写入失败（非致命）: {e}")

def is_process_running(pid):
    """检查 PID 是否仍在运行"""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False

def cleanup_previous_instances():
    """清理之前的实例"""
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            if is_process_running(old_pid):
                log_message(f"⚠️ 发现旧实例 PID={old_pid}，正在终止...")
                os.kill(old_pid, signal.SIGTERM)
                time.sleep(2)
                if is_process_running(old_pid):
                    os.kill(old_pid, signal.SIGKILL)
                    log_message(f"🔴 强制终止 PID={old_pid}")
            else:
                log_message(f"ℹ️ PID 文件存在但进程 {old_pid} 已退出，清理残留文件。")
            PID_FILE.unlink()
        except (ValueError, ProcessLookupError, PermissionError, OSError) as e:
            log_message(f"⚠️ 清理旧实例时出错: {type(e).__name__}: {e}")

def download_and_verify_installer():
    """下载并校验安装脚本"""
    installer_path = INSTALL_DIR / "get_sshx.sh"
    
    # 确保安装目录存在（双重保险）
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    
    log_message("⬇️ 开始下载 sshx 安装脚本...")
    
    # 使用 curl（Colab 默认有 curl），带重试机制
    cmd = [
        "curl", "--retry", "5", "--retry-delay", "2",
        "-sSL", SSHX_URL, "-o", str(installer_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"下载失败（HTTP/网络错误）:\nstdout: {result.stdout}\nstderr: {result.stderr}")

    # 🔍 校验哈希（如果提供了 EXPECTED_SHA256）
    if EXPECTED_SHA256:
        import hashlib
        try:
            actual_hash = hashlib.sha256(installer_path.read_bytes()).hexdigest()
            if actual_hash != EXPECTED_SHA256:
                raise RuntimeError(f"校验失败! 期望 SHA256: {EXPECTED_SHA256}, 实际: {actual_hash}")
            log_message("✅ 安装脚本 SHA256 校验通过!")
        except FileNotFoundError:
            raise RuntimeError("下载的安装脚本文件不存在，无法校验")
        except Exception as e:
            raise RuntimeError(f"校验过程中出错: {e}")
    else:
        log_message("⚠️ 跳过 SHA256 校验（EXPECTED_SHA256 未设置）")

    # 设置可执行权限
    installer_path.chmod(0o755)
    return installer_path

def launch_sshx_with_monitoring():
    """启动 sshx 并监控其状态"""
    try:
        installer_path = download_and_verify_installer()
    except Exception as e:
        log_message(f"❌ 下载/校验失败: {e}")
        return False, -1

    log_message("🚀 启动 sshx 实例...")
    
    env = os.environ.copy()
    env["PATH"] = f"{INSTALL_DIR}:{env.get('PATH', '')}"

    # 启动 sshx run 命令
    process = subprocess.Popen(
        [str(installer_path), "run"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        bufsize=1,
        env=env
    )

    # 记录 PID
    with open(PID_FILE, "w") as f:
        f.write(str(process.pid))
    log_message(f"mPid={process.pid} 已记录到 {PID_FILE}")

    success_flag_found = False
    # 实时读取输出
    for line in iter(process.stdout.readline, ""):
        log_message(f"sshx 输出: {line.strip()}")
        if "sshx.io/s/" in line and "#" in line:  # 匹配会话链接格式
            log_message(f"🎉 成功获取 sshx 链接: {line.strip()}")
            success_flag_found = True

    process.wait()
    ret_code = process.returncode
    log_message(f"🔴 sshx 进程已退出，返回码: {ret_code}")

    # 清理 PID 文件
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except OSError as e:
            log_message(f"⚠️ 清理 PID 文件失败: {e}")

    return success_flag_found, ret_code

def main():
    log_message("=== 开始启动 Colab 专用 sshx ===")
    
    # 1. 防重跑：清理旧实例（即使之前崩溃未清理）
    cleanup_previous_instances()
    
    # 2. 自动重连循环
    attempt = 1
    max_attempts = 5
    while attempt <= max_attempts:
        log_message(f"\n🔄 第 {attempt} 次启动尝试...")
        success, ret_code = launch_sshx_with_monitoring()
        
        if success:
            log_message("✅ sshx 启动成功！请查看上方日志中的链接（如 sshx.io/s/xxx#...）。")
            break
        elif attempt < max_attempts:
            wait_time = 5 + (attempt - 1) * 2  # 递增等待时间：5s, 7s, 9s...
            log_message(f"⚠️ 启动失败（返回码 {ret_code}），将在 {wait_time} 秒后重试... (剩余 {max_attempts - attempt} 次)")
            time.sleep(wait_time)
            attempt += 1
        else:
            log_message(f"❌ 经过 {max_attempts} 次尝试后仍未能成功启动 sshx。")
            log_message(f"📌 建议检查：1) 网络是否能访问 sshx.io；2) 是否需更新 EXPECTED_SHA256；3) 查看日志: {LOG_FILE}")
            sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log_message("🛑 用户手动中断。")
        sys.exit(1)
    except Exception as e:
        log_message(f"💥 主程序异常退出: {type(e).__name__}: {e}")
        sys.exit(1)
