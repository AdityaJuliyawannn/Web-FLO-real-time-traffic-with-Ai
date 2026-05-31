# 🚦 FLO: Sistem Navigasi Cerdas Berbasis Deteksi Kendaraan dan Rute Optimal

Flo adalah sistem navigasi berbasis web yang memanfaatkan deteksi kendaraan secara real-time menggunakan YOLOv8 dan perhitungan rute terbaik dengan algoritma A*. Sistem ini dirancang untuk membantu pengguna menentukan rute perjalanan terbaik di Kota Semarang berdasarkan kondisi lalu lintas terkini yang diambil dari CCTV di berbagai titik strategis.

## 🗝️ Fitur Utama 
- Deteksi kendaraan secara real-time dari live streaming CCTV
- Klasifikasi kondisi lalu lintas (lancar, padat, macet)
- Sitem UI dengan warna dan informatif
- Perhitungna rute tercepat menggunakan algoritma A*
- Rute otomatis berubah sesuai update kondisi lalu lintas
- Antarmuka web interaktif dan informatif

## 🗺️ Area Cakupan CCTV
- Kalibanteng
- Kaligarang
- Madukuro
- Kariadi
- Tugu Muda
- Indraprasta
- Bergota
- Simpang Kyai Saleh

## 🛠️ Cara Kerja Sistem
1. **Input CCTV** : Video streaming langsung dari titik strategis kota.
2. **Deteksi YOLOv8** : Mengenali kendaraan seperti mobil, truk, bus, dan motor.
3. **Klasifikasi lalu lintas** :
- Lancar (<=5 kendaraan)
- Padat (6-15 kendaraan)
- Macet (>=15 kendaraan)
4. **Graf Lalu Lintas** : Penetapan bobot berdasarkan kepadatan lalu lintas
5. **A*** : Menghitung rute terpendek dari titik asal tujuan
6. **UI Web** : Menampilak statistik lalu lintas dan rute optimal dari kondisi jalan

