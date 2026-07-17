/* =========================================================================
   SCAN.GATE v4 · 前端逻辑
   后端通过 pywebview 暴露 Api（window.pywebview.api.*），
   结果通过全局回调 onStatus / onProgress / onList / onPreview / onOverlay /
   onConfigStatus 推回（由 Python 端 evaluate_js 调用）。
   ========================================================================= */

(function () {
  "use strict";

  // ---------------- 状态 ----------------
  var state = {
    items: [],
    selected: null,        // { path, is_dir, name }
    preview: null,         // { path, page, total }
    connected: false,      // 当前是否已连接共享（删除/下载前需判断）
    tools: { path: null, level: "standard", rate: 70 },  // 小工具：PDF 压缩；rate 仅自定义级别生效
  };

  // ---------------- DOM ----------------
  var $ = function (id) { return document.getElementById(id); };
  var statusDot = $("statusDot");
  var statusText = $("statusText");
  var connDot = $("connDot");
  var connText = $("connText");
  var fileList = $("fileList");
  var listEmpty = $("listEmpty");
  var previewStage = $("previewStage");
  var previewInfo = $("previewInfo");
  var previewNav = $("previewNav");
  var previewPage = $("previewPage");
  var overlay = $("overlay");
  var overlayTitle = $("overlayTitle");
  var overlayMsg = $("overlayMsg");
  var progressBar = $("progressBar");
  var btnCancel = $("btnCancel");
  var modal = $("modal");
  var authorModal = $("authorModal");
  // 首次启动强制实名弹窗
  var nameModal = $("nameModal");
  var fRealName = $("fRealName");
  var btnNameOk = $("btnNameOk");
  var btnNameCancel = $("btnNameCancel");
  var nameError = $("nameError");
  var btnMin = $("btnMin");
  var btnMax = $("btnMax");
  var btnClose = $("btnClose");
  var btnLinkInternal = $("btnLinkInternal");
  var btnLinkExternal = $("btnLinkExternal");
  var btnAuthorClose = $("btnAuthorClose");

  // 服务器管理
  var btnManage = $("btnManage");
  var serverModal = $("serverModal");
  var serverFormModal = $("serverFormModal");
  var serverList = $("serverList");
  var btnAddServer = $("btnAddServer");
  var btnServerClose = $("btnServerClose");
  var btnServerFormClose = $("btnServerFormClose");
  var btnServerSave = $("btnServerSave");
  var btnServerCancel = $("btnServerCancel");
  var serverFormTitle = $("serverFormTitle");
  var sfName = $("sfName"), sfHost = $("sfHost"), sfShare = $("sfShare"),
      sfSub = $("sfSub"), sfUser = $("sfUser"), sfPass = $("sfPass");
  var editingId = "";        // 表单正在编辑的服务器 id（空 = 新增）
  var currentId = null;      // 当前生效档 id

  // 作者联系方式链接（来自 about()）：公司内 / 公司外
  var authorLinks = { internal: "", external: "" };

  // 小工具弹窗（工具箱）
  var btnTools = $("btnTools");
  var toolsModal = $("toolsModal");
  var btnToolsClose = $("btnToolsClose");
  var toolGrid = $("toolGrid");
  var pdfPanel = $("pdfPanel");
  var btnToolBack = $("btnToolBack");
  var toolsDrop = $("toolsDrop");
  var btnPickPdf = $("btnPickPdf");
  var toolsPdfPath = $("toolsPdfPath");
  var toolsLevel = $("toolsLevel");
  var btnDoCompress = $("btnDoCompress");
  var toolsStatus = $("toolsStatus");
  var toolsCustom = $("toolsCustom");
  var toolsRate = $("toolsRate");
  var toolsRateVal = $("toolsRateVal");
  var toolProgress = $("toolProgress");
  var toolProgressBar = $("toolProgressBar");
  var toolsResult = $("toolsResult");
  var trOrig = $("trOrig");
  var trNew = $("trNew");
  var trSaved = $("trSaved");

  // ---------------- 八向自由缩放（无边框窗口） ----------------
  var MIN_W = 760, MIN_H = 480;            // 最小尺寸限制，防止窗口过小
  // 仅记录尺寸即可：缩放时的窗口位移由后端 fix_point 锚点处理，无需 JS 维护坐标。
  var winState = { w: 1180, h: 720 };
  var resizeDir = null;                    // 当前缩放方向 n/s/e/w/ne/nw/se/sw
  var resizeStart = null;                  // { mx, my, w, h } 起点快照
  var resizePending = null;                // { w, h, dir } 待应用的目标尺寸（每帧最多一次）
  var resizeRAF = null;
  var isMax = false;                       // 与后端 _maximized 同步，最大化态禁用缩放

  // ---------------- 工具 ----------------
  function fmtSize(n) {
    n = Number(n) || 0;
    var u = ["B", "KB", "MB", "GB", "TB"];
    var i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return (i === 0 ? n : n.toFixed(1)) + u[i];
  }
  function fmtTime(t) {
    if (!t) return "";
    var d = new Date(Number(t) * 1000);
    var p = function (x) { return (x < 10 ? "0" : "") + x; };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) +
           " " + p(d.getHours()) + ":" + p(d.getMinutes());
  }
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // ---------------- 全局回调（供 Python 端 evaluate_js 调用） ----------------
  window.onStatus = function (text, kind) {
    statusText.textContent = text || "就绪";
    var cls = "status-dot";
    if (kind === "success") cls += " success";
    else if (kind === "warn") cls += " warn";
    else if (kind === "error") cls += " error";
    statusDot.className = cls;
  };

  window.onConfigStatus = function (text, connected) {
    connText.textContent = text || "未连接";
    connDot.className = "conn-dot" + (connected ? " on" : " off");
    state.connected = !!connected;
    if (!connected) {
      // 断开后清空列表与已选项，避免对已断开的共享执行删除 / 下载
      state.items = [];
      state.selected = null;
      renderList();
      showPreviewText("暂无预览");
    }
  };

  window.onProgress = function (pct, msg) {
    var p = Math.max(0, Math.min(100, Number(pct) || 0));
    progressBar.style.width = p + "%";
    if (msg) overlayMsg.textContent = msg;
  };

  window.onOverlay = function (show, cancelable) {
    overlay.hidden = !show;
    if (show) {
      progressBar.style.width = "0%";
      overlayMsg.textContent = "";
      btnCancel.hidden = !cancelable;
    }
  };

  // 小工具：压缩结果回写弹窗内的状态行
  window.onToolStatus = function (text, kind) {
    var el = $("toolsStatus");
    if (!el) return;
    el.textContent = text || "";
    el.className = "tool-status" + (kind === "success" ? " ok" : kind === "error" ? " err" : "");
  };

  // 小工具：压缩进度（pct 0-100）
  window.onToolProgress = function (pct) {
    var p = Math.max(0, Math.min(100, Number(pct) || 0));
    toolProgress.hidden = false;
    toolProgressBar.style.width = p + "%";
  };

  // 小工具：压缩完成的结构化结果（原/新大小、节省率、输出路径）
  window.onToolResult = function (orig, newSize, saved, dst) {
    trOrig.textContent = fmtSize(orig);
    trNew.textContent = fmtSize(newSize);
    var s = Number(saved) || 0;
    if (s >= 0) {
      trSaved.textContent = "节省 " + s.toFixed(0) + "%";
      trSaved.className = "tr-saved";
    } else {
      trSaved.textContent = "体积增加 " + Math.abs(s).toFixed(0) + "%（该文件重光栅化后未变小，建议提高压缩率）";
      trSaved.className = "tr-saved warn";
    }
    toolsResult.hidden = false;
  };

  // ---------------- 在线更新 ----------------
  var updState = { latest: null, downloading: false };

  function fmtSpeed(bps) {
    bps = Number(bps) || 0;
    if (bps <= 0) return "";
    if (bps >= 1024 * 1024) return (bps / 1024 / 1024).toFixed(1) + " MB/s";
    if (bps >= 1024) return (bps / 1024).toFixed(0) + " KB/s";
    return bps.toFixed(0) + " B/s";
  }

  function openUpdateModal() {
    $("updFound").hidden = true;
    $("updProgressWrap").hidden = true;
    $("btnUpdNow").hidden = true;
    $("btnUpdLater").hidden = false;
    setUpdState("正在检查更新…", "");
    $("updateModal").hidden = false;
  }
  function closeUpdateModal() {
    if (updState.downloading) return;   // 下载中不允许关闭，避免误触
    $("updateModal").hidden = true;
  }
  function setUpdState(text, kind) {
    var el = $("updState");
    el.textContent = text || "";
    el.className = "upd-state" + (kind === "err" ? " err" : kind === "ok" ? " ok" : "");
  }

  // 关于弹窗「检查更新」：打开更新弹窗并触发检查（非静默）
  function checkUpdate() {
    openUpdateModal();
    apiCall("check_update", false);
  }

  function doUpdateNow() {
    updState.downloading = true;
    $("btnUpdNow").hidden = true;
    $("btnUpdLater").hidden = true;
    $("updProgressWrap").hidden = false;
    $("updBar").style.width = "0%";
    $("updPct").textContent = "0%";
    $("updStage").textContent = "下载中";
    setUpdState("正在下载更新包…", "");
    apiCall("download_and_install_update");
  }

  // 后端事件：状态文本（含成功/失败/回滚/安装等）
  window.onUpdateStatus = function (kind, text) {
    // kind: checking/up_to_date/error/installing/ready/restarting/need_manual/updated/rolledback
    if (kind === "up_to_date") {
      setUpdState(text, "ok");
      $("updFound").hidden = true;
      $("btnUpdNow").hidden = true;
    } else if (kind === "error") {
      updState.downloading = false;
      setUpdState(text, "err");
      $("btnUpdLater").hidden = false;
    } else if (kind === "installing" || kind === "ready" || kind === "restarting") {
      setUpdState(text, "");
    } else if (kind === "need_manual") {
      updState.downloading = false;
      setUpdState(text, "");
      $("btnUpdLater").hidden = false;
    } else if (kind === "updated") {
      // 启动自检：上次更新成功，仅轻提示主状态栏
      onStatus(text, "success");
    } else if (kind === "rolledback") {
      onStatus(text, "error");
    } else {
      setUpdState(text, "");
    }
  };

  // 后端事件：发现新版本
  window.onUpdateFound = function (info) {
    if (!info) return;
    updState.latest = info;
    // 若更新弹窗未打开（启动静默检查发现新版），则自动打开提示
    if ($("updateModal").hidden) openUpdateModal();
    setUpdState("发现新版本，可立即更新：", "");
    $("updCur").textContent = "当前 v" + (info.current || "");
    $("updNew").textContent = "最新 v" + (info.version || "");
    $("updNotes").textContent = info.notes || "（无更新说明）";
    $("updFound").hidden = false;
    $("btnUpdNow").hidden = false;
    $("btnUpdLater").hidden = false;
  };

  // 后端事件：下载/校验进度
  window.onUpdateProgress = function (stage, pct, speed) {
    $("updProgressWrap").hidden = false;
    var p = Math.max(0, Math.min(100, Number(pct) || 0));
    $("updBar").style.width = p + "%";
    $("updPct").textContent = p + "%";
    $("updStage").textContent = stage === "verifying" ? "校验中" : "下载中";
    $("updSpeed").textContent = stage === "downloading" ? fmtSpeed(speed) : "";
  };

  // ---------------- 小工具（工具箱） ----------------
  // 进入某个工具面板（目前仅 pdf_compress）
  function showTool(id) {
    toolGrid.hidden = true;
    if (id === "pdf_compress") {
      pdfPanel.hidden = false;
    }
    // 未来新增工具：else if (id === "xxx") { $("xxxPanel").hidden = false; }
  }
  // 返回工具选择列表
  function backToTools() {
    pdfPanel.hidden = true;
    toolGrid.hidden = false;
  }
  function openTools() {
    toolsModal.hidden = false;
    backToTools();  // 默认展示工具选择列表
  }
  function closeTools() {
    toolsModal.hidden = true;
  }
  function pickPdf() {
    var r = apiCall("pick_pdf");
    var handle = function (p) {
      if (p) {
        state.tools.path = p;
        toolsPdfPath.textContent = p;
        toolsStatus.className = "tool-status";
        toolsStatus.textContent = "";
        toolsResult.hidden = true;  // 清除上一次结果
      }
    };
    if (r && r.then) r.then(handle); else handle(r);
  }
  function doCompress() {
    if (!state.tools.path) {
      toolsStatus.className = "tool-status err";
      toolsStatus.textContent = "请先选择要压缩的 PDF 文件";
      return;
    }
    toolsStatus.className = "tool-status";
    toolsStatus.textContent = "压缩中…";
    toolsResult.hidden = true;
    toolProgress.hidden = false;
    toolProgressBar.style.width = "0%";
    var rate = state.tools.level === "custom" ? state.tools.rate : null;
    apiCall("compress_pdf", state.tools.path, state.tools.level, rate);
  }

  window.onList = function (items) {
    state.items = items || [];
    renderList();
  };

  window.onPreview = function (obj) {
    if (!obj || obj.error) {
      showPreviewText(obj && obj.error ? obj.error : "无法预览此文件");
      state.preview = null;
      return;
    }
    state.preview = { path: state.selected ? state.selected.path : null,
                      page: obj.page, total: obj.total };
    previewInfo.textContent = obj.name;
    previewStage.innerHTML = "";
    if (obj.data) {
      var img = document.createElement("img");
      img.src = obj.data;
      previewStage.appendChild(img);
    } else {
      showPreviewText("无法生成预览");
    }
    // 多页导航
    if (obj.pdf && obj.total > 1) {
      previewNav.hidden = false;
      previewPage.textContent = (obj.page + 1) + " / " + obj.total;
      $("btnPrev").disabled = obj.page <= 0;
      $("btnNext").disabled = obj.page >= obj.total - 1;
    } else {
      previewNav.hidden = true;
    }
  };

  // ---------------- 渲染 ----------------
  function renderList() {
    fileList.innerHTML = "";
    if (!state.items.length) {
      var e = document.createElement("div");
      e.className = "list-empty";
      e.textContent = "连接共享后显示文件列表";
      fileList.appendChild(e);
      return;
    }
    state.items.forEach(function (it) {
      var row = document.createElement("div");
      row.className = "list-row" + (it.is_dir ? " dir" : "");
      row.dataset.path = it.path;
      row.innerHTML =
        '<span class="col-name">' + esc(it.name) + '</span>' +
        '<span class="col-size">' + (it.is_dir ? "" : fmtSize(it.size)) + '</span>' +
        '<span class="col-time">' + fmtTime(it.mtime) + '</span>';
      row.addEventListener("click", function () { selectRow(row, it); });
      fileList.appendChild(row);
    });
  }

  function selectRow(row, it) {
    var prev = fileList.querySelector(".list-row.selected");
    if (prev) prev.classList.remove("selected");
    row.classList.add("selected");
    state.selected = { path: it.path, is_dir: it.is_dir, name: it.name };
    if (!it.is_dir) {
      apiCall("preview", it.path, 0);
    } else {
      showPreviewText("文件夹不支持预览");
    }
  }

  function showPreviewText(msg) {
    previewStage.innerHTML = '<span class="preview-placeholder">' + esc(msg) + '</span>';
    previewNav.hidden = true;
    previewInfo.textContent = "";
  }

  // ---------------- API 调用封装 ----------------
  function apiCall(method) {
    var args = Array.prototype.slice.call(arguments, 1);
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api[method]) {
        return window.pywebview.api[method].apply(window.pywebview.api, args);
      }
    } catch (e) { /* 忽略桥尚未就绪等瞬态错误 */ }
    return undefined;
  }

  // ---------------- 八向自由缩放逻辑 ----------------
  function refreshWinState() {
    var p = apiCall("get_window_rect");
    if (p && p.then) {
      p.then(function (r) {
        if (r && typeof r.width === "number") { winState.w = r.width; winState.h = r.height; }
      });
    }
  }

  function onResizeDown(e) {
    var dir = e.currentTarget.getAttribute("data-dir");
    if (!dir) return;
    e.preventDefault();
    resizeDir = dir;
    resizeStart = { mx: e.clientX, my: e.clientY, w: winState.w, h: winState.h };
    resizePending = null;
    document.body.classList.add("resizing");
    document.body.style.cursor = e.currentTarget.style.cursor;
    document.addEventListener("mousemove", onResizeMove);
    document.addEventListener("mouseup", onResizeUp);
    if (!resizeRAF) resizeRAF = requestAnimationFrame(applyResize);
  }

  function onResizeMove(e) {
    if (!resizeDir || !resizeStart) return;
    var dx = e.clientX - resizeStart.mx;
    var dy = e.clientY - resizeStart.my;
    var w = resizeStart.w, h = resizeStart.h;
    if (resizeDir.indexOf("e") >= 0) w = resizeStart.w + dx;
    if (resizeDir.indexOf("w") >= 0) w = resizeStart.w - dx;
    if (resizeDir.indexOf("s") >= 0) h = resizeStart.h + dy;
    if (resizeDir.indexOf("n") >= 0) h = resizeStart.h - dy;
    w = Math.max(MIN_W, Math.round(w));
    h = Math.max(MIN_H, Math.round(h));
    resizePending = { w: w, h: h, dir: resizeDir };
  }

  // 每帧最多提交一次缩放，避免高频 mousemove 造成卡顿/堆积
  function applyResize() {
    if (resizePending) {
      apiCall("resize_window", resizePending.w, resizePending.h, resizePending.dir);
      resizePending = null;
    }
    if (resizeDir) {
      resizeRAF = requestAnimationFrame(applyResize);
    } else {
      resizeRAF = null;
    }
  }

  function onResizeUp() {
    document.removeEventListener("mousemove", onResizeMove);
    document.removeEventListener("mouseup", onResizeUp);
    document.body.classList.remove("resizing");
    document.body.style.cursor = "";
    resizeDir = null;
    resizeStart = null;
    refreshWinState();   // 缩放结束后同步最新尺寸，保证下一次拖拽基准准确
  }

  // ---------------- 事件绑定 ----------------
  function bind() {
    $("btnConnect").addEventListener("click", function () {
      saveConfigFromForm();
      apiCall("connect");
    });
    $("btnDisconnect").addEventListener("click", function () { apiCall("disconnect"); });
    $("btnRefresh").addEventListener("click", function () { apiCall("refresh"); });
    $("btnUpload").addEventListener("click", function () { apiCall("upload"); });
    $("btnDownload").addEventListener("click", function () {
      if (!state.connected) { alert("请先连接共享"); return; }
      if (!state.selected || state.selected.is_dir) { alert("请先选择要下载的文件"); return; }
      apiCall("download", state.selected.path);
    });
    $("btnDelete").addEventListener("click", function () {
      if (!state.connected) { alert("请先连接共享后再删除"); return; }
      if (!state.selected) { alert("请先选择要删除的文件"); return; }
      if (!confirm("确定删除 " + state.selected.name + "？此操作不可恢复。")) return;
      apiCall("delete", state.selected.path);
    });
    $("btnAbout").addEventListener("click", showAbout);
    $("btnModalClose").addEventListener("click", function () { modal.hidden = true; });

    // ---- 在线更新 ----
    $("btnCheckUpdate").addEventListener("click", checkUpdate);
    $("btnUpdateClose").addEventListener("click", closeUpdateModal);
    $("btnUpdLater").addEventListener("click", closeUpdateModal);
    $("btnUpdNow").addEventListener("click", doUpdateNow);
    $("updateModal").addEventListener("click", function (e) {
      if (e.target === $("updateModal")) closeUpdateModal();
    });
    $("chkAutoCheck").addEventListener("change", function () {
      apiCall("set_update_prefs", $("chkAutoCheck").checked, null);
    });

    // ---- 小工具（工具箱） ----
    btnTools.addEventListener("click", openTools);
    btnToolsClose.addEventListener("click", closeTools);
    toolsModal.addEventListener("click", function (e) { if (e.target === toolsModal) closeTools(); });
    // 工具选择列表：点击卡片进入对应工具面板
    toolGrid.addEventListener("click", function (e) {
      var card = e.target.closest(".tool-card");
      if (card) showTool(card.getAttribute("data-tool"));
    });
    // 返回工具箱列表
    btnToolBack.addEventListener("click", backToTools);
    // 选择 PDF：按钮或点击拖拽区（按钮点击会冒泡，这里跳过按钮自身避免重复触发）
    btnPickPdf.addEventListener("click", pickPdf);
    toolsDrop.addEventListener("click", function (e) {
      if (e.target.closest("#btnPickPdf")) return;
      pickPdf();
    });
    // 拖拽支持：系统拖入仅能拿到文件名，无法获取真实路径，故触发系统选择框
    ["dragenter", "dragover"].forEach(function (ev) {
      toolsDrop.addEventListener(ev, function (e) {
        e.preventDefault();
        toolsDrop.classList.add("drag-over");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      toolsDrop.addEventListener(ev, function (e) {
        e.preventDefault();
        toolsDrop.classList.remove("drag-over");
      });
    });
    toolsDrop.addEventListener("drop", function () { pickPdf(); });
    btnDoCompress.addEventListener("click", doCompress);
    toolsLevel.querySelectorAll(".seg-btn").forEach(function (b) {
      b.addEventListener("click", function () {
        toolsLevel.querySelectorAll(".seg-btn").forEach(function (x) { x.classList.remove("active"); });
        b.classList.add("active");
        state.tools.level = b.getAttribute("data-level");
        // 仅自定义级别显示压缩率滑块
        toolsCustom.hidden = state.tools.level !== "custom";
      });
    });
    toolsRate.addEventListener("input", function () {
      state.tools.rate = parseInt(toolsRate.value, 10) || 0;
      toolsRateVal.textContent = state.tools.rate + "%";
    });

    // ---- 首次启动强制实名 ----
    btnNameOk.addEventListener("click", submitName);
    btnNameCancel.addEventListener("click", function () { apiCall("close_window"); });
    fRealName.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); submitName(); }
    });
    // 关闭增强：点击遮罩空白处 / 按 Esc 均可关闭「关于」与「作者选择」弹窗
    modal.addEventListener("click", function (e) { if (e.target === modal) modal.hidden = true; });
    authorModal.addEventListener("click", function (e) { if (e.target === authorModal) authorModal.hidden = true; });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        // 实名弹窗为强制项，Esc 不可关闭
        if (!nameModal.hidden) return;
        if (!modal.hidden) modal.hidden = true;
        if (!authorModal.hidden) authorModal.hidden = true;
        if (!serverFormModal.hidden) serverFormModal.hidden = true;
        else if (!serverModal.hidden) serverModal.hidden = true;
      }
    });

    // ---- 服务器管理 ----
    btnManage.addEventListener("click", openServerModal);
    btnServerClose.addEventListener("click", function () { serverModal.hidden = true; });
    btnAddServer.addEventListener("click", function () { openServerForm(null); });
    btnServerFormClose.addEventListener("click", function () { serverFormModal.hidden = true; });
    btnServerCancel.addEventListener("click", function () { serverFormModal.hidden = true; });
    btnServerSave.addEventListener("click", saveServerForm);
    serverModal.addEventListener("click", function (e) { if (e.target === serverModal) serverModal.hidden = true; });
    serverFormModal.addEventListener("click", function (e) { if (e.target === serverFormModal) serverFormModal.hidden = true; });
    btnCancel.addEventListener("click", function () { apiCall("cancel"); });
    $("btnPrev").addEventListener("click", function () { navPreview(-1); });
    $("btnNext").addEventListener("click", function () { navPreview(1); });

    // ---- 无边框窗口控制 ----
    btnMin.addEventListener("click", function () { apiCall("minimize"); });
    btnMax.addEventListener("click", function () {
      isMax = !isMax;
      document.body.classList.toggle("is-max", isMax);
      apiCall("toggle_maximize");
    });
    btnClose.addEventListener("click", function () { apiCall("close_window"); });
    // 双击标题栏区域 = 最大化 / 还原（仅 .title-drag 内生效，内容区不触发）
    var titleDrag = document.querySelector(".title-drag");
    if (titleDrag) {
      titleDrag.addEventListener("dblclick", function () {
        isMax = !isMax;
        document.body.classList.toggle("is-max", isMax);
        apiCall("toggle_maximize");
      });
    }

    // ---- 八向自由缩放热区 ----
    Array.prototype.forEach.call(document.querySelectorAll(".rz"), function (el) {
      el.addEventListener("mousedown", onResizeDown);
    });
    // 窗口几何变化（最大化/还原/外部缩放）后同步基准尺寸
    window.addEventListener("resize", refreshWinState);

    // ---- 关于弹窗中的「作者」可点击 → 弹出公司内 / 公司外选择 ----
    var mAuthor = $("mAuthor");
    function openAuthorChooser() { authorModal.hidden = false; }
    mAuthor.addEventListener("click", openAuthorChooser);
    mAuthor.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openAuthorChooser(); }
    });
    btnLinkInternal.addEventListener("click", function () {
      apiCall("open_url", authorLinks.internal);
      authorModal.hidden = true;
    });
    btnLinkExternal.addEventListener("click", function () {
      apiCall("open_url", authorLinks.external);
      authorModal.hidden = true;
    });
    btnAuthorClose.addEventListener("click", function () { authorModal.hidden = true; });
    authorModal.addEventListener("click", function (e) {
      if (e.target === authorModal) authorModal.hidden = true;
    });
  }

  function navPreview(delta) {
    if (!state.preview || !state.preview.path) return;
    var np = state.preview.page + delta;
    if (np < 0 || np >= state.preview.total) return;
    apiCall("preview", state.preview.path, np);
  }

  function saveConfigFromForm() {
    var cfg = {
      host: $("fHost").value.trim(),
      share: $("fShare").value.trim(),
      subfolder: $("fSub").value.trim(),
      username: $("fUser").value.trim(),
      password: $("fPass").value,
    };
    apiCall("save_config", cfg);
  }

  function showAbout() {
    var p = apiCall("about");
    if (p && p.then) {
      p.then(function (a) {
        if (!a) return;
        $("mName").textContent = a.app_name;
        $("mVer").textContent = "v" + a.version;
        $("mAuthor").textContent = a.author;
        $("mCopy").textContent = a.copyright;
        // 记录联系方式链接，供作者名点击后弹出选择使用
        authorLinks.internal = a.link_internal || "";
        authorLinks.external = a.link_external || "";
        modal.hidden = false;
      });
    }
  }

  // ---------------- 服务器多档管理 ----------------
  function applyConfig(cfg) {
    if (!cfg) return;
    $("fHost").value = cfg.host || "";
    $("fShare").value = cfg.share || "";
    $("fSub").value = cfg.subfolder || "";
    $("fUser").value = cfg.username || "";
    $("fPass").value = cfg.password || "";
  }

  function mkBtn(text, cls, handler) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.textContent = text;
    b.addEventListener("click", handler);
    return b;
  }

  function openServerModal() {
    var p = apiCall("list_servers");
    if (p && p.then) {
      p.then(function (list) { renderServerList(list || []); });
    } else {
      renderServerList([]);
    }
    serverModal.hidden = false;
  }

  function renderServerList(list) {
    serverList.innerHTML = "";
    if (!list.length) {
      var e = document.createElement("div");
      e.className = "server-empty";
      e.textContent = "暂无已保存的服务器，点击「添加服务器」新建。";
      serverList.appendChild(e);
      return;
    }
    list.forEach(function (s) {
      var item = document.createElement("div");
      item.className = "server-item" + (s.id === currentId ? " active" : "");
      var meta = "\\\\" + s.host + "\\" + s.share + (s.subfolder ? "\\" + s.subfolder : "");
      var info = document.createElement("div");
      info.className = "server-info";
      info.innerHTML =
        '<div class="server-name">' + esc(s.name) +
          (s.id === currentId ? '<span class="server-badge">当前</span>' : "") +
        '</div>' +
        '<div class="server-meta">' + esc(meta) + '</div>';
      var ops = document.createElement("div");
      ops.className = "server-ops";
      ops.appendChild(mkBtn("连接", "btn btn-secondary btn-sm", function () { useServer(s.id); }));
      ops.appendChild(mkBtn("编辑", "btn btn-ghost btn-sm", function () { openServerForm(s); }));
      ops.appendChild(mkBtn("删除", "btn btn-danger btn-sm", function () { deleteServer(s.id); }));
      item.appendChild(info);
      item.appendChild(ops);
      serverList.appendChild(item);
    });
  }

  function openServerForm(profile) {
    editingId = profile ? (profile.id || "") : "";
    serverFormTitle.textContent = profile ? "编辑服务器" : "添加服务器";
    sfName.value = profile ? (profile.name || "") : "";
    sfHost.value = profile ? (profile.host || "") : "";
    sfShare.value = profile ? (profile.share || "") : "";
    sfSub.value = profile ? (profile.subfolder || "") : "";
    sfUser.value = profile ? (profile.username || "") : "";
    sfPass.value = profile ? (profile.password || "") : "";
    serverFormModal.hidden = false;
    sfName.focus();
  }

  function saveServerForm() {
    var data = {
      id: editingId,
      name: sfName.value.trim(),
      host: sfHost.value.trim(),
      share: sfShare.value.trim(),
      subfolder: sfSub.value.trim(),
      username: sfUser.value.trim(),
      password: sfPass.value,
    };
    if (!data.host) { alert("请填写服务器地址"); sfHost.focus(); return; }
    var p = apiCall("save_server", data);
    var done = function (newId) {
      if (!newId) { alert("保存失败"); return; }
      serverFormModal.hidden = true;
      refreshServers();
    };
    if (p && p.then) p.then(done); else done(null);
  }

  function deleteServer(id) {
    if (!confirm("确定删除该服务器配置？此操作不可恢复。")) return;
    var q = apiCall("delete_server", id);
    var done = function () { refreshServers(); };
    if (q && q.then) q.then(done); else done();
  }

  function useServer(id) {
    var p = apiCall("use_server", id);
    var done = function () {
      refreshServers();                      // 同步主面板 + 列表高亮
      onStatus("已切换服务器配置", "success");
    };
    if (p && p.then) p.then(done); else done();
  }

  function refreshServers() {
    var p = apiCall("get_init");
    if (p && p.then) {
      p.then(function (init) {
        if (!init) return;
        currentId = init.current_id || null;
        applyConfig(init.config);
        if (!serverModal.hidden) {
          var q = apiCall("list_servers");
          if (q && q.then) q.then(function (list) { renderServerList(list || []); });
        }
      });
    }
  }

  // ---------------- 首次启动强制实名 ----------------
  function validateName(name) {
    name = (name || "").trim();
    if (!name) return "姓名不能为空";
    if (name.length < 2) return "姓名至少需 2 个汉字（姓氏 + 名字）";
    if (!/^[\u4e00-\u9fff·\u00b7\u30fb]+$/.test(name))
      return "姓名只能由中文及间隔号（·）组成，不能含字母、数字或特殊符号";
    return "";
  }

  function showNameModal() {
    nameError.textContent = "";
    fRealName.value = "";
    nameModal.hidden = false;
    setTimeout(function () { fRealName.focus(); }, 60);
  }

  function submitName() {
    var err = validateName(fRealName.value);
    if (err) { nameError.textContent = err; fRealName.focus(); return; }
    var p = apiCall("set_operator", fRealName.value.trim());
    var done = function (res) {
      if (res && res.ok) {
        nameModal.hidden = true;
      } else {
        nameError.textContent = (res && res.error) || "提交失败，请重试";
      }
    };
    if (p && p.then) p.then(done);
    else done({ ok: false, error: "接口未就绪" });
  }

  function maybeAskName(init) {
    // 仅当配置中尚无真实姓名时（首次启动）才强制弹出
    if (init && !init.operator) showNameModal();
  }

  // ---------------- 初始化 ----------------
  function renderInit(init) {
    if (!init) return;
    $("brandName").textContent = init.app_name || "SCAN.GATE";
    $("brandVer").textContent = "v" + (init.version || "");
    $("fHost").value = (init.config && init.config.host) || "";
    $("fShare").value = (init.config && init.config.share) || "";
    $("fSub").value = (init.config && init.config.subfolder) || "";
    $("fUser").value = (init.config && init.config.username) || "";
    $("fPass").value = (init.config && init.config.password) || "";
    currentId = (init.current_id != null) ? init.current_id : currentId;
    if (init.connected) {
      onConfigStatus("已连接", true);
    } else {
      onConfigStatus("未连接", false);
    }
    // 同步「启动自动检查更新」开关状态
    var chk = $("chkAutoCheck");
    if (chk && init.update) chk.checked = init.update.auto_check !== false;
    onStatus("就绪", "idle");
  }

  window.addEventListener("pywebviewready", function () {
    bind();
    refreshWinState();
    var p = apiCall("get_init");
    if (p && p.then) {
      p.then(function (init) {
        renderInit(init);
        maybeAskName(init);
        // 启动自检：写成功标记 / 报告上次更新结果 / 按偏好后台静默检查
        apiCall("startup_update_check");
      });
    }
  });

  // 兜底：若 pywebviewready 已过（极少数竞态），也尝试初始化
  if (window.pywebview) {
    var q = apiCall("get_init");
    if (q && q.then) q.then(function (init) { renderInit(init); maybeAskName(init); });
  }
})();
