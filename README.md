# My Photo Studio — Giai đoạn 6

Ứng dụng chỉnh sửa ảnh và thiết kế đồ họa chạy trên máy tính Windows, viết bằng Python.
Toàn bộ xử lý diễn ra cục bộ trên máy; ứng dụng không tự kết nối Internet và không gửi ảnh
của bạn đi đâu.

Đây là sản phẩm độc lập, không sao chép mã nguồn, logo, giao diện độc quyền hay tài sản
có bản quyền của Adobe Photoshop.

![Vùng chọn ellipse và layer mask](artifacts/phase2_selection.png)

![Crop với overlay và lưới](artifacts/phase2_crop.png)

![Xoay canvas và xoay riêng layer](artifacts/phase3_transform.png)

![Xoay tự do canvas 12° và xoay layer -6°](artifacts/phase3_free_rotate.png)

![Layer văn bản với font, màu và căn lề](artifacts/phase4_text.png)

![Hộp thoại sửa layer văn bản có xem trước](artifacts/phase4_text_dialog.png)

![Bộ lọc Hue/Saturation áp dụng cho layer đang chọn](artifacts/phase5_filters.png)

![Hộp thoại Gaussian Blur có xem trước thu nhỏ](artifacts/phase5_blur_dialog.png)

![Layer hình khối với tô màu, viền và bo góc](artifacts/phase6_shapes.png)

![Hộp thoại sửa hình khối có xem trước](artifacts/phase6_shape_dialog.png)

![Brush, Eraser và vẽ trực tiếp lên layer mask](artifacts/phase6_brush.png)

![Gradient tuyến tính/hình tròn tô lên pixel và layer mask](artifacts/phase6_gradient.png)

![Vùng chọn ellipse với feather 40 px và layer mask mép mềm](artifacts/phase6_feather.png)

![Magic Wand, Quick Mask và bộ chọn nâng cao](artifacts/phase6_select_tools.png)

![Giãn dòng và giãn chữ trong layer văn bản](artifacts/phase6_rich_text.png)

![Hộp thoại văn bản với ô Giãn dòng / chữ](artifacts/phase6_rich_text_dialog.png)

![Định dạng font, cỡ, màu theo từng đoạn trong một layer](artifacts/phase6_rich_runs.png)

![Hộp thoại định dạng đoạn chữ đang bôi đen](artifacts/phase6_rich_runs_dialog.png)

![Uốn chữ: cung, sóng, vòm, xoắn và phồng trên các layer văn bản](artifacts/phase6_text_warp.png)

![Hộp thoại sửa văn bản với kiểu uốn Cung tròn và độ uốn](artifacts/phase6_text_warp_dialog.png)

![Gõ chữ trực tiếp trên canvas: khung soạn thảo trong suốt đặt đúng vị trí](artifacts/phase6_canvas_text.png)

![Sau khi nhấn Ctrl+Enter, chữ được tạo thành layer văn bản mới](artifacts/phase6_canvas_text_result.png)

![Hai layer điều chỉnh Hue/Saturation và Brightness/Contrast áp lên ảnh bên dưới](artifacts/phase6_adjustment_layers.png)

![Hộp thoại sửa layer điều chỉnh kèm xem trước trên ảnh thật](artifacts/phase6_adjustment_dialog.png)

![Mask của layer điều chỉnh: gradient đen → trắng giới hạn hiệu ứng Hue/Saturation theo từng điểm ảnh](artifacts/phase6_adjustment_mask.png)

![Hộp thoại sửa layer điều chỉnh có xem trước áp cả layer mask](artifacts/phase6_adjustment_mask_dialog.png)

![Ba layer điều chỉnh Levels, Curves và Color Balance xếp trên ảnh gốc](artifacts/phase6_advanced_adjustments.png)

![Hộp thoại Levels với điểm đen/trắng vào-ra và gamma](artifacts/phase6_levels_dialog.png)

![Hộp thoại Curves với đường cong bốn điểm kéo được](artifacts/phase6_curves_dialog.png)

![Curves chọn kênh Đỏ: histogram nền và đường cong riêng của kênh](artifacts/phase6_curves_red_channel.png)

![Hộp thoại Color Balance ba vùng tối/trung gian/sáng và giữ độ sáng](artifacts/phase6_color_balance_dialog.png)

![Layer group lồng nhau: opacity/blend/mask áp lên cả nhóm và panel Layers phân cấp](artifacts/phase6_layer_groups.png)

![Chữ trên đường dẫn: cung tròn, vòng tròn, lượn sóng, chữ S và kerning cặp thủ công](artifacts/phase6_text_path.png)

![Hộp thoại văn bản với ô Kerning cặp và kiểu chữ trên đường dẫn](artifacts/phase6_text_path_dialog.png)

![Layer tô gradient và smart object xoay/thu nhỏ không phá huỷ trên cùng tài liệu](artifacts/phase6_fill_smart.png)

![Hộp thoại Fill với loại tô màu/gradient, góc gradient và xem trước trực tiếp](artifacts/phase6_fill_dialog.png)

![Hộp thoại Smart Object với góc xoay, tỉ lệ thu nhỏ, lật ngang/dọc và xem trước](artifacts/phase6_smart_object_dialog.png)

![Hộp thoại Levels với Auto Levels và hai tay nắm đen/trắng kéo trực tiếp trên histogram](artifacts/phase6_levels_auto.png)

![Xử lý hàng loạt: 3 file đã xong với action "Ảnh web 1600px" và thanh tiến trình](artifacts/phase6_batch_dialog.png)

![Hộp thoại Levels mở thư viện preset SQLite, đã áp preset "Ấm hoàng hôn"](artifacts/phase6_preset_library.png)

![Tài liệu 3600 × 2400 xem ở 100%: canvas chỉ composite các ô 256 × 256 trong khung nhìn](artifacts/phase6_tiles.png)

## 1. Đã làm được gì

### Giai đoạn 1 — Core Application
- Cửa sổ chính có menu, thanh công cụ, thanh tuỳ chọn, canvas, panel Layers/Properties,
  thanh trạng thái và nhiều tab tài liệu.
- Màn hình chào, mở lại file gần đây, ghi nhớ vị trí/kích thước cửa sổ.
- Tạo tài liệu mới với kích thước, độ phân giải, nền trắng/trong suốt/đen/màu tuỳ chọn.
- Mở ảnh PNG, JPEG, BMP, TIFF, GIF (khung đầu), WebP; tự áp dụng hướng EXIF.
- Lưu dự án `.mps` (ZIP gồm manifest + từng layer PNG), mở lại đúng thứ tự layer.
- Xuất ảnh PNG, JPEG, BMP, TIFF, WebP.
- Layer pixel: tạo, nhân bản, đổi tên, xoá, kéo thả đổi thứ tự, ẩn/hiện, opacity,
  15 chế độ hoà trộn, Merge Down, Flatten Image.
- Undo/Redo theo Command Pattern cho thao tác layer và di chuyển layer.
- Công cụ Move, Hand, Zoom; zoom tại con trỏ, kéo pan bằng Space/chuột giữa,
  Fit on Screen và Actual Pixels.
- Theme Dark (mặc định) và Light; panel có thể kéo, di chuyển, ẩn/hiện.
- Kiểm tra kích thước ảnh trước khi mở/tạo để tránh hết RAM; log lỗi vào
  `%APPDATA%\MyPhotoStudio\logs`.

### Giai đoạn 2 — Vùng chọn, layer mask, crop, kích thước
- Công cụ chọn chữ nhật (M) và ellipse (E); giữ Shift để cộng, Alt để trừ,
  Shift+Alt để giao vùng chọn.
- Select All (Ctrl+A), Deselect (Ctrl+D), Invert Selection (Ctrl+Shift+I).
- Vùng chọn hiển thị bằng "marching ants" chuyển động, cắt đúng biên tài liệu.
- Layer mask: thêm từ vùng chọn hoặc trắng toàn bộ, bật/tắt, xoá, áp dụng vĩnh viễn;
  thumbnail mask hiện cạnh layer, gạch chéo khi tắt.
- Crop (C) với overlay làm tối vùng ngoài, viền trắng, lưới một phần ba và tay nắm;
  Enter áp dụng, Escape huỷ; có Crop to Selection trong menu Image.
- Image Size (Ctrl+Alt+I): khoá tỉ lệ, chọn nearest/bilinear/bicubic/lanczos.
- Canvas Size (Ctrl+Alt+C): 9 điểm neo, dịch layer và vùng chọn theo neo.
- Mọi thao tác trên đều có Undo/Redo.
- Giai đoạn này dùng `.mps` phiên bản 2 (lưu kèm mask); định dạng hiện tại là phiên
  bản 4, vẫn mở được dự án phiên bản 1–3.
- Vùng chọn là trạng thái tạm của phiên làm việc, không lưu vào file dự án.

### Giai đoạn 3 — Xoay và lật
- Xoay canvas 90° theo chiều kim đồng hồ, 90° ngược chiều kim đồng hồ và 180°.
- Xoay canvas tự do theo góc bất kỳ (Image ▸ Image Rotation ▸ Arbitrary Rotation…);
  góc dương xoay theo chiều kim đồng hồ, canvas tự mở rộng và vùng ngoài trong suốt.
