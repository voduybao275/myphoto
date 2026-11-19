# Trạng thái dự án — My Photo Studio

Cập nhật lần cuối: 2026-11-19  
Phiên bản: 0.25.0  
Giai đoạn hiện tại: **Giai đoạn 6 — Layer hình khối, Cọ/Tẩy, Gradient, Feather, chọn nâng cao, Quick Mask, giãn dòng/giãn chữ, định dạng theo từng đoạn chữ, uốn chữ, gõ chữ trên canvas, layer điều chỉnh không phá huỷ, mask cho layer điều chỉnh, Levels/Curves/Color Balance, Curves tách kênh + histogram + eyedropper, Layer Group, chữ trên đường dẫn + kerning cặp, layer fill + smart object, Auto Levels + kéo histogram, Automation batch/action + preset SQLite, tối ưu tile/lazy rendering đã HOÀN THÀNH**

## 1. Tóm tắt

Giai đoạn 1 đã có một ứng dụng chạy thật: mở cửa sổ trên Windows, tạo/mở/lưu tài liệu,
quản lý layer pixel, undo/redo, zoom/pan và đổi theme. Giai đoạn 2 bổ sung công cụ chọn
chữ nhật/ellipse, layer mask có thumbnail, crop có overlay trực quan, Image Size và
Canvas Size. Giai đoạn 3 bổ sung xoay canvas/layer 90° và 180°, xoay tự do theo góc bất
kỳ, lật ngang/dọc, xoay kèm mask và vùng chọn, có Undo/Redo. Giai đoạn 4 bổ sung layer
văn bản có thể chỉnh sửa: chọn font, cỡ chữ, màu, đậm/nghiêng, căn lề, xem trước trực
tiếp, sửa nội dung và rasterize, lưu trong dự án `.mps` v3. Giai đoạn 5 bổ sung bộ lọc
và hiệu ứng cơ bản: brightness/contrast, hue/saturation, auto contrast, invert,
desaturate, Gaussian blur và unsharp mask, có xem trước, tôn trọng vùng chọn và
Undo/Redo. Giai đoạn 6 bắt đầu bằng layer hình khối vector: công cụ Shape kéo vẽ hình
chữ nhật/chữ nhật bo góc/ellipse, tô màu và viền RGBA, preview trên canvas, sửa thuộc
tính bằng hộp thoại và lưu trong `.mps` v4. Phần 2 của Giai đoạn 6 bổ sung công cụ Brush
và Eraser: vẽ màu Foreground với cỡ/độ cứng/độ đục tuỳ chỉnh, tẩy pixel, giới hạn theo
vùng chọn, một bước Undo cho mỗi nét, và vẽ trực tiếp lên layer mask theo độ sáng màu.
Phần 3 bổ sung công cụ Gradient: tô dải màu tuyến tính/hình tròn lên layer hoặc layer
mask, bốn mẫu màu, preview khi kéo, giới hạn theo vùng chọn và Undo một bước. Phần 4
bổ sung Feather và anti-alias cho vùng chọn: biên mềm dùng cho layer mask, cọ, gradient
và bộ lọc, đổi bán kính bằng Options Bar hoặc menu Select ▸ Feather Selection…, có
Undo/Redo và giữ tuỳ chọn qua các phép biến đổi vùng chọn. Phần 5 bổ sung Lasso, Magic
Wand và Quick Selection: vẽ vùng chọn tự do, chọn theo màu tương tự với dung sai và chế
độ liền mạch, kéo cọ để cộng dần vùng chọn; kèm Quick Mask tô đỏ phần chưa chọn. Cả ba
công cụ dùng chung quy tắc cộng/trừ/giao vùng chọn và ghi đúng một bước Undo mỗi lần
nhấp/kéo. Phần 6 bổ sung giãn dòng (0,5..5,0 lần) và giãn chữ (−200..500 px) cho layer
văn bản: render lại đúng baseline/khoảng cách ký tự, xem trước trong hộp thoại, hiển thị
ở panel Properties, lưu trong metadata `.mps` v4 và có Undo/Redo. Phần 7 bổ sung định
dạng theo từng đoạn chữ trong cùng một layer văn bản: mỗi đoạn có font family, cỡ chữ,
màu RGBA, đậm và nghiêng riêng; hộp thoại dùng vùng nhập nhiều định dạng, áp dụng thay
đổi cho phần đang bôi đen hoặc toàn bộ văn bản, tự đồng bộ điều khiển theo con trỏ và
vẫn giữ căn lề/giãn dòng/giãn chữ ở cấp layer. Phần 8 bổ sung uốn chữ cho toàn layer
văn bản với 9 kiểu (cung tròn, vòm, phồng, ép dọc, lượn sóng, cờ, đuôi cá, dốc, xoắn)
và độ uốn −100..100%; nội dung vẫn sửa được, có Undo/Redo và lưu trong `.mps` v4.
Phần 9 bổ sung gõ/sửa chữ trực tiếp trên canvas bằng công cụ Text: khung soạn thảo
trong suốt đặt đúng vị trí và tỉ lệ zoom, giữ nguyên định dạng từng đoạn, căn lề,
giãn dòng/chữ và uốn chữ; Ctrl+Enter hoặc nhấp ra ngoài để xong, Esc để huỷ, mỗi lần
xác nhận ghi đúng một bước Undo/Redo. Phần 10 bổ sung layer điều chỉnh không phá huỷ:
Brightness/Contrast, Hue/Saturation, Invert và Desaturate áp lên toàn bộ layer nằm bên
dưới, độ mạnh điều chỉnh bằng Opacity, sửa tham số bằng hộp thoại có xem trước hoặc
nhấp đôi layer, lưu trong `.mps` v4 và có Undo/Redo. Phần 11 bổ sung mask cấp tài liệu
cho layer điều chỉnh: mask đúng kích thước canvas giới hạn hiệu ứng theo từng điểm ảnh,
tạo từ vùng chọn hoặc mask trắng, vẽ bằng Brush/Gradient, nhân với Opacity, đi theo
Crop/Canvas Size/Image Size/xoay/lật, lưu trong `.mps` v4 và có xem trước trong hộp
thoại sửa điều chỉnh. Phần 12 bổ sung ba loại điều chỉnh nâng cao: Levels với điểm
đen/trắng vào-ra và gamma, Curves với đường cong RGB 2..16 điểm kéo được, và Color
Balance cho vùng tối/trung gian/sáng kèm tuỳ chọn giữ độ sáng; cả ba không phá huỷ, có
mask, Undo/Redo, xem trước và lưu tham số trong `.mps` v4. Phần 13 bổ sung Curves tách
kênh R/G/B (mỗi kênh một đường cong, chạy trước đường RGB tổng hợp), histogram độ sáng
và histogram kênh trong hộp thoại Levels/Curves, cùng eyedropper lấy điểm đen/trắng
trực tiếp từ ảnh xem trước. Phần 14 bổ sung Layer Group: nhóm lồng nhau, panel Layers
phân cấp, opacity/blend/mask áp lên cả nhóm, layer điều chỉnh trong nhóm chỉ tác động
layer cùng nhóm, Undo/Redo một bước và lưu `.mps` v5 với `group_id`. Phần 15 bổ sung
chữ trên đường dẫn (cung tròn, vòng tròn, lượn sóng, chữ S với độ cong −100..100%) và
kerning cặp thủ công (tối đa 200 cặp, ±200 px): mỗi ký tự được xếp và xoay theo đường
dẫn, giữ định dạng riêng của từng run, lưu trong `.mps` và có Undo/Redo. Phần 16 bổ
sung **layer tô** (solid/gradient sinh pixel theo canvas, sửa màu/góc bất cứ lúc nào) và
**smart object** (giữ ảnh nguồn, xoay −180..180°, thu phóng 10..400%, lật ngang/dọc,
thay nội dung giữ nguyên biến đổi, reset, rasterize); cả hai lưu trong `.mps` v6 với ảnh
nguồn ở `sources/<layer_id>.png` và có Undo/Redo đầy đủ. Phần 17 bổ sung **Auto
Levels** (tự tính điểm đen/trắng theo histogram luma, cắt 0,5 % nhiễu mỗi đầu, bỏ qua
pixel trong suốt) và **kéo trực tiếp hai tay nắm đen/trắng trên histogram** của hộp
thoại Levels, đồng bộ hai chiều với slider/ô số và xem trước. Phần 18 bổ sung
**Automation**: hộp thoại xử lý hàng loạt (tối đa 500 file, thêm cả thư mục) với 11
loại bước (Auto Levels, Auto Contrast, Grayscale, Invert, Brightness/Contrast,
Hue/Saturation, Levels, Gaussian Blur, Unsharp Mask, resize theo %/cạnh lớn nhất),
lưu/tải/xoá **action**, xuất PNG/JPEG/WebP với hậu tố an toàn và không ghi đè ảnh gốc;
kèm **thư viện preset SQLite** cho layer điều chỉnh (lưu/áp/xoá preset theo loại,
dữ liệu trong `presets.sqlite3` cạnh cấu hình). Phần 19 bổ sung **tile/lazy rendering**:
compositor theo vùng, cache ô 256 × 256 LRU (tối đa 96 ô), dirty rect cho cọ/tẩy/
gradient và ảnh preview thu nhỏ (cạnh dài ≤ 2048 px) khi zoom dưới 50%, giúp ảnh lớn
chỉ dựng phần đang nhìn thấy.
Không có nút giả: các chức năng chưa làm được để mờ hoặc chưa đưa vào giao diện.

- Kiểm thử: **519 passed** với PySide2 5.15.2.1 (môi trường chạy thật trên máy).
- Kiểm thử: **519 passed** với PySide6 6.3.2 (offscreen, kiểm tra lớp tương thích).
- Đã mở thử `main.py` trên nền tảng Windows thật: cửa sổ chạy ổn định, không crash.
- Ảnh xem trước: `artifacts/phase1_dark.png`, `artifacts/phase1_light.png`,
  `artifacts/phase2_selection.png`, `artifacts/phase2_crop.png`,
  `artifacts/phase2_image_size.png`, `artifacts/phase2_canvas_size.png`,
  `artifacts/phase3_transform.png`, `artifacts/phase3_free_rotate.png`,
  `artifacts/phase4_text.png`, `artifacts/phase4_text_dialog.png`,
  `artifacts/phase5_filters.png`, `artifacts/phase5_blur_dialog.png`,
  `artifacts/phase6_shapes.png`, `artifacts/phase6_shape_dialog.png`,
  `artifacts/phase6_brush.png`, `artifacts/phase6_gradient.png`,
  `artifacts/phase6_feather.png`, `artifacts/phase6_select_tools.png`,
  `artifacts/phase6_rich_text.png`, `artifacts/phase6_rich_text_dialog.png`,
  `artifacts/phase6_rich_runs.png`, `artifacts/phase6_rich_runs_dialog.png`,
  `artifacts/phase6_text_warp.png`, `artifacts/phase6_text_warp_dialog.png`,
  `artifacts/phase6_canvas_text.png`, `artifacts/phase6_canvas_text_result.png`,
  `artifacts/phase6_adjustment_layers.png`, `artifacts/phase6_adjustment_dialog.png`,
  `artifacts/phase6_adjustment_mask.png`,
  `artifacts/phase6_adjustment_mask_dialog.png`,
  `artifacts/phase6_advanced_adjustments.png`,
  `artifacts/phase6_levels_dialog.png`,
  `artifacts/phase6_curves_dialog.png`,
  `artifacts/phase6_color_balance_dialog.png`,
  `artifacts/phase6_curves_red_channel.png`,
  `artifacts/phase6_layer_groups.png`,
  `artifacts/phase6_text_path.png`,
  `artifacts/phase6_text_path_dialog.png`,
  `artifacts/phase6_fill_smart.png`,
  `artifacts/phase6_fill_dialog.png`,
  `artifacts/phase6_smart_object_dialog.png`,
  `artifacts/phase6_levels_auto.png`,
  `artifacts/phase6_batch_dialog.png`,
  `artifacts/phase6_preset_library.png`, `artifacts/phase6_tiles.png`.

