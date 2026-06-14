# Clip Board Workbench

Clip Board 是一个正在成长中的桌面视觉素材板和轻量动画剪贴工具台。当前版本使用
`PySide6 + Qt Graphics View + Pillow`，项目格式已经为后续 FFmpeg 导出、关键帧和多轨
时间轴预留结构。

## 当前可用

- 无限画布：缩放、空白处拖拽平移、中键平移、框选和多选。
- 素材导入：GIF、PNG、JPG、JPEG、WEBP、BMP、APNG。
- 素材库：导入后按内容哈希去重，双击素材可再次放到画布。
- GIF 预览：播放、暂停、逐帧查看以及 `0.25x` 到 `4x` 调速。
- 文字批注：支持同框富文本混排、字号、文字颜色、粗体、斜体、下划线和段落对齐。
- 批注背景：可选择背景颜色和透明度，保存重启后保持一致。
- GIF 浮动控制条：选中 GIF 后显示在画面下方，包含上一帧、播放/暂停、下一帧、倍速和当前帧数；点击画布空白处自动隐藏。
- GIF 帧面板：选中 GIF 后自动展开全部缩略图、帧号与逐帧时长；点击帧数按钮可收起或再次展开。
- 帧编辑：支持 `Cmd/Ctrl` 多选、`Shift` 区间选择、复制、删除和拖拽重排。
- 帧粘贴：未选中 GIF 时生成新 GIF；选中 GIF 时插入到当前帧之后。
- 帧拖放：拖到画布空白处生成新 GIF，拖到另一个 GIF 上直接插入。
- 时间轴基线：Composition、Track、Clip、播放头和非破坏性入点/出点数据。
- 撤销重做：覆盖画布对象增删，以及 GIF 插帧、删帧和重排。
- 项目存档：`.clipboard` 是包含 `project.json` 与素材文件的便携压缩包。
- 存档入口：第一次主动保存弹出另存为，后续保存沿用同一路径；macOS 可双击 `.clipboard` 直接打开工具。
- 自动恢复：编辑状态每 30 秒自动保存，下次启动自动恢复。
- 剪贴板：可粘贴图片文件、系统图片和 Clip Board 帧选择。

## 本地运行

需要 Python 3.11 或更新版本。macOS 不建议使用系统自带的 Xcode Python 3.9。

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python main.py
```

### macOS 应用

如果直接从 Python 启动遇到 Qt Cocoa 插件问题，构建标准 `.app`：

```bash
chmod +x build_macos.sh
./build_macos.sh
```

脚本会把应用安装到：

```text
~/Applications/Clip Board.app
```

之后可在 Finder 的个人 Applications 文件夹中双击，或在终端运行：

```bash
open "$HOME/Applications/Clip Board.app"
```

Windows:

```bat
run.bat
```

也可以直接打开项目：

```bash
.venv/bin/python main.py example.clipboard
```

## 主要快捷键

| 快捷键 | 功能 |
| --- | --- |
| `Ctrl/Cmd+I` | 导入图片或 GIF |
| `Ctrl/Cmd+C` | 复制帧面板中选中的帧 |
| `Ctrl/Cmd+V` | 生成新 GIF，或插入当前选中的 GIF |
| `Ctrl/Cmd+S` | 保存项目 |
| `Ctrl/Cmd+Shift+S` | 另存为 |
| `Backspace` / `Delete` | 删除选中的帧或画布对象 |
| `Space` | 播放 / 暂停 |
| `Left` / `Right` | 选中 GIF 逐帧查看，支持长按连续切换 |
| `1` 到 `5` | 速度 0.25x、0.5x、1x、2x、4x |
| `F` | 适应全部画布内容 |
| `Ctrl/Cmd+0` | 重置视图 |

触控板双指滚动用于平移画布，捏合手势用于缩放。鼠标或触控板配合
`Cmd/Ctrl + 滚动` 会以指针位置为中心平滑缩放。左键拖拽空白处或中键拖拽可平移，
按住 `Shift` 在空白处拖拽可框选。

## 测试

```bash
.venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=offscreen .venv/bin/python scripts/smoke_ui.py
```

Smoke test 会生成 PNG/GIF，完整执行导入、GIF 控制条、帧面板、保存、重新加载和截图。

## Windows 构建

```bat
build.bat
```

脚本使用 Qt 官方的 `pyside6-deploy`。首次构建会安装其构建依赖。Windows 成品需要在
Windows 机器上构建和验证，macOS 不能交叉生成 Windows exe。

## 下一阶段

1. 时间轴编辑：Clip 拖拽、裁切、轨道增删、吸附和缩放。
2. 舞台模式：固定画幅、图层顺序、对齐、安全框和背景设置。
3. 动画示意：位置、缩放、旋转、透明度关键帧和缓动曲线。
4. FFmpeg 导出：GIF、APNG、WebM、MP4，并把耗时任务放入后台 worker。

完整架构、运行流程、存档格式、打包方式和强制维护规则见
[ARCHITECTURE.md](ARCHITECTURE.md)。
