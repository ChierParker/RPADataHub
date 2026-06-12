import os
from datetime import datetime, timedelta
import shutil


final_path = r"C:\iecom\RPAdataCollector\data"

def get_app_name() -> str:
    """
    获取应用名称
    main.py 所在的文件夹名称，即为应用名称
    :return:
    """

    # 1) 计算 main.py 的绝对路径
    path_main_py = get_path("main.py")

    # 2) 计算所在文件夹的名称，即为应用名称
    app_name = path_main_py.parent.name

    return app_name



def get_app_data_final_dir(process_name):
    """
    判断本机是否有icem路径
    
    :param process_name: 流程名称
    """
    date_folder_name = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(final_path):
        file_dir = os.path.join(final_path,process_name,date_folder_name)
        if not os.path.exists(file_dir):
            os.mkdir(file_dir)
        return file_dir
    return False



def get_app_data_file(*dir_file_names: str):
    """
    获取应用数据目录下的文件路径，支持多级文件夹
    
    Args:
        *dir_file_names: 可变参数，最后一个参数是文件名，前面的都是文件夹名
                        例如: get_app_data_dir_file("config.json")
                             get_app_data_dir_file("logs", "app.log")
                             get_app_data_dir_file("data", "cache", "temp.txt")
    
    Returns:
        str: 完整的文件路径
    """
    if not dir_file_names:
        raise ValueError("至少需要提供一个文件名参数")
    
    # 分离目录名和文件名
    *dir_names, file_name = dir_file_names
    
    # 获取目录路径（自动创建多级目录）
    dir_path = get_app_data_dir(*dir_names)
    
    # 拼接文件路径
    return os.path.join(dir_path, file_name)

def get_app_data_dir(*dir_names: str):
    """
    获取应用的数据目录，支持多级文件夹

    Args:
        *dir_names: 可变参数，支持多级目录路径
                   例如: get_app_data_dir("logs", "2024", "01")
                        get_app_data_dir("config")
                        get_app_data_dir()

    注意:
    1) 应用数据存档在: 用户目录下的 Documents/Robots/<app_name> 目录下,
    例如 D:/Users/liaohai1/Documents/Robots/<app_name>;
    """

    # 获取用户数据目录
    user_data_dir = os.path.expanduser("~")

    # 获取基础数据目录
    _app_data_dir = os.path.join(
        user_data_dir, "Documents", "Robots", get_app_name()
    )
    
    # 如果有子目录参数，则拼接多级路径
    if dir_names:
        _app_data_dir = os.path.join(_app_data_dir, *dir_names)

    # 检查并创建目录（os.makedirs 默认支持创建多级目录）
    if not os.path.exists(_app_data_dir):
        os.makedirs(_app_data_dir, exist_ok=True)

    return _app_data_dir



def get_clean_path(file_name):
    """
    此函数接收一个文件名作为输入，并返回清理过的文件名。
    它会移除任何在文件名中不合法的字符。

    参数:
    file_name (str): 需要被清理的原始文件名。

    返回:
    str: 所有不合法字符被替换为下划线的清理过的文件名。
    """
    # 遍历在文件名中不合法的字符字符串中的每个字符
    for c in r'\/:*?"<>|':
        # 用下划线替换每个不合法的字符
        file_name = file_name.replace(c, "_")
    # 返回清理过的文件名
    return file_name


def get_user_directory():
    """获取用户目录"""
    return os.path.expanduser("~")


def get_path(filename):
    """
    获取相相对于 main.py 的文件路径
    :param filename:
    :return:
    """
    import os
    from pathlib import Path

    # 判断是否为绝对路径
    if os.path.isabs(filename):
        return Path(filename)

    # 如果不是绝对路径，则获取相对于 main.py 的文件路径
    # 获取 main.py 文件路径
    main_file_path = Path(__file__).parent.parent / "main.py"

    # 检查 main.py 文件是否存在
    if not os.path.exists(main_file_path):
        raise FileNotFoundError("main.py 文件不存在, 请检查路径是否正确。")

    # 计算文件路径
    _path = main_file_path.parent / filename

    # 确保文件夹存在
    _path.parent.mkdir(parents=True, exist_ok=True)

    return _path


def move_file(file_path, final_folder, in_country, recollect, search_method):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    filename = os.path.basename(file_path)
    backup_filename = f"{in_country}{recollect}_{search_method}_completed_{timestamp}.csv"
    backup_path = os.path.join(final_folder, filename)
    if os.path.exists(backup_path):
        backup_path = os.path.join(final_folder, backup_filename)
    # 移动完成的文件到备份文件夹
    shutil.copy(file_path, backup_path)
    # print(f"已完成的关键词文件已移动到: {backup_path}")
    return backup_path

if __name__ == "__main__":
    print(get_app_data_dir())
    print(get_app_data_dir_file('aaa.xxx','test','sss'))
    print(get_app_data_dir('test','20251114'))