## 2. Chức năng đã hoàn thành

### Tài liệu và lịch sử
- `Document`: kích thước, DPI, tên, đường dẫn, trạng thái modified, giới hạn 400 MP.
- Nhiều tài liệu mở cùng lúc bằng tab; đóng tab có cảnh báo chưa lưu.
- Undo/Redo bằng Command Pattern, tối đa 60 trạng thái; lưu dự án không xoá lịch sử.
- Signal `content_changed`, `structure_changed`, `history_changed`, `title_changed`,
  `selection_changed`.
- Undo/Redo cho thay đổi vùng chọn, mask, crop, canvas size, image size và xoay/lật.

### Layer
- Layer pixel RGBA 8-bit, layer văn bản (kind `text`), layer hình khối (kind `shape`),
  layer điều chỉnh (kind `adjustment`) và layer nhóm (kind `group`), offset, opacity,
  visibility, lock, blend mode.
- 15 chế độ hoà trộn theo công thức W3C, xử lý alpha thẳng.
- Tạo, nhân bản, đổi tên, xoá, chọn active, kéo thả đổi thứ tự.
- Merge Down, Flatten Image, kiểm tra hợp lệ khi chọn active.
- Thumbnail trong panel, cache theo `pixel_revision`.
- Di chuyển layer bằng công cụ Move (preview khi kéo, commit khi thả, có Undo).

### Vùng chọn (Giai đoạn 2)
- Công cụ Rectangular Marquee (M) và Elliptical Marquee (E), kéo để tạo vùng chọn.
- Shift để cộng, Alt để trừ, Shift+Alt để giao; thả chuột mới ghi history.
- Select All (Ctrl+A), Deselect (Ctrl+D), Invert (Ctrl+Shift+I) từ menu Select
  và Options Bar.
- Vùng chọn hiển thị bằng "marching ants" (nét đen liền + nét trắng đứt chuyển động),
  cắt đúng trong biên tài liệu; Escape huỷ thao tác đang kéo.
- Vùng chọn dùng toạ độ pixel tài liệu, được nhân bản và chuẩn hoá trước khi lưu history.
- Vùng chọn là trạng thái tạm của phiên làm việc, **không lưu vào file `.mps`**.

### Layer mask (Giai đoạn 2)
- Thêm mask từ vùng chọn (trong vùng chọn = trắng, ngoài = đen) hoặc mask trắng toàn bộ.
- Bật/tắt mask, xoá mask, áp dụng mask vĩnh viễn vào alpha của layer.
- Compositor nhân alpha nguồn với mask/255; tự tắt fast path khi layer có mask hoạt động.
- Panel Layers hiển thị thumbnail mask cạnh thumbnail layer, gạch chéo khi mask bị tắt,
  phụ đề "Mask" / "Mask tắt".
- Mask tỉ lệ đúng theo pixel layer, được giữ khi đổi kích thước ảnh (resample).

### Crop, Image Size, Canvas Size (Giai đoạn 2)
- Công cụ Crop (C): kéo vùng giữ lại, Shift để vuông; overlay làm tối vùng ngoài,
  viền trắng, lưới một phần ba và tay nắm góc; Enter áp dụng, Escape huỷ.
- Menu Image ▸ Crop, Crop to Selection; nút Apply Crop / Cancel trên Options Bar.
- Crop giữ nguyên pixel/mask của layer, thay đổi kích thước tài liệu và dịch offset.
- Image Size (Ctrl+Alt+I): khoá tỉ lệ, chọn nearest/bilinear/bicubic/lanczos, resample
  mọi layer và mask, ước tính bộ nhớ.
- Canvas Size (Ctrl+Alt+C): chọn 1 trong 9 điểm neo, dịch layer và vùng chọn theo neo.
- Hộp thoại kiểm tra kích thước, chặn vượt giới hạn an toàn.

### Xoay và lật (Giai đoạn 3)
- Menu Image ▸ Image Rotation: 90° theo chiều kim đồng hồ, 90° ngược chiều, 180° và
  Arbitrary Rotation… để xoay tự do.
- Menu Image ▸ Flip Canvas Horizontal / Vertical.
- Menu Edit ▸ Transform: xoay 90°/180°, Rotate… (góc tự do) và lật riêng layer đang
  chọn, quanh tâm layer.
- Xoay tự do dùng phép biến đổi affine tự dựng: kích thước mới tính chính xác, vùng
  ngoài ảnh trong suốt, hỗ trợ nearest/bilinear/bicubic/lanczos.
- Góc 90°/180° tự động dùng phép xoay chính xác từng điểm ảnh thay vì nội suy.
- Hộp thoại xoay hiển thị kích thước mới dự kiến và ước tính bộ nhớ; chặn góc 0° và
  kích thước vượt giới hạn an toàn.
- Xoay canvas đổi kích thước tài liệu và tính lại offset của mọi layer theo đúng
  phép biến đổi, kể cả layer không phủ kín canvas.
- Layer mask và vùng chọn được xoay/lật đồng bộ với canvas; flip layer giữ nguyên kích
  thước và offset.
- Undo/Redo cho cả xoay canvas, lật canvas và xoay/lật layer.
- Sau khi xoay canvas, ứng dụng tự Fit on Screen và huỷ vùng crop đang dở.

### Layer văn bản (Giai đoạn 4)
- Mô hình `TextProperties` bất biến lưu nội dung, font, cỡ chữ (px), màu RGBA,
  đậm/nghiêng và căn lề trái/giữa/phải; từ phần 7, nội dung được mở rộng thành danh
  sách `TextRun` để mỗi đoạn có kiểu riêng.
- Render bằng QPainter/QFontMetricsF ra ảnh RGBA nền trong suốt; layer văn bản tham
  gia composite, mask, di chuyển, sắp xếp và xuất ảnh như layer pixel.
- Công cụ Text (T): nhấp vào canvas để đặt layer văn bản tại đúng vị trí.
- Menu Type: New Text Layer… (Ctrl+Shift+T), Edit Text… và Rasterize Text; nút
  "New Text Layer…" trên Options Bar và nút T trong panel Layers.
- Hộp thoại tạo/sửa có xem trước trực tiếp (debounce 150 ms), chọn font hệ thống,
  cỡ chữ 1..1000 px, màu có alpha, đậm/nghiêng, căn lề và thông tin kích thước dự kiến.
- Sửa văn bản cập nhật kích thước layer, render lại pixel và ghi một bước Undo.
- Rasterize chuyển layer văn bản thành layer pixel; Undo khôi phục lại metadata văn bản.
- Nhân bản layer văn bản giữ nguyên metadata; hai layer sửa độc lập.
- Layer văn bản có mask: phải áp hoặc xoá mask trước khi sửa nội dung; áp dụng mask
  sẽ rasterize nhưng Undo khôi phục được kind/text.
- Các phép biến đổi pixel (resize, xoay/lật canvas hoặc layer, xoay tự do) tự rasterize
  layer văn bản; crop và canvas size giữ layer văn bản chỉnh sửa được.
- Giới hạn an toàn: 10.000 ký tự, 500 dòng, font 1..1000 px, kích thước render tối đa
  64 MP; chặn và báo lỗi thân thiện khi vượt giới hạn.

### Bộ lọc và hiệu ứng (Giai đoạn 5)
- `core/filters.py` xử lý trực tiếp mảng NumPy RGBA `(H, W, 4)` uint8, không phụ thuộc Qt.
- Adjustments: Brightness/Contrast (công thức tương phản chuẩn), Hue/Saturation (HSL
  vector hoá, hue −180°..180°, saturation/lightness −100..100), Auto Contrast (cắt
  percentile, lấy mẫu tối đa 500k điểm ảnh), Invert và Desaturate (luma Rec.709).
- Blur: Gaussian xấp xỉ bằng 3 lượt box blur dùng cumulative sum, biên padding; xử lý
  trên dữ liệu premultiplied để alpha đúng và không có quầng tối.
- Sharpen: Unsharp Mask với lượng 0..300 %, bán kính 0,1..50 px, ngưỡng 0..255.
- Chia khối 1 triệu điểm ảnh cho phép toán điểm ảnh/HSL; giới hạn 64 MP cho bộ lọc
  điểm ảnh, 24 MP cho blur, 16 MP cho unsharp mask; báo lỗi thân thiện khi quá lớn.
- `Document.apply_layer_filter`: chỉ áp dụng cho layer đang chọn, từ chối layer khoá,
  trộn kết quả với pixel gốc theo mask của vùng chọn, giữ nguyên layer mask và tạo
  đúng một bước Undo qua `LayerTransformCommand`.
- Layer văn bản tự rasterize khi áp bộ lọc; Undo khôi phục lại kind/text.
- Áp dụng không tạo thay đổi (ảnh đồng nhất, tham số trung tính) sẽ không ghi history
  và hiển thị thông báo.
- UI: menu Filter gồm Adjustments / Blur / Sharpen, action chỉ bật khi có layer đang
  chọn và không bị khoá; các action có phím tắt Ctrl+U, Ctrl+I, Ctrl+Shift+U.
- Hộp thoại xem trước dùng layer thu nhỏ tối đa 420 px, debounce 150 ms; khi bấm Áp
  dụng mới chạy bộ lọc ở độ phân giải đầy đủ. Bán kính blur được nhân theo tỉ lệ thu
  nhỏ để xem trước sát kết quả thật.
- Nút áp dụng/huỷ chuẩn, thông báo trạng thái sau khi áp dụng và Undo/Redo hoạt động.

### Layer hình khối (Giai đoạn 6 — phần 1)
- Mô hình `ShapeProperties` bất biến: loại hình (chữ nhật, chữ nhật bo góc, ellipse),
  kích thước, màu tô RGBA hoặc không tô, màu viền RGBA, độ dày viền và bán kính bo góc.
- Render bằng QPainter với khử răng cưa ra ảnh RGBA nền trong suốt; viền được vẽ lùi
  vào trong để không vượt kích thước layer.
- Công cụ Shape (U): kéo trên canvas để vẽ, kẹp trong biên tài liệu; Shift tạo hình
  vuông/tròn; Escape huỷ. Preview tô màu mờ + viền nét đứt, trạng thái hiện kích thước.
- Options Bar: chọn loại hình, bật/tắt tô, màu tô, độ dày viền, màu viền, bo góc và
  nút New Shape Layer…; bán kính bo góc chỉ bật với chữ nhật bo góc.
- Menu Layer ▸ Shape: New Shape Layer…, Edit Shape… và Rasterize Shape; panel Layers
  có nút hình khối; panel Properties hiển thị loại hình, màu tô, viền và bo góc.
