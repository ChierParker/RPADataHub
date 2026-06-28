"""验证新创建的共享模块语法正确"""
import ast
import sys

modules = [
    "src/rpa/core/shared.py",
    "src/rpa/core/logger.py",
    "src/rpa/core/validators.py",
]

ok = True
for mod in modules:
    try:
        with open(mod, encoding="utf-8") as f:
            ast.parse(f.read())
        print(f"  ✅ {mod} — 语法正确")
    except SyntaxError as e:
        print(f"  ❌ {mod} — 语法错误: {e}")
        ok = False

if ok:
    print("\n所有模块验证通过！")
else:
    print("\n存在语法错误，请检查！")
    sys.exit(1)
