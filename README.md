# colab sshx_auto
!wget -O /content/sshx_auto.py https://raw.githubusercontent.com/ltianw-eng/colabgoogle/main/sshx_auto.py
%run /content/sshx_auto.py
# 更新软件索引，确保能找到最新版软件
sudo apt upgrade

# 将旧软件替换为最新的稳定版，防止脚本报错
sudo apt update

# 安装系统配置展示工具
sudo apt install neofetch

neofetch
