import fitz
import os

pdf_path = r"D:/BaiduSyncdisk/赛博英雄传/投研罗盘/outputs/project_one_pager.pdf"
out_dir = r"D:/BaiduSyncdisk/赛博英雄传/投研罗盘/outputs"

doc = fitz.open(pdf_path)
print(f"页数: {len(doc)}")
for i, page in enumerate(doc):
    rect = page.rect
    print(f"第{i+1}页尺寸: {rect.width:.1f} x {rect.height:.1f} pt")
    # 高清渲染
    mat = fitz.Matrix(2.5, 2.5)
    pix = page.get_pixmap(matrix=mat)
    out_path = os.path.join(out_dir, f"_preview_page_{i+1}.png")
    pix.save(out_path)
    print(f"已保存: {out_path}  ({pix.width}x{pix.height})")
doc.close()
