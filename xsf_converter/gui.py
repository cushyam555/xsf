"""Tk widgets are touched only by the main thread."""
from __future__ import annotations
import queue
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from . import __version__
from .core import Cancelled, convert, diagnostic

class App:
    def __init__(self, root):
        self.root, self.bus, self.stop = root, queue.Queue(), threading.Event()
        self.busy = False
        root.title(f"XSF → SF2  {__version__}")
        root.geometry("780x570");root.minsize(680, 510)
        outer = ttk.Frame(root, padding=24);outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="XSF → SF2", font=("Segoe UI", 24, "bold")).pack(anchor="w")
        ttk.Label(outer, text="แปลงไฟล์ในเครื่อง • รองรับไฟล์ใหญ่ด้วยการอ่านเขียนทีละส่วน").pack(anchor="w", pady=(4, 20))
        self.path = tk.StringVar()
        row = ttk.Frame(outer);row.pack(fill="x")
        self.entry = ttk.Entry(row, textvariable=self.path);self.entry.pack(side="left", fill="x", expand=True)
        self.browse = ttk.Button(row, text="เลือกไฟล์ .XSF", command=self.choose);self.browse.pack(side="left", padx=(8, 0))
        row = ttk.Frame(outer);row.pack(fill="x", pady=16)
        self.run = ttk.Button(row, text="แปลงและบันทึก .SF2", command=self.start);self.run.pack(side="left")
        self.cancel = ttk.Button(row, text="ยกเลิก", command=self.stop.set, state="disabled");self.cancel.pack(side="left", padx=8)
        self.diag = ttk.Button(row, text="ส่งออกข้อมูลวิเคราะห์", command=self.export);self.diag.pack(side="left")
        self.bar = ttk.Progressbar(outer, maximum=100);self.bar.pack(fill="x")
        self.status = tk.StringVar(value="พร้อมใช้งาน")
        ttk.Label(outer, textvariable=self.status, wraplength=710).pack(anchor="w", pady=12)
        self.result = tk.Text(outer, height=7, wrap="word", font=("Consolas", 10), state="disabled")
        self.result.pack(fill="both", expand=True)
        ttk.Label(outer, text="รองรับ XSTM v1 แบบที่ทดสอบแล้ว การหาคีย์ยังเป็นการอนุมาน\n"
                  "หากถอดไม่ได้ ให้ส่งข้อมูลวิเคราะห์กลับมาตรวจต่อ ไม่อัปโหลดไฟล์โดยอัตโนมัติ",
                  wraplength=710).pack(anchor="w", pady=(16, 0))
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
    def choose(self):
        path = filedialog.askopenfilename(filetypes=[("XSF", "*.xsf"), ("ทุกไฟล์", "*.*")])
        if path:self.path.set(path)
    def selected(self):
        p = Path(self.path.get())
        if not p.is_file():
            messagebox.showerror("เลือกไฟล์", "กรุณาเลือกไฟล์ .XSF ที่มีอยู่จริง");return None
        return p
    def set_busy(self, value):
        self.busy = value
        for widget in (self.entry, self.browse, self.run, self.diag):
            widget.configure(state="disabled" if value else "normal")
        self.cancel.configure(state="normal" if value else "disabled")
    def show_result(self, text):
        self.result.configure(state="normal");self.result.delete("1.0", "end")
        self.result.insert("end", text);self.result.configure(state="disabled")
    def start(self):
        source = self.selected()
        if source is None:return
        target = filedialog.asksaveasfilename(defaultextension=".sf2", initialfile=source.stem+".recovered.sf2",
                                             filetypes=[("SoundFont", "*.sf2")])
        if not target:return
        self.stop.clear();self.bar["value"]=0;self.set_busy(True);self.show_result("")
        def worker():
            started = time.monotonic();last = 0
            def progress(done, size):
                nonlocal last
                now = time.monotonic()
                if now-last >= .15 or done == size:
                    self.bus.put(("progress", (done, size, now-started)));last=now
            try:
                result = convert(source, target, overwrite=True, cancel=self.stop.is_set,
                                 progress=progress, status=lambda s:self.bus.put(("status", s)))
                self.bus.put(("success", result))
            except Cancelled:self.bus.put(("cancelled", None))
            except Exception as error:self.bus.put(("error", str(error)))
        threading.Thread(target=worker, daemon=True).start()
    def export(self):
        source=self.selected()
        if source is None:return
        target=filedialog.asksaveasfilename(defaultextension=".json", initialfile=source.name+".diagnostic.json",
                                          filetypes=[("Diagnostic JSON", "*.json")])
        if not target:return
        # Diagnostics use exclusive creation, even after a save dialog.
        if Path(target).exists():
            messagebox.showerror("ไฟล์มีอยู่แล้ว", "กรุณาเลือกชื่อใหม่สำหรับข้อมูลวิเคราะห์");return
        self.stop.clear();self.set_busy(True);self.cancel.configure(state="disabled")
        self.status.set("กำลังส่งออกส่วนหัว 4 KiB และส่วนท้ายไม่เกิน 4 MiB…")
        def worker():
            try:diagnostic(source, target);self.bus.put(("diagnostic", target))
            except Exception as error:self.bus.put(("error", str(error)))
        threading.Thread(target=worker, daemon=True).start()
    def poll(self):
        try:
            while True:
                kind,value=self.bus.get_nowait()
                if kind=="status":self.status.set(value)
                elif kind=="progress":
                    done,size,elapsed=value;self.bar["value"]=100*done/size
                    self.status.set(f"{100*done/size:.1f}% • {done/1048576:,.0f} / {size/1048576:,.0f} MiB • {done/1048576/max(elapsed,.001):.1f} MiB/s")
                else:
                    self.set_busy(False)
                    if kind=="success":
                        self.status.set("บันทึกสำเร็จ")
                        self.show_result(f"{value.path}\n\nSHA-256: {value.sha256}\n"
                                         f"{value.info.size:,} ไบต์ • {value.info.presets} พรีเซ็ต • {value.info.samples} ตัวอย่างเสียง\n\n"
                                         "ตรวจโครงสร้างผ่าน ไม่ใช่การรับรองเสียงทุกตัวสำหรับไฟล์ที่ยังไม่เคยเทียบต้นฉบับ")
                    elif kind=="diagnostic":
                        self.status.set("ส่งออกข้อมูลวิเคราะห์แล้ว")
                        self.show_result(f"{value}\n\nไฟล์นี้มีส่วนหัวและท้ายของ XSF สามารถแนบกลับมาเพื่อตรวจสอบได้")
                    elif kind=="cancelled":self.status.set("ยกเลิกแล้ว ไฟล์ต้นทางไม่ถูกเปลี่ยน")
                    else:self.status.set("ทำงานไม่สำเร็จ");self.show_result(value)
        except queue.Empty:pass
        self.root.after(100, self.poll)
    def close(self):
        if self.busy:
            messagebox.showinfo("กำลังทำงาน", "กรุณากดยกเลิกและรอให้หยุดก่อนปิดโปรแกรม");return
        self.root.destroy()

def main():
    root=tk.Tk();ttk.Style(root).theme_use("clam");App(root);root.mainloop()
