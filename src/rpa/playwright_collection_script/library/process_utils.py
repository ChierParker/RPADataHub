import functools
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from traceback import format_exc

import pandas as pd
import psutil

from library.logger import logger
from library.utils import get_app_name, get_path


def write_df_to_json(df: pd.DataFrame, file_path: Path):
    """
    将 DataFrame 写入到 JSON 列表文件。

    :param df: DataFrame
    :type df: pd.DataFrame
    :param file_path: JSON 文件的路径
    :type file_path: Path
    """
    Path(file_path.parent).mkdir(parents=True, exist_ok=True)
    # 使用 orient="records" 来表示DataFrame的每一行作为一个记录，整个DataFrame作为一个列表
    # 去掉 lines=True，以确保整个DataFrame被写为一个JSON数组
    df.to_json(file_path, force_ascii=False, orient="records", indent=4)
    # logger.info(f"写入了 {df.shape[0]} 行数据到文件<{file_path.name}>")


def print_process_info(pid: int):
    """
    根据进程ID打印进程信息。
    """
    try:
        # 根据PID创建Process对象
        proc = psutil.Process(pid)

        # 获取进程信息
        name = proc.name()  # 进程名
        exe = proc.exe()  # 进程的执行路径
        cwd = proc.cwd()  # 当前工作目录
        cmdline = proc.cmdline()  # 命令行参数列表
        ppid = proc.ppid()  # 父进程ID
        status = proc.status()  # 进程状态

        # 使用logger.info输出进程信息
        logger.info(f"Process ID: {pid}")
        logger.info(f"Name: {name}")
        logger.info(f"Executable Path: {exe}")
        logger.info(f"Current Working Directory: {cwd}")
        logger.info(f"Command Line Arguments: {cmdline}")
        logger.info(f"Parent Process ID: {ppid}")
        logger.info(f"Status: {status}")

    except psutil.NoSuchProcess:
        logger.info(f"No process found with PID: {pid}")
    except psutil.AccessDenied:
        logger.info(f"Access denied to process with PID: {pid}")
    except Exception as e:
        logger.info(f"An error occurred: {e}")


def get_process_list_by_cmdline_ex(keyword: str) -> pd.DataFrame:
    """
    遍历所有进程，找到包含指定关键字的进程，并返回一个包含进程信息的DataFrame。

    包含的信息有：PID、命令行、名称、用户名、创建时间、CPU时间等。
    如果没有找到符合条件的进程，则返回None。

    参数:
        keyword (str): 要在进程命令行中搜索的关键字。

    返回:
        pd.DataFrame 或 None: 包含匹配进程信息的DataFrame，如果没有匹配的进程则返回None。
    """
    process_list = []
    for proc in psutil.process_iter(attrs=['pid', 'cmdline', 'name', 'username', 'create_time', 'cpu_times']):
        try:
            # 跳过没有cmdline属性的进程
            if proc.info.get('cmdline', []) is None:
                continue

            # 将命令行参数列表转换为字符串
            cmdline_str = ' '.join(proc.info.get('cmdline', []))

            # 检查命令行字符串是否包含关键字
            if keyword in cmdline_str:
                try:
                    cwd = proc.cwd()
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    cwd = "N/A"

                create_time = datetime.fromtimestamp(
                    proc.info['create_time']).strftime('%Y-%m-%d %H:%M:%S') if proc.info.get('create_time') else "N/A"

                cpu_times = proc.info.get('cpu_times')
                cpu_time_user = cpu_times.user if cpu_times else "N/A"
                cpu_time_system = cpu_times.system if cpu_times else "N/A"

                process_item = {
                    "pid": proc.info['pid'],
                    "cmdline": cmdline_str,
                    "name": proc.info.get('name'),
                    "cwd": cwd,
                    "user": proc.info.get('username', "N/A"),
                    "create_time": create_time,
                    "cpu_time_user": cpu_time_user,
                    "cpu_time_system": cpu_time_system,
                }
                process_list.append(process_item)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # 转换process_list为DataFrame
    if process_list:
        df_process = pd.DataFrame(process_list)
        return df_process

    return None