- Hộp thoại tạo/sửa hình khối có kích thước, màu tô/viền RGBA, bo góc và xem trước
  trực tiếp (debounce 120 ms).
- Thêm/sửa/rasterize đều đi qua `LayerTransformCommand`, giữ đúng một bước Undo;
  Undo khôi phục cả pixel lẫn metadata vector.
- Xoay/lật/resize/áp bộ lọc tự rasterize layer hình khối; Undo khôi phục kind/shape.
- Layer hình khối có mask: phải áp hoặc xoá mask trước khi sửa thuộc tính.
- Giới hạn an toàn: cạnh 1..30.000 px, vùng render tối đa 64 MP, viền 0..500 px và
  không vượt nửa cạnh nhỏ, bo góc 0..15.000 px và tự kẹp theo nửa cạnh nhỏ.

### Cọ, Tẩy và vẽ layer mask (Giai đoạn 6 — phần 2)
- `core/paint.py` thuần NumPy: `BrushSettings` (cỡ 1..2000 px, độ cứng 0..1, độ đục
  0..1, màu RGBA, chế độ tẩy), dấu cọ mềm theo khoảng cách, nội suy nét và ghép màu
  alpha thẳng; không phụ thuộc Qt.
- `BrushStrokeSession` giữ buffer độ phủ riêng cho từng nét nên độ đục không cộng dồn
  trong cùng một nét; preview ghi trực tiếp vào layer và chỉ vẽ lại vùng dirty.
- Giới hạn theo vùng chọn: độ phủ từng dấu cọ được nhân với mask vùng chọn cắt theo
  toạ độ layer, mép vùng chọn được trộn mượt.
- Khi thả chuột, nét cọ ghi đúng một bước Undo (`LayerTransformCommand` cho pixel,
  `SetLayerMaskCommand` cho mask); Escape huỷ nét và trả layer về trạng thái trước.
- Vẽ lên mask lấy giá trị theo độ sáng Rec.601 của màu Foreground (đen = ẩn,
  trắng = hiện); nét vẽ trộn dần về giá trị đích. Eraser không tẩy được mask.
- Vẽ lên layer văn bản/hình khối tự rasterize; Undo khôi phục lại kind/text/shape.
- Công cụ Brush (B) và Eraser (Shift+E) với con trỏ vòng tròn theo cỡ cọ × zoom
  (dùng dấu chữ thập khi < 6 px hoặc > 160 px); danh sách công cụ có icon và gợi ý.
- Options Bar: cỡ, độ cứng, độ đục, ô màu Foreground đồng bộ từ toolbox, combo
  "Vẽ lên" (Layer / Layer Mask) và dòng thông tin mask. Combo mask chỉ bật khi layer
  đang chọn có mask.
- Menu Layer ▸ Layer Mask ▸ Paint on Layer Mask (checkable) bật/tắt chế độ vẽ mask,
  tự chuyển sang công cụ Brush và báo trạng thái; action tự tắt khi layer không có mask.
- Không thay đổi định dạng `.mps`: dữ liệu pixel và mask đã có từ phiên bản 2, hiện
  vẫn là phiên bản 4.

### Gradient (Giai đoạn 6 — phần 3)
- `core/gradient.py` thuần NumPy: `GradientSettings` (loại `linear`/`radial`, màu đầu
  và màu cuối RGBA) và `gradient_ramp` tính dải màu float32 trong 0..1.
- `GradientSession` chụp trạng thái trước khi tô, tính lại dải màu mỗi lần kéo và ghi
  trực tiếp vào layer để xem trước; nhả chuột mới ghi đúng một bước Undo
  (`LayerTransformCommand` cho pixel, `SetLayerMaskCommand` cho mask).
- Tô đè toàn bộ layer/mask trong phạm vi vùng chọn: pixel được trộn với màu gốc theo
  độ mạnh vùng chọn, mask trộn giữa độ sáng Rec.601 của màu đầu và màu cuối.
- Gradient tuyến tính tính theo hình chiếu lên đoạn kéo; gradient hình tròn lấy tâm
  là điểm bắt đầu và bán kính là độ dài đoạn kéo; điểm ảnh lấy tâm (i + 0,5).
- Render theo dải tối đa 1 triệu điểm ảnh để giới hạn bộ nhớ; với layer trên 16 MP
  tạm bỏ xem trước trực tiếp và chỉ render khi thả chuột.
- Bốn mẫu màu: Foreground → Background, Foreground → Trong suốt, Đen → Trắng,
  Trắng → Đen; nhả chuột mà không kéo hoặc Escape sẽ trả layer về như cũ và không ghi
  history.
- Vẽ lên layer văn bản/hình khối tự rasterize; Undo khôi phục lại kind/text/shape.
- Công cụ Gradient (G) đặt sau Brush trong toolbox, có icon riêng và gợi ý.
- Options Bar: combo kiểu (Tuyến tính / Hình tròn), combo mẫu màu, ô xem trước dải
  màu, combo "Vẽ lên" (Layer / Layer Mask) và dòng thông tin mask. Combo mask bật/tắt
  đồng bộ với công cụ Brush.
- Menu Layer ▸ Layer Mask ▸ Paint on Layer Mask bật/tắt chế độ vẽ mask cho cả Brush
  và Gradient; action tự tắt khi layer đang chọn không có mask.
- Không thay đổi định dạng `.mps`: gradient chỉ sinh ra pixel/mask đã có từ phiên bản
  2, hiện vẫn là phiên bản 4.

### Feather và anti-alias vùng chọn (Giai đoạn 6 — phần 4)
- `Selection` lưu thêm `feather` (0..250 px) và `antialias`; mặc định 0 px và bật.
- `Selection.mask()` raster hoá có/không khử răng cưa, sau đó làm mềm bằng Gaussian xấp
  xỉ 3 lượt box blur; phần feather chỉ tính trên biên mở rộng của đường bao để tiết
  kiệm bộ nhớ, luôn cắt trong phạm vi tài liệu.
- `bounds()` mở rộng theo bán kính feather (tối đa ~1,5 × bán kính) để crop, mask và
  thông tin kích thước phản ánh cả vùng chuyển tiếp.
- Feather/anti-alias được giữ khi copy, dịch, scale, xoay/lật, đảo vùng chọn; thao tác
  cộng/trừ/giao dùng tuỳ chọn của lần kéo mới nhất.
- `Document.feather_selection(radius)` đổi bán kính của vùng chọn hiện tại và ghi đúng
  một bước Undo/Redo; nhập 0 px trả lại biên cứng, không tạo history nếu không đổi.
- Vùng chọn feather được dùng thống nhất cho layer mask, Brush, Eraser, Gradient và
  `apply_layer_filter`: mép chuyển tiếp trộn dần thay vì cắt cứng.
- Options Bar của Rectangular/Elliptical Marquee có ô Feather (0..250 px, hiển thị
  "px") và hộp kiểm Anti-alias; mỗi công cụ chọn giữ tuỳ chọn riêng.
- Menu Select ▸ Feather Selection… (Shift+F6) mở hộp thoại nhập bán kính, có gợi ý
  phạm vi chuyển tiếp và nút Áp dụng/Huỷ.
- Thanh trạng thái khi kéo chọn hiện thêm "Feather N px" và "Không anti-alias" nếu tắt;
  dòng thông tin trên Options Bar hiển thị tuỳ chọn của vùng chọn hiện tại.
- Không đổi định dạng `.mps`: vùng chọn vẫn là trạng thái tạm của phiên làm việc.

### Lasso, Magic Wand, Quick Selection và Quick Mask (Giai đoạn 6 — phần 5)
- `core/wand.py` thuần NumPy: `layer_sample` đặt pixel layer vào toạ độ tài liệu,
  `color_eligibility` so sánh từng kênh RGBA với dung sai, `flood_fill_eligible` loang
  theo dòng quét (scanline) trên vùng màu hợp lệ, `flood_fill_mask` hỗ trợ chế độ
  liền mạch hoặc toàn tài liệu.
- `mask_to_path` dò biên mask nhị phân thành `QPainterPath` (WindingFill) bằng đồ thị
  cạnh có hướng, ưu tiên rẽ phải, nên giữ được cả lỗ hổng; `Selection.from_path` tạo
  vùng chọn từ đường bao đó nên dùng lại được feather, anti-alias, mask, crop và Undo.
- Công cụ Lasso (L): rê chuột để vẽ đường bao tự do, thả chuột chốt vùng chọn; Escape
  huỷ; mỗi nét ghi một bước Undo.
- Công cụ Magic Wand (W): nhấp để chọn vùng màu tương tự trên layer đang chọn; Options
  Bar có Dung sai 0..255, "Liền mạch" và Feather; tắt liền mạch để chọn mọi điểm ảnh
  giống màu trên toàn tài liệu.
- Công cụ Quick Selection (Shift+W): kéo cọ để loang cục bộ quanh đầu cọ và cộng dần
  vào vùng chọn; vùng chọn tạm hiện màu xanh mờ khi kéo, thả chuột mới chốt và ghi một
  bước Undo; Escape trả lại vùng chọn ban đầu.
- Cả ba công cụ dùng chung `combine_selection` với Shift (cộng), Alt (trừ) và
  Shift+Alt (giao); thanh trạng thái hiển thị kích thước, dung sai và chế độ.
- Quick Mask: phím Q khi canvas đang focus hoặc menu View ▸ Quick Mask; tô đỏ mờ lên
  phần **chưa** chọn (alpha = 255 − mask), ảnh overlay được cache và chỉ dựng lại khi
  vùng chọn đổi; tự tắt khi không còn vùng chọn và đồng bộ giữa các tab.
- Khi bật Quick Mask, hiệu ứng "marching ants" tạm dừng; tắt Quick Mask trả lại hiển
  thị viền vùng chọn như cũ. Có thể bật/tắt nhiều lần mà không đổi vùng chọn.

### Giãn dòng và giãn chữ (Giai đoạn 6 — phần 6)
- `TextProperties` có thêm `line_spacing` (0,5..5,0 lần) và `letter_spacing`
  (−200..500 px), được chuẩn hoá (làm tròn 2 chữ số / số nguyên) và kiểm tra khi tạo.
- Render dùng `QFont.setLetterSpacing` với đơn vị tuyệt đối cho giãn chữ; giãn dòng nhân
  bước baseline giữa các dòng. Chiều rộng layer trừ phần giãn thừa sau ký tự cuối để
  căn trái/giữa/phải theo đúng mực in.
- Chiều cao layer = lineSpacing + (số dòng − 1) × lineSpacing × hệ số + padding; văn
  bản một dòng không đổi chiều cao khi chỉ tăng giãn dòng.
- Hộp thoại Text có hàng "Giãn dòng / chữ" gồm ô Dòng (bước 0,1 ×, 2 chữ số thập phân)
  và ô Chữ (bước 1 px); xem trước và dòng "Layer dự kiến" cập nhật khi thay đổi.
- Sửa giãn dòng/giãn chữ dùng `update_text_layer`, render lại pixel, cập nhật kích thước
  layer và ghi đúng một bước Undo/Redo; Undo khôi phục cả thuộc tính lẫn pixel.