- Lật canvas theo chiều ngang hoặc chiều dọc.
- Xoay/lật riêng layer đang chọn qua menu Edit ▸ Transform; layer xoay quanh tâm của nó.
- Xoay layer tự do theo góc bất kỳ (Edit ▸ Transform ▸ Rotate…), chọn nearest/bilinear/
  bicubic/lanczos và xem trước kích thước mới ngay trong hộp thoại.
- Layer mask và vùng chọn được xoay/lật đồng bộ với canvas.
- Kích thước tài liệu, kích thước layer và offset được cập nhật chính xác, kể cả layer
  không phủ kín canvas.
- Góc 90°/180° dùng phép xoay chính xác từng điểm ảnh; góc bất kỳ dùng nội suy đã chọn.
- Mọi thao tác đều có Undo/Redo; thao tác xoay canvas tự Fit on Screen và huỷ vùng crop
  đang dở.

### Giai đoạn 4 — Layer văn bản
- Công cụ Text (T): nhấp vào canvas để tạo layer văn bản tại vị trí đã chọn.
- Hộp thoại tạo/sửa văn bản: nội dung, font hệ thống, cỡ chữ, màu RGBA, đậm/nghiêng,
  căn trái/giữa/phải và khung xem trước cập nhật trực tiếp.
- Menu Type ▸ New Text Layer… (Ctrl+Shift+T), Edit Text… và Rasterize Text; ngoài ra
  có nút "New Text Layer…" trên Options Bar và nút T trong panel Layers.
- Văn bản vẫn chỉnh sửa được sau khi tạo; mỗi lần sửa render lại pixel và ghi Undo.
- Rasterize chuyển layer văn bản thành layer pixel; Undo khôi phục lại nội dung văn bản.
- Layer văn bản hoạt động như layer pixel: composite, di chuyển, mask, nhân bản,
  đổi thứ tự và xuất ảnh.
- Khi layer văn bản có mask, cần áp hoặc xoá mask trước khi sửa nội dung.
- Resize/xoay/lật tự rasterize văn bản; crop và canvas size giữ nguyên khả năng chỉnh sửa.
- Giai đoạn này dùng `.mps` phiên bản 3 (lưu thuộc tính văn bản); định dạng hiện tại là
  phiên bản 4, vẫn mở được dự án phiên bản 1–3.
- Giới hạn an toàn: 10.000 ký tự, 500 dòng, font 1..1000 px, render tối đa 64 MP.

### Giai đoạn 5 — Bộ lọc và hiệu ứng
- Menu Filter gồm Adjustments, Blur và Sharpen; các mục tự bật/tắt theo layer đang chọn.
- Adjustments: Brightness/Contrast…, Hue/Saturation… (Ctrl+U), Auto Contrast, Invert
  (Ctrl+I) và Desaturate (Ctrl+Shift+U).
- Blur ▸ Gaussian Blur… với bán kính 0,1..100 px; làm mờ cả kênh màu lẫn alpha bằng
  xấp xỉ Gaussian 3 lượt box blur trên dữ liệu premultiplied, tránh quầng tối.
- Sharpen ▸ Unsharp Mask… với lượng làm nét, bán kính và ngưỡng chống nhiễu.
- Hộp thoại có xem trước thu nhỏ (tự thu nhỏ layer, cập nhật sau 150 ms) và áp dụng
  đúng độ phân giải đầy đủ khi bấm Áp dụng.
- Bộ lọc chỉ tác động lên layer đang chọn; nếu có vùng chọn thì chỉ áp dụng bên trong
  vùng chọn, mép vùng chọn được trộn mượt theo mask.
- Layer mask được giữ nguyên; layer văn bản/hình khối tự rasterize khi áp bộ lọc.
- Mỗi lần áp dụng là một bước Undo/Redo; layer bị khoá không áp dụng được.
- Tối ưu cho 8GB RAM: xử lý từng khối 1 triệu điểm ảnh, giới hạn 64 MP cho bộ lọc
  điểm ảnh và 24 MP cho blur; báo lỗi thân thiện khi ảnh quá lớn.

### Giai đoạn 6 — Layer hình khối (phần 1)
- Công cụ Shape (U): kéo trên canvas để vẽ hình chữ nhật, chữ nhật bo góc hoặc ellipse.
- Kéo từ điểm bắt đầu tới điểm kết thúc; hình được kẹp trong biên tài liệu, giữ Shift
  để tạo hình vuông/tròn, Escape huỷ khi đang kéo.
- Preview ngay trên canvas trong lúc kéo: tô màu mờ theo màu thật và viền nét đứt;
  thanh trạng thái hiện kích thước theo px.
- Options Bar cho Shape: loại hình, bật/tắt màu tô, chọn màu tô RGBA, độ dày viền,
  màu viền RGBA và bán kính bo góc (chỉ bật khi chọn chữ nhật bo góc).
- Layer hình khối giữ dữ liệu vector trong bộ nhớ; menu Layer ▸ Shape gồm
  New Shape Layer…, Edit Shape… và Rasterize Shape. Nút hình khối cũng có trong
  panel Layers.
- Hộp thoại tạo/sửa hình khối có kích thước, màu tô, viền, bo góc và xem trước trực tiếp.
- Thêm/sửa/rasterize đều có Undo/Redo; xoay/lật/resize/áp bộ lọc tự rasterize layer
  hình khối, Undo khôi phục lại dữ liệu vector.
- Khi layer hình khối có mask, cần áp hoặc xoá mask trước khi sửa thuộc tính.
- Định dạng `.mps` phiên bản 4 lưu thuộc tính hình khối; kiểm tra kích thước metadata
  khớp với dữ liệu pixel khi mở file, vẫn đọc được dự án phiên bản 1–3.
- Giới hạn an toàn: cạnh tối đa 30.000 px, vùng render tối đa 64 MP, viền tối đa
  500 px và bán kính bo góc tối đa 15.000 px.

### Giai đoạn 6 — Cọ, Tẩy và vẽ layer mask (phần 2)
- Công cụ Brush (B) và Eraser (Shift+E); con trỏ là vòng tròn hiển thị đúng đường kính
  theo tỉ lệ zoom (đổi sang dấu chữ thập khi quá nhỏ hoặc quá lớn).
- Options Bar cho cọ: cỡ 1..2000 px, độ cứng mép 0..100 %, độ đục 1..100 %, ô màu
  Foreground và lựa chọn vẽ lên Layer hoặc Layer Mask.
- Màu cọ luôn lấy từ màu Foreground của toolbox; đổi màu ở toolbox sẽ cập nhật ngay.
- Nét cọ được nội suy theo khoảng cách đầu cọ, độ đục không cộng dồn trong cùng một nét,
  mép mềm theo độ cứng và luôn giới hạn trong vùng chọn đang có.
- Đang kéo thì canvas cập nhật trực tiếp; thả chuột mới ghi một bước Undo duy nhất;
  Escape huỷ nét đang vẽ và trả layer về trạng thái trước khi kéo.
- Vẽ lên Layer Mask: giá trị mask lấy theo độ sáng của màu Foreground (đen = ẩn,
  trắng = hiện); bật bằng combo "Vẽ lên" hoặc menu Layer ▸ Layer Mask ▸ Paint on Layer Mask.
- Eraser chỉ tẩy pixel (giảm alpha), không tẩy lên mask; layer khoá không vẽ được.
- Vẽ lên layer văn bản/hình khối sẽ tự rasterize; Undo khôi phục lại dữ liệu vector.
- Không đổi định dạng `.mps`: pixel và mask đã được lưu từ phiên bản 2 (nay là v5 khi
  có layer group).

### Giai đoạn 6 — Gradient (phần 3)
- Công cụ Gradient (G): kéo trên canvas để tô gradient theo đúng hướng và độ dài kéo.
- Hai kiểu: tuyến tính (màu chạy dọc hướng kéo) và hình tròn (toả từ điểm bắt đầu).
- Bốn mẫu màu: Foreground → Background, Foreground → Trong suốt, Đen → Trắng và
  Trắng → Đen; màu Foreground/Background luôn đồng bộ từ Toolbox.
- Options Bar hiển thị kiểu, mẫu, ô xem trước dải màu, đích tô (Layer / Layer Mask) và
  giá trị mask đầu/cuối khi tô lên mask.
- Tô lên Layer thay thế pixel trong phạm vi gradient (kể cả alpha); tô lên Layer Mask
  dùng độ sáng hai màu đầu/cuối (đen = ẩn, trắng = hiện).
- Đang kéo thì gradient cập nhật trực tiếp trên canvas theo từng dải điểm ảnh; với layer
  rất lớn (> 16 MP) chỉ áp dụng khi thả chuột để giữ phản hồi mượt.
- Vùng chọn giới hạn phạm vi tô, mép vùng chọn được trộn mượt; mỗi lần kéo ghi đúng
  một bước Undo, Escape huỷ và trả layer về trạng thái trước.
- Nút Paint on Layer Mask dùng chung cho Brush và Gradient; tô lên layer văn bản/hình
  khối tự rasterize và Undo khôi phục dữ liệu vector.
