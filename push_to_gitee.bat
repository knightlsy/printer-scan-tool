@echo off
REM ============================================================
REM  推送 SCAN.GATE 源码到 Gitee  (knightlsy/printer-scan-tool)
REM  用法：双击本文件即可。
REM  首次会弹出 Gitee 登录框：
REM      用户名：knightlsy
REM      密码：  你的 Gitee 私人令牌（不是登录密码）
REM  推送完成后会自动移除本地 remote（令牌不会留在配置里）。
REM ============================================================
cd /d "%~dp0"

git remote remove origin 2>nul
git remote add origin https://gitee.com/knightlsy/printer-scan-tool.git

git push -u origin master
set PUSH_EXIT=%errorlevel%

git remote remove origin 2>nul

if "%PUSH_EXIT%"=="0" (
    echo.
    echo ========== 推送成功！源码已同步到 Gitee ==========
) else (
    echo.
    echo ========== 推送失败（错误码 %PUSH_EXIT%）==========
    echo 请确认：1) 网络可访问 gitee.com  2) 令牌有效且有 projects 权限
)
echo.
pause