- Metadata `text` trong `.mps` v4 có thêm `line_spacing` và `letter_spacing`; dự án cũ
  thiếu hai khoá này vẫn mở được với giá trị mặc định 1,0× và 0 px.
- Panel Properties hiển thị "Giãn dòng: …× · Giãn chữ: … px" khi khác mặc định.
- Giới hạn render an toàn giữ nguyên: cạnh tối đa 30.000 px, vùng render tối đa 64 MP.

### Định dạng theo từng đoạn chữ (Giai đoạn 6 — phần 7)
- `TextRun` (bất biến) giữ text + font family + cỡ chữ + màu RGBA + đậm/nghiêng;
  `TextProperties.runs` là tuple các đoạn và tự tạo text bằng cách nối các đoạn.
- Khi khởi tạo từ runs, các trường phẳng `font_family/font_size/color/bold/italic` được
  suy ra từ đoạn đầu để dữ liệu và phép so sánh ổn định; các đoạn liền kề cùng kiểu được
  gộp lại, đoạn rỗng bị bỏ qua.
- Render chia mỗi run theo ký tự xuống dòng, dựng từng dòng thành các segment có font
  riêng, cộng advance để tính bề rộng; chiều cao/ascent lấy theo segment lớn nhất nên
  các cỡ chữ khác nhau vẫn chia sẻ baseline.
- Hộp thoại Text dùng `QTextEdit` nhiều định dạng. Bôi đen một phần rồi đổi
  Font/Cỡ/Đậm/Nghiêng/Màu chỉ áp dụng cho phần chọn; không bôi đen thì áp dụng toàn bộ.
  Con trỏ di chuyển sẽ đồng bộ điều khiển theo định dạng tại vị trí đó.
- Cỡ chữ pixel được lưu trong thuộc tính người dùng của `QTextCharFormat` (Qt không có
  cỡ pixel cho char format), nên trích xuất run giữ đúng cỡ sau khi sửa.
- Căn lề, giãn dòng và giãn chữ vẫn ở cấp layer; khi trích xuất, ký tự xuống dòng được
  gắn vào run trước để giữ nguyên nội dung nhiều dòng.
- Metadata `text` trong `.mps` v4 có thêm mảng `runs`; dự án cũ không có `runs` được đọc
  thành một run duy nhất từ các trường phẳng.
- Panel Layers hiển thị số kiểu chữ; panel Properties tóm tắt số đoạn và kiểu đoạn đầu.
- Sửa định dạng render lại pixel, cập nhật kích thước layer và ghi một bước Undo/Redo.

### Uốn chữ (Giai đoạn 6 — phần 8)
- `TextProperties` có thêm `warp_style` và `warp_bend` (−100..100%). Kiểu hợp lệ gồm
  `none`, `arc` (cung tròn), `arch` (vòm), `bulge` (phồng), `squeeze` (ép dọc), `wave`
  (lượn sóng), `flag` (cờ), `fish` (đuôi cá), `rise` (dốc), `twist` (xoắn); chọn
  "none" tự đưa độ uốn về 0.
- Render văn bản sạch trước, sau đó biến đổi bitmap bằng phép lấy mẫu ngược song tuyến
  theo từng hàng để giữ RAM thấp; màu được nhân trước alpha khi nội suy nên mép chữ
  không bị viền tối. Ảnh kết quả được cắt theo bao alpha để layer gọn đúng nội dung.
- Mỗi kiểu có công thức riêng: cung/vòm nâng tâm chữ, phồng/ép thay đổi tỉ lệ theo trục,
  sóng dùng sin, cờ/dốc nghiêng, đuôi cá uốn hai đầu, xoắn xoay dần theo vị trí ngang.
- Uốn áp dụng cho toàn layer nhưng vẫn giữ mọi `TextRun`, căn lề và giãn dòng/chữ;
  `text_size` trả kích thước sau uốn nên hộp thoại báo đúng "Layer dự kiến".
- Hộp thoại Text có hàng "Uốn chữ" gồm combo kiểu và ô độ uốn; chọn kiểu khác "Không
  uốn" khi độ uốn đang 0 sẽ tự đặt 50%; ô độ uốn bị mờ khi chọn "Không uốn".
- Panel Layers thêm nhãn "uốn …"; panel Properties hiển thị kiểu và độ uốn khi khác mặc định.
- Sửa uốn dùng `update_text_layer`, render lại pixel và ghi đúng một bước Undo/Redo;
  rasterize, nhân bản, mask và biến đổi pixel hoạt động như văn bản thường.
- `.mps` v4 lưu `warp_style`/`warp_bend` trong metadata `text`; dự án cũ thiếu hai khoá
  này mở với "Không uốn" và 0%.
- Giới hạn an toàn: ảnh trung gian khi uốn tối đa 24 MP; vượt giới hạn báo lỗi và gợi ý
  giảm cỡ chữ, bớt nội dung hoặc giảm độ uốn.

### Gõ chữ trên canvas (Giai đoạn 6 — phần 9)
- Công cụ Text nhấp lên vùng trống sẽ mở `InlineTextEditor` ngay trên canvas; nhấp lên
  layer văn bản có sẵn sẽ sửa nội dung tại chỗ thay vì mở hộp thoại.
- Editor là `QTextEdit` trong suốt đặt đúng toạ độ ảnh và co giãn theo zoom; cỡ chữ hiển
  thị theo zoom nhưng cỡ pixel thật được lưu trong thuộc tính người dùng của char format.
- Khi sửa, canvas vẽ ảnh nền đã trộn mọi layer khác (trừ layer đang sửa) nên không thấy
  chữ trùng hai lần; viền nét đứt màu accent đánh dấu khung soạn thảo.
- Trích xuất nội dung theo từng block/fragment, giữ font, cỡ, màu, đậm/nghiêng của từng
  đoạn cùng căn lề, giãn dòng, giãn chữ và kiểu uốn của layer.
- Ctrl+Enter hoặc focus ra ngoài để xác nhận; Esc huỷ; nhấp ra ngoài canvas xác nhận và
  "nuốt" cú nhấp để không tạo layer ngoài ý muốn. Nội dung rỗng/không có ký tự tự huỷ.
- Xác nhận gọi `update_text_layer` cho layer cũ hoặc `add_text_layer` cho vị trí mới, nên
  chỉ ghi một bước Undo/Redo; layer có mask bị chặn sửa trực tiếp kèm thông báo.
- Chuyển công cụ, đổi zoom và thay đổi kích thước cửa sổ đều đồng bộ hoặc kết thúc editor
  đúng cách; đóng tab/tài liệu dọn editor trước khi giải phóng canvas.

### Layer điều chỉnh không phá huỷ (Giai đoạn 6 — phần 10)
- `core/adjustment_layer.py` thuần NumPy: `AdjustmentProperties` bất biến cho bốn loại
  `brightness_contrast`, `hue_saturation`, `invert`, `desaturate`; tham số được kẹp
  trong miền hợp lệ (brightness/contrast −100..100, hue −180..180, saturation/lightness
  −100..100) và `apply_adjustment_rgb` chỉ đổi RGB, giữ nguyên kênh alpha.
- Brightness/Contrast dùng công thức tương phản chuẩn giống bộ lọc phá huỷ;
  Hue/Saturation dùng chung HSL vector hoá của `core/filters.py`; Desaturate theo luma
  Rec.709; Invert là 1 − RGB.
- `core/canvas.py` áp điều chỉnh lên accumulator của toàn bộ layer nằm bên dưới ngay
  trong dải đang composite (`_apply_adjustment_band`), nên chỉ cần 1 × 1 pixel trong
  suốt cho layer và không tốn bộ nhớ theo kích thước tài liệu.
- Opacity của layer điều chỉnh là độ mạnh hiệu ứng (pha giữa ảnh gốc và ảnh đã điều
  chỉnh); blend mode bị bỏ qua. Layer phía trên layer điều chỉnh không bị ảnh hưởng.
- `Document.add_adjustment_layer` và `update_adjustment_layer` ghi đúng một bước
  Undo/Redo qua `LayerTransformCommand`; sửa mà không đổi tham số không ghi history.
- Layer điều chỉnh giữ nguyên 1 × 1, offset (0, 0) qua crop, Canvas Size, Image Size,
  xoay 90°/tự do và lật canvas; không bị resample.
- Các thao tác phá huỷ bị chặn kèm thông báo rõ: Brush/Gradient tô vào "Layer", áp bộ
  lọc, Move, xoay/lật riêng layer. Có thể đổi tên, nhân bản, sắp xếp, ẩn/hiện và xoá
  như layer thường.
- UI: menu Layer ▸ New Adjustment Layer (bốn loại) và Edit Adjustment…; nhấp đôi layer
  điều chỉnh để sửa. Hộp thoại có thanh trượt/ô số và xem trước trực tiếp (debounce
  150 ms) dựng từ composite các layer bên dưới, thu nhỏ tối đa 420 px.
- Panel Layers hiển thị badge "fx", phụ đề loại điều chỉnh và tóm tắt tham số; panel
  Properties hiển thị loại, tham số, độ mạnh và ghi chú "áp lên layer bên dưới".
  Blend mode và ô X/Y của công cụ Move bị mờ với layer điều chỉnh.
- `.mps` v4 lưu thêm `kind: "adjustment"` và metadata `adjustment`; dự án cũ mở bình
  thường.
- Giới hạn: chưa có Curves/Levels riêng cho từng kênh màu (bản tổng hợp ở phần 12).

### Mask cho layer điều chỉnh (Giai đoạn 6 — phần 11)
- Mask của layer điều chỉnh là **mask cấp tài liệu** (`uint8`, đúng `height × width` của
  canvas) và được phép khác kích thước 1 × 1 của layer; `Layer.set_mask` bỏ kiểm tra
  kích thước theo layer cho riêng `LayerKind.ADJUSTMENT`.
- `Compositor._apply_adjustment_band` cắt mask theo dải đang composite, đổi sang
  `float32/255` rồi nhân với độ mạnh (Opacity): trắng = áp đầy đủ, đen = giữ nguyên ảnh
  gốc, xám = một phần. Mask đang tắt (`mask_enabled = False`) bị bỏ qua hoàn toàn.
- `Document._mask_from_selection` với layer điều chỉnh lấy mask vùng chọn cấp tài liệu
  (hoặc trắng toàn canvas khi không có vùng chọn), hỗ trợ đảo mask. `add_layer_mask` cho
  phép layer điều chỉnh; mỗi lần thêm/xoá/bật/tắt mask là một bước Undo/Redo qua
  `SetLayerMaskCommand`.
- `apply_layer_mask` bị chặn với layer điều chỉnh kèm thông báo hướng dẫn (layer không có
  pixel riêng để áp).
- Hình học: Crop coi mask như ảnh cấp tài liệu và cắt theo vùng crop; Canvas Size dùng
  `_move_canvas_mask` đặt mask theo anchor và tô 0 (đen) cho vùng mới; Image Size gọi
  `_resample_mask`; xoay/lật canvas dùng `_rotate_array`/`_rotate_mask_free`/`_flip_array`.
  `GeometryCommand` nhận thêm danh sách `old_masks`/`new_masks` để Undo/Redo khôi phục
  mask cho mọi phép biến đổi kể cả xoay tự do.
