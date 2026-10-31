# Detector Belakang (Motion Alert)

Aplikasi pendeteksi gerakan di belakang user menggunakan webcam. Saat ada orang bergerak di belakang (selain wajah user yang di-ignore), aplikasi akan:
- Membawa window ke depan (topmost)
- Memainkan suara alarm (`alert.wav`)
- Menyimpan screenshot + log

## Struktur Folder

```text
.
├── motion_alert_prod.py          # Script utama
├── requirements.txt              # Daftar dependency Python
├── .gitignore
├── README.md
├── alert.wav                     # Suara alarm (sediakan sendiri)
├── blaze_face_short_range.tflite # Model MediaPipe Face Detector
├── env/                          # Virtual environment (di-gitignore)
├── screenshots/                  # Hasil screenshot saat ada gerakan
└── logs/                         # Log deteksi harian
```

## Instalasi

```bash
# 1. Buat virtual environment
python -m venv env

# 2. Aktifkan env
# Windows:
env\Scripts\activate
# Linux/Mac:
source env/bin/activate

# 3. Install dependency
pip install -r requirements.txt
```

> **Catatan:** 
> - File `alert.wav` dan `blaze_face_short_range.tflite` harus ada di folder yang sama dengan `motion_alert_prod.py`.

## Menjalankan

```bash
python motion_alert_prod.py
```

## Kontrol

| Aksi | Cara |
|------|------|
| ON/OFF detector | Klik tombol hijau/merah di pojok kanan atas, atau tekan `P` |

- **Hijau (ON)**: deteksi aktif
- **Merah (OFF)**: deteksi nonaktif, overlay hitam tampil

## Konfigurasi

Edit di bagian `# --- KONFIGURASI ---` pada `motion_alert_prod.py`:

| Variabel | Default | Keterangan |
|----------|---------|------------|
| `TARGET_CAMERA_NAME` | `"Logitech"` | **Nama unik webcam fisik** (auto-detect). Ubah sesuai nama hardware Anda agar tidak tertukar dengan virtual camera. |
| `SENSITIVITAS` | `800` | Minimum area kontur (piksel) untuk dianggap gerakan |
| `VAR_THRESHOLD` | `16` | Ambang varians background subtractor MOG2 |
| `COOLDOWN` | `2` | Jarak minimal antar alert (detik) |
| `MODEL_PATH` | `"blaze_face_short_range.tflite"` | Path model face detector |
| `SCREENSHOT_MAX_AGE_HOURS` | `12` | Umur maksimal screenshot sebelum dihapus otomatis |
| `CLEANUP_INTERVAL_SECONDS` | `3600` | Interval pengecekan cleanup (detik) |
| `WINDOW_WIDTH` | `1366` | Lebar window |
| `WINDOW_HEIGHT` | `768` | Tinggi window |

## Fitur Utama

1. **Auto-Detect Webcam by Name** — Menggunakan `pygrabber` untuk mencari webcam berdasarkan nama hardware unik. Mengabaikan virtual camera (seperti Phone Link/OBS) yang sering berubah indeks atau terputus.
2. **Face Ignoring** — wajah user (paling besar & dekat posisi duduk) di-ignore agar tidak memicu alarm.
3. **Locking Box** — histeresis IoU agar kotak ignore tidak loncat ke orang lain saat user menoleh.
4. **Topmost Alert** — window otomatis muncul paling depan saat terdeteksi gerakan.
5. **Toggle ON/OFF** — via klik tombol atau hotkey `P`.
6. **Auto Cleanup** — screenshot lama dihapus otomatis berdasarkan umur.
7. **Logging** — setiap event dicatat di `logs/detector_log_YYYYMMDD.txt`.
8. **Screenshot** — disimpan di `screenshots/motion_YYYYMMDD_HHMMSS.jpg`.

## Output

- **Screenshot**: `screenshots/`
- **Log harian**: `logs/detector_log_YYYYMMDD.txt`

## Troubleshooting

- **"Kamera dengan nama mengandung 'X' tidak ditemukan"** → Buka script, lihat output `=== Daftar Kamera Terdeteksi ===` di terminal. Salin nama webcam fisik Anda dan ubah variabel `TARGET_CAMERA_NAME` di konfigurasi.
- **Terdeteksi virtual camera (Phone Link/OBS)** → Pastikan `TARGET_CAMERA_NAME` hanya mengarah ke webcam fisik (misal: `"Integrated Camera"`, `"HD Pro Webcam"`). Virtual camera akan otomatis diabaikan.
- **File `alert.wav` tidak ditemukan** → letakkan di folder yang sama dengan script.
- **Model tidak ditemukan** → download `blaze_face_short_range.tflite` dari MediaPipe dan letakkan di folder project.
- **Cleanup tidak jalan** → pastikan folder `screenshots/` dapat ditulis (permission OK).