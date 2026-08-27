//! PDF 预览与压缩。

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

/// 图片/PDF 预览。
pub fn make_preview(
    path: &str,
    page: u32,
    cancel: &Arc<AtomicBool>,
) -> Result<crate::commands::PreviewResult, String> {
    let ext = std::path::Path::new(path)
        .extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .unwrap_or_default();

    // 图片：直接用 PNG data URL（简单路径，无 pdfium 依赖）
    if matches!(
        ext.as_str(),
        "png" | "jpg" | "jpeg" | "bmp" | "gif" | "tiff" | "webp"
    ) {
        let bytes = std::fs::read(path).map_err(|e| format!("读取 {path} 失败: {e}"))?;
        let mime = match ext.as_str() {
            "png" => "image/png",
            "jpg" | "jpeg" => "image/jpeg",
            "gif" => "image/gif",
            "webp" => "image/webp",
            _ => "image/png",
        };
        if cancel.load(Ordering::Relaxed) {
            return Err("已取消".into());
        }
        let data_url = format!("data:{};base64,{}", mime, base64_encode(&bytes));
        return Ok(crate::commands::PreviewResult {
            image: Some(data_url),
            page: 0,
            total: 1,
            pdf: false,
        });
    }

    // PDF：pdfium 渲染第一页（或指定页）为 base64 PNG
    if ext == "pdf" {
        return render_pdf_page(path, page, cancel);
    }

    Err(format!("暂不支持预览该文件类型: {ext}"))
}

fn render_pdf_page(
    path: &str,
    page: u32,
    cancel: &Arc<AtomicBool>,
) -> Result<crate::commands::PreviewResult, String> {
    if cancel.load(Ordering::Relaxed) {
        return Err("已取消".into());
    }
    // 初始化 pdfium（绑定系统 pdfium.dll）
    let bindings = pdfium_render::prelude::Pdfium::bind_to_system_library()
        .map_err(|e| format!("初始化 PDFium 失败: {e}"))?;
    let pdfium = pdfium_render::prelude::Pdfium::new(bindings);
    let pdf = pdfium
        .load_pdf_from_file(path, None)
        .map_err(|e| format!("打开 PDF 失败: {e}"))?;

    let total = pdf.pages().len() as u32;
    if total == 0 {
        return Ok(crate::commands::PreviewResult {
            image: None,
            page: 0,
            total: 0,
            pdf: true,
        });
    }
    let idx = page.min(total.saturating_sub(1));
    let page_handle = pdf.pages().get(idx).ok_or("渲染页面失败")?;
    let bitmap = page_handle
        .render_with_config(&pdfium_render::prelude::RenderConfig::default().set_target_width(560))
        .map_err(|e| format!("渲染失败: {e}"))?;
    let png = bitmap
        .as_image()
        .into_rgba()
        .expect("PNG 编码失败")
        .encode_png()
        .map_err(|e| format!("编码失败: {e}"))?;

    let data_url = format!("data:image/png;base64,{}", base64_encode(&png));
    Ok(crate::commands::PreviewResult {
        image: Some(data_url),
        page: idx,
        total,
        pdf: true,
    })
}

/// PDF 压缩：调用 Ghostscript（子进程）重光栅化。
/// - standard: 无损子集化
/// - high: 高压缩（重光栅化 108dpi）
/// - custom: rate 指定精度（0-100 越小压缩越狠）
pub fn compress(
    path: &str,
    level: &str,
    rate: Option<u32>,
    cancel: &Arc<AtomicBool>,
) -> Result<String, String> {
    if cancel.load(Ordering::Relaxed) {
        return Err("已取消".into());
    }
    // 输出文件名：原名_compressed.pdf（冲突追加序号）
    let base = path.trim_end_matches(".pdf");
    let mut dst = format!("{base}_compressed.pdf");
    let mut i = 1;
    while std::path::Path::new(&dst).exists() {
        dst = format!("{base}_compressed_{i}.pdf");
        i += 1;
    }

    // 查找 Ghostscript 可执行文件
    let gs = find_ghostscript().ok_or_else(|| {
        "未找到 Ghostscript（gswin64c.exe）。请安装后重试，或检查 PATH。".to_string()
    })?;

    // 参数：/sDEVICE=pdfwrite + 压缩级别
    let (dpi, pdfsettings): (u32, &str) = match level {
        "high" => (108, "/ebook"),
        "custom" => {
            let r = rate.unwrap_or(50).clamp(1, 100);
            // 0-100 映射到 dpi 200→72（值越大 DPI 越低)
            let dpi = 200u32.saturating_sub((r as f32 * 1.28) as u32).max(72);
            (dpi, "/ebook")
        }
        _ => (0, "/screen"),
    };

    let mut args = vec![
        "-q".to_string(),
        "-dNOPAUSE".to_string(),
        "-dBATCH".to_string(),
        "-dSAFER".to_string(),
        format!("-sDEVICE=pdfwrite"),
        format!("-dPDFSETTINGS={pdfsettings}"),
    ];
    if dpi > 0 {
        args.push(format!("-dDownsampleColorImages=true"));
        args.push(format!("-dColorImageResolution={dpi}"));
        args.push(format!("-dDownsampleGrayImages=true"));
        args.push(format!("-dGrayImageResolution={dpi}"));
        args.push(format!("-dDownsampleMonoImages=true"));
        args.push(format!("-dMonoImageResolution={dpi}"));
    }
    args.push(format!("-sOutputFile={dst}"));
    args.push(path.to_string());

    let st = std::process::Command::new(&gs)
        .args(&args)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map_err(|e| format!("Ghostscript 执行失败: {e}"))?;

    if !st.success() {
        return Err("Ghostscript 压缩失败".into());
    }
    let _ = std::fs::metadata(&dst).map(|m| m.len()).unwrap_or(0);
    Ok(dst)
}

fn find_ghostscript() -> Option<String> {
    for name in ["gswin64c.exe", "gswin32c.exe", "gs"] {
        if let Ok(path) = which(name) {
            return Some(path);
        }
    }
    // 常见安装路径
    for p in [
        r"C:\Program Files\gs\gswin64c.exe",
        r"C:\Program Files (x86)\gs\gswin64c.exe",
    ] {
        if std::path::Path::new(p).exists() {
            return Some(p.to_string());
        }
    }
    None
}

fn which(name: &str) -> Result<String, ()> {
    let path = std::env::var("PATH").unwrap_or_default();
    for dir in path.split(';') {
        let full = std::path::Path::new(&dir).join(name);
        if full.exists() {
            return Ok(full.to_string_lossy().to_string());
        }
    }
    Err(())
}

/// 标准库 base64 编码（避免额外依赖冲突）。
fn base64_encode(bytes: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(bytes.len() * 4 / 3 + 4);
    for chunk in bytes.chunks(3) {
        let b0 = chunk[0] as u32;
        let b1 = *chunk.get(1).unwrap_or(&0) as u32;
        let b2 = *chunk.get(2).unwrap_or(&0) as u32;
        let n = (b0 << 16) | (b1 << 8) | b2;
        out.push(TABLE[(n >> 18) as usize & 63] as char);
        out.push(TABLE[(n >> 12) as usize & 63] as char);
        if chunk.len() > 1 {
            out.push(TABLE[(n >> 6) as usize & 63] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(TABLE[n as usize & 63] as char);
        } else {
            out.push('=');
        }
    }
    out
}