- Brush/Gradient: `BrushStrokeSession` và `GradientSession` lấy kích thước đích từ mask
  của layer; với mask điều chỉnh, toạ độ tính theo tài liệu (không trừ offset) và dùng
  `document.selection_mask()` để giới hạn nét vẽ.
- UI: Add Layer Mask bật cho layer điều chỉnh (kèm thông báo trắng = áp, đen = giữ),
  Apply Layer Mask mờ; panel Layers vẽ thumbnail mask theo kích thước mask thật; panel
  Properties ghi "Mask: không có / bật / đang tắt"; hộp thoại sửa điều chỉnh nhận mask
  và xem trước kết quả đã nhân mask, ghi chú "đã áp layer mask".
- `.mps` v4 lưu mask của layer điều chỉnh trong `masks/<id>.png`; loader kiểm tra mask
  phải khớp `(document.height, document.width)` và báo lỗi nếu sai.
- Giới hạn: mask điều chỉnh chưa xem như kênh riêng, chưa lưu kèm vùng chọn.

### Levels, Curves và Color Balance (Giai đoạn 6 — phần 12)
- `AdjustmentProperties` có thêm ba loại `levels`, `curves`, `color_balance` cùng các
  trường: điểm đen/trắng vào-ra, gamma (0,10..9,99), danh sách điểm đường cong, ba bộ
  cân màu cho vùng tối/trung gian/sáng (−100..100) và cờ giữ độ sáng.
- Validation: gamma và cân màu được kẹp trong miền hợp lệ; điểm đen phải nhỏ hơn điểm
  trắng (tự điều chỉnh), điểm ra được sắp thứ tự; đường cong cần 2..16 điểm, toạ độ
  0..255, hoành độ phân biệt và được sắp tăng dần. `to_dict`/`from_dict` lưu và đọc đủ
  trường mới, dự án cũ thiếu khoá sẽ dùng mặc định.
- `apply_adjustment_rgb`:
  - Levels chuẩn hoá theo khoảng đen–trắng, áp gamma bằng luỹ thừa `1/gamma`, rồi ánh xạ
    vào khoảng đầu ra.
  - Curves dựng LUT bằng `np.interp` trên 0..255; điểm ngoài hai đầu giữ giá trị đầu mút.
  - Color Balance dùng trọng số tam giác theo luma cho ba vùng, cộng dịch chuyển kênh
    R/G/B; khi giữ độ sáng thì nhân lại RGB theo tỉ lệ luma gốc/mới.
- UI: ba mục mới trong Layer ▸ New Adjustment Layer; hộp thoại Levels có 5 thanh trượt
  (gamma dùng ô thập phân), hộp thoại Curves có `CurveEditor` vẽ lưới, đường 45° và
  đường cong, thêm/kéo/xoá điểm bằng chuột cùng nút đặt lại; Color Balance có 3 nhóm
  thanh trượt và checkbox giữ độ sáng. Xem trước cập nhật trực tiếp và vẫn áp layer mask.
- Mọi thao tác tạo/sửa ghi một bước Undo/Redo qua `LayerTransformCommand`; Opacity là độ
  mạnh hiệu ứng, mask hoạt động như phần 11, hình học giữ layer 1×1 như các loại trước.
- Giới hạn: đường cong kênh R/G/B, histogram và eyedropper có ở phần 13; chưa có auto
  levels.

### Curves tách kênh, histogram và eyedropper (Giai đoạn 6 — phần 13)
- `AdjustmentProperties` thêm `curve_red`, `curve_green`, `curve_blue` (mặc định đường
  45°), cùng validation như `curve_points`: 2..16 điểm, toạ độ kẹp 0..255, hoành độ
  phân biệt, sắp tăng dần. `to_dict`/`from_dict` lưu đủ ba kênh; dự án cũ thiếu khoá
  dùng mặc định nên mở bình thường và vẫn tương thích `.mps` v4.
- `apply_adjustment_rgb` cho Curves: áp LUT từng kênh R/G/B trước (kênh nào để mặc định
  thì giữ nguyên), sau đó áp LUT RGB tổng hợp lên kết quả. `is_identity` chỉ đúng khi cả
  bốn đường cong đều mặc định; `summary` ghi số điểm RGB và các kênh R/G/B đã chỉnh.
- `core/histogram.py`: `compute_histogram(rgba, bins=256)` trả bốn mảng đếm cho luma và
  R/G/B, bỏ qua pixel alpha = 0; kiểm tra mảng phải là RGBA uint8 và số cột 2..4096.
- UI Curves: combo chọn `RGB (tổng hợp)` / `Đỏ` / `Xanh lá` / `Xanh dương`; mỗi kênh
  giữ đường cong riêng, đổi kênh đổi cả màu nét vẽ, histogram nền và đường cong đang
  hiển thị; "Đặt lại đường 45°" chỉ đặt lại kênh đang chọn.
- UI Levels: `HistogramView` hiển thị histogram độ sáng của ảnh bên dưới. Hai nút
  eyedropper đen/trắng bật chế độ lấy mẫu; nhấp ảnh xem trước sẽ đặt điểm đen/trắng đầu
  vào (Levels) hoặc thêm điểm `(độ sáng, 0/255)` vào kênh đang chọn (Curves), có ghi
  chú mức sáng lấy mẫu trong dòng thông tin.
- Nguồn mẫu và histogram lấy từ ảnh ghép thu nhỏ bên dưới layer (cùng ảnh xem trước),
  không đọc ảnh gốc toàn độ phân giải; mask và Opacity vẫn áp như phần 11–12.

### Layer Group (Giai đoạn 6 — phần 14)
- `LayerKind.GROUP`: nhóm là layer 1×1 có `group_id` liên kết phẳng; mỗi layer có
  `group_id` trỏ tới nhóm cha trực tiếp (hoặc `None`). `uses_canvas_mask` gộp chung
  adjustment và group để dùng mask kích thước canvas.
- `LayerManager.children_of(group_id)` trả layer con trực tiếp; nhóm lồng nhau không
  giới hạn độ sâu. `Document.add_group` tạo nhóm rỗng (tự nằm trong nhóm đang chọn),
  `group_layers` đưa một hoặc nhiều layer vào nhóm mới, `ungroup_layer` bỏ một cấp.
- `GroupLayersCommand`/`UngroupLayersCommand` giữ đúng thứ tự layer trước/sau và
  `group_id` cũ, nên mỗi thao tác nhóm/bỏ nhóm là một bước Undo/Redo.
- `Duplicate` và `Remove` trên nhóm xử lý toàn bộ cây con (nhân bản remap id, xoá bằng
  `MacroCommand`); `merge_down` từ chối nhóm hoặc hai layer khác nhóm; `Apply Mask` từ
  chối nhóm vì nhóm không có pixel riêng.
- Compositor dựng `parent_map` từ danh sách phẳng rồi đệ quy `_composite_children`:
  layer con hợp nhất trước, sau đó opacity/blend/mask của nhóm áp lên cả khối; nhóm ẩn
  ẩn toàn cây con; layer điều chỉnh trong nhóm chỉ áp lên accumulator của nhóm.
- Mask nhóm đúng kích thước tài liệu, co giãn theo Crop/Canvas Size/Image Size/xoay/lật
  và dùng chung Brush/Gradient như mask adjustment.
- Panel Layers hiển thị cây phân cấp: icon thư mục, tên đậm, phụ đề "Nhóm · N layer",
  thụt lề và đường dẫn nhóm; nút New Group, menu Layer ▸ New Group/Group Layers/
  Ungroup Layers với Ctrl+G và Ctrl+Shift+G.
- Panel Properties của nhóm hiển thị số layer con trực tiếp, opacity, blend, trạng thái
  mask và tên nhóm cha; transformation/filter bị tắt với nhóm.
- `.mps` v5 thêm `group_id` cho từng layer; file v4/v3/v2/v1 thiếu khoá được đọc là
  layer cấp gốc. Khi mở, `_validate_groups` kiểm tra nhóm cha tồn tại, đúng loại và
  không có vòng lặp; dữ liệu sai bị từ chối bằng `ProjectFormatError`.
- Giới hạn: chưa có clipping mask theo nhóm, kéo-thả layer giữa các nhóm, và phải xoá
  mask nhóm trước khi bỏ nhóm.

### Chữ trên đường dẫn và kerning cặp (Giai đoạn 6 — phần 15)
- `TextProperties` có thêm `kerning_pairs` (tuple cặp ký tự → px), `path_style` và
  `path_bend` (−100..100%). Kerning hợp lệ: đúng 2 ký tự, giá trị −200..200 px, tối đa
  200 cặp; cặp trùng lấy giá trị sau, giá trị 0 bị bỏ và danh sách được chuẩn hoá.
- `parse_kerning_pairs`/`format_kerning_pairs` đọc và ghi dạng `AV=-6, To=-3`; chấp nhận
  dấu phẩy, chấm phẩy hoặc xuống dòng, báo lỗi thân thiện khi sai cú pháp.
- Bốn kiểu đường dẫn: `arc` (cung tròn tối đa ±80°), `circle` (quét 360° × max(8%,
  |bend|); 100% là vòng kín), `wave` (2 chu kỳ) và `s_curve` (1 chu kỳ). Wave/S dùng
  tham số hoá theo độ dài cung thật nên chữ giãn đều và kéo giãn lấp đầy đường dẫn.
- Mỗi ký tự được đặt tại điểm trên đường dẫn với tâm ký tự trùng điểm đó và xoay theo
  tiếp tuyến; kerning áp giữa hai ký tự liền kề, cộng giãn chữ chung. Khi có kerning
  hoặc đường dẫn, layer xếp từng glyph với font/màu/đậm/nghiêng riêng của run.
- Render cắt theo bao alpha, giới hạn cạnh 30.000 px và 24 MP cho ảnh trung gian; lỗi
  vượt giới hạn gợi ý giảm cỡ chữ, bớt nội dung hoặc giảm độ cong.
- Đường dẫn thay thế hiệu ứng uốn chữ khi bật; kiểu "Không" hoặc độ cong 0 trả về chữ
  thường (bỏ qua warp). Xuống dòng được đổi thành khoảng trắng khi chạy trên đường dẫn.
- Hộp thoại Text có ô "Kerning cặp" và hàng "Chữ trên đường dẫn" (kiểu + độ cong);
  chọn kiểu đường dẫn tự đặt 60% và làm mờ điều khiển uốn chữ; xem trước trực tiếp và
  dòng thông tin hiển thị số cặp kerning hoặc kiểu đường dẫn.
- Panel Properties tóm tắt đường dẫn/độ cong (ưu tiên hơn warp) và vài cặp kerning đầu;
  gõ chữ trên canvas giữ nguyên kerning và đường dẫn của layer.
- Sửa thuộc tính qua `update_text_layer` render lại pixel, cập nhật kích thước layer và
  ghi đúng một bước Undo/Redo; `.mps` lưu `kerning_pairs`, `path_style`, `path_bend`
  trong metadata `text`, dự án cũ mở với mặc định không kerning/không đường dẫn.
- Giới hạn: chỉ có bốn kiểu đường dẫn dựng sẵn, chưa vẽ đường dẫn tuỳ ý.

### Layer tô và Smart Object (Giai đoạn 6 — phần 16)
- `FillProperties` (bất biến) gồm `fill_type` (`solid`/`gradient`), hai màu RGBA,
  `gradient_type` (`linear`/`radial`) và góc 0..359°. Validation chặt chẽ màu RGBA và
  kiểu; `from_dict` nâng lỗi thành thông báo tiếng Việt.
