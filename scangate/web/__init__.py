"""pywebview 混合架构包。

前端：scangate/web/static 下的 index.html + style.css + app.js（真·backdrop-filter 毛玻璃）。
后端：复用 scangate.services / scangate.config，通过 Api 类暴露给 JS。
后端只在独立线程中做阻塞工作，结果通过 evaluate_js 推回前端，绝不阻塞 UI 线程。
"""