def get_all_processes(file_path: Path = None) -> pd.DataFrame:
    """
    遍历所有进程，并返回一个包含进程信息的DataFrame。

    包含的信息有：PID、命令行、名称、用户名、创建时间、CPU时间等。
    如果没有找到任何进程，则返回None。

    返回:
        pd.DataFrame 或 None: 包含所有进程信息的DataFrame，如果没有进程则返回None。
    """
    process_list = []
    for proc in psutil.process_iter(attrs=['pid', 'cmdline', 'name', 'username', 'create_time', 'cpu_times']):
        try:
            # 尝试获取进程的当前工作目录
            try:
                cwd = proc.cwd()
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                cwd = "N/A"

            # 格式化创建时间
            create_time = datetime.fromtimestamp(
                proc.info['create_time']).strftime('%Y-%m-%d %H:%M:%S') if proc.info.get('create_time') else "N/A"

            # 获取CPU时间信息，如果可能的话
            cpu_times = proc.info.get('cpu_times')
            cpu_time_user = cpu_times.user if cpu_times else "N/A"
            cpu_time_system = cpu_times.system if cpu_times else "N/A"

            if proc.info.get('cmdline', []) is None:
                cmdline_str = "N/A"
            else:
                # 将命令行参数列表转换为字符串
                cmdline_str = ' '.join(proc.info.get('cmdline', []))

            process_item = {
                "pid": proc.info['pid'],
                "cmdline": cmdline_str,
                "name": proc.info.get('name'),
                "cwd": cwd,
                "user": proc.info.get('username', "N/A"),
                "create_time": create_time,
                "cpu_time_user": cpu_time_user,
                "cpu_time_system": cpu_time_system,
            }
            process_list.append(process_item)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    # 转换process_list为DataFrame
    if process_list:
        df_process = pd.DataFrame(process_list)

        # 如果传入了文件路径，则将DataFrame写入到JSON文件
        if file_path:
            write_df_to_json(df_process, file_path)

        return df_process

    return None


def terminate_process_by_names(names: list):
    """
    根据一组进程名结束匹配的进程。

    参数:
        names (list): 要结束的进程名列表。
    """
    logger.info(f"Terminating processes with names: {names}")
    for proc in psutil.process_iter(attrs=['pid', 'name']):
        proc_name = proc.info['name']  # 获取当前进程的名称
        try:
            # 检查当前进程的名称是否在目标列表中
            if proc_name in names:
                proc.terminate()  # 结束进程
                logger.info(f"Process with name: {proc_name} terminated successfully.")
        except psutil.NoSuchProcess:
            logger.info(f"No process found with name: {proc_name}")
        except psutil.AccessDenied:
            logger.info(f"Access denied to terminate process with name: {proc_name}")
        except Exception as e:
            logger.error(f"An error occurred while trying to terminate {proc_name}: {e}")


def close_all_applications():
    """
    关闭所有应用程序
    """
    logger.info("关闭所有应用程序")
    names = ["EXCEL.EXE", "chrome.exe"]
    terminate_process_by_names(names)


def terminate_process_by_pid(pid: int):
    """
    根据进程ID结束进程。
    """
    try:
        # 根据PID创建Process对象
        proc = psutil.Process(pid)

        # 结束进程
        proc.terminate()

        logger.info(f"Process with PID: {pid} terminated successfully.")
    except psutil.NoSuchProcess:
        logger.info(f"No process found with PID: {pid}")
    except psutil.AccessDenied:
        logger.warning(f"Access denied to terminate process with PID: {pid}")
    except Exception as e:
        logger.info(f"An error occurred: {e}")


def terminate_process_by_keyword(keyword: str):
    """
    根据命令行参数结束匹配的进程。

    参数:
        keyword (str): 要结束的进程的命令行参数。
    """
    # 1) 获取符合条件的进程列表
    process_list = get_process_list_by_cmdline(keyword)

    # 2) 结束进程
    if process_list:
        for process_item in process_list:
            pid = process_item["pid"]
            terminate_process_by_pid(pid)

    logger.info(f"Terminated {len(process_list)} processes with keyword: {keyword}")


def terminate_app_by_script(file_path_script: Path = None):
    """
    基于启动脚本路径关闭应用程序

    """
    if file_path_script is None:
        file_path_script = Path(get_path("main.py"))
    terminate_process_by_keyword(str(file_path_script))


class KeepOneInstance:
    """
    一个用于确保应用只运行一个实例的类。
    """

    def __init__(self, file_path_script: str = None):
        # 初始化时，设置实例信息文件的路径并确保其父目录存在。
        # 获取当前运行脚本的绝对路径。
        if file_path_script:
            self.file_path_script = file_path_script
        else:
            self.file_path_script = str(Path(get_path("main.py")).resolve())

    def __call__(self, func):
        @functools.wraps(func)
        def wrapped(*args, **kwargs):

            # 获取包含当前脚本路径的进程列表，排除当前进程。
            process_list = get_process_list_by_cmdline(self.file_path_script)

            # 如果找到了其他实例，记录日志并退出程序
            if process_list:
                logger.info(f"有 {len(process_list)} 个符合条件的进程。")
                if len(process_list) > 3:
                    logger.warning("有多个实例在运行，程序退出。")
                    sys.exit(0)

            # 如果没有找到其他实例，记录当前实例信息并继续执行。
            app_name = get_app_name()
            launch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            logger.info(f"应用 {app_name} ，开始启动: {launch_time}")

            return func(*args, **kwargs)

        return wrapped