- Định dạng `.mps` không thay đổi: dữ liệu pixel và mask đã có từ phiên bản 2.
- Phần còn lại của Giai đoạn 6 (smart object, automation, preset SQLite,
  tối ưu nâng cao) sẽ làm ở các bước tiếp theo.

### Giai đoạn 6 — Feather và anti-alias vùng chọn (phần 4)
- Options Bar của Rectangular/Elliptical Marquee có ô Feather (0..250 px) và hộp kiểm
  Anti-alias; tuỳ chọn được ghi nhớ riêng cho từng công cụ chọn.
- Feather làm mềm biên bằng Gaussian xấp xỉ 3 lượt box blur; biên mềm mở rộng ra ngoài
  đường bao nhưng luôn cắt trong phạm vi tài liệu.
- Anti-alias bật cho biên ellipse/chữ nhật lẻ pixel mượt; tắt để giữ biên răng cưa
  (mask chỉ còn 0 và 255).
- Vùng chọn đã feather được dùng thống nhất cho layer mask, cọ, tẩy, gradient và bộ lọc;
  mép vùng chọn trộn dần thay vì cắt cứng.
- Menu Select ▸ Feather Selection… (Shift+F6) đổi bán kính feather của vùng chọn hiện tại;
  áp dụng có một bước Undo/Redo, nhập 0 px để trả lại biên cứng.
- Feather và anti-alias được giữ khi dịch, scale, xoay/lật vùng chọn và khi đảo vùng chọn;
  thao tác cộng/trừ/giao dùng tuỳ chọn của lần kéo mới nhất.
- Thanh trạng thái hiển thị kích thước và bán kính feather khi kéo chọn.
- Không đổi định dạng `.mps`; vùng chọn vẫn là trạng thái tạm của phiên làm việc.

### Giai đoạn 6 — Lasso, Magic Wand, Quick Selection và Quick Mask (phần 5)
- Công cụ Lasso (L): giữ chuột và rê để vẽ đường bao tự do; thả chuột là chốt vùng chọn,
  Escape huỷ khi đang vẽ. Vùng chọn kín được tạo từ đa giác các điểm đã rê.
- Công cụ Magic Wand (W): nhấp để chọn vùng màu tương tự dựa trên layer đang chọn.
  Options Bar có Dung sai 0..255, "Liền mạch" (chỉ loang các điểm kề nhau) và Feather.
  Tắt "Liền mạch" để chọn mọi điểm ảnh có màu gần giống trên toàn tài liệu.
- Công cụ Quick Selection (Shift+W): kéo cọ trên ảnh để cộng dần vùng có màu tương tự
  quanh đầu cọ; vùng chọn tạm hiện màu xanh mờ trong lúc kéo, thả chuột mới chốt.
- Cả ba công cụ dùng chung quy tắc cộng/trừ/giao: giữ Shift để cộng, Alt để trừ,
  Shift+Alt để giao với vùng chọn hiện có; kích thước và Feather hiện ở thanh trạng thái.
- Lõi chọn nâng cao chạy bằng NumPy: loang theo dòng quét (scanline) và dò biên mask
  thành QPainterPath, nên vẫn dùng được feather, anti-alias, layer mask, crop và Undo.
- Quick Mask (phím Q hoặc menu View ▸ Quick Mask): tô đỏ mờ lên phần **chưa** chọn để
  nhìn rõ biên; bật/tắt không đổi vùng chọn, tự tắt khi không còn vùng chọn.
- Magic Wand và Quick Selection ghi đúng một bước Undo cho mỗi lần nhấp/kéo; Quick
  Selection không tạo lịch sử trong lúc kéo, chỉ ghi khi thả chuột.
- Không đổi định dạng `.mps`; vùng chọn vẫn là trạng thái tạm của phiên làm việc.

### Giai đoạn 6 — Giãn dòng và giãn chữ (phần 6)
- Layer văn bản có thêm hai thuộc tính: **giãn dòng** (0,5..5,0 lần, mặc định 1,0) và
  **giãn chữ** (−200..500 px, mặc định 0).
- Giãn dòng nhân khoảng cách baseline giữa các dòng; dòng đầu và mép trên layer không
  đổi, các dòng sau giãn đều nên dễ đọc hơn với đoạn văn dài.
- Giãn chữ dùng letter spacing tuyệt đối của Qt: số dương giãn rộng, số âm thu hẹp
  khoảng cách giữa các ký tự; độ rộng layer và căn trái/giữa/phải được tính lại đúng.
- Hộp thoại tạo/sửa văn bản có thêm hàng "Giãn dòng / chữ" với ô Dòng (×) và ô Chữ (px);
  xem trước và dòng thông tin kích thước cập nhật ngay khi đổi giá trị.
- Panel Properties hiển thị giãn dòng/giãn chữ khi khác mặc định.
- Sửa giãn dòng/chữ render lại pixel, cập nhật kích thước layer và ghi đúng một bước
  Undo/Redo như các thay đổi văn bản khác.
- Hai thuộc tính được lưu trong metadata `text` của `.mps` v4; dự án cũ không có hai
  khoá này vẫn mở được với giá trị mặc định 1,0× và 0 px.
- Giới hạn an toàn giữ nguyên: 64 MP cho vùng render, 10.000 ký tự và 500 dòng.

### Giai đoạn 6 — Định dạng theo từng đoạn chữ (phần 7)
- Mỗi layer văn bản chứa danh sách **đoạn chữ** (`TextRun`); từng đoạn có font family,
  cỡ chữ (px), màu RGBA, đậm và nghiêng riêng.
- Hộp thoại tạo/sửa văn bản dùng vùng nhập nhiều định dạng: bôi đen một phần chữ rồi
  đổi Font, Cỡ chữ, Đậm, Nghiêng hoặc Màu thì chỉ phần được chọn thay đổi. Không bôi
  đen thì thay đổi áp dụng cho toàn bộ văn bản.
- Di chuyển con trỏ trong vùng nhập sẽ tự đồng bộ Font/Cỡ/Màu/Đậm/Nghiêng theo đoạn
  tại con trỏ, nên biết ngay đoạn đang sửa đang dùng kiểu gì.
- Căn lề, giãn dòng và giãn chữ vẫn là thuộc tính chung của cả layer.
- Bộ render xếp các đoạn trên cùng một baseline; chiều cao dòng lấy theo đoạn cao nhất,
  chiều rộng layer lấy theo tổng bề rộng các đoạn nên trộn cỡ chữ vẫn cân đối.
- Sửa định dạng render lại pixel và ghi đúng một bước Undo/Redo như các thay đổi văn
  bản khác; con trỏ và vùng bôi đen không bị mất khi đổi kiểu.
- `.mps` v4 lưu thêm khoá `runs` trong metadata `text`. Dự án cũ không có `runs` vẫn mở
  được và được hiểu là một đoạn duy nhất với thuộc tính phẳng cũ.
- Panel Layers hiển thị số kiểu chữ (ví dụ "6 kiểu"); panel Properties tóm tắt số đoạn
  và kiểu của đoạn đầu.
- Giới hạn an toàn giữ nguyên: 10.000 ký tự, 500 dòng, cỡ chữ 1..1.000 px và 64 MP
  cho vùng render.

### Giai đoạn 6 — Uốn chữ (phần 8)
- Layer văn bản có thêm **kiểu uốn** và **độ uốn** (−100..100%): Không uốn, Cung tròn,
  Vòm, Phồng, Ép dọc, Lượn sóng, Cờ, Đuôi cá, Dốc và Xoắn.
- Uốn áp dụng cho toàn layer, kể cả văn bản nhiều đoạn với font/cỡ/màu khác nhau.
  Nội dung vẫn sửa được sau khi uốn; không cần rasterize.
- Cách làm: render chữ sạch trước, sau đó biến đổi điểm ảnh bằng phép lấy mẫu ngược
  song tuyến (nhân trước alpha để mép chữ không bị quầng tối), rồi tự cắt viền trong
  suốt để layer gọn đúng nội dung.
- Hộp thoại tạo/sửa văn bản có hàng "Uốn chữ": chọn kiểu và nhập độ uốn. Khi chọn
  kiểu khác "Không uốn" mà độ uốn đang là 0, ứng dụng tự đặt 50% để thấy ngay hiệu ứng;
  ô độ uốn bị mờ khi chọn "Không uốn".
- Xem trước trong hộp thoại và dòng thông tin kích thước cập nhật ngay, ví dụ
  "uốn cung tròn +55%"; panel Layers thêm nhãn "uốn …", panel Properties hiển thị kiểu
  và độ uốn.
- Sửa kiểu/độ uốn render lại pixel, cập nhật kích thước layer và ghi đúng một bước
  Undo/Redo; rasterize, nhân bản, mask và biến đổi pixel hoạt động như văn bản thường.
- `.mps` v4 lưu thêm `warp_style` và `warp_bend` trong metadata `text`; dự án cũ không
  có hai khoá này mở với "Không uốn" và 0%.
- Giới hạn an toàn: ảnh trung gian khi uốn tối đa 24 MP; quá giới hạn sẽ báo lỗi và
  hướng dẫn giảm cỡ chữ, bớt nội dung hoặc giảm độ uốn.