- `render_fill_band` dựng pixel float 0..1 theo từng dải quét cho compositor; gradient
  tuyến tính chiếu theo trục xoay quanh tâm canvas, gradient hình tròn theo khoảng cách
  tới tâm. `render_fill` render toàn layer cho rasterize và thumbnail hộp thoại.
- Layer `FILL` chiếm 1×1 px, không giữ mảng pixel; compositor gọi `render_fill_band`
  mỗi lần vẽ nên đổi màu/gradient chỉ render lại. Layer tô thuộc nhóm canvas-mask:
  nhận mask đúng cỡ tài liệu, không xoay/lật riêng, không di chuyển bằng Move, không
  nhận Brush/Gradient/filter trực tiếp; Merge Down/Flatten tự rasterize.
- `SmartObjectProperties` lưu tên/kích thước ảnh nguồn, góc (−180..180°), tỉ lệ
  (10..800%), lật ngang/dọc; `validate_source` giới hạn 30.000 px mỗi cạnh và 64 MP.
- `render_smart_object` xoay quanh tâm rồi thu phóng/lật bằng `QTransform`, cắt theo
  bao sau biến đổi, giới hạn cạnh 30.000 px và 64 MP; ảnh nguồn gốc không bị sửa.
- `Document.add_smart_object_layer` đặt layer vào giữa canvas; `update_smart_object`
  và `replace_smart_contents` render lại pixel, đổi kích thước layer và ghi đúng một
  bước Undo/Redo (Undo thay nội dung khôi phục cả ảnh nguồn cũ); `reset_smart_object`
  trả về biến đổi gốc; `rasterize_smart_layer` biến thành layer pixel.
- Smart object có mask riêng đúng kích thước layer đã render; khi mask đang bật, sửa
  biến đổi/thay nội dung/reset bị chặn (rasterize vẫn cho phép và áp mask).
- Hộp thoại `FillDialog` (loại tô, hai màu, kiểu/góc gradient, preview 320×160) và
  `SmartObjectDialog` (góc, tỉ lệ, lật, preview) cập nhật trực tiếp; nhấp đôi layer tô
  hoặc smart object trong panel mở đúng hộp thoại tương ứng.
- Panel Layers hiển thị thumbnail/loại layer và phụ đề (`Tô · Gradient · 32°`,
  `Smart object · 88 % · 7°`); panel Properties tóm tắt tham số tô hoặc nguồn/biến đổi.
- Menu Layer có New Fill Layer (Solid/Gradient), Place as Smart Object…, Edit Fill…,
  Edit Smart Object…, Replace Contents…, Reset Transform và Rasterize theo loại layer;
  action tự bật/tắt theo layer đang chọn và trạng thái mask.
- `.mps` v6 thêm metadata `fill` và `smart`, cùng ảnh nguồn `sources/<layer_id>.png`;
  khi mở kiểm tra metadata, kích thước ảnh nguồn và sự tồn tại file nguồn. File v1–v5
  vẫn mở bình thường.
- Giới hạn: chưa có perspective warp cho smart object, chưa lồng smart object trong
  smart object và chưa có smart filter không phá huỷ.

### Auto Levels và kéo histogram (Giai đoạn 6 — phần 17)
- `compute_auto_levels(rgba, clip_percent=0.5)` tính điểm đen/trắng từ histogram độ
  sáng luma của pixel có alpha > 0; cắt `clip_percent` % số pixel mỗi đầu bằng
  cumulative histogram nên bỏ qua nhiễu và điểm bất thường. Ảnh phẳng hoặc toàn trong
  suốt trả về 0..255 (không thay đổi); tham số ngoài 0..50 % bị từ chối.
- Nút **Auto Levels** trong hộp thoại Levels đặt lại đúng hai điểm vào, giữ gamma và
  điểm ra. Dòng thông tin ghi `Auto Levels đen..trắng`; sửa tay điểm vào sau đó tự bỏ
  ghi chú auto. Mọi thay đổi vẫn đi qua layer điều chỉnh và Undo/Redo như cũ.
- `HistogramView` của Levels có thêm chế độ tương tác: hai tay nắm đen/trắng vẽ đúng vị
  trí 0..255 kèm đường gióng và nhãn giá trị. Kéo tay nắm hoặc nhấp vào dải dưới
  histogram phát `rangeChanged(black, white)`; tay nắm đen bị kẹp dưới trắng và ngược
  lại nên không bao giờ tạo dải âm.
- Hộp thoại nối hai chiều: `rangeChanged` cập nhật ô Điểm đen/trắng vào; thay đổi từ
  slider, ô số hoặc eyedropper gọi `set_range` để tay nắm và đường gióng bám theo.
  Xem trước và layer mask được tính lại ngay khi kéo.
- Tham số vẫn lưu trong `.mps` v6 qua `levels_black`/`levels_white`; mở lại dự án khôi
  phục đúng dải đã chỉnh, không cần định dạng mới.
- Giới hạn: auto levels dùng luma tổng hợp trên ảnh xem trước thu nhỏ, chưa cân bằng
  riêng từng kênh và chưa cho đổi tỉ lệ cắt trong giao diện.

### Automation và preset SQLite (Giai đoạn 6 — phần 18)
- `core/batch.py`: `BatchStep` (frozen dataclass, chuẩn hoá/clamp tham số) cho 11 loại
  bước — Auto Levels, Auto Contrast, Grayscale, Invert, Brightness/Contrast,
  Hue/Saturation, Levels, Gaussian Blur, Unsharp Mask, Resize %, Resize max (không
  phóng to). `BatchAction` gói ≥1 bước với tên ≤48 ký tự.
- `BatchRunner(steps, output_dir, …)`: đọc ảnh bằng Pillow, áp bước trên mảng RGBA,
  xuất qua `export_image` (file tạm + `os.replace`). Hậu tố `_edited`, tên đích tự
  thêm `(2)`, `(3)` khi trùng, tuyệt đối không ghi đè ảnh nguồn trừ khi bật rõ ràng.
  Giới hạn 500 file và 80 triệu pixel mỗi ảnh; lỗi từng file không dừng cả lô.
- `BatchRunner.run` báo tiến trình `(done, total, source)` và kiểm tra hàm `cancel`
  giữa các file; file còn lại được đánh dấu `cancelled`.
- `core/presets.py`: `PresetStore` dùng `sqlite3` chuẩn, schema `presets(kind, name,
  payload, updated_at)` với `UNIQUE(kind,name) COLLATE NOCASE`; lưu/đọc/xoá/đổi tên,
  kiểm tra payload JSON và bỏ qua hàng hỏng. Preset điều chỉnh và action dùng chung
  kho, mặc định `presets.sqlite3` cạnh file cấu hình.
- Hộp thoại **Batch Processing** (Automation menu, Ctrl+Shift+B): danh sách file đầu
  vào (thêm file/thư mục/bỏ chọn, chống trùng, tối đa 500), danh sách bước có
  thêm/sửa/xoá/lên/xuống, action combo tải/lưu/xoá, thư mục ra, định dạng PNG/JPEG/
  WebP kèm chất lượng, hậu tố, tuỳ chọn ghi đè; thanh tiến trình, trạng thái và bảng
  kết quả, nút "Huỷ sau file hiện tại".
- `AdjustmentLayerDialog` có khung **Preset điều chỉnh**: combo preset đúng loại điều
  chỉnh đang sửa, ô tên, nút Lưu/Xoá; chọn preset áp lại tham số và cập nhật xem trước.
  Ghi đè cùng tên phải xác nhận.
- Batch chạy cục bộ, không truy cập Internet; action/preset chỉ chứa số và chuỗi nên
  không thể chạy mã lạ.
- Giới hạn: chạy tuần tự trong tiến trình giao diện (xử lý sự kiện giữa các file),
  huỷ chỉ sau file đang xử lý; chưa đa luồng, chưa xem trước action trên ảnh mẫu.

### Tile và lazy rendering (Giai đoạn 6 — phần 19)
- `core/canvas.py`: `composite_region(layers, width, height, x0, y0, x1, y1)` composite
  đúng một hình chữ nhật, xử lý layer pixel (offset âm, cắt biên), mask, 15 blend mode,
  layer tô, layer điều chỉnh và layer group; fast path sao chép vùng cho một layer
  normal. `composite_layers` toàn ảnh chạy theo dải và gọi cùng hạt nhân này nên hai
  đường đi luôn cho kết quả khớp.
- `scale_layers_for_preview(layers, width, height, max_side)`: tạo bản sao nông, lấy mẫu
  pixel/mask theo bước (không sửa layer gốc), chia offset và giữ nguyên điều chỉnh,
  group, fill; trả kích thước thu nhỏ.
- `core/tiles.py`: `TileCache` giữ tối đa 96 ô 256 × 256 theo LRU (khoảng 24 MB RGBA),
  bộ đếm hit/miss/composite; `sync()` đọc `Document.changes_since` để chỉ xoá ô giao
  với vùng đã đổi, xoá toàn bộ khi có invalidation toàn ảnh.
- `Document`: nhật ký dirty rect tối đa 64 mục, `revision`, `changes_since(revision)`
  trả `[]` khi không đổi, `None` khi cần xoá toàn bộ; `preview_image(max_side)` cache
  theo cặp (revision, cạnh) và `memory_estimate` cộng ảnh preview.
- `CanvasView`: zoom ≥ 50% vẽ từng ô giao với khung nhìn qua cache; zoom < 50% hoặc
  vượt 96 ô dùng `preview_image` (cạnh dài ≤ 2048 px). Chế độ hiện tại đọc được qua
  `render_mode` (`tiles`/`preview`/`inline`); `dispose()` xoá cache.
- `BrushStrokeSession` và `GradientSession` chỉ invalidate hình chữ nhật layer-local bị
  sửa (cộng offset), nhờ đó mỗi nét vẽ chỉ composite lại vài ô thay vì toàn tài liệu.
- Đo trên máy 8 GB RAM, tài liệu 17,5 MP/3 layer: composite toàn ảnh 13,8 s / 70 MB;
  một ô 256 × 256 50,6 ms / 256 KB; `sync()` dirty rect 0,02 ms; preview cạnh 1600
  832 ms cho ảnh 1250 × 875 / 4,4 MB; ước tính bộ nhớ tài liệu 214,4 MB.
- Giới hạn: ô ngoài cache phải dựng lại khi cuộn ngược; preview dựng lại toàn bộ sau
  mỗi lần sửa; gõ chữ trên canvas vẫn dùng composite toàn ảnh; chưa đa luồng và chưa
  lưu cache ra đĩa.

### Canvas và công cụ
- Zoom 2%–3200%, zoom tại con trỏ, Fit on Screen, Actual Pixels.
- Render hai chế độ: ô 256 × 256 composite theo khung nhìn (zoom ≥ 50%) và ảnh preview
  thu nhỏ dựng một lần cho mỗi revision (zoom < 50% hoặc vượt sức chứa cache).
