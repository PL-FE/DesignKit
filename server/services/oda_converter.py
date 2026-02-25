import asyncio
import os
import tempfile
import shutil
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

async def convert_dwg_version(input_file_path: str, target_version: str) -> str:
    """
    使用 ODA File Converter 将 CAD 文件转换为目标版本
    
    :param input_file_path: 原始 CAD 文件的绝对路径
    :param target_version: 目标版本标识，例如 ACAD2018
    :return: 转换后的文件绝对路径
    """
    input_path = Path(input_file_path)
    file_name = input_path.name
    
    # 获取 ODA File Converter 执行路径（根据不同系统可能不同）
    # 在 Docker 容器中通常安装在 /usr/bin/ODAFileConverter
    # macOS 本地通常在 /Applications/ODAFileConverter.app/Contents/MacOS/ODAFileConverter
    oda_exec = os.environ.get("ODA_CONVERTER_PATH", "ODAFileConverter")
    
    # 创建临时输出目录
    output_dir = tempfile.mkdtemp(prefix="oda_out_")
    
    try:
        # 命令行参数: ODAFileConverter <InputFolder> <OutputFolder> <Version> <Output_Format> <Recurse> <Audit>
        # Output_Format="DWG", Recurse="0", Audit="1"
        args = [
            oda_exec,
            str(input_path.parent),
            output_dir,
            target_version,
            "DWG",
            "0",
            "1"
        ]
        
        logger.info(f"执行命令: {' '.join(args)}")
        
        # 异步执行子进程
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"ODA 转换失败: stdout={stdout.decode()}, stderr={stderr.decode()}")
            raise Exception("文件转换过程中发生错误，ODA File Converter 退出代码非 0")
            
        # 转换成功后，从输出目录中找到文件
        converted_file = Path(output_dir) / file_name
        
        if not converted_file.exists():
            raise Exception("转换成功但未找到输出文件")
            
        temp_dest = tempfile.mktemp(suffix=".dwg")
        shutil.copy2(converted_file, temp_dest)
        return temp_dest
        
    finally:
        # 清理临时输出目录
        shutil.rmtree(output_dir, ignore_errors=True)