@KeepOneInstance()
def keep_one_instance():
    logger.info("保持只有一个实例在运行")


def get_process_list_by_cmdline(keyword: str) -> list:
    # 循环遍历所有进程，找到 cmdline 包含指定关键字的进程
    process_list = []
    for proc in psutil.process_iter(attrs=['pid', 'cmdline']):

        try:
            # 有些进程可能没有 cmdline 属性，跳过这些进程
            if proc.info.get('cmdline', []) is None:
                continue

            # 将命令行参数列表转换为字符串
            cmdline_str = ' '.join(proc.info.get('cmdline', []))

            # 检查转换后的命令行字符串是否包含关键字
            if keyword in cmdline_str:
                process_item = {
                    "pid": proc.info['pid'],
                    "cmdline": cmdline_str,
                    "name": proc.info['cmdline'][0] if proc.info['cmdline'] else None,
                    "cwd": proc.cwd() if proc.cwd() else "N/A",
                }
                # 符合条件则添加到 process_list
                process_list.append(process_item)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    return process_list


def get_file_path_info(file_path_script: Path) -> Path:
    """
    获取进程文件信息的路径。
    Args:
        file_path_script:

    Returns:

    """
    app_name = file_path_script.parent.name
    file_path_info = file_path_script.parent / "data" / f"last_run_{app_name}.json"
    return file_path_info


def check_instance(file_path_script: Path) -> bool:
    """
    检查当前应用的main进程是否存在。

    :return: 如果存在返回True，否则返回False。
    """
    process_list = get_process_list_by_cmdline(str(file_path_script))
    logger.info(f"有 {len(process_list)} 个符合条件的进程。")
    return len(process_list) > 0


def check_last_run_time(file_path_script: Path, interval_run: int = 60 * 15) -> bool:
    """
    检查上次运行时间是否超过指定间隔。

    :return: 如果未超过指定间隔返回True，否则返回False。
    """
    file_path_info = get_file_path_info(file_path_script)
    if file_path_info.exists():
        try:
            with open(file_path_info, "r") as file:
                info = json.load(file)
                last_run_time = info.get("last_run_time")

                if last_run_time is None:
                    logger.error("文件中不存在上次运行时间")
                    return False

            last_run_time = datetime.strptime(last_run_time, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            time_diff = (now - last_run_time).total_seconds()

            if time_diff < interval_run:
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"读取文件 {file_path_info.name} 时发生错误：{e}")
            return False
    else:
        logger.error(f"没有找到文件 {file_path_info.name}，无法检查上次运行时间")
        return False


def update_last_run_time(file_path_script: Path):
    """
    更新上次运行时间。
    """
    app_name = file_path_script.parent.name
    file_path_info = get_file_path_info(file_path_script)

    if file_path_info.exists():
        try:
            with open(file_path_info, "r") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            logger.error(f"读取文件 {file_path_info} 时发生错误，文件可能为空或格式不正确")
            data = {}
    else:
        data = {"app_name": app_name, "last_run_time": None}

    last_run_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data["last_run_time"] = last_run_time

    file_path_info.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path_info, "w") as file:
        json.dump(data, file)

    logger.info(f"更新上次运行时间为 {last_run_time}")


def launch_app(file_path_script: Path):
    """
    运行应用程序
    """
    app_name = file_path_script.parent.name
    file_path_cmd_lnk = file_path_script.parent / f"commands/{app_name}.lnk"
    if file_path_cmd_lnk.exists():
        try:
            logger.info(f"运行快捷方式 {file_path_cmd_lnk}")
            absolute_shortcut_path = str(file_path_cmd_lnk.absolute())
            subprocess.Popen(f'cmd /c start "" "{absolute_shortcut_path}"', shell=True)
        except Exception as e:
            logger.error(format_exc())
            logger.error(f"运行快捷方式 {file_path_cmd_lnk} 时发生错误：{e}")
    else:
        logger.error(f"找不到快捷方式 {file_path_cmd_lnk}")


if __name__ == "__main__":
    # terminate_process_by_keyword(fr"{get_app_name()}\main.py")
    close_all_applications()
    # get_all_processes(Path("test\data\processes.json"))