### Giai đoạn 6 — Gõ chữ trên canvas (phần 9)
- Công cụ Text (T) cho phép **gõ trực tiếp trên canvas**: nhấp vào vùng trống để tạo chữ
  mới, nhấp vào layer văn bản có sẵn để sửa ngay tại chỗ, không cần mở hộp thoại.
- Khung soạn thảo trong suốt đặt đúng vị trí và đúng tỉ lệ zoom; trong lúc sửa, layer
  đang chỉnh được ẩn khỏi ảnh nền để không thấy chữ lặp hai lần.
- Nội dung nhiều đoạn vẫn giữ font, cỡ, màu, đậm/nghiêng riêng của từng đoạn, cùng căn
  lề, giãn dòng, giãn chữ và kiểu uốn của layer.
- **Ctrl+Enter** hoặc nhấp ra ngoài để xong (nhấp ra ngoài chỉ ghi nhận thao tác xong,
  không tạo thêm chữ mới); **Esc** để huỷ. Nội dung rỗng tự huỷ, không tạo layer trống.
- Mỗi lần xác nhận ghi đúng một bước Undo/Redo: tạo layer mới nếu trước đó chưa có chữ,
  hoặc cập nhật layer hiện có.
- Layer văn bản đang có mask sẽ không cho sửa trực tiếp; ứng dụng báo cần áp hoặc xoá
  mask trước để tránh ghi đè mask ngoài ý muốn.
- Giới hạn an toàn của văn bản giữ nguyên: 10.000 ký tự, 500 dòng, cỡ chữ 1..1.000 px
  và 64 MP cho vùng render.

### Giai đoạn 6 — Layer điều chỉnh (phần 10)
- Thêm **layer điều chỉnh không phá huỷ** tại menu Layer ▸ New Adjustment Layer:
  Brightness/Contrast, Hue/Saturation, Invert và Desaturate.
- Hiệu ứng áp lên toàn bộ layer nằm bên dưới theo thứ tự chồng layer; layer phía trên
  không bị ảnh hưởng. Ẩn layer điều chỉnh (biểu tượng mắt) sẽ tạm bỏ hiệu ứng.
- Layer điều chỉnh chỉ lưu tham số nên chiếm 1×1 px; **Opacity đóng vai trò độ mạnh
  hiệu ứng** (0% = không đổi, 100% = đầy đủ). Blend mode không áp dụng cho layer này.
- Hộp thoại tạo/sửa có xem trước lấy từ chính ảnh phía dưới. Nhấp đôi layer trong
  panel Layers hoặc chọn Layer ▸ Edit Adjustment… để sửa lại bất cứ lúc nào.
- Mỗi lần tạo/sửa ghi đúng một bước Undo/Redo; tham số được lưu vào lịch sử nên hoàn
  tác khôi phục đúng hiệu ứng cũ.
- Layer điều chỉnh đi theo canvas khi Crop, Canvas Size, Image Size, xoay và lật; không
  bị xoay/lật riêng và không di chuyển bằng công cụ Move.
- Các thao tác phá huỷ bị chặn với thông báo rõ ràng: vẽ cọ/gradient lên pixel, áp bộ
  lọc, xoay/lật layer. Muốn áp vĩnh viễn hãy dùng Merge Down hoặc Flatten Image.
- `.mps` v4 lưu `kind: "adjustment"` kèm tham số; dự án cũ mở bình thường.
- Giới hạn hiện tại: chưa có Curves/Levels riêng cho từng kênh màu; bản tổng hợp ba
  kênh có ở phần 12, tách kênh và histogram ở phần 13.

### Giai đoạn 6 — Mask cho layer điều chỉnh (phần 11)
- Layer điều chỉnh nhận **mask cấp tài liệu**: mask có đúng kích thước canvas và giới
  hạn hiệu ứng theo từng điểm ảnh; trắng = áp đầy đủ, đen = giữ nguyên ảnh gốc, xám =
  áp một phần. Mask nhân với Opacity của layer để thành độ mạnh cuối cùng.
- Tạo mask bằng Layer ▸ Layer Mask ▸ Add Layer Mask: nếu đang có vùng chọn thì mask lấy
  từ vùng chọn, nếu không thì mask trắng toàn canvas. Mỗi lần thêm/xoá mask là một bước
  Undo/Redo; tắt mask (Disable Layer Mask) tạm cho hiệu ứng áp toàn ảnh mà vẫn giữ dữ
  liệu mask.
- Vẽ mask bằng Brush hoặc Gradient với chế độ Paint on Layer Mask; khi vẽ lên mask của
  layer điều chỉnh, toạ độ tính theo tài liệu và vùng chọn hiện có vẫn giới hạn nét vẽ.
- Mask đi theo mọi biến đổi hình học: Crop cắt mask tương ứng, Canvas Size đặt mask vào
  vị trí mới và tô đen vùng mới, Image Size lấy mẫu lại mask, xoay/lật canvas xoay/lật
  mask; Undo/Redo khôi phục cả ảnh lẫn mask.
- Panel Layers hiển thị thumbnail mask riêng của layer điều chỉnh; panel Properties ghi
  rõ mask có/đang tắt. Hộp thoại sửa điều chỉnh xem trước kết quả đã áp cả mask.
- Apply Layer Mask bị chặn với layer điều chỉnh vì layer không có pixel riêng; hãy giữ
  mask, xoá mask hoặc chỉnh tham số. `.mps` lưu mask của layer điều chỉnh và kiểm tra
  kích thước mask phải khớp tài liệu khi mở.

### Giai đoạn 6 — Levels, Curves và Color Balance (phần 12)
- **Levels**: điểm đen/trắng đầu vào (0..255), gamma 0,10..9,99 và điểm đen/trắng đầu ra;
  ánh xạ lại toàn dải sáng, hỗ trợ tăng sáng vùng tối hoặc nén dải động.
- **Curves**: đường cong RGB tổng hợp 2..16 điểm. Nhấp vào lưới để thêm điểm, kéo để
  chỉnh, chuột phải để xoá; nút "Đặt lại đường 45°" trả về đường thẳng. Điểm ngoài hai
  đầu được kẹp theo giá trị đầu mút, nên có thể tạo đường cong cắt (clip) như mong muốn.
- **Color Balance**: ba nhóm thanh trượt cho vùng tối, trung gian và sáng theo ba cặp
  Cyan–Đỏ, Magenta–Xanh lá, Vàng–Xanh dương (−100..100); tuỳ chọn **giữ nguyên độ sáng**
  (luminosity) để đổi màu mà không làm đổi độ sáng tổng thể.
- Cả ba là layer điều chỉnh không phá huỷ: áp lên layer bên dưới, độ mạnh theo Opacity,
  nhận layer mask như phần 11, có Undo/Redo và lưu đầy đủ tham số trong `.mps` v4.
- Hộp thoại có xem trước trực tiếp trên ảnh thật (thu nhỏ) và ghi chú mask nếu layer
  đang có mask; dự án cũ thiếu khoá mới sẽ tự dùng giá trị mặc định (đường 45°, gamma 1,
  cân màu 0) nên mở bình thường.
- Giới hạn: đường cong kênh và histogram có ở phần 13; auto levels và kéo trực tiếp
  điểm đen/trắng trên histogram có ở phần 17.

### Giai đoạn 6 — Curves tách kênh, histogram và eyedropper (phần 13)
- **Curves theo kênh**: chọn RGB (tổng hợp), Đỏ, Xanh lá hoặc Xanh dương trong hộp
  thoại; mỗi kênh có đường cong 2..16 điểm riêng và được lưu độc lập. Khi áp dụng,
  đường cong từng kênh chạy trước, sau đó đường cong RGB tổng hợp chạy trên kết quả.
- Đường cong kênh R/G/B hiển thị đúng màu kênh; nút "Đặt lại đường 45°" chỉ đặt lại kênh
  đang chọn, các kênh khác giữ nguyên.
- **Histogram**: hộp thoại Levels hiển thị histogram độ sáng của ảnh bên dưới layer;
  hộp thoại Curves vẽ histogram của kênh đang chọn làm nền phía sau đường cong. Histogram
  bỏ qua pixel trong suốt hoàn toàn, tính từ ảnh xem trước thu nhỏ nhưng đúng dữ liệu.
- **Eyedropper**: nút "Hút điểm đen" / "Hút điểm trắng" bật chế độ lấy mẫu, sau đó nhấp
  vào ảnh xem trước. Với Levels, mẫu đặt ngay điểm đen/trắng đầu vào (đảm bảo đen <
  trắng). Với Curves, mẫu thêm một điểm (độ sáng vào → 0 hoặc 255) vào kênh đang chọn;
  nhấp lại nút để tắt chế độ.
- Tất cả tham số kênh được lưu trong `.mps` v4; dự án cũ thiếu `curve_red/green/blue`
  mở với đường 45° mặc định. Hộp thoại vẫn xem trước trực tiếp và áp layer mask như
  phần 11–12.
- Giới hạn: histogram lấy từ ảnh xem trước thu nhỏ (không phải toàn ảnh gốc); auto
  levels và kéo trực tiếp điểm đen/trắng trên histogram có ở phần 17.