- Pan bằng Space+kéo, chuột giữa, công cụ Hand; Shift+lăn chuột để pan ngang.
- Nền ca-rô cho vùng trong suốt; viền canvas; hiển thị toạ độ con trỏ.
- Công cụ Move (V), Rect Select (M), Ellipse Select (E), Lasso (L), Magic Wand (W),
  Quick Selection (Shift+W), Crop (C), Text (T), Shape (U), Brush (B), Gradient (G),
  Eraser (Shift+E), Hand (H), Zoom (Z).
- Phím tắt một chữ cái chỉ hoạt động khi canvas có focus, không cướp phím khi gõ.

### Giao diện
- Menu File/Edit/Image/Layer/Type/Select/Filter/View/Window/Help.
- Toolbox trái, Options Bar trên, dock Layers + Properties bên phải (kéo/ẩn được).
- Options Bar đổi theo công cụ: nút chọn nhanh, Feather và Anti-alias cho công cụ chọn,
  Dung sai/Liền mạch cho Magic Wand, Cỡ/Dung sai cho Quick Selection, Apply/Cancel cho
  Crop.
- Menu View ▸ Quick Mask (checkable, phím Q khi canvas focus) tô đỏ phần chưa chọn;
  action tự đồng bộ với từng tab và tắt khi không còn vùng chọn.
- Menu Select ▸ Feather Selection… (Shift+F6) mở hộp thoại đổi bán kính feather của
  vùng chọn hiện tại; action tự bật khi có vùng chọn.
- Menu Layer ▸ Layer Mask: Add/Remove/Apply/Toggle và Paint on Layer Mask (áp dụng
  cho cả Brush và Gradient); Options Bar của Brush có cỡ/độ cứng/độ đục/màu, của
  Gradient có kiểu/mẫu màu, cả hai đều chọn Layer hoặc Layer Mask.
- Menu Image ▸ Image Rotation (kèm Arbitrary Rotation…) / Flip Canvas; menu Edit ▸
  Transform cho layer (kèm Rotate… góc tự do).
- Menu Type cho layer văn bản; panel Layers có nút T; panel Properties hiển thị nội
  dung, font, cỡ chữ, kiểu, căn lề, giãn dòng/giãn chữ, đường dẫn hoặc uốn chữ và kerning
  của layer văn bản đang chọn.
- Menu Layer ▸ Shape; Options Bar của công cụ Shape; panel Layers có nút hình khối;
  panel Properties hiển thị thuộc tính hình khối đang chọn.
- Menu Layer ▸ New Adjustment Layer (Brightness/Contrast, Hue/Saturation, Invert,
  Desaturate) và Edit Adjustment…; hộp thoại xem trước, nhấp đôi layer để sửa; panel
  Layers có badge "fx"; action tự tắt với layer không phải điều chỉnh.
- Hộp thoại Levels có nút Auto Levels và hai tay nắm đen/trắng kéo trực tiếp trên
  histogram, đồng bộ với các ô điểm vào và phần xem trước.
- Menu Layer ▸ New Group / Group Layers (Ctrl+G) / Ungroup Layers (Ctrl+Shift+G); nút
  New Group trên panel Layers; panel hiển thị nhóm phân cấp với icon thư mục, thụt lề,
  tên đậm và phụ đề số layer; action transform/filter/apply mask tự tắt với nhóm.
- Menu Filter ▸ Adjustments / Blur / Sharpen với các hộp thoại có xem trước thu nhỏ;
  action tự bật/tắt theo layer đang chọn và trạng thái khoá.
- Theme Dark mặc định và Light; đổi theme không cần khởi động lại.
- Welcome page, Open Recent, lưu/khôi phục geometry và state cửa sổ.
- Hộp thoại phím tắt, About, thông báo lỗi thân thiện.
- Icon vẽ bằng QPainter, không dùng tài sản có bản quyền.

### File
- Import: PNG, JPEG, BMP, TIFF, GIF (khung đầu), WebP; EXIF orientation.
- Export: PNG (giữ alpha), JPEG/BMP (nền trắng), TIFF, WebP.
- Dự án `.mps` **phiên bản 6**: ZIP gồm `manifest.json` + PNG từng layer +
  `masks/<layer_id>.png` (Pillow mode L) + `sources/<layer_id>.png` cho smart object;
  layer văn bản lưu thêm `text` (nội dung, font, cỡ, màu, đậm/nghiêng, căn lề, giãn
  dòng, giãn chữ, uốn chữ, kerning cặp, chữ trên đường dẫn); layer hình khối lưu thêm
  `shape` (loại, kích thước, màu tô/viền, độ dày viền, bo góc); layer điều chỉnh dùng
  `kind: "adjustment"` kèm metadata `adjustment`; layer tô dùng `kind: "fill"` kèm
  metadata `fill`; smart object dùng `kind: "smart"` kèm metadata `smart` và ảnh
  nguồn PNG; layer nhóm dùng `group_id` để dựng cây. Ghi qua file tạm rồi thay thế.
- Đọc được dự án phiên bản 1–5; từ chối phiên bản mới hơn; kiểm tra và báo lỗi nếu
  metadata văn bản/hình khối/điều chỉnh/nhóm/fill/smart sai, kể cả kích thước hình khối
  không khớp pixel, layer điều chỉnh có mask sai cỡ, nhóm cha không tồn tại/vòng lặp,
  hoặc smart object thiếu/sai kích thước ảnh nguồn.
- Kiểm tra manifest, phiên bản, đường dẫn không an toàn, file thiếu/hỏng, mask sai kích thước.

### Nền tảng
- Log xoay vòng tại `%APPDATA%\MyPhotoStudio\logs\myphotostudio.log`.
- Excepthook hiển thị hộp thoại lỗi thay vì thoát im lặng.
- Lớp tương thích `compat/qt.py`: ưu tiên PySide2 trên Windows build < 14393,
  ưu tiên PySide6 trên Windows mới.

## 3. Kiểm thử

| Nhóm | Số bài | Nội dung |
| --- | --- | --- |
| `test_compositor.py` | 27 | fast path, offset/clipping, alpha over, multiply/screen, 15 blend mode, band, downsample |
| `test_layers.py` | 8 | mặc định, fill, validate, copy, blend catalog, LayerManager |
| `test_document.py` | 17 | layer, undo/redo, thuộc tính, rename, duplicate/remove, merge, flatten, reorder, offset, cache, mark_saved, memory |
| `test_selection.py` | 39 | boolean combine, invert, bounds chính xác, rasterize, scale/place; selection/mask/crop/canvas/resize + undo + validation; feather mask/giới hạn biên, anti-alias on/off, giữ tuỳ chọn qua biến đổi, undo feather, trộn filter và mask theo feather |
| `test_transform.py` | 26 | xoay/lật canvas 90°/180°: pixel, offset, mask, selection, composite, undo/redo; xoay/lật layer quanh tâm; xoay tự do: kích thước, trong suốt, selection, undo, lỗi đầu vào |
| `test_native_project.py` | 25 | roundtrip, manifest v6, mask/text/shape roundtrip, runs nhiều kiểu, văn bản uốn, chữ trên đường dẫn + kerning, dự án cũ không có runs/warp/path, rasterized text/shape, tương thích v1–v3, metadata văn bản/hình khối hỏng, kích thước shape lệch, phiên bản, file/mask hỏng, đường dẫn nguy hiểm |
| `test_text_layer.py` | 101 | validation/normalization TextProperties (giãn dòng/chữ, warp style/bend, kerning cặp, path style/bend), TextRun và validation runs, render alpha/màu/nhiều dòng/căn lề/giãn dòng/giãn chữ/nhiều kiểu chữ, 9 kiểu uốn + kích thước sau uốn + không tràn biên, 4 kiểu chữ trên đường dẫn + hướng cong + ưu tiên hơn warp, kerning làm hẹp/rộng chữ và giữ màu run, trộn cỡ chữ, tạo/sửa/rasterize/nhân bản, undo/redo, mask, biến đổi pixel và crop |
| `test_shape_layer.py` | 18 | validation/normalization ShapeProperties, render chữ nhật/ellipse/bo góc/viền, dict roundtrip, tạo/sửa/rasterize, undo/redo, mask, tự rasterize khi biến đổi và áp bộ lọc |
| `test_filters.py` | 24 | validation, invert, brightness/contrast, desaturate, auto contrast, hue/saturation, blur alpha/không quầng tối, unsharp mask/ngưỡng; Document áp dụng với vùng chọn, undo/redo, rasterize văn bản, giữ mask, layer khoá, đầu vào sai |
| `test_adjustment_layer.py` | 14 | bốn phép điều chỉnh màu giữ alpha, validation/clamp AdjustmentProperties, chỉ tác động layer bên dưới, opacity/visibility, undo/redo, sửa không đổi không ghi history, giữ 1×1 qua resize/crop/canvas/rotate/flip, chặn brush/gradient/filter/transform, roundtrip `.mps` v4 |
| `test_adjustment_mask.py` | 13 | tạo mask đúng cỡ canvas + undo/redo, mask từ vùng chọn, giới hạn hiệu ứng theo điểm ảnh, tắt/bật mask, opacity × mask, brush/gradient lên mask điều chỉnh, giới hạn theo vùng chọn, crop/canvas size/resize/xoay/lật biến đổi mask + undo, roundtrip `.mps`, chặn Apply Layer Mask |
| `test_adjustment_advanced.py` | 13 | Levels: identity, clamp, toán black/white/gamma/output, summary, roundtrip, black &lt; white; Curves: LUT, identity, hai đầu mút, validation (trùng x, 1 điểm, 17 điểm, dict hỏng); Color Balance: hướng vùng tối/trung gian, giữ luminosity, nhãn tiếng Việt, validation, roundtrip; Document ghép 3 layer + undo; đổi kind Levels ↔ Curves + undo/redo; `.mps` roundtrip; metadata cũ thiếu trường và metadata curves hỏng |
| `test_adjustment_channels.py` | 12 | Curves kênh R/G/B: chỉ đổi kênh tương ứng, thứ tự kênh trước RGB tổng hợp, validation/clamp, identity/summary, serialize; histogram luma + R/G/B, bỏ pixel trong suốt, bins và validation; Document composite + undo; `.mps` roundtrip và metadata cũ thiếu kênh; UI đổi kênh, histogram, reset kênh, eyedropper Levels/Curves |
| `test_layer_groups.py` | 22 | compositor: opacity/blend/mask của nhóm áp lên cả cây con, nhóm ẩn/lồng nhau, adjustment chỉ tác động trong nhóm; Document: nhóm/bỏ nhóm/nhân bản/xoá cây con + undo/redo, layer mới vào nhóm, merge guard, mask canvas-size và resize; `.mps` v6 roundtrip, `group_id` thiếu cha/vòng lặp bị từ chối, file v4 không có group_id; UI: panel phân cấp/độ sâu, action nhóm, Properties, New Group, layer mới vào nhóm |
| `test_fill_smart.py` | 24 | FillProperties validation/from_dict, render solid/dải/radial, Document thêm/sửa/undo/redo, rasterize kèm mask, chặn transform, blend/opacity; SmartObjectProperties validation/biến đổi/identity, render xoay-thu phóng-lật, đặt giữa canvas, cập nhật/undo/mask guard, replace khôi phục nguồn cũ, reset/rasterize + undo; `.mps` v6 roundtrip fill+smart và mask fill, file nguồn; UI: FillDialog, SmartObjectDialog, trạng thái action, phụ đề panel, double-click panel, Properties |
| `test_levels_auto.py` | 9 | `compute_auto_levels`: gradient đầy đủ, clip 0, bỏ pixel trong suốt, ảnh phẳng/toàn trong suốt, validation đầu vào và tỉ lệ cắt, kéo giãn dải sáng 40..210 về 0..255; UI: nút Auto Levels và đồng bộ histogram, kéo tay nắm đen/trắng đổi dải và phát signal, bỏ qua nhấp ngoài dải, kéo histogram cập nhật ô điểm vào |
| `test_batch.py` | 18 | BatchStep validation/clamp và dict roundtrip, BatchAction ≥1 bước/tên; apply_step màu, resize %/max không phóng to, auto levels/contrast; runner giữ ảnh gốc, hậu tố, chống trùng tên `(2)`, ghi đè, PNG/JPEG/WebP, lỗi từng file không dừng, tiến trình + huỷ giữa file; UI BatchStepDialog đổi loại bước, BatchDialog thêm/xoá/đổi thứ tự bước và chạy, lưu/tải/xoá action, cảnh báo khi thiếu đầu vào |
| `test_tiles.py` | 16 | `composite_region` khớp composite toàn ảnh (pixel/mask/multiply, fill + adjustment + group, offset âm), validation vùng; `scale_layers_for_preview` kích thước và không sửa layer gốc; `preview_image` cache theo revision/cạnh và bước 1; `changes_since` rect, cắt biên, log bị cắt; TileCache nội dung ô mép, LRU/bộ đếm, xoá theo dirty rect, xoá toàn bộ và validation; CanvasView chế độ preview khi fit, tile khi 100%, hit tăng, repaint sau invalidation và dispose |
| `test_presets.py` | 10 | SQLite lưu/đọc, sắp xếp không phân biệt hoa thường, trùng tên và ghi đè, tên/kind/payload sai, xoá/đổi tên, helper adjustment/action roundtrip, bỏ qua hàng JSON hỏng; AdjustmentLayerDialog lưu/áp/xoá preset và lọc theo loại; MainWindow action batch + đường dẫn `presets.sqlite3` |
| `test_brush.py` | 21 | BrushSettings clamp/validation, dấu cọ cứng/mềm, vùng chọn, nội suy nét, ghép màu alpha thẳng, tẩy alpha, mask lerp/luminance; Document vẽ/undo/redo, độ đục không cộng dồn, giới hạn vùng chọn, mask, layer khoá/thiếu mask, huỷ nét, rasterize hình khối |
| `test_gradient.py` | 13 | GradientSettings validation/clamp, ramp tuyến tính/hình tròn, tô pixel + undo/redo, giới hạn vùng chọn, gradient hình tròn, alpha trong suốt, gradient lên mask + undo/redo, giới hạn vùng chọn trên mask, nhấp không kéo không ghi history, huỷ gradient, lỗi đầu vào, rasterize hình khối |
| `test_wand.py` | 15 | layer_sample đặt/cắt pixel, eligibility theo dung sai/alpha, flood fill liền mạch và toàn tài liệu, seed ngoài tài liệu, mask_to_path rỗng/roundtrip/lỗ hổng/tiếp xúc chéo, from_path validation |
| `test_export.py` | 7 | PNG alpha, JPEG/BMP nền trắng, TIFF/WebP, đuôi không hỗ trợ |
| `test_import.py` | 5 | PNG, JPEG, file thiếu/rỗng/hỏng |
| `test_ui_smoke.py` | 22 | MainWindow, layer/undo, theme, chụp ảnh; công cụ chọn, mask, crop, hộp thoại size; action xoay/lật; hộp thoại xoay tự do; hộp thoại văn bản và luồng tạo/sửa/rasterize; menu Filter, hộp thoại bộ lọc, xem trước và bật/tắt action; hộp thoại shape, công cụ Shape kéo vẽ, Options Bar, menu/panel, undo/redo, rasterize và huỷ bằng Escape; Brush/Eraser kéo vẽ, phím tắt, mask target, Paint on Layer Mask và huỷ nét; Gradient kéo tô, Options Bar, mẫu màu, undo, gradient hình tròn, vẽ mask dùng chung với Brush, phím G và Escape; Feather/Anti-alias trên Options Bar, kéo chọn, menu Feather, hộp thoại và tuỳ chọn riêng từng công cụ; Lasso/Wand/Quick Selection, phím L/W/Shift+W, cộng/trừ vùng chọn, preview Quick Selection, Quick Mask phím Q/menu/tự tắt; ô Giãn dòng / chữ trong hộp thoại văn bản, xem trước và đọc lại thuộc tính; định dạng theo vùng bôi đen, đồng bộ điều khiển theo con trỏ, sửa runs nhiều kiểu và roundtrip văn bản cũ/nhiều dòng; layer điều chỉnh: badge/subtitle/tooltip, blend combo bị mờ, trạng thái action, panel Properties, hộp thoại xem trước và nhấp đôi để sửa; hộp thoại Levels/Curves/Color Balance: trường nhập, gamma, trình vẽ đường cong, đặt lại 45°, giữ luminosity, panel Properties; ô Kerning cặp và chữ trên đường dẫn trong hộp thoại văn bản, xem trước, báo lỗi cú pháp, panel Properties hiển thị đường dẫn/kerning |

