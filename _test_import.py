import sys, os
sys.path.insert(0, "src/rpa")
sys.path.insert(0, "src")

try:
    from rpa.blueprint import create_rpa_data_hub_blueprint
    print("✅ blueprint 导入成功")
    bp = create_rpa_data_hub_blueprint()
    print("✅ create蓝图成功")

    # 检查 tasks_page 路由
    for rule in bp.deferred_functions:
        print(f"  路由: {rule}")
    print(f"\n端点列表: {[r for r in dir(bp)]}")
except Exception as e:
    print(f"❌ 失败: {e}")
    import traceback
    traceback.print_exc()
