# -*- coding: utf-8 -*-
"""Build final single-file HTML guide with all schematic figures embedded inline."""
import os

BASE = r"C:\Users\EDY\WorkBuddy\2026-07-07-10-57-44\printer-scan-tool"
IMG = os.path.join(BASE, "docs", "images")
OUT = os.path.join(BASE, "docs", "产品使用指南.html")

def read_svg(name):
    with open(os.path.join(IMG, name), encoding="utf-8") as f:
        return f.read()

def fig(svg_content, caption):
    return f'''<div class="fig">
{svg_content}
<div class="figcap">{caption}</div>
</div>'''

# Load all figures
f_main_ui  = fig(read_svg("main-ui.svg"),         "图 1 · 主界面布局：顶部标题栏（品牌 + 连接状态 + 窗口按钮）、左侧「连接设置」、中间「文件列表」、右侧「预览」。示意图，以实际程序为准。")
f_step1    = fig(read_svg("fg_step1.svg"),        "图 3 · 步骤 1 示意：连接成功后，指示灯变绿（①），文件列表出现扫描件（②）。示意图，以实际程序为准。")
f_step2    = fig(read_svg("fg_step2.svg"),        "图 4 · 步骤 2 示意：文件列表面板展示名称/大小/修改时间三列及若干 PDF 行。示意图，以实际程序为准。")
f_step3    = fig(read_svg("fg_step3.svg"),        "图 5 · 步骤 3 示意：选中文件后右侧预览面板显示文档图像及翻页控件。示意图，以实际程序为准。")
f_step4    = fig(read_svg("fg_step4.svg"),        "图 6 · 步骤 4 示意：系统「另存为」对话框（文件名已自动填充 PDF 名称）。示意图，以实际程序为准。")
f_step5    = fig(read_svg("fg_step5.svg"),        "图 7 · 步骤 5 示意：系统文件选择对话框（可多选状态，已勾选两份文件）。示意图，以实际程序为准。")
f_step6    = fig(read_svg("fg_step6.svg"),        "图 8 · 步骤 6 示意：删除确认弹窗（含文件名与「不可恢复」警示）。示意图，以实际程序为准。")
f_srv      = fig(read_svg("server-manage.svg"),   "图 2 · 服务器管理弹窗：列出已保存配置，每项含「连接 / 编辑 / 删除」，底部可新增。示意图，以实际程序为准。")
f_step8    = fig(read_svg("fg_step8.svg"),        "图 9 · 步骤 8 示意：窗口右下角悬停时显示斜向缩放箭头光标。示意图，以实际程序为准。")
f_step9a   = fig(read_svg("fg_step9a.svg"),       "图 10 · 步骤 9 示意：「关于 SCAN.GATE」信息弹窗。示意图，以实际程序为准。")
f_step9b   = fig(read_svg("fg_step9b.svg"),       "图 11 · 步骤 9 示意：身份选择弹窗（公司内 / 公司外）。示意图，以实际程序为准。")

html = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SCAN.GATE 打印机扫描共享工具 · 产品使用指南</title>
<style>
  :root{
    --accent:#2f6bff; --accent2:#5689ff; --ink:#1f2d4d; --sub:#5a6a88;
    --line:#e3e9f4; --card:#ffffff; --danger:#ff4d4f; --green:#1fa463;
  }
  *{box-sizing:border-box}
  body{
    margin:0; font-family:"Segoe UI","Microsoft YaHei",sans-serif;
    color:var(--ink); background:#f3f6fc; line-height:1.7; font-size:15px;
  }
  .wrap{max-width:920px; margin:0 auto; padding:32px 26px 64px; background:#fff;
    box-shadow:0 6px 30px rgba(31,45,77,.08);}
  header.cover{
    background:linear-gradient(135deg,#eef2f9,#d8e2f2); border-radius:16px;
    padding:30px 30px 26px; margin-bottom:8px; position:relative; overflow:hidden;
  }
  header.cover .dot{display:inline-block; width:14px; height:14px; border-radius:50%;
    background:linear-gradient(135deg,var(--accent2),var(--accent)); margin-right:10px;
    box-shadow:0 0 0 6px rgba(86,137,255,.18);}
  header.cover h1{margin:0; font-size:26px; font-weight:800; letter-spacing:.5px}
  header.cover .ver{color:var(--sub); font-size:13px; margin-top:8px}
  header.cover .tag{display:inline-block; margin-top:14px; padding:4px 12px;
    background:rgba(47,107,255,.1); color:var(--accent); border-radius:20px; font-size:12px}
  h2{font-size:20px; margin:38px 0 14px; padding-left:12px; border-left:4px solid var(--accent)}
  h3{font-size:16px; margin:24px 0 10px; color:var(--accent)}
  p{margin:8px 0}
  .note{background:#f5f8ff; border:1px solid var(--line); border-left:4px solid var(--accent);
    border-radius:8px; padding:12px 16px; margin:12px 0}
  .warn{background:#fff5f5; border:1px solid #ffd9d9; border-left:4px solid var(--danger);
    border-radius:8px; padding:12px 16px; margin:12px 0}
  .tip{background:#f3fbf6; border:1px solid #cdeedd; border-left:4px solid var(--green);
    border-radius:8px; padding:12px 16px; margin:12px 0}
  .shot{background:#fbfcff; border:1px dashed #c4d2ec; border-radius:10px;
    padding:12px 16px; margin:12px 0; font-size:13px; color:var(--sub)}
  .shot b{color:var(--accent)}
  table{width:100%; border-collapse:collapse; margin:14px 0; font-size:14px}
  th,td{border:1px solid var(--line); padding:10px 12px; text-align:left; vertical-align:top}
  th{background:#f5f8ff; color:var(--accent); font-weight:700}
  tr:nth-child(even) td{background:#fafcff}
  ol.steps{counter-reset:s; padding:0; margin:0}
  ol.steps>li{list-style:none; position:relative; padding:14px 18px 14px 56px;
    margin:14px 0; background:#fbfcff; border:1px solid var(--line); border-radius:12px}
  ol.steps>li::before{counter-increment:s; content:counter(s);
    position:absolute; left:14px; top:14px; width:28px; height:28px; border-radius:50%;
    background:linear-gradient(135deg,var(--accent2),var(--accent)); color:#fff;
    font-weight:700; display:flex; align-items:center; justify-content:center; font-size:14px}
  .purpose{color:var(--sub); font-size:13px; margin:2px 0 8px}
  .purpose b,.method b,.result b{color:var(--ink)}
  .method,.result{margin:6px 0}
  .fig{margin:18px 0; border:1px solid var(--line); border-radius:12px; overflow:hidden; background:#fbfcff}
  .fig svg{display:block; width:100%; height:auto}
  .figcap{font-size:12px; color:var(--sub); padding:8px 14px; background:#f5f8ff; border-top:1px solid var(--line)}
  code{background:#eef2fb; color:#1f3a8a; padding:1px 6px; border-radius:5px; font-size:13px}
  footer{margin-top:40px; padding-top:18px; border-top:1px solid var(--line);
    text-align:center; color:var(--sub); font-size:12px}
  @media print{
    body{background:#fff} .wrap{box-shadow:none; max-width:none; padding:0}
    .fig,ol.steps>li,.note,.warn,.tip,.shot{break-inside:avoid}
  }
</style>
</head>
<body>
<div class="wrap">

  <header class="cover">
    <div><span class="dot"></span><h1>SCAN.GATE 打印机扫描共享工具</h1></div>
    <div class="ver">产品使用指南 ｜ 版本 v4.0.0 ｜ 适用对象：运营 / 行政 / 普通办公用户</div>
    <div><span class="tag">从入门到进阶 · 图文操作手册</span></div>
  </header>

  <p>本文档按「从入门到进阶」顺序编排，每步均含 <b>操作目的 · 操作方法 · 预期结果</b>，并在关键处给出注意事项与常见问题提示。</p>

  <!-- ============ 一 ============ -->
  <h2>一、产品简介与功能概述</h2>
  <p><b>SCAN.GATE</b> 是一款连接公区打印机网络扫描共享目录的桌面工具，帮助你在电脑上<b>浏览、预览、上传、下载、删除</b>扫描出来的 PDF 文件，无需手动映射网络驱动器。</p>

  <h3>核心功能</h3>
  <table>
    <tr><th>功能</th><th>说明</th></tr>
    <tr><td>服务器连接</td><td>输入带用户名/密码的 SMB 共享路径（如 <code>\\192.168.4.82\share\PDF</code>），一键连接</td></tr>
    <tr><td>文件浏览</td><td>列表展示扫描件名称、大小、修改时间，支持刷新</td></tr>
    <tr><td>文件预览</td><td>选中 PDF 即时生成缩略预览，多页文档可翻页</td></tr>
    <tr><td>上传 / 下载</td><td>把本地文件传入共享目录，或把扫描件保存到本机</td></tr>
    <tr><td>删除</td><td>清理过期扫描件（带二次确认，防误删）</td></tr>
    <tr><td>多服务器管理</td><td>保存多组服务器配置，一键切换，支持增 / 改 / 删</td></tr>
    <tr><td>会话溯源日志</td><td>每次「连接→断开」自动在共享目录写一份中文操作日志</td></tr>
    <tr><td>窗口自由操控</td><td>无边框毛玻璃界面，支持标题栏拖动、八向缩放、最大化</td></tr>
  </table>

''' + f_main_ui + '''

  <!-- ============ 二 ============ -->
  <h2>二、环境要求与启动</h2>
  <ul>
    <li><b>操作系统</b>：Windows 10 / Windows 11（系统已自带 Edge WebView2 运行环境，无需额外安装）。</li>
    <li><b>网络</b>：与目标打印机/共享服务器在同一内网，且拥有该共享目录的访问账号。</li>
    <li><b>启动方式</b>：双击 <code>打印机扫描工具_v4.exe</code> 即可。程序为<b>单实例</b>——若已在运行，再次双击只会提示而不会打开第二个窗口。</li>
  </ul>
  <div class="warn">&#x26A0;&#xFE0F; <b>注意</b>：程序不依赖外部浏览器，但首次启动需系统 WebView2 组件。若公司电脑禁用了系统组件导致白屏，请联系 IT 确认 WebView2 已启用。</div>
  <div class="tip">&#x1F4A1; <b>提示</b>：建议将 <code>打印机扫描工具_v4.exe</code> 固定到任务栏或发送到桌面快捷方式，便于日常使用。</div>

  <!-- ============ 三 ============ -->
  <h2>三、入门操作</h2>
  <ol class="steps">

    <li>
      <h3 style="margin-top:0">步骤 1 · 认识主界面并连接默认服务器</h3>
      <div class="purpose"><b>操作目的</b>：建立与打印机扫描共享目录的连接，是后续所有操作的前提。</div>
      <div class="method"><b>操作方法</b>：
        <ol>
          <li>程序启动后，左侧「连接设置」面板已预填默认服务器（<code>192.168.4.82</code> / <code>share</code> / <code>PDF</code> / 账号 <code>share</code>）。</li>
          <li>确认信息无误，点击蓝色按钮 <b>「连接共享」</b>。</li>
        </ol>
      </div>
      <div class="result"><b>预期结果</b>：顶部状态栏显示「已连接」，连接状态指示灯由<b>红色变为绿色</b>；中间「文件列表」开始加载并显示扫描件。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：连接成功后，截取主界面，重点展示左上角连接指示灯变绿、中间文件列表出现文件行。</div>
''' + f_step1 + '''
      <div class="warn">&#x26A0;&#xFE0F; <b>注意</b>：若提示连接失败，请检查：① 电脑与打印机是否在同一网段；② 共享地址/共享名/子目录/账号密码是否填写正确；③ 账号是否被服务器锁定。详见文末「故障排除」。</div>
    </li>

    <li>
      <h3 style="margin-top:0">步骤 2 · 浏览与刷新文件列表</h3>
      <div class="purpose"><b>操作目的</b>：查看当前共享目录中有哪些扫描件。</div>
      <div class="method"><b>操作方法</b>：文件列表已自动加载；如需手动刷新，点击列表上方 <b>「刷新」</b> 按钮。</div>
      <div class="result"><b>预期结果</b>：列表按「名称 / 大小 / 修改时间」三列展示所有文件；新扫描的文件在刷新后出现。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：截取文件列表面板，展示若干 PDF 行及表头三列。</div>
''' + f_step2 + '''
      <div class="tip">&#x1F4A1; <b>提示</b>：文件名带日期（如 <code>扫描件_20260709_001.pdf</code>）便于识别扫描时间。</div>
    </li>

    <li>
      <h3 style="margin-top:0">步骤 3 · 预览扫描件内容</h3>
      <div class="purpose"><b>操作目的</b>：在下载/删除前先确认内容，避免误操作。</div>
      <div class="method"><b>操作方法</b>：在文件列表中<b>单击任意文件行</b>。</div>
      <div class="result"><b>预期结果</b>：右侧「预览」面板显示该 PDF 首页图像；若为多页文档，面板底部出现 <b>「&#x2039; 上一页 / 下一页 &#x203A;</b>」翻页控件。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：选中一个文件后，截取右侧预览面板显示文档图像、底部翻页控件的画面。</div>
''' + f_step3 + '''
      <div class="warn">&#x26A0;&#xFE0F; <b>注意</b>：文件夹（目录）不支持预览，选中后会提示「文件夹不支持预览」。</div>
    </li>

    <li>
      <h3 style="margin-top:0">步骤 4 · 下载文件到本机</h3>
      <div class="purpose"><b>操作目的</b>：把需要的扫描件保存到自己的电脑。</div>
      <div class="method"><b>操作方法</b>：
        <ol>
          <li>在文件列表中<b>单击选中</b>目标文件（确保不是文件夹）。</li>
          <li>点击 <b>「下载」</b> 按钮。</li>
          <li>在弹出的系统「选择保存位置」对话框中指定路径并确认。</li>
        </ol>
      </div>
      <div class="result"><b>预期结果</b>：文件保存到指定位置，进度条短暂显示后完成；状态栏提示成功。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：截取点击「下载」后弹出的系统「另存为」对话框。</div>
''' + f_step4 + '''
      <div class="warn">&#x26A0;&#xFE0F; <b>注意</b>：未连接共享或尚未选中文件时点击「下载」，会弹出提示「请先连接共享 / 请先选择要下载的文件」，操作不会执行。</div>
    </li>

  </ol>

  <!-- ============ 四 ============ -->
  <h2>四、进阶操作</h2>
  <ol class="steps" start="5">

    <li>
      <h3 style="margin-top:0">步骤 5 · 上传文件到共享目录</h3>
      <div class="purpose"><b>操作目的</b>：将本地文件（如已签字的回执）回传到扫描共享目录，供他人取用。</div>
      <div class="method"><b>操作方法</b>：点击 <b>「上传」</b> 按钮，在文件选择对话框中选中要上传的文件（可多选），确认后等待上传完成。</div>
      <div class="result"><b>预期结果</b>：上传成功后，刷新文件列表可见新文件；会话日志会记录本次上传。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：截取点击「上传」后弹出的系统文件选择对话框（可多选状态）。</div>
''' + f_step5 + '''
    </li>

    <li>
      <h3 style="margin-top:0">步骤 6 · 删除过期扫描件</h3>
      <div class="purpose"><b>操作目的</b>：清理共享目录中不再需要的文件，释放空间。</div>
      <div class="method"><b>操作方法</b>：
        <ol>
          <li>单击选中要删除的文件。</li>
          <li>点击 <b>「删除」</b> 按钮。</li>
          <li>在确认框中点击「确定」（此操作不可恢复）。</li>
        </ol>
      </div>
      <div class="result"><b>预期结果</b>：文件从列表中移除，并从共享目录删除；会话日志记录删除操作。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：截取点击「删除」后弹出的确认对话框（含文件名与「不可恢复」警示）。</div>
''' + f_step6 + '''
      <div class="warn">&#x26A0;&#xFE0F; <b>注意事项（重要）</b>：
        <ul style="margin:6px 0 0">
          <li>删除前务必通过「预览」确认内容，避免误删他人文件。</li>
          <li><b>已断开连接时无法删除</b>：指示灯为红色（未连接）时点「删除」会被拦截并提示「请先连接共享后再删除」。</li>
          <li>删除动作会写入溯源日志，操作人可追溯，请谨慎使用。</li>
        </ul>
      </div>
    </li>

    <li>
      <h3 style="margin-top:0">步骤 7 · 管理多组服务器配置</h3>
      <div class="purpose"><b>操作目的</b>：在多个打印机/共享位置之间快速切换，免去反复手填。</div>
      <div class="method"><b>操作方法</b>：
        <ol>
          <li>点击左侧面板标题旁的 <b>「管理」</b> 按钮，打开「服务器管理」弹窗。</li>
          <li>在弹窗中可：
            <br>&bull; <b>连接</b>：把某配置切换为当前使用项（主面板同步填充）。
            <br>&bull; <b>编辑</b>：修改该配置的名称/地址/账号等。
            <br>&bull; <b>删除</b>：移除该配置（至少保留一项，不可清空）。
            <br>&bull; <b>+ 添加服务器</b>：新建一组配置，填写「配置名称 / 服务器地址 / 共享名 / 子目录 / 用户名 / 密码」后保存。</li>
          <li>完成后点击弹窗空白处或右上角 &times; 关闭。</li>
        </ol>
      </div>
      <div class="result"><b>预期结果</b>：配置被保存并持久化；「当前」徽标标记正在使用的服务器。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：截取「服务器管理」弹窗，展示含「当前」徽标的配置列表与「+ 添加服务器」按钮。</div>
''' + f_srv + '''
      <div class="tip">&#x1F4A1; <b>提示</b>：把常用的公区打印机设为「当前」配置，下次启动即自动预填，直接点「连接共享」即可。</div>
    </li>

    <li>
      <h3 style="margin-top:0">步骤 8 · 窗口移动、缩放与最大化</h3>
      <div class="purpose"><b>操作目的</b>：根据屏幕空间自由调整窗口大小与位置。</div>
      <div class="method"><b>操作方法</b>：
        <ul style="margin:6px 0 0">
          <li><b>移动</b>：在顶部标题栏空白处（品牌名区域）按下并拖动。</li>
          <li><b>八向缩放</b>：将鼠标移到窗口<b>上 / 下 / 左 / 右 / 四角</b>边缘，光标变为双向箭头后拖动，即可从对应方向改变大小（最小 760&times;480）。</li>
          <li><b>最大化 / 还原</b>：点击右上角最大化按钮，或<b>双击标题栏</b>。</li>
          <li><b>最小化 / 关闭</b>：点击右上角对应按钮。</li>
        </ul>
      </div>
      <div class="result"><b>预期结果</b>：窗口随拖动实时变化；最大化后缩放热区自动禁用，避免误触。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：截取鼠标悬停在窗口右下角时显示斜向缩放箭头的画面。</div>
''' + f_step8 + '''
      <div class="warn">&#x26A0;&#xFE0F; <b>注意</b>：拖动请使用标题栏区域，不要在文件列表/按钮上拖，否则不会移动窗口。</div>
    </li>

    <li>
      <h3 style="margin-top:0">步骤 9 · 查看「关于」与联系作者</h3>
      <div class="purpose"><b>操作目的</b>：了解版本信息，或在需要时联系程序作者。</div>
      <div class="method"><b>操作方法</b>：点击左侧 <b>「关于程序」</b>，弹窗显示名称、版本、作者、版权；点击作者名，选择「公司内 / 公司外」身份后跳转对应飞书邀请链接。</div>
      <div class="result"><b>预期结果</b>：弹出「关于 SCAN.GATE」窗口；选择身份后浏览器打开联系入口。</div>
      <div class="shot">&#x1F4F7; <b>截图指示</b>：截取「关于」弹窗及随后出现的「公司内 / 公司外」选择弹窗。</div>
''' + f_step9a + f_step9b + '''
    </li>

  </ol>

  <!-- ============ 五 ============ -->
  <h2>五、会话溯源日志</h2>
  <ul>
    <li><b>日志位置</b>：自动写入当前所连服务器的共享根目录下 <code>share\log</code> 文件夹，即 <code>\\&lt;服务器IP&gt;\share\log\</code>。</li>
    <li><b>文件命名</b>：<code>log_YYYYMMDD_HHMMSS.log</code>（以本次连接开始时间命名，精确到秒，避免重名）。</li>
    <li><b>记录内容</b>：一次「连接 &rarr; 断开」（或关闭窗口）会话内的全部操作，含操作时间、操作人、前后状态对比、结果。</li>
    <li><b>溯源价值</b>：操作人默认取本机 Windows 登录账号；如需显示友好姓名，可在配置文件 <code>~\.printer_scan_config.json</code> 中加入 <code>"operator":"你的姓名"</code>。</li>
  </ul>
  <div class="tip">&#x1F4A1; <b>提示</b>：日志仅在<b>成功连接后产生操作、再断开</b>时生成。仅浏览不操作也会生成一条含连接/断开信息的会话记录。</div>

  <!-- ============ 六 ============ -->
  <h2>六、注意事项汇总</h2>
  <ol>
    <li><b>先连接，后操作</b>：上传 / 下载 / 删除都要求处于「已连接」状态；断开后按钮会被拦截并提示。</li>
    <li><b>删除需谨慎</b>：删除有二次确认且写入日志，操作可追溯，误删不可恢复。</li>
    <li><b>单实例限制</b>：程序只能同时运行一个，重复启动会被提示。</li>
    <li><b>网络依赖</b>：所有文件操作依赖内网共享可达，离网或 VPN 断开会导致连接失败。</li>
    <li><b>配置持久化</b>：服务器配置保存在本机 <code>~\.printer_scan_config.json</code>，重装系统前请备份。</li>
  </ol>

  <!-- ============ 七 ============ -->
  <h2>七、故障排除（FAQ）</h2>
  <table>
    <tr><th>现象</th><th>可能原因</th><th>解决办法</th></tr>
    <tr><td>双击后无窗口 / 白屏</td><td>系统 WebView2 组件缺失或被禁用</td><td>确认 Win10/11 已启用 Edge WebView2；联系 IT 修复系统组件</td></tr>
    <tr><td>提示「连接失败」</td><td>地址/账号错误、不在同网段、服务器不可达</td><td>核对 IP、共享名、子目录、用户名、密码；用 <code>ping &lt;IP&gt;</code> 测试连通性</td></tr>
    <tr><td>文件列表为空</td><td>已连接但目录无文件，或子目录填错</td><td>检查「子目录」是否应为空或具体文件夹名（如 <code>PDF</code>）</td></tr>
    <tr><td>点「下载/删除」没反应并弹提示</td><td>未连接或没选中文件</td><td>先「连接共享」，再在列表单击选中具体文件</td></tr>
    <tr><td>指示灯是红色仍想操作</td><td>当前处于「未连接」状态</td><td>重新点击「连接共享」；断开后列表已清空属正常</td></tr>
    <tr><td>重建后 exe 图标没变</td><td>Windows 资源管理器图标缓存未刷新</td><td>桌面按 <b>F5</b> 刷新，或重启「资源管理器」，或执行 <code>ie4uinit.exe -show</code> 清缓存</td></tr>
    <tr><td>提示「程序已在运行」</td><td>已有一个实例</td><td>切到已打开的窗口，或结束后台进程后再启动</td></tr>
    <tr><td>日志没生成</td><td>未成功连接，或共享 <code>log</code> 目录无写权限</td><td>确认先连接并产生操作；检查对 <code>\\&lt;IP&gt;\share</code> 是否有写入权限</td></tr>
    <tr><td>预览不显示</td><td>文件非 PDF / 文件损坏 / 正在生成</td><td>刷新重试；非 PDF 文件不支持预览</td></tr>
  </table>
  <div class="note">若以上方法无法解决，请将现象截图及 <code>\\&lt;IP&gt;\share\log</code> 下对应日志文件一并反馈给作者。</div>

  <footer>&mdash; SCAN.GATE 打印机扫描共享工具 &middot; 产品使用指南 v4.0.0 &mdash;</footer>

</div>
</body>
</html>'''

with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print(f"SAVED: {OUT} ({os.path.getsize(OUT)} bytes)")