Lệnh chạy:

```powershell
cd D:\python\myphoto
.\.venv310qt5\Scripts\python.exe -m pytest -q
```

## 4. Hạn chế đã biết

1. **Môi trường Windows 10 build 10240**: Qt 6 không nạp được `qwindows.dll` vì thiếu
   các hàm DPI (`GetDpiForWindow`, `SetProcessDpiAwarenessContext`, ...). Vì vậy bản
   chạy thật dùng PySide2/Qt 5.15. Trên Windows 10 1607+/11 có thể dùng PySide6.
2. PySide2 5.15.2.1 là bản cũ, không còn cập nhật bảo mật từ Qt; rủi ro thấp với ứng
   dụng desktop cục bộ nhưng cần nâng cấp khi hệ điều hành được cập nhật.
3. Vùng chọn hiện gồm chữ nhật/ellipse, Lasso, Magic Wand và Quick Selection, có feather
   (0..250 px) và bật/tắt anti-alias; chưa có Select Subject bằng AI, refine edge hoặc
   lưu vùng chọn trong `.mps`.
4. Layer mask vẽ/sửa được bằng Brush và Gradient, tạo được mask mép mềm từ vùng chọn
   feather và xem nhanh bằng Quick Mask; chưa xem mask như một kênh (Channels) riêng.
5. Vùng chọn không được lưu trong `.mps` (mask thì có).
6. Layer văn bản đã có giãn dòng, giãn chữ, định dạng theo từng đoạn, uốn chữ theo
   9 kiểu, gõ/sửa trực tiếp trên canvas, kerning cặp thủ công và chữ trên bốn kiểu
   đường dẫn dựng sẵn; chưa hỗ trợ đường dẫn tuỳ ý do người dùng vẽ.
7. Layer hình khối mới có 3 loại cơ bản; chưa chỉnh bằng tay nắm/đường dẫn. Layer điều
   chỉnh đã có Brightness/Contrast, Hue/Saturation, Invert, Desaturate, Levels, Curves,
   Color Balance, Curves tách kênh R/G/B, histogram và eyedropper, cùng mask cấp tài
   liệu (tạo từ vùng chọn, vẽ Brush/Gradient), auto levels và kéo trực tiếp điểm
   đen/trắng trên histogram. Layer group đã có (nhóm lồng nhau, opacity/blend/mask,
   Undo/Redo, `.mps` v6); chưa có clipping mask theo nhóm hay kéo-thả layer giữa các
   nhóm. Layer tô và smart object đã có (xoay/thu phóng/lật, thay nội dung, reset,
   rasterize); smart object chưa có perspective warp hoặc lồng smart object.
8. Bộ lọc hiện gồm các phép cơ bản; chưa có blur theo hướng/chuyển động, radial blur,
   noise, vignette, lens correction, smart filter không phá huỷ, hiệu ứng layer hoặc
   tách nền/loại bỏ vật thể.
9. Xem trước bộ lọc dùng ảnh thu nhỏ; bán kính blur được nhân theo tỉ lệ nên kết quả
   xem trước chỉ gần đúng, kết quả cuối cùng luôn tính ở độ phân giải đầy đủ.
10. Chưa hỗ trợ kéo thả file vào cửa sổ, chưa đọc/ghi PSD.
11. Undo vẫn lưu bản sao layer nên tốn RAM với ảnh lớn; canvas đã dùng tile/lazy
    rendering nhưng cache giới hạn 96 ô 256 × 256 (khoảng 24 MB), ô bị đẩy khỏi cache
    sẽ composite lại khi cuộn ngược và chưa có composite đa luồng.
12. Biến đổi pixel (resize, xoay/lật, áp bộ lọc) tự rasterize layer văn bản/hình khối
    nên không sửa lại nội dung/thuộc tính sau các thao tác đó; cần Undo nếu muốn khôi phục.
13. `QActionGroup`/`QAction` được ánh xạ từ QtGui sang QtWidgets trên Qt 5 qua lớp
    compat; đây là điểm cần giữ khi thêm module mới.
14. Xử lý hàng loạt chạy tuần tự trong tiến trình giao diện (giữa các file có xử lý
    sự kiện để cửa sổ phản hồi); nút huỷ chỉ có hiệu lực sau file đang xử lý; chưa
    đa luồng và chưa xem trước action trên ảnh mẫu. Giới hạn cứng 500 file và 80 MP
    mỗi ảnh để bảo vệ RAM; preset/action nằm trong một file SQLite cục bộ, chưa có
    xuất/nhập preset giữa các máy.

## 5. Môi trường đã kiểm chứng

| Thành phần | Phiên bản |
| --- | --- |
| Windows | 10.0.10240 (64-bit) |
| Python | 3.10.22 (uv-managed) |
| Qt binding chạy thật | PySide2 5.15.2.1 + shiboken2 5.15.2.1 |
| Qt binding kiểm thử phụ | PySide6 6.3.2 (offscreen) |
| NumPy | 1.26.4 |
| Pillow | 12.3.0 |
| pytest | 9.2.0 |

## 6. Việc tiếp theo — Giai đoạn 6

Phần 1–19 của Giai đoạn 6 (layer hình khối; cọ, tẩy, vẽ layer mask; gradient; feather
và anti-alias; Lasso/Magic Wand/Quick Selection và Quick Mask; giãn dòng/giãn chữ; định
dạng theo từng đoạn chữ; uốn chữ; gõ chữ trên canvas; layer điều chỉnh không phá huỷ;
mask cho layer điều chỉnh; Levels, Curves và Color Balance; Curves tách kênh, histogram
và eyedropper; layer group; chữ trên đường dẫn và kerning cặp; layer fill và smart
object; Auto Levels và kéo histogram; automation batch/action và preset SQLite; tối ưu
tile/lazy rendering cho ảnh lớn) đã hoàn thành. Các mục còn lại:

1. Cân nhắc đa luồng cho batch, composite tile và xem trước action trên ảnh mẫu.
2. Tiếp tục kiểm thử UI, ảnh xem trước và cập nhật tài liệu cho từng phần.

Mỗi phần phải chạy được, có kiểm thử và cập nhật file trạng thái này trước khi
tuyên bố hoàn thành.
