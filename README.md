# Lite-Gauge

简洁的 Windows 桌面性能监控工具。在一个置顶小窗口里查看 CPU、内存、GPU、显存占用和实时网速。

![Lite-Gauge 界面预览](docs/预览.png)

## 功能

- **四组圆环仪表**：直观显示 CPU、内存、GPU 和显存使用率，约每秒更新一次。
- **容量与型号**：显示已用 / 总内存、已用 / 总显存，以及当前监控的 GPU 型号。
- **实时网速**：查看上传与下载速度。
- **桌面置顶**：拖动窗口自由摆放，也可一键移至屏幕右下角。
- **深浅主题**：点击按钮即可切换明暗外观。

## 开始使用

解压完整程序包，双击 `LiteGauge.exe` 即可运行，无需安装 Python。

请保留程序包中的文件夹和依赖文件，不要单独移动 EXE。使用外层启动器时，旁边的 `LiteGauge` 文件夹也需要一起保留。

| 操作 | 方法 |
| --- | --- |
| 移动窗口 | 按住窗口空白处拖动 |
| 切换主题 | 点击右下角月亮 / 太阳按钮 |
| 移至右下角 | 点击右下角箭头按钮 |
| 退出程序 | 点击右上角 `×` |

请保持只运行一个实例。

## GPU 与显存支持

GPU 占用优先使用 Windows 提供的数据，并识别对应显卡的型号。多显卡设备会显示当前最繁忙的 GPU 引擎占用。

显存监控目前支持可通过 NVML 读取数据的 NVIDIA 显卡。无法读取显存时，圆环显示 `0%`，底部不显示显存容量；这不代表实际没有使用显存。多显卡设备的 GPU 占用与显存数据可能来自不同显卡。

## 从源码运行

项目已在 Windows、Python 3.11 环境下验证。在项目目录打开 PowerShell，执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install PyQt6 psutil nvidia-ml-py
.\.venv\Scripts\python.exe start.py
```

没有 NVIDIA 显卡时，可以省略 `nvidia-ml-py`。

<details>
<summary>自行打包</summary>

完成上面的依赖安装后，关闭正在运行的程序，再执行：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm LiteGauge-onedir.spec
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm LiteGauge-launcher.spec
```

生成的程序位于 `dist/`。分发时保留整个目录，包括外层启动器和 `LiteGauge/` 文件夹。

</details>