### Giai đoạn 6 — Layer Group (phần 14)
- **Nhóm layer**: mỗi nhóm là một layer đặc biệt chứa danh sách layer con. Panel Layers
  hiển thị phân cấp với biểu tượng thư mục, thụt lề và đường dẫn nhóm; nhóm lồng nhau
  không giới hạn độ sâu. Nút **New Group** trên panel, menu Layer và phím tắt **Ctrl+G**
  (nhóm layer đang chọn) / **Ctrl+Shift+G** (bỏ nhóm).
- **Compositor theo nhóm**: các layer con được hợp nhất trước, sau đó áp opacity, blend
  mode và layer mask của nhóm lên toàn bộ kết quả như một khối. Nhóm ẩn sẽ ẩn cả cây con;
  nhóm lồng nhau hoạt động đúng thứ tự. Layer điều chỉnh nằm trong nhóm chỉ ảnh hưởng
  các layer cùng nhóm, không tác động layer bên dưới nhóm.
- **Layer mask của nhóm**: mask kích thước bằng tài liệu (trắng = hiện, đen = ẩn toàn
  nhóm), dùng chung Brush/Gradient như mask của layer điều chỉnh; mask tự co giãn khi
  đổi kích thước/xoay canvas.
- **Undo/Redo một bước** cho tạo nhóm, nhóm nhiều layer, bỏ nhóm, nhân bản nhóm và xoá
  nhóm. Nhân bản/xoá nhóm xử lý toàn bộ cây con; bỏ nhóm chỉ bỏ một cấp và đưa layer con
  về nhóm cha. Merge Down bị chặn khi có nhóm hoặc khi hai layer khác nhóm; Apply Mask
  bị chặn với nhóm vì nhóm không có pixel riêng.
- **Panel Properties** của nhóm hiển thị số layer con trực tiếp, opacity, blend, trạng
  thái mask và tên nhóm cha; layer mới tạo khi đang chọn nhóm sẽ tự nằm trong nhóm đó.
- Định dạng `.mps` nâng lên **v5** với khoá `group_id` cho từng layer. File v4 trở về
  trước vẫn mở bình thường (mọi layer là cấp gốc); khi mở, ứng dụng kiểm tra nhóm cha
  phải tồn tại, đúng loại và không tạo vòng lặp.
- Giới hạn: chưa có clipping mask theo nhóm, chưa kéo-thả layer giữa các nhóm, và muốn
  bỏ nhóm đang có layer mask phải xoá mask trước.

### Giai đoạn 6 — Chữ trên đường dẫn và kerning thủ công (phần 15)
- **Kerning cặp thủ công**: ô "Kerning cặp" trong hộp thoại văn bản nhận danh sách dạng
  `AV=-6, To=-3`, mỗi cặp đúng 2 ký tự với giá trị -200..200 px (tối đa 200 cặp).
  Khoảng cách được áp giữa đúng hai ký tự đó, cộng thêm giãn chữ chung; cặp trùng lấy
  giá trị sau, giá trị 0 bị bỏ, dữ liệu được gộp ổn định sau mỗi lần sửa.
- **Chữ trên đường dẫn**: chọn kiểu **Cung tròn**, **Vòng tròn**, **Lượn sóng** hoặc
  **Chữ S** kèm độ cong -100..100%. Mỗi ký tự giữ đúng hướng tiếp tuyến của đường dẫn,
  kể cả khi chữ có nhiều run khác font/màu trong cùng một layer. Đường dẫn thay thế hiệu
  ứng uốn chữ khi được bật; độ cong 0 hoặc kiểu "Không" trả về chữ thường.
- **Bố cục theo ký tự**: khi có kerning hoặc chữ trên đường dẫn, layer được xếp từng
  glyph (font, màu, đậm/nghiêng riêng), sau đó render bằng QPainter với phép xoay quanh
  tâm ký tự; kết quả cắt theo vùng mực in nên layer có kích thước sát nội dung.
- **Xem trước trực tiếp** trong hộp thoại: thông tin layer ước tính hiển thị thêm số cặp
  kerning hoặc kiểu đường dẫn/độ cong; panel Properties tóm tắt hiệu ứng đang dùng và
  vài cặp kerning đầu tiên. Gõ chữ trực tiếp trên canvas giữ nguyên kerning và đường dẫn.
- **Undo/Redo** hoạt động như mọi lần sửa văn bản; kiểu đường dẫn, độ cong và danh sách
  kerning được lưu trong `.mps`, dự án cũ mở với giá trị mặc định (không kerning,
  không đường dẫn).
- Giới hạn: chữ trên đường dẫn trải nội dung theo một dòng (xuống dòng được đổi thành
  khoảng trắng), độ cong tối đa 100%, và chưa hỗ trợ đường dẫn tuỳ ý do người dùng vẽ.

### Giai đoạn 6 — Layer tô và Smart Object (phần 16)
- **Layer tô (Fill layer)**: chọn Layer ▸ New Fill Layer ▸ Solid Color hoặc Gradient.
  Layer tô sinh pixel theo kích thước canvas ở mỗi lần vẽ lại, không lưu mảng lớn, nên
  đổi màu/gradient gần như tức thì và tiết kiệm RAM. Layer tô nhận opacity, blend mode
  và layer mask như layer thường.
- **Hộp thoại Fill** có chọn loại tô, hai màu, kiểu gradient tuyến tính/hình tròn, góc
  0..359° và khung xem trước 320×160 cập nhật trực tiếp. Nhấp đôi layer tô hoặc chọn
  Layer ▸ Edit Fill… để sửa lại; mỗi lần sửa ghi đúng một bước Undo/Redo.
- **Smart Object**: đặt một file ảnh thành layer thông minh bằng Layer ▸ Place as Smart
  Object…; ảnh nguồn được giữ nguyên, layer chỉ render lại từ nguồn với góc xoay
  −180..180°, tỉ lệ 10..800% quanh tâm và lật ngang/dọc. Sửa tham số không làm mất chất
  lượng ảnh gốc; hộp thoại Smart Object có xem trước và nút đặt lại biến đổi.
- **Thay nội dung** giữ nguyên biến đổi: Layer ▸ Replace Contents… chọn ảnh mới cùng
  góc xoay, tỉ lệ và hướng lật đang dùng. Reset Transform trả layer về đúng kích thước
  và hướng ban đầu. Mọi thao tác đều hoàn tác/redo được, kể cả khi đã thay nội dung.
- **Rasterize**: Layer ▸ Rasterize chuyển layer tô hoặc smart object thành layer pixel
  (đã áp cả mask đang bật), sau đó vẽ cọ, áp bộ lọc và biến đổi pixel bình thường.
- **An toàn dữ liệu**: layer tô luôn phủ đúng canvas nên không xoay/lật riêng và không
  di chuyển bằng Move. Với smart object, khi layer đang có mask, các lệnh sửa nội
  dung/biến đổi bị chặn cho tới khi áp hoặc xoá mask để tránh lệch mask.
- **`.mps` nâng lên v6**: lưu tham số tô trong metadata `fill`, tham số smart `smart` và
  ảnh nguồn nén trong `sources/<layer_id>.png`. File v1–v5 vẫn mở bình thường.
- Giới hạn: layer tô luôn phủ đúng kích thước canvas; smart object chưa hỗ trợ perspective
  warp, chưa lồng smart object trong smart object và chưa chỉnh tay nắm vector.

### Giai đoạn 6 — Auto Levels và kéo histogram (phần 17)
- **Auto Levels** trong hộp thoại Levels: nút "Auto Levels" tự tính điểm đen/trắng từ
  histogram độ sáng của ảnh bên dưới layer, cắt bỏ 0,5 % số pixel tối nhất và sáng nhất
  ở mỗi đầu để bỏ qua nhiễu; pixel trong suốt hoàn toàn không được tính.
- Auto Levels chỉ đặt lại hai điểm vào **Điểm đen vào** và **Điểm trắng vào**, giữ
  nguyên gamma và điểm ra; kết quả cập nhật ngay trong xem trước và dòng thông tin ghi
  "Auto Levels đen..trắng". Ảnh phẳng không có dải động được giữ nguyên 0..255.
- **Kéo tay nắm trên histogram**: histogram của Levels có hai tay nắm đen/trắng đặt đúng
  theo giá trị 0..255. Kéo tay nắm (hoặc nhấp vào dải dưới histogram) cập nhật ngay hai
  ô điểm vào, xem trước và layer mask đang áp; tay nắm đen không vượt qua tay nắm trắng
  và ngược lại.
- Hai chiều đồng bộ: kéo slider/ô số hoặc dùng eyedropper thì tay nắm và đường gióng
  trên histogram di chuyển theo; kéo histogram thì slider và ô số cập nhật tương ứng.
- Toàn bộ tham số vẫn là của layer Levels không phá huỷ: mỗi lần áp dụng ghi đúng một
  bước Undo/Redo, lưu trong `.mps` v6 và mở lại đúng điểm đen/trắng đã chỉnh.
