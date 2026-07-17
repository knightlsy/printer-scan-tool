#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
打印机扫描工具 - 带文件管理UI的应用程序
将原有的批处理脚本转换为图形界面应用程序
"""

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
from datetime import datetime

class PrinterScannerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("打印机扫描工具 - 文件管理器")
        self.root.geometry("900x700")
        
        # 默认配置
        self.share_path = r"\\192.168.4.82\share\PDF"
        self.username = "share"
        self.password = "share"
        
        self.setup_ui()
        
    def setup_ui(self):
        # 主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 配置区域
        config_frame = ttk.LabelFrame(main_frame, text="网络共享配置", padding="10")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # 共享路径
        ttk.Label(config_frame, text="共享路径:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.share_var = tk.StringVar(value=self.share_path)
        self.share_entry = ttk.Entry(config_frame, textvariable=self.share_var, width=50)
        self.share_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=(0, 10))
        
        # 用户名
        ttk.Label(config_frame, text="用户名:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.user_var = tk.StringVar(value=self.username)
        self.user_entry = ttk.Entry(config_frame, textvariable=self.user_var, width=20)
        self.user_entry.grid(row=1, column=1, sticky=tk.W, padx=(0, 10), pady=(5, 0))
        
        # 密码
        ttk.Label(config_frame, text="密码:").grid(row=2, column=0, sticky=tk.W, padx=(0, 5), pady=(5, 0))
        self.pass_var = tk.StringVar(value=self.password)
        self.pass_entry = ttk.Entry(config_frame, textvariable=self.pass_var, width=20, show="*")
        self.pass_entry.grid(row=2, column=1, sticky=tk.W, padx=(0, 10), pady=(5, 0))
        
        # 测试连接按钮
        ttk.Button(config_frame, text="测试连接", command=self.test_connection).grid(
            row=0, column=2, rowspan=3, padx=(20, 0), sticky=tk.N)
        
        # 控制按钮区域
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Button(button_frame, text="连接共享", command=self.connect_share).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="断开连接", command=self.disconnect_share).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="打开文件夹", command=self.open_folder).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="刷新文件列表", command=self.refresh_file_list).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="上传文件", command=self.upload_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="下载文件", command=self.download_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="删除文件", command=self.delete_file, style="Danger.TButton").pack(side=tk.LEFT)
        
        # 文件列表区域
        list_frame = ttk.LabelFrame(main_frame, text="文件列表", padding="10")
        list_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        # 创建Treeview
        columns = ("文件名", "大小", "修改时间", "类型")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        
        # 设置列标题
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=150)
        
        # 设置列宽
        self.tree.column("文件名", width=300)
        self.tree.column("大小", width=100)
        self.tree.column("修改时间", width=150)
        self.tree.column("类型", width=100)
        
        # 添加滚动条
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # 网格布局
        self.tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 使列表区域可扩展
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        
        # 状态区域
        status_frame = ttk.LabelFrame(main_frame, text="状态信息", padding="10")
        status_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        self.status_text = scrolledtext.ScrolledText(status_frame, height=8, width=80)
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 底部信息
        info_frame = ttk.Frame(main_frame)
        info_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(10, 0))
        
        self.info_label = ttk.Label(info_frame, text="就绪")
        self.info_label.pack(side=tk.LEFT)
        
        # 配置网格权重
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(2, weight=1)
        
        # 绑定双击事件
        self.tree.bind("<Double-1>", self.on_file_double_click)
        
        # 初始化文件列表
        self.refresh_file_list()
        
    def log_message(self, message):
        """记录状态消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        self.status_text.insert(tk.END, log_entry)
        self.status_text.see(tk.END)
        self.info_label.config(text=message)
        
    def test_connection(self):
        """测试网络连接"""
        def test_thread():
            self.log_message("正在测试连接...")
            share_path = self.share_var.get()
            
            try:
                # 尝试ping目标主机
                host = share_path.split("\\")[2]
                result = subprocess.run(["ping", "-n", "2", host], 
                                      capture_output=True, text=True, shell=True)
                
                if result.returncode == 0:
                    self.log_message(f"连接测试成功: 可以访问 {host}")
                    messagebox.showinfo("连接测试", f"可以访问主机 {host}")
                else:
                    self.log_message(f"连接测试失败: 无法访问 {host}")
                    messagebox.showerror("连接测试", f"无法访问主机 {host}")
                    
            except Exception as e:
                self.log_message(f"连接测试出错: {str(e)}")
                messagebox.showerror("连接测试", f"测试出错: {str(e)}")
        
        threading.Thread(target=test_thread, daemon=True).start()
        
    def connect_share(self):
        """连接网络共享"""
        def connect_thread():
            share_path = self.share_var.get()
            username = self.user_var.get()
            password = self.pass_var.get()
            
            self.log_message(f"正在连接共享: {share_path}")
            
            try:
                # 先断开已有连接
                subprocess.run(f"net use {share_path} /delete /y", 
                             shell=True, capture_output=True)
                
                # 建立新连接
                cmd = f'net use "{share_path}" "{password}" /user:"{username}" /persistent:no'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                
                if result.returncode == 0:
                    self.log_message(f"成功连接共享: {share_path}")
                    messagebox.showinfo("连接成功", f"已成功连接到 {share_path}")
                    self.refresh_file_list()
                else:
                    self.log_message(f"连接失败: {result.stderr}")
                    messagebox.showerror("连接失败", f"连接失败:\n{result.stderr}")
                    
            except Exception as e:
                self.log_message(f"连接出错: {str(e)}")
                messagebox.showerror("连接出错", f"连接过程中出错: {str(e)}")
        
        threading.Thread(target=connect_thread, daemon=True).start()
        
    def disconnect_share(self):
        """断开网络共享"""
        share_path = self.share_var.get()
        
        try:
            result = subprocess.run(f"net use {share_path} /delete /y", 
                                  shell=True, capture_output=True, text=True)
            
            if result.returncode == 0:
                self.log_message(f"已断开共享连接: {share_path}")
                messagebox.showinfo("断开成功", f"已断开与 {share_path} 的连接")
                # 清空文件列表
                for item in self.tree.get_children():
                    self.tree.delete(item)
            else:
                self.log_message(f"断开失败: {result.stderr}")
                messagebox.showerror("断开失败", f"断开连接失败:\n{result.stderr}")
                
        except Exception as e:
            self.log_message(f"断开连接出错: {str(e)}")
            messagebox.showerror("断开出错", f"断开连接过程中出错: {str(e)}")
            
    def open_folder(self):
        """打开共享文件夹"""
        share_path = self.share_var.get()
        
        try:
            subprocess.run(f'explorer "{share_path}"', shell=True)
            self.log_message(f"已打开文件夹: {share_path}")
        except Exception as e:
            self.log_message(f"打开文件夹出错: {str(e)}")
            messagebox.showerror("打开失败", f"无法打开文件夹:\n{str(e)}")
            
    def refresh_file_list(self):
        """刷新文件列表"""
        def refresh_thread():
            share_path = self.share_var.get()
            
            # 清空现有列表
            for item in self.tree.get_children():
                self.tree.delete(item)
                
            self.log_message("正在刷新文件列表...")
            
            try:
                # 检查路径是否存在
                if not os.path.exists(share_path):
                    self.log_message(f"路径不存在: {share_path}")
                    return
                    
                # 获取文件列表
                files = []
                for item in os.listdir(share_path):
                    item_path = os.path.join(share_path, item)
                    if os.path.isfile(item_path):
                        size = os.path.getsize(item_path)
                        mtime = datetime.fromtimestamp(os.path.getmtime(item_path))
                        files.append((item, size, mtime, "文件"))
                    else:
                        files.append((item, "-", "-", "文件夹"))
                
                # 按类型排序（文件夹在前）
                files.sort(key=lambda x: (0 if x[3] == "文件夹" else 1, x[0].lower()))
                
                # 添加到Treeview
                for file_info in files:
                    size_str = self.format_size(file_info[1]) if file_info[1] != "-" else "-"
                    time_str = file_info[2].strftime("%Y-%m-%d %H:%M") if file_info[2] != "-" else "-"
                    self.tree.insert("", tk.END, values=(
                        file_info[0], size_str, time_str, file_info[3]
                    ))
                
                self.log_message(f"找到 {len(files)} 个项目")
                
            except Exception as e:
                self.log_message(f"刷新文件列表出错: {str(e)}")
                
        threading.Thread(target=refresh_thread, daemon=True).start()
        
    def format_size(self, size_bytes):
        """格式化文件大小"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
        
    def on_file_double_click(self, event):
        """双击文件事件"""
        item = self.tree.selection()
        if item:
            values = self.tree.item(item[0], "values")
            if values and values[3] == "文件夹":
                # 如果是文件夹，进入该文件夹
                share_path = self.share_var.get()
                folder_name = values[0]
                new_path = os.path.join(share_path, folder_name)
                self.share_var.set(new_path)
                self.refresh_file_list()
            else:
                # 如果是文件，尝试打开
                self.open_selected_file()
                
    def open_selected_file(self):
        """打开选中的文件"""
        item = self.tree.selection()
        if item:
            values = self.tree.item(item[0], "values")
            if values and values[3] == "文件":
                share_path = self.share_var.get()
                file_name = values[0]
                file_path = os.path.join(share_path, file_name)
                
                try:
                    os.startfile(file_path)
                    self.log_message(f"已打开文件: {file_name}")
                except Exception as e:
                    self.log_message(f"打开文件失败: {str(e)}")
                    messagebox.showerror("打开失败", f"无法打开文件:\n{str(e)}")
                    
    def upload_file(self):
        """上传文件到共享"""
        file_path = filedialog.askopenfilename(title="选择要上传的文件")
        if not file_path:
            return
            
        share_path = self.share_var.get()
        file_name = os.path.basename(file_path)
        dest_path = os.path.join(share_path, file_name)
        
        try:
            # 检查目标路径是否存在
            if not os.path.exists(share_path):
                messagebox.showerror("上传失败", "共享路径不存在，请先连接共享")
                return
                
            # 复制文件
            import shutil
            shutil.copy2(file_path, dest_path)
            
            self.log_message(f"已上传文件: {file_name}")
            messagebox.showinfo("上传成功", f"文件 {file_name} 上传成功")
            self.refresh_file_list()
            
        except Exception as e:
            self.log_message(f"上传文件失败: {str(e)}")
            messagebox.showerror("上传失败", f"上传文件失败:\n{str(e)}")
            
    def download_file(self):
        """从共享下载文件"""
        item = self.tree.selection()
        if not item:
            messagebox.showwarning("选择文件", "请先选择一个文件")
            return
            
        values = self.tree.item(item[0], "values")
        if not values or values[3] != "文件":
            messagebox.showwarning("选择文件", "请选择一个文件（不能是文件夹）")
            return
            
        share_path = self.share_var.get()
        file_name = values[0]
        source_path = os.path.join(share_path, file_name)
        
        dest_path = filedialog.asksaveasfilename(
            title="保存文件",
            initialfile=file_name,
            defaultextension=os.path.splitext(file_name)[1]
        )
        
        if not dest_path:
            return
            
        try:
            import shutil
            shutil.copy2(source_path, dest_path)
            
            self.log_message(f"已下载文件: {file_name} -> {dest_path}")
            messagebox.showinfo("下载成功", f"文件 {file_name} 下载成功")
            
        except Exception as e:
            self.log_message(f"下载文件失败: {str(e)}")
            messagebox.showerror("下载失败", f"下载文件失败:\n{str(e)}")
            
    def delete_file(self):
        """删除选中的文件"""
        item = self.tree.selection()
        if not item:
            messagebox.showwarning("选择文件", "请先选择一个文件或文件夹")
            return
            
        values = self.tree.item(item[0], "values")
        if not values:
            return
            
        file_name = values[0]
        file_type = values[3]
        
        # 确认对话框
        confirm = messagebox.askyesno(
            "确认删除",
            f"确定要删除{file_type} '{file_name}' 吗？\n此操作不可恢复！"
        )
        
        if not confirm:
            return
            
        share_path = self.share_var.get()
        target_path = os.path.join(share_path, file_name)
        
        try:
            if file_type == "文件":
                os.remove(target_path)
            else:
                import shutil
                shutil.rmtree(target_path)
                
            self.log_message(f"已删除{file_type}: {file_name}")
            self.refresh_file_list()
            
        except Exception as e:
            self.log_message(f"删除{file_type}失败: {str(e)}")
            messagebox.showerror("删除失败", f"删除{file_type}失败:\n{str(e)}")

def main():
    root = tk.Tk()
    
    # 设置样式
    style = ttk.Style()
    style.configure("Danger.TButton", foreground="red")
    
    app = PrinterScannerApp(root)
    
    # 使窗口可调整大小
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)
    
    root.mainloop()

if __name__ == "__main__":
    main()