#!/usr/bin/env python3
"""
SQL 拆分工具 - GUI 界面
基于 tkinter 的最简可用版，专业版功能

功能:
  - 选择SQL文件/目录
  - 选择输出目录
  - 选择方言
  - 一键拆分+转换
  - 查看转换报告
"""

import os
import sys
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext
from pathlib import Path
from typing import Optional

# 导入核心模块
try:
    from split_sql_v21 import split_sql_file, SQLDialect
    from dm_converter import DMConverter, convert_sqlserver_to_dm
    from report_generator import ConversionReportGenerator
    from license_checker import require_feature
except ImportError:
    from .split_sql_v21 import split_sql_file, SQLDialect
    from .dm_converter import DMConverter, convert_sqlserver_to_dm
    from .report_generator import ConversionReportGenerator
    from .license_checker import require_feature


class SQLSplitterGUI:
    """SQL拆分工具 GUI"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SQL Splitter - SQL Server→达梦迁移工具")
        self.root.geometry("720x560")
        self.root.resizable(True, True)
        
        self._build_ui()
    
    def _build_ui(self):
        """构建界面"""
        # ---- 顶部：输入选择 ----
        input_frame = ttk.LabelFrame(self.root, text="输入", padding=8)
        input_frame.pack(fill=tk.X, padx=8, pady=4)
        
        # 文件选择
        row1 = ttk.Frame(input_frame)
        row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="SQL文件:").pack(side=tk.LEFT)
        self.input_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.input_var, width=50).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ttk.Button(row1, text="浏览...", command=self._browse_input).pack(side=tk.RIGHT)
        
        # 输出目录
        row2 = ttk.Frame(input_frame)
        row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="输出目录:").pack(side=tk.LEFT)
        self.output_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.output_var, width=50).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ttk.Button(row2, text="浏览...", command=self._browse_output).pack(side=tk.RIGHT)
        
        # ---- 选项 ----
        opt_frame = ttk.LabelFrame(self.root, text="选项", padding=8)
        opt_frame.pack(fill=tk.X, padx=8, pady=4)
        
        opt_row = ttk.Frame(opt_frame)
        opt_row.pack(fill=tk.X)
        
        ttk.Label(opt_row, text="方言:").pack(side=tk.LEFT)
        self.dialect_var = tk.StringVar(value='auto')
        dialect_combo = ttk.Combobox(opt_row, textvariable=self.dialect_var, 
                                     values=['auto', 'sqlserver', 'oracle', 'mysql', 'postgresql', 'dm'],
                                     state='readonly', width=12)
        dialect_combo.pack(side=tk.LEFT, padx=4)
        
        self.convert_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_row, text="转换为达梦语法", variable=self.convert_var).pack(side=tk.LEFT, padx=12)
        
        self.report_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_row, text="生成质量报告", variable=self.report_var).pack(side=tk.LEFT, padx=4)
        
        # ---- 执行按钮 ----
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=8, pady=4)
        
        self.run_btn = ttk.Button(btn_frame, text="🚀 开始拆分+转换", command=self._run)
        self.run_btn.pack(side=tk.LEFT, padx=4)
        
        self.progress = ttk.Progressbar(btn_frame, mode='indeterminate')
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side=tk.RIGHT, padx=4)
        
        # ---- 输出区域（Notebook: 日志 | 报告） ----
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        
        # 日志tab
        log_frame = ttk.Frame(notebook)
        notebook.add(log_frame, text="日志")
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, font=("Menlo", 11))
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
        # 报告tab
        report_frame = ttk.Frame(notebook)
        notebook.add(report_frame, text="质量报告")
        self.report_text = scrolledtext.ScrolledText(report_frame, height=12, font=("Menlo", 10))
        self.report_text.pack(fill=tk.BOTH, expand=True)
        
        # ---- 底部状态栏 ----
        footer = ttk.Frame(self.root)
        footer.pack(fill=tk.X, padx=8, pady=2)
        try:
            from license_checker import get_current_tier
            tier = get_current_tier()
            tier_names = {'community': '社区版', 'pro': '专业版', 'enterprise': '企业版'}
            ttk.Label(footer, text=f"版本: {tier_names.get(tier, tier)}").pack(side=tk.LEFT)
        except:
            ttk.Label(footer, text="版本: 社区版").pack(side=tk.LEFT)
    
    def _browse_input(self):
        path = filedialog.askopenfilename(
            title="选择SQL文件",
            filetypes=[("SQL文件", "*.sql"), ("所有文件", "*.*")]
        )
        if path:
            self.input_var.set(path)
            # 自动推导输出目录
            if not self.output_var.get():
                self.output_var.set(os.path.splitext(path)[0] + '_split')
    
    def _browse_output(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_var.set(path)
    
    def _log(self, msg: str):
        """追加日志"""
        self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def _run(self):
        """执行拆分+转换"""
        input_path = self.input_var.get().strip()
        output_dir = self.output_var.get().strip()
        
        if not input_path:
            messagebox.showwarning("提示", "请选择SQL文件")
            return
        
        if not output_dir:
            output_dir = os.path.splitext(input_path)[0] + '_split'
            self.output_var.set(output_dir)
        
        if not os.path.isfile(input_path):
            messagebox.showerror("错误", f"文件不存在: {input_path}")
            return
        
        # 禁用按钮
        self.run_btn.config(state='disabled')
        self.progress.start()
        self.status_var.set("处理中...")
        self.log_text.delete('1.0', tk.END)
        self.report_text.delete('1.0', tk.END)
        
        try:
            self._do_split(input_path, output_dir)
        except Exception as e:
            self._log(f"❌ 错误: {e}")
            messagebox.showerror("错误", str(e))
        finally:
            self.run_btn.config(state='normal')
            self.progress.stop()
            self.status_var.set("就绪")
    
    def _do_split(self, input_path: str, output_dir: str):
        """执行拆分"""
        dialect_str = self.dialect_var.get()
        dialect = None
        if dialect_str != 'auto':
            try:
                dialect = SQLDialect[dialect_str.upper()]
            except KeyError:
                dialect = None
        
        self._log(f"📁 输入: {input_path}")
        self._log(f"📁 输出: {output_dir}")
        self._log(f"🔤 方言: {dialect_str}")
        self._log("")
        
        # Step 1: 拆分
        self._log("=== Step 1: 拆分SQL文件 ===")
        result = split_sql_file(
            input_path, output_dir,
            dialect=dialect,
            verbose=False,
            generate_merge=True,
        )
        
        if not result.success:
            self._log(f"❌ 拆分失败")
            for err in result.errors:
                self._log(f"  错误: {err}")
            return
        
        self._log(f"✅ 拆分完成: {result.total} 个对象")
        if result.stats:
            for obj_type, count in sorted(result.stats.items()):
                self._log(f"  {obj_type}: {count}")
        self._log("")
        
        # Step 2: 达梦转换
        if self.convert_var.get():
            self._log("=== Step 2: 转换为达梦语法 ===")
            dm_dir = output_dir + '_dm'
            os.makedirs(dm_dir, exist_ok=True)
            
            schema_prefix = os.path.basename(output_dir).replace('_split', '')
            converter = DMConverter()
            report_results = []
            ok = err_count = 0
            err_list = []
            
            type_map = {'proc': 'procedure', 'func': 'function', 'trig': 'trigger',
                        'view': 'view', 'table': 'table', 'idx': 'index', 'uidx': 'index',
                        'con': 'constraint', 'seq': 'sequence'}
            
            for f in sorted(os.listdir(output_dir)):
                if not f.endswith('.sql') or f == 'merge_all.sql':
                    continue
                
                obj_type = f.split('_')[0]
                mapped_type = type_map.get(obj_type, 'generic')
                
                with open(os.path.join(output_dir, f), 'r', encoding='utf-8') as fh:
                    content = fh.read()
                
                try:
                    converted = converter.convert(content, mapped_type, schema_prefix=schema_prefix)
                    with open(os.path.join(dm_dir, f), 'w', encoding='utf-8') as fh:
                        fh.write(converted.converted)
                    ok += 1
                    
                    # 收集报告数据
                    if self.report_var.get():
                        orig_lines = content.strip().count('\n') + 1
                        conv_lines = converted.converted.strip().count('\n') + 1
                        name = f.replace('.sql', '')
                        report_results.append({
                            'name': name, 'type': mapped_type, 'result': converted,
                            'original_lines': orig_lines, 'converted_lines': conv_lines,
                        })
                    
                    self._log(f"  ✅ {f}")
                except Exception as e:
                    err_count += 1
                    err_list.append(f"{f}: {str(e)[:80]}")
                    self._log(f"  ❌ {f}: {str(e)[:60]}")
            
            self._log(f"\n转换完成: {ok} 成功, {err_count} 失败")
            if err_list:
                for e in err_list[:5]:
                    self._log(f"  - {e}")
            self._log(f"\n达梦版输出: {dm_dir}")
            
            # Step 3: 生成质量报告
            if self.report_var.get() and report_results:
                self._log("\n=== Step 3: 转换质量报告 ===")
                batch = ConversionReportGenerator.generate_batch(report_results, schema_prefix=schema_prefix)
                
                # 保存报告文件
                report_md = os.path.join(dm_dir, 'conversion_report.md')
                report_html = os.path.join(dm_dir, 'conversion_report.html')
                report_json = os.path.join(dm_dir, 'conversion_report.json')
                
                batch.save_markdown(report_md)
                batch.save_html(report_html)
                batch.save_json(report_json)
                
                self._log(f"综合兼容性评分: {batch.overall_score}/100")
                self._log(f"报告已保存: {report_md}")
                
                # 在报告tab显示
                self.report_text.insert(tk.END, batch.to_markdown())
                self.report_text.see('1.0')
        else:
            self._log("\n(跳过达梦转换)")


def run_gui():
    """启动GUI"""
    root = tk.Tk()
    app = SQLSplitterGUI(root)
    root.mainloop()


if __name__ == '__main__':
    run_gui()
