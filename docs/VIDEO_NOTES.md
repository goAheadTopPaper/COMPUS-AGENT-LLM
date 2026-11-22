# Demo 视频交付说明

成片：`COMP5584_Demo.mp4`（桌面），85 秒，1920×1080，4.1 MB，字幕已烧入。

| 段落 | 时间 | 内容 |
|---|---|---|
| 架构静帧 | 0:00–0:05 | `docs/slides/01-architecture.png` |
| 录屏（含字幕） | 0:05–1:20 | 三条查询实测 |
| 汇总静帧 | 1:20–1:25 | `docs/slides/02-results.png` |

字幕时间轴以**录屏内部**时间为基准，因前面插了 5 秒架构图，成片里整体后移 5 秒
（第 1 条出现在 0:05，最后一条在 1:15–1:20）。

重新生成需要 ffmpeg（本机通过 `python3 -m pip install imageio-ffmpeg` 获得）：

```bash
python3 /tmp/build_video.py          # 需要 /tmp/slide_intro.png、slide_outro.png
```

字幕文案见 `docs/SUBTITLES.md`。
