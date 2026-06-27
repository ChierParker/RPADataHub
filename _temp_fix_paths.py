import pathlib

target = pathlib.Path(r"c:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor\tests\test_collectors.py")
content = target.read_text(encoding="utf-8-sig")
content = content.replace(
    r"C:\Users\JackPeesao\Desktop\EcomIQ\CompetitorWatch",
    r"C:\Users\JackPeesao\Desktop\EcomIQ-RPA\src\competitor"
)
target.write_text(content, encoding="utf-8")
print("Done: test_collectors.py updated")