- Giới hạn: Auto Levels tính trên ảnh xem trước thu nhỏ và theo độ sáng tổng hợp,
  chưa cân bằng từng kênh R/G/B riêng và chưa cho đổi tỉ lệ cắt trong giao diện.

### Giai đoạn 6 — Xử lý hàng loạt và thư viện preset SQLite (phần 18)
- **Xử lý hàng loạt**: menu Automation ▸ Batch Processing… (Ctrl+Shift+B) mở hộp
  thoại chọn nhiều file ảnh (tối đa 500 file) và thêm cả thư mục.
  Mỗi file được đọc, áp lần lượt danh sách bước rồi xuất sang thư mục đích; ảnh gốc
  không bao giờ bị sửa hay ghi đè trừ khi bạn tự bật "Cho phép ghi đè file đích".
- **Các bước xử lý**: Auto Levels, Auto Contrast, Grayscale, Invert,
  Brightness/Contrast, Hue/Saturation, Levels (đen/trắng/gamma), Gaussian Blur,
  Unsharp Mask, Resize theo % và Resize theo cạnh lớn nhất (không phóng to ảnh nhỏ).
  Mỗi bước có hộp thoại riêng và tham số hợp lệ hoá; đổi thứ tự bằng Lên/Xuống.
- **Action**: lưu chuỗi bước thành action có tên, tải lại, xoá ngay trong hộp thoại
  Batch. Action dùng chung kho preset SQLite nên mở lại lần sau vẫn còn.
- **Định dạng đầu ra**: PNG, JPEG, WebP với chất lượng 1..100 cho JPEG/WebP; hậu tố
  mặc định `_edited`, tên đích tự thêm `(2)`, `(3)` khi đã tồn tại. File đích ghi qua
  file tạm rồi thay thế để không để lại file hỏng khi lỗi giữa chừng.
- **Theo dõi và huỷ**: thanh tiến trình cập nhật theo từng file, dòng trạng thái ghi
  tên file đang xử lý và bảng kết quả liệt kê thành công/lỗi. Nút "Huỷ sau file hiện
  tại" dừng sau khi file đang xử lý xong; các file còn lại được đánh dấu "đã huỷ".
- **Preset SQLite**: hộp thoại sửa layer điều chỉnh có khung "Preset điều chỉnh" cho
  phép lưu tham số hiện tại theo tên, chọn preset để áp lại và xoá preset. Dữ liệu
  nằm trong `presets.sqlite3` cạnh file cấu hình, tách riêng theo loại điều chỉnh
  (Hue/Saturation, Levels, Curves, Color Balance…); ghi đè cùng tên phải xác nhận.
- **An toàn**: batch chạy cục bộ hoàn toàn, không truy cập Internet; mọi file được
  kiểm tra phần mở rộng và giới hạn 80 triệu pixel trước khi xử lý để tránh hết RAM.
  Action/preset chỉ chứa tham số số và chuỗi nên không chạy mã lạ.
- Giới hạn: batch chạy tuần tự trong tiến trình giao diện (giữa các file có xử lý
  sự kiện để cửa sổ phản hồi); huỷ chỉ có hiệu lực sau file đang xử lý; chưa có
  đa luồng, chưa xem trước toàn bộ action trên một ảnh mẫu.

### Giai đoạn 6 — Tile và lazy rendering cho ảnh lớn (phần 19)
- **Compositor theo vùng**: hạt nhân mới `composite_region` chỉ trộn đúng hình chữ nhật
  cần vẽ, xử lý đủ layer pixel (kể cả offset âm), mask, blend mode, layer tô, layer
  điều chỉnh và layer group. `composite_layers` toàn ảnh vẫn chạy theo dải như trước
  nhưng nay gọi chung hạt nhân này nên kết quả hai đường đi luôn khớp nhau.
- **Cache ô 256 × 256**: canvas xem ở mức phóng to ≥ 50% chỉ composite các ô giao với
  khung nhìn và lưu tối đa 96 ô theo LRU (khoảng 24 MB RGBA). Cuộn/pan trong vùng đã
  dựng chỉ vẽ lại từ cache; ô ngoài khung nhìn không bao giờ được composite.
- **Dirty rect**: `Document.invalidate(rect)` ghi nhật ký vùng thay đổi (tối đa 64 mục).
  Thao tác cọ, tẩy và gradient chỉ vô hiệu hoá đúng hình chữ nhật bị sửa, nên lần vẽ
  sau chỉ dựng lại các ô giao với vùng đó thay vì toàn bộ tài liệu.
- **Lazy preview khi thu nhỏ**: khi zoom dưới 50% hoặc số ô cần vẽ vượt sức chứa cache,
  canvas dùng một ảnh tổng hợp thu nhỏ (cạnh dài tối đa 2048 px) tạo một lần cho mỗi
  revision và mức thu nhỏ. Ảnh preview lấy mẫu pixel/mask theo bước và giữ nguyên layer
  điều chỉnh, group, fill; chỉnh sửa bất kỳ đâu sẽ làm mới đúng một lần.
- **Đo hiệu năng thực tế** trên máy 8 GB RAM, tài liệu 17,5 MP với 3 layer: composite
  toàn ảnh 13,8 giây / 70 MB; một ô 256 × 256 chỉ 50,6 ms / 256 KB; đồng bộ dirty rect
  0,02 ms; preview cạnh 1600 mất 832 ms cho ảnh 1250 × 875 / 4,4 MB. Nhờ vậy mở và
  cuộn ảnh lớn không còn phải dựng lại toàn bộ canvas sau mỗi nét vẽ.
- **An toàn bộ nhớ**: cache giới hạn số ô cố định, preview có cạnh tối đa, `memory_estimate`
  cộng cả ảnh preview; không có luồng nền hay dữ liệu gửi ra ngoài.
- Giới hạn: các ô nằm ngoài cache bị dựng lại khi cuộn ngược; preview được tạo lại toàn
  bộ sau mỗi lần sửa; chữ đang gõ trên canvas tạm dùng composite toàn ảnh; chưa có
  composite đa luồng hoặc lưu cache ra đĩa.

## 2. Chạy ứng dụng

### Cách nhanh nhất

Nhấp đúp file `run.bat` trong thư mục `D:\python\myphoto`.

Hoặc mở PowerShell và chạy:

```powershell
cd D:\python\myphoto
.\.venv310qt5\Scripts\python.exe main.py
```

Có thể mở kèm file ngay khi khởi động:

```powershell
.\.venv310qt5\Scripts\python.exe main.py "D:\anh\photo.jpg"
```

### Cài đặt lần đầu (nếu chưa có thư mục .venv310qt5)

Máy hiện tại dùng Python 3.10 do `uv` quản lý. Trong PowerShell:

```powershell
cd D:\python\myphoto
uv venv --python 3.10 .venv310qt5
uv pip install --python .venv310qt5\Scripts\python.exe -r requirements.txt
```

Nếu PowerShell báo không tìm thấy `uv`, dùng đường dẫn đầy đủ:

```powershell
& "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts\uv.exe" venv --python 3.10 .venv310qt5
& "$env:LOCALAPPDATA\Programs\Python\Python313\Scripts\uv.exe" pip install --python .venv310qt5\Scripts\python.exe -r requirements.txt
```

### Vì sao dùng PySide2/Qt 5.15?

Máy này chạy Windows 10 build 10240. Plugin cửa sổ của Qt 6 cần các hàm hệ thống chỉ có
từ Windows 10 build 14393 trở lên, nên Qt 6 không mở được cửa sổ native trên máy.
Qt 5.15 chạy bình thường. Mã nguồn có lớp `compat/qt.py` tự chọn:

- Windows cũ + có PySide2: dùng PySide2.
- Windows mới hoặc không có PySide2: dùng PySide6.

