# SCAN.GATE 打印机扫描共享工具

将网络共享（打印机扫描目录）变成带完整文件管理 UI 的桌面 / Web 应用。

## 功能特性

### 1. 网络共享管理
- **连接共享**: 输入共享路径、用户名、密码连接网络共享（SMB）
- **断开连接**: 断开已连接的共享
- **测试连接**: 测试网络连通性
- **打开文件夹**: 在资源管理器中打开共享目录

### 2. 文件管理
- **文件浏览**: 列表显示共享目录中的文件和文件夹
- **文件排序**: 按名称、大小、修改时间排序
- **文件操作**: 双击打开、上传、下载、删除
- **图片/PDF 预览**: 内置预览面板（图片直接渲染，PDF 栅格化缩略）
- **压缩导出**: 多文件压缩，可选压缩等级
- **实时刷新**: 随时刷新文件列表

### 3. 状态监控
- **操作日志**: 记录所有操作的详细日志
- **审计日志**: 按主机/共享/操作员记录会话，可上传到 Cloudflare Worker
- **实名校验**: 内置姓氏校验工具

### 4. 自动更新
- 版本清单检测（`version.json`）、增量下载、自动安装、失败回滚

## 双端架构

本工具提供两种界面，共享同一套业务逻辑（`scangate/services/`）：

| 入口 | 技术 | 说明 |
|---|---|---|
| `scangate/main.py` | customtkinter（原生桌面） | Windows 桌面版 |
| `main_web.py` | pywebview + HTML/CSS | Web 混合版（真·毛玻璃前端） |

### 源码结构

```
scangate/
├── main.py          # 桌面版入口（单实例 + 主窗口）
├── config.py        # 配置管理（连接配置/版本/常量）
├── installer.py     # onedir 安装模式（装到本机 + 快捷方式）
├── core/            # 单实例互斥体、worker 线程池
├── ui/              # customtkinter 界面（window/panels/dialogs/theme/fx/overlay）
├── web/             # pywebview 版（app/api/static 前端）
├── services/        # 业务逻辑（connection/files/compress/preview/auditlog/surnames）
└── updater/         # 自动更新（manifest/download/install/rollback/settings）
assets/              # 图标、启动屏
design/              # 设计规范（Liquid Glass 设计语言）
docs/                # 产品使用指南
cloudflare/          # 审计日志上报 Worker
tools/               # 构建辅助脚本
```

## 使用方法

### 桌面版
```bash
python scangate/main.py
```

### Web 混合版
```bash
python main_web.py
```

### 构建可执行文件
项目使用 PyInstaller 的 **onedir 模式**打包（规避 Defender 拦截），主 spec 为 `main.spec`：
```bash
pip install -r requirements.txt pyinstaller
pyinstaller main.spec
```
产物在 `dist/`，配合 `scangate/installer.py` 首次运行自动安装到本机并创建快捷方式。

**CI 自动构建**：仓库已配置 GitHub Actions（`.github/workflows/`），推 tag 自动在 Windows 上构建 zip 并发布到 GitHub Releases，更新器自动拉取。

## 依赖

见 `requirements.txt`（customtkinter / Pillow / pywebview），其余均为 Python 标准库。

## 系统要求

- Windows 10/11（Windows 7/8 可运行但未充分测试）
- Python 3.10+（仅运行脚本时需要，打包版无需）

## 常见问题

### Q1: 无法连接共享
- 检查网络连接、共享路径/用户名/密码
- 检查防火墙、确认有访问权限

### Q2: 文件列表为空
- 确认已成功连接共享，检查目录内是否有文件，尝试刷新

### Q3: 无法上传/下载文件
- 检查写入权限、目标路径、磁盘空间

### Q4: 程序运行缓慢
- 大目录首次扫描较慢；关闭不必要后台程序

## 更新日志

### v4.7.0 (2026-07-20)
- 安装模式（onedir 打包）：规避 Defender 拦截临时 DLL
- 首次运行自动安装到本机，创建桌面/开始菜单快捷方式
- 自动更新改为下载 zip 整体替换安装目录

## 许可证

MIT License