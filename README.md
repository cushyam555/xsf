# XSF → SF2 สำหรับ Windows

โปรแกรมแปลงไฟล์ XSF/XSTM v1 รูปแบบที่วิเคราะห์จากตัวอย่าง ให้กลับเป็น SoundFont 2

## ดาวน์โหลดและใช้งาน

1. เปิด [Releases ล่าสุด](https://github.com/cushyam555/xsf/releases/latest)
2. ดาวน์โหลด `XSF-to-SF2-Windows-x64.zip` แล้วแตก ZIP
3. เปิด `XSF-to-SF2.exe` บน Windows 10/11 แบบ 64 บิต ไม่ต้องติดตั้ง Python
4. เลือก `.XSF` กด **แปลงและบันทึก .SF2** แล้วเลือกปลายทาง

ไฟล์ EXE รุ่นนี้ยังไม่ได้ลงลายเซ็นดิจิทัล โปรแกรมแสดง SHA-256 ของ SF2 ที่สร้างเสร็จเพื่อใช้เทียบกับต้นฉบับถ้ามี

## ความสามารถและขอบเขต

- อ่านและเขียนทีละ 8 MiB ใช้ CPU/NumPy สำหรับ XOR ไม่ต้องใช้ GPU
- แปลงใน worker thread พร้อมความคืบหน้า ความเร็ว และปุ่มยกเลิก
- บันทึกลงไฟล์ชั่วคราว แล้วเปลี่ยนเป็นไฟล์ปลายทางเมื่อทำงานสำเร็จเท่านั้น
- คำนวณ SHA-256 ระหว่างเขียนโดยไม่โหลดทั้งไฟล์เข้า RAM
- ส่งออกข้อมูลวิเคราะห์ส่วนหัว 4 KiB และท้ายไม่เกิน 4 MiB เป็น JSON ไม่มีการอัปโหลดอัตโนมัติ
- รองรับเฉพาะส่วนหัว `XSTM` รุ่น 1 ขนาด 1,116 ไบต์ และ payload แบบ XOR คีย์ 128 ไบต์วนซ้ำ
- คีย์ถูกอนุมานจากสถิติหลายช่วงและหัว SF2 แล้วตรวจโครงสร้าง RIFF/INFO/sdta/pdta วิธีนี้ยังไม่รับรอง XSF ทุกไฟล์
- การตรวจโครงสร้างผ่านไม่ได้พิสูจน์ความถูกต้องของเสียงทุกตัว เว้นแต่เทียบกับต้นฉบับครบทุกไบต์หรือ SHA-256
- RIFF/SF2 แบบนี้มีขอบเขตขนาดประมาณ 4 GiB โปรแกรมเล่น SoundFont อาจมีข้อจำกัดต่ำกว่านี้

หากขึ้นว่าหาคีย์ไม่ได้ ให้กด **ส่งออกข้อมูลวิเคราะห์** แล้วแนบ JSON กลับมาเพื่อตรวจรูปแบบเพิ่มเติม การเพิ่ม RAM/CPU/GPU อย่างเดียวไม่แก้คีย์ที่ผิด

## ผลทดสอบ

ก่อนพอร์ตเป็น Windows ได้ตรวจไฟล์ GeneralUser-GS XSF สองตัวอย่างขนาดประมาณ 31 MiB แล้วได้ผลตรงกับ SF2 ต้นฉบับทุกไบต์ และได้ทดสอบการอ่านเขียนแบบ streaming กับไฟล์จำลอง 1 GiB โดยตรวจผลครบทุกไบต์ ตัวอย่างของผู้ใช้ไม่ได้อัปโหลดไว้ใน repository นี้

โค้ด Python รุ่น Windows ทดสอบซ้ำกับตัวอย่างจริงทั้งสองและไฟล์จำลองขนาดใหญ่ก่อนเผยแพร่ ดูผล CI สำหรับการทดสอบบน Windows และ Linux รวมถึงการทดสอบไฟล์ EXE หลัง build

## Command line

ใช้ `XSF-to-SF2-CLI.exe` เมื่อเรียกจาก PowerShell:

```powershell
.\XSF-to-SF2-CLI.exe --cli "bank.xsf" "bank.recovered.sf2"
.\XSF-to-SF2-CLI.exe --cli "bank.xsf" "bank.diagnostic.json" --diagnostic
```

เพิ่ม `--force` เมื่อต้องการเขียนทับ SF2 ปลายทางที่มีอยู่แล้ว ไม่สามารถเขียนทับต้นทางได้

## รันและ build จากซอร์ส

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-build.txt
python -m unittest discover -v
python main.py
python -m PyInstaller --noconfirm --clean --onefile --windowed --name XSF-to-SF2 main.py
```

GitHub Actions ทดสอบบน Windows/Linux และสร้าง EXE บน Windows จริง การ push tag `v*` จะสร้าง Release พร้อม ZIP และ checksum หลังผ่านการทดสอบ