Trên Windows 10 1607+/Windows 11 dùng Python 3.11+, có thể cài bộ mới:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements-modern.txt
.\.venv\Scripts\python.exe main.py
```

## 3. Phím tắt và thao tác

| Thao tác | Cách dùng |
| --- | --- |
| Tạo tài liệu | Ctrl+N |
| Mở file | Ctrl+O |
| Lưu dự án | Ctrl+S |
| Lưu thành dự án mới | Ctrl+Shift+S |
| Xuất ảnh | Ctrl+Alt+S |
| Đóng tài liệu | Ctrl+W |
| Undo / Redo | Ctrl+Z / Ctrl+Shift+Z (hoặc Ctrl+Y) |
| Chọn toàn bộ / Bỏ chọn | Ctrl+A / Ctrl+D |
| Đảo vùng chọn | Ctrl+Shift+I |
| Feather vùng chọn | Shift+F6, hoặc ô Feather trên Options Bar |
| Lasso / Magic Wand / Quick Selection | L / W / Shift+W khi canvas đang focus |
| Quick Mask | Q khi canvas đang focus (cần có vùng chọn), hoặc menu View ▸ Quick Mask |
| Cộng / trừ / giao vùng chọn | Shift / Alt / Shift+Alt khi kéo |
| Tạo crop và áp dụng | C, kéo vùng giữ lại, Enter (Esc để huỷ) |
| Crop theo vùng chọn | Menu Image ▸ Crop to Selection |
| Image Size / Canvas Size | Ctrl+Alt+I / Ctrl+Alt+C |
| Xoay canvas 90° / 180° | Menu Image ▸ Image Rotation |
| Xoay canvas tự do | Menu Image ▸ Image Rotation ▸ Arbitrary Rotation… |
| Lật canvas | Menu Image ▸ Flip Canvas Horizontal/Vertical |
| Xoay/lật layer đang chọn | Menu Edit ▸ Transform |
| Xoay layer tự do | Menu Edit ▸ Transform ▸ Rotate… |
| Layer mới | Ctrl+Shift+N |
| Nhóm layer đang chọn / Bỏ nhóm | Ctrl+G / Ctrl+Shift+G |
| Tạo layer văn bản | Ctrl+Shift+T |
| Giãn dòng / giãn chữ | Trong hộp thoại Text, hàng "Giãn dòng / chữ" |
| Định dạng theo đoạn chữ | Trong hộp thoại Text: bôi đen đoạn rồi đổi Font/Cỡ/Màu/Đậm/Nghiêng |
| Vẽ hình khối | Công cụ Shape (U), kéo trên canvas, Shift để vuông/tròn |
| Tạo/sửa/rasterize hình khối | Menu Layer ▸ Shape |
| Layer tô màu/gradient | Menu Layer ▸ New Fill Layer, sửa bằng Layer ▸ Edit Fill… |
| Đặt ảnh làm smart object | Menu Layer ▸ Place as Smart Object… |
| Sửa/thay nội dung/reset smart object | Menu Layer ▸ Edit Smart Object… / Replace Contents… / Reset Transform |
| Rasterize layer tô hoặc smart object | Menu Layer ▸ Rasterize |
| Vẽ / tẩy | Công cụ Brush (B) / Eraser (Shift+E), kéo trên canvas |
| Gradient | Công cụ Gradient (G), kéo từ điểm đầu tới điểm cuối |
| Vẽ lên layer mask | Menu Layer ▸ Layer Mask ▸ Paint on Layer Mask hoặc combo "Vẽ lên"/"Tô lên" |
| Gõ/sửa chữ trực tiếp trên canvas | Công cụ Text (T), nhấp lên canvas hoặc lên layer chữ; Ctrl+Enter xong, Esc huỷ |
| Sửa văn bản trong hộp thoại / Rasterize | Menu Type ▸ Edit Text… / Rasterize Text |
| Hue/Saturation | Ctrl+U |
| Invert / Desaturate | Ctrl+I / Ctrl+Shift+U |
| Brightness/Contrast, Auto Contrast | Menu Filter ▸ Adjustments |
| Tạo layer điều chỉnh | Menu Layer ▸ New Adjustment Layer |
| Sửa layer điều chỉnh | Nhấp đôi layer trong panel Layers, hoặc Layer ▸ Edit Adjustment… |
| Levels / Curves / Color Balance | Menu Layer ▸ New Adjustment Layer |
| Auto Levels / kéo điểm đen/trắng | Trong hộp thoại Levels: nút Auto Levels và tay nắm trên histogram |
| Lưu/áp/xoá preset điều chỉnh | Khung "Preset điều chỉnh" trong hộp thoại sửa layer điều chỉnh |
| Xử lý hàng loạt | Menu Automation ▸ Batch Processing… (Ctrl+Shift+B) |
| Mask cho layer điều chỉnh | Menu Layer ▸ Layer Mask ▸ Add Layer Mask (mask theo kích thước canvas) |
| Gaussian Blur / Unsharp Mask | Menu Filter ▸ Blur / Sharpen |
| Nhân bản layer | Ctrl+J |
| Đổi tên layer | F2 |
| Merge Down / Flatten | Ctrl+E / Ctrl+Shift+E |
| Zoom In / Out | Ctrl+= / Ctrl+- |
| Fit on Screen / 100% | Ctrl+0 / Ctrl+1 |
| Chuyển tài liệu | Ctrl+Tab / Ctrl+Shift+Tab |
| Di chuyển khung nhìn | Giữ Space và kéo, hoặc kéo bằng chuột giữa |
| Zoom tại con trỏ | Lăn chuột |
| Pan ngang | Shift + lăn chuột |
| Công cụ Move / Rect / Ellipse / Lasso / Wand / Quick Select / Crop / Text / Shape / Brush / Gradient / Eraser / Hand / Zoom | V / M / E / L / W / Shift+W / C / T / U / B / G / Shift+E / H / Z khi canvas đang focus |

Gõ văn bản trong ô nhập sẽ không bị các phím tắt một chữ cái cướp mất.

## 4. Kiểm thử

Chạy toàn bộ kiểm thử (chế độ offscreen, không mở cửa sổ):

```powershell
cd D:\python\myphoto
.\.venv310qt5\Scripts\python.exe -m pytest -q
```

Kết quả đã kiểm tra:

- PySide2 5.15.2.1: **519 passed**
- PySide6 6.3.2 (offscreen): **519 passed**

Tạo lại ảnh xem trước giao diện:

```powershell
.\.venv310qt5\Scripts\python.exe tools\preview_screenshots.py
```

Ảnh được ghi vào `artifacts/`:

- `phase1_dark.png`, `phase1_light.png` — giao diện tổng thể.
- `phase2_selection.png` — vùng chọn ellipse và thumbnail mask.
- `phase2_crop.png` — overlay crop.
- `phase2_image_size.png`, `phase2_canvas_size.png` — hộp thoại kích thước.
- `phase3_transform.png` — canvas xoay dọc, mũi tên xoay xuống, thẻ chữ được xoay
  riêng về đứng.
- `phase3_free_rotate.png` — canvas xoay tự do 12° với vùng trong suốt, thẻ chữ xoay
  riêng -6°.
- `phase4_text.png` — layer văn bản với nhiều kiểu chữ, màu và căn lề trong panel Layers.
- `phase4_text_dialog.png` — hộp thoại sửa văn bản kèm xem trước trực tiếp.
- `phase5_filters.png` — so sánh ảnh trước/sau khi áp dụng Hue/Saturation cho layer.
- `phase5_blur_dialog.png` — hộp thoại Gaussian Blur với xem trước thu nhỏ.
- `phase6_shapes.png` — cụm layer hình khối, Options Bar của công cụ Shape và panel
  Properties hiển thị thuộc tính hình.
- `phase6_shape_dialog.png` — hộp thoại sửa hình khối bo góc kèm xem trước.
- `phase6_brush.png` — nét cọ nhiều màu, vùng mask được vẽ mềm và Options Bar của công
  cụ Brush đang chọn chế độ vẽ lên Layer Mask.
- `phase6_gradient.png` — gradient bầu trời, quầng nắng hình tròn và mask được tô
  gradient, Options Bar của công cụ Gradient.
- `phase6_feather.png` — vùng chọn ellipse feather 40 px tạo layer mask mép mềm,
  Options Bar hiển thị Feather và Anti-alias.
- `phase6_select_tools.png` — Magic Wand chọn vùng trời với Feather 8 px, Quick Mask
  tô đỏ phần chưa chọn và Options Bar của công cụ Magic Wand.
- `phase6_rich_text.png` — hai khối văn bản so sánh giãn dòng 1,0× và 1,6× kèm giãn chữ
  +5 px, panel Properties hiển thị thuộc tính layer đang chọn.
- `phase6_rich_text_dialog.png` — hộp thoại sửa văn bản với ô Giãn dòng / chữ và xem
  trước cập nhật trực tiếp.
- `phase6_rich_runs.png` — tiêu đề và đoạn văn trộn nhiều font/cỡ/màu trong cùng một
  layer; panel Layers hiển thị số kiểu chữ của từng layer.
- `phase6_rich_runs_dialog.png` — hộp thoại sửa văn bản nhiều kiểu, đoạn "giãn dòng
  1,4×" đang được bôi đen và điều khiển đã đồng bộ theo đoạn đó.
- `phase6_text_warp.png` — một tài liệu có 5 layer văn bản uốn theo cung tròn, lượn
  sóng, vòm, xoắn và phồng; panel Layers hiển thị nhãn kiểu uốn.
- `phase6_text_warp_dialog.png` — hộp thoại sửa văn bản với hàng Uốn chữ (Cung tròn,
  độ uốn 75%) và khung xem trước cong theo đúng lựa chọn.
- `phase6_canvas_text.png` — khung soạn thảo trong suốt có viền nét đứt đang gõ chữ
  trực tiếp trên canvas, layer đang sửa được ẩn khỏi nền.
- `phase6_canvas_text_result.png` — sau Ctrl+Enter, chữ trở thành layer văn bản mới,
  panel Layers và Properties cập nhật theo layer đó.
- `phase6_adjustment_layers.png` — hai layer điều chỉnh Hue/Saturation và
  Brightness/Contrast áp lên ảnh phía dưới; thumbnail "fx" và panel Properties
  hiển thị tham số.
- `phase6_adjustment_dialog.png` — hộp thoại sửa Hue/Saturation với ba thanh trượt và
  xem trước lấy từ ảnh thật bên dưới.
- `phase6_adjustment_mask.png` — layer điều chỉnh Hue/Saturation có mask gradient
  đen → trắng: bên trái giữ ảnh gốc, bên phải áp đầy đủ hiệu ứng; panel Layers có
  thumbnail mask và Options Bar đang bật Paint on Layer Mask.
- `phase6_adjustment_mask_dialog.png` — hộp thoại sửa điều chỉnh xem trước kết quả đã
  nhân với layer mask.
- `phase6_advanced_adjustments.png` — ba layer điều chỉnh Levels, Curves và Color
  Balance xếp trên ảnh gốc, panel Properties tóm tắt tham số cân màu.
- `phase6_levels_dialog.png` — hộp thoại Levels với điểm đen/trắng vào, gamma, điểm
  đen/trắng ra và xem trước trực tiếp.
- `phase6_curves_dialog.png` — hộp thoại Curves với đường cong bốn điểm kéo được, lưới
  và nút đặt lại đường 45°.
- `phase6_curves_red_channel.png` — hộp thoại Curves chọn kênh Đỏ, histogram làm nền
  và đường cong riêng của kênh.
- `phase6_color_balance_dialog.png` — hộp thoại Color Balance ba nhóm vùng tối/trung
  gian/sáng, tuỳ chọn giữ nguyên độ sáng và xem trước.
- `phase6_layer_groups.png` — nhóm "Bố cục" lồng "Tông màu" và "Huy hiệu"; panel Layers
  thụt lề theo cấp, thumbnail thư mục và Properties tóm tắt nhóm đang chọn.
- `phase6_text_path.png` — poster với tiêu đề cung tròn, dòng lượn sóng, chữ S, nhãn
  vòng tròn khép kín và dòng "AVATAR WAVE" dùng kerning cặp thủ công.
- `phase6_text_path_dialog.png` — hộp thoại văn bản của nhãn vòng tròn: ô Kerning cặp,
  kiểu chữ trên đường dẫn "Vòng tròn", độ cong 100% và xem trước trực tiếp.
- `phase6_fill_smart.png` — tài liệu có layer tô gradient làm nền và smart object xoay
  7°, thu nhỏ 88% cùng lớp tô màu phủ lên; panel Layers hiển thị nhãn loại layer và
  Properties tóm tắt biến đổi không phá huỷ.
- `phase6_fill_dialog.png` — hộp thoại Fill chọn tô gradient, hai màu, góc 32° và xem
  trước trực tiếp.
- `phase6_smart_object_dialog.png` — hộp thoại Smart Object với góc xoay, tỉ lệ, lật
  ngang/dọc và xem trước ảnh nguồn đã biến đổi.
- `phase6_levels_auto.png` — hộp thoại Levels sau khi bấm Auto Levels: hai tay nắm
  đen/trắng kéo được trên histogram, giá trị 20..228 và xem trước trực tiếp.
- `phase6_batch_dialog.png` — hộp thoại Batch Processing với 3 file đầu vào, action
  "Ảnh web 1600px", thanh tiến trình 3/3 và trạng thái "Hoàn tất: 3 thành công".
- `phase6_preset_library.png` — hộp thoại Levels với khung preset SQLite: preset
  "Ấm hoàng hôn" (đen 18, trắng 238, gamma 1,15) đã được chọn và áp vào xem trước.
- `phase6_tiles.png` — tài liệu 3600 × 2400 xem ở 100%: canvas chỉ dựng các ô
  256 × 256 giao với khung nhìn, ảnh phụ nằm ngoài khung nhìn không được composite.

## 5. Cấu trúc thư mục

```text
myphoto/
├── main.py                     # điểm khởi chạy
├── run.bat                     # chạy nhanh trên Windows
├── requirements.txt            # bộ thư viện cho Windows 10 build cũ
├── requirements-modern.txt     # bộ thư viện cho Windows mới
├── conftest.py                 # cấu hình pytest + Qt offscreen
├── compat/qt.py                # tự chọn PySide2 hoặc PySide6
├── config/settings.py          # hằng số, đường dẫn, lưu cấu hình JSON
├── core/
│   ├── layer.py                # Layer, LayerManager, 15 blend mode, mask
│   ├── canvas.py               # compositor NumPy, QImage, downsample
│   ├── document.py             # tài liệu, lịch sử, selection, mask, crop, resize, xoay/lật
│   ├── selection.py            # QPainterPath, boolean combine, rasterize, transform
│   ├── wand.py                 # lõi chọn nâng cao: color distance, flood fill, mask → path
│   ├── text_layer.py           # TextProperties, layout và render văn bản bằng QPainter
│   ├── shape_layer.py          # ShapeProperties và render hình khối bằng QPainter
│   ├── paint.py                # lõi cọ: BrushSettings, stamp và BrushStrokeSession
│   ├── gradient.py             # lõi gradient: ramp tuyến tính/hình tròn, GradientSession
│   ├── filters.py              # bộ lọc NumPy: điểm ảnh, HSL, Gaussian blur, unsharp
│   ├── histogram.py            # histogram độ sáng và từng kênh R/G/B cho hộp thoại
│   ├── batch.py                # batch step/action, BatchRunner xuất ảnh an toàn
│   ├── presets.py              # thư viện preset/action SQLite (PresetStore)
│   ├── tiles.py                # cache ô 256 × 256 LRU và đồng bộ dirty rect
│   ├── command_manager.py      # Command Pattern (layer, mask, geometry, transform)
│   ├── history_manager.py      # Undo/Redo stack
│   └── color_manager.py        # màu foreground/background
├── formats/
│   ├── import_manager.py       # đọc ảnh bằng Pillow
│   ├── export_manager.py       # xuất ảnh
│   └── native_project.py       # định dạng .mps v6
├── tools/                      # Move, chọn, Crop, Text, Shape, Brush, Eraser, Gradient, Hand, Zoom
├── ui/                         # main window, canvas, panels, theme, icons, dialogs
├── assets/themes/              # dark.qss, light.qss
├── tests/                      # 519 bài kiểm thử
└── artifacts/                  # ảnh xem trước giao diện
```

## 6. Chưa làm (sẽ làm ở các giai đoạn sau)

Các mục dưới đây **chưa được triển khai**, không có nút giả:

- Chỉnh vector bằng tay nắm/đường dẫn.
- Xem mask như một kênh riêng (Channels) và lưu vùng chọn vào file dự án.
- Rich text nâng cao còn lại: đường dẫn tuỳ ý do người dùng vẽ (đã có cung tròn,
  vòng tròn, lượn sóng, chữ S và kerning cặp).
- Bộ lọc nâng cao: blur theo hướng/chuyển động, radial blur, noise, vignette,
  lens correction và bộ lọc tuỳ biến.
- Hiệu ứng layer (glow, drop shadow, bevel), smart filter không phá huỷ.
- Tách nền/loại bỏ vật thể bằng AI; nếu triển khai sẽ ưu tiên xử lý offline, có công
  tắc bật/tắt và hiển thị tiến trình.
- Plugin hệ thống và script tuỳ biến (ứng dụng luôn từ chối chạy mã lạ).
- Nhập/xuất PSD, kéo thả file vào cửa sổ.

Mục nào chưa làm được để mờ, không bấm được; không có nút giả hoặc nút chỉ hiện
thông báo mà không xử lý.

## 7. Lộ trình

| Giai đoạn | Nội dung |
| --- | --- |
| 1 | Core Application: tài liệu, layer pixel, lịch sử, canvas, lưu/mở/xuất (đã xong) |
| 2 | Vùng chọn chữ nhật/ellipse, layer mask, crop, Image Size, Canvas Size (đã xong) |
| 3 | Xoay/lật canvas và layer, gồm xoay tự do (đã xong) |
| 4 | Layer văn bản (đã xong) |
| 5 | Bộ lọc cơ bản: brightness/contrast, hue/saturation, auto contrast, invert, desaturate, Gaussian blur, unsharp mask (đã xong); tiếp theo: hiệu ứng nâng cao, tách nền |
| 6 | Shape/vector cơ bản, Brush/Eraser, Gradient, feather/anti-alias, Lasso/Magic Wand/Quick Selection, Quick Mask, giãn dòng/giãn chữ, định dạng font/cỡ/màu theo từng đoạn chữ, uốn chữ, gõ chữ trực tiếp trên canvas, layer điều chỉnh không phá huỷ, mask cho layer điều chỉnh, Levels/Curves/Color Balance, Curves tách kênh + histogram + eyedropper, layer group, chữ trên đường dẫn + kerning cặp, layer fill + smart object, Auto Levels + kéo điểm đen/trắng trên histogram, automation batch/action + thư viện preset SQLite, tối ưu hiệu năng tile/lazy loading cho ảnh lớn (đã xong) |
| 7 | Kiểm thử toàn diện, đóng gói và phát hành |

## 8. Quyền riêng tư và an toàn dữ liệu

- Không tự động truy cập Internet, không gửi ảnh hay dữ liệu người dùng ra ngoài.
- Không ghi đè file gốc khi lưu dự án; file `.mps` được ghi an toàn qua file tạm.
- Kiểm tra định dạng, kích thước và cấu trúc dự án trước khi mở.
- Cảnh báo khi đóng tài liệu còn thay đổi chưa lưu.
