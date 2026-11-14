# PotPlayer 26.x 兼容性修复说明

> 本文档记录针对 PotPlayer **26.x**（2026 年起的新版本）适配本插件的全部改动。
> 原插件最后更新于 2025-05-22（v1.3），而 PotPlayer 26.x 对 AngelScript 扩展系统做了较大重构，
> 导致原版插件在新版播放器上出现多种播放失败。以下修复已在 PotPlayer **26.10.21** 上实测通过。

---

## 一、问题现象

在原版插件 + PotPlayer 26.x 的组合下，会出现以下一种或多种症状：

| 现象 | 具体表现 |
|---|---|
| 黑屏转圈 | 点击播放后一直加载，无画面无声音 |
| 报错「服务器已关闭或地址错误」 | 弹窗提示，附带「在渲染下列 Pin 时失败了」 |
| 只有第一个分P能播 | 合集列表里第 1 集正常，第 2 集起全部「文件无法播放」 |
| 有画面没声音 | 视频正常渲染，但音轨完全静音 |
| 画质模糊 | 明明选了 1080P，实际画面像 360P |
| 失败无任何提示 | 因为原插件不设置 `errorMessage` 字段 |

---

## 二、根本原因

排查后确认是 **6 个独立问题叠加**，而非单一故障：

### 1. 旧式账号回调被废弃 → 配置文件读不进来

PotPlayer 26.x 的 `Extension/api.txt` 中，`GetUserText` / `GetPasswordText` / `ServerCheck` /
`ServerLogin` 这些旧接口**已全部移除**，改为 WebView2 登录 + `HostGetCookie()`。

而原插件把「读取配置文件」写在 `ServerLogin()` 里，这个方法在新版中**永远不会被调用**，
于是 `ConfigData` 始终是默认值：Cookie 为空、弹幕地址为空。

### 2. `HostSetUrlHeaderHTTP` 写入注册表但不生效

插件通过该 API 给 CDN 域名设置 Referer，注册表 `_UrlHeader` 里确实能看到值，
但 **实际播放时 PotPlayer 并未把 Referer 发出去**。

而 B站 CDN 强制校验 Referer，实测：

```
带 Referer  → HTTP 206  正常返回视频流
不带 Referer → HTTP 403  拒绝访问
```

403 在 PotPlayer 里就表现为「服务器已关闭或地址错误」+「Pin 渲染失败」。

### 3. 弹幕服务器域名已失效

默认配置 `server: https://subtitle.chen310.repl.co` —— 该域名 **DNS 已无法解析**（NXDOMAIN），
Replit 的免费托管服务早已关停。插件会把每集的弹幕当成「字幕」去加载，请求必然失败。

### 4. `durl` 分支会把空 URL 塞进画质列表

原代码遍历 `accept_quality` 为每个画质单独请求播放地址，但请求失败时
`qualityitem["url"]` 保持空字符串，仍然被 `insertLast` 加入 `QualityList`。
PotPlayer 一旦选中这个空项，就是「文件无法播放」。

同时 `int quality_codecid;` 未初始化，失败时 `itag` 会算成错误值。

### 5. DASH 分离流音轨配对失败 → 无声

`fnval=4048` 返回的是 DASH 格式，**视频流和音频流是分离的两个文件**，
需要播放器按 `itag` 自行配对合并。PotPlayer 26.x 下该机制失效，
结果就是画面正常、音轨为空。

### 6. 多P 缺少唯一标识

原插件从不设置 `MetaData["vid"]`，而新版 API 文档明确要求
「Give each part of a multi-part video its own vid」，
否则多P 的播放进度、音轨记忆会相互串扰。

---

## 三、修复清单

修改后的 `MediaPlayParse - Bilibili.as` 相对原版 **+116 行 / -22 行**，共 9 处改动：

| # | 改动 | 作用 |
|---|---|---|
| 1 | `EnsureConfig()` 懒加载配置 | 在 `PlaylistParse` / `PlayitemParse` 入口读取配置文件，绕过被废弃的 `ServerLogin` |
| 2 | 弹幕/字幕 URL 空值保护 | `danmakuUrl.empty()` 时不再构造无效字幕地址 |
| 3 | `forceMuxed` 开关 + `getFnval()` | 默认走 `fnval=1`（音视频合一的 mp4），彻底解决无声 |
| 4 | durl 循环只保留最高画质 | 不再插入空 URL 项，也不会误选 360P |
| 5 | `quality_codecid` 初始化 | 避免 itag 计算出错值 |
| 6 | `MetaData["vid"] = bvid + "_p" + p` | 每个分P 独立标识，进度/音轨记忆互不干扰 |
| 7 | 4 处 `errorMessage` | 失败时明确告知原因，不再静默 |
| 8 | `post()` 自动降级 | `HostUrlGetStringWithAPI` 返回空时自动改用 `HostUrlGetString` 重试 |
| 9 | `ApplyCdnHeader()` + `WrapProxy()` | 精确到实际 CDN 子域名设置 Referer；并接入本地转发服务 |

### 关于第 9 项（最终解法）

前 8 项修复后，解析链路已完全正常（控制台可见 `result: OK`、URL 成功获取），
但 PotPlayer 仍然发不出 Referer，CDN 依旧 403。因此增加**本地转发方案**：

```
PotPlayer ──► http://127.0.0.1:18999/p/<id>
                     │
                     ├─ 本地服务补上 Referer/UA/Origin
                     ▼
              B站 CDN（返回 206 视频流）
                     │
                     ▼
              流式转发回 PotPlayer
```

由于 PotPlayer 请求的是本机地址，不涉及任何 header 校验，问题被彻底绕开。

`proxy/bili_proxy.py` 即该服务，仅依赖 Python 3 标准库，无需安装任何第三方包。
服务未启动时，插件会自动回退到直连 CDN（即修复前的行为），不会导致更差的结果。

---

## 四、安装步骤

### 1. 复制插件文件

将以下文件复制到 PotPlayer 安装目录：

```
<PotPlayer 安装目录>\Extension\Media\PlayParse\
    ├─ MediaPlayParse - Bilibili.as
    ├─ MediaPlayParse - Bilibili.ico
    └─ Bilibili_Config.json

<PotPlayer 安装目录>\Extension\Media\UrlList\
    ├─ MediaUrlList - Bilibili.as
    └─ MediaUrlList - Bilibili.ico
```

> 若目录已存在同名文件，直接覆盖。建议先备份原文件。

### 2. 填写 Cookie

编辑 `Bilibili_Config.json`，把 `"cookie": ""` 填成你自己的 B站 Cookie。

获取方法见 <https://github.com/chen310/BilibiliPotPlayer/issues/62>。

至少需要包含 `SESSDATA` 和 `bili_jct` 两项，否则只能拿到低画质甚至无法解析。

### 3. 在 PotPlayer 中指定配置路径

打开 PotPlayer → 按 `F5` → **扩展功能** → **媒体播放列表/项目** → 选中 `Bilibili` →
点击 **账户设置** → 在「配置文件路径」填入**完整绝对路径**，例如：

```
D:\Program Files\DAUM\PotPlayer\Extension\Media\PlayParse\Bilibili_Config.json
```

填写后点击「测试」，若能弹出账号信息即表示成功。

> 注意：受限于 PotPlayer 26.x 移除了旧式登录回调，此处的「测试」按钮可能无响应。
> 没关系——修复版插件已用 `EnsureConfig()` 自行读取配置文件，不依赖这个回调。
> **每次修改配置文件后都需要重启 PotPlayer。**

### 4. 启动转发服务

双击 `proxy\start_proxy.bat`。

- 已有实例在运行时脚本会提示 `already running`，直接关闭即可。
- 服务在后台运行（`pythonw.exe`），无窗口。
- 验证：浏览器打开 <http://127.0.0.1:18999/ping>，看到 `pong` 即正常。

### 5. 设置开机自启（可选但推荐）

把 `start_proxy.bat` 的快捷方式放入启动文件夹：

1. 按 `Win + R`，输入 `shell:startup`，回车
2. 将 `start_proxy.bat` 的**快捷方式**拖进去

这样每次开机会自动启动转发服务，无需手动操作。

### 6. 开始播放

- 直接把 B站链接拖进 PotPlayer，或按 `Ctrl + U` 粘贴链接
- 合集链接（不带 `?p=`）会解析出全部分P 列表
- 单集链接（带 `?p=N`）直接播放该集

---

## 五、配置项说明

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `cookie` | `""` | B站账号 Cookie，必填 |
| `forceMuxed` | `true` | `true` 走音视频合一的 mp4，声音必定正常，画质上限 1080P<br>`false` 走 DASH 分离流，画质更高但 PotPlayer 26.x 下可能无声 |
| `danmaku.enable` | `false` | 弹幕开关。默认服务器已失效，未换可用服务器前请保持 `false` |
| `danmaku.server` | `""` | 弹幕服务器地址，需自行部署或寻找可用实例 |
| `showRecommendedVideos` | `true` | 播放单集时是否在列表中附加推荐视频 |
| `debug` | `false` | 开启后播放时弹出 AngelScript 控制台，输出解析日志，排查问题用 |

### 画质与声音的取舍

B站 对同一视频会提供多档码率。实测同一 1080P 视频：

```
DASH 分离流 (forceMuxed=false)  →  视频流 133 kbps + 音频流 127 kbps
durl 合一流 (forceMuxed=true)   →  单文件 265 kbps（含音视频）
```

屏幕录制类内容（如编程教程）B站 压缩很激进，133 kbps 的 1080P 本身就偏糊。
`forceMuxed=true` 的 265 kbps 反而是更高的整体码率，且不存在无声问题。

若播放真 4K / HDR 内容需要更高画质，可将 `forceMuxed` 改为 `false`，
但需自行确认音轨是否正常。

---

## 六、故障排查

| 现象 | 检查项 |
|---|---|
| 提示「服务器已关闭或地址错误」 | ① 转发服务是否在运行（访问 `/ping`）② Cookie 是否失效 |
| 有画面没声音 | `forceMuxed` 是否为 `true` |
| 播不了第 2 集及以后 | 确认插件文件已更新为新版（文件大小应约 66 KB） |
| 完全没反应、列表也解析不出 | 插件未加载。检查 `Extension\Media\PlayParse\` 下文件名是否正确（注意空格和大小写），并确认 PotPlayer 中已启用该扩展 |
| 想确认解析过程 | 把 `debug` 改为 `true`，播放时会弹出控制台，可见 `request:` / `result:` / `url:` / `proxy-id:` 等日志 |
| `proxy-id` 没有出现 | 转发服务未启动，插件已回退到直连模式 |

### 关键日志含义

```
Playitem path: https://www.bilibili.com/video/BVxxxx?p=1   ← 收到播放请求
request: https://api.bilibili.com/x/web-interface/view?...  ← 请求视频信息
result: OK                                                  ← 请求成功
request: https://api.bilibili.com/x/player/playurl?...      ← 请求播放地址
result: OK
url: https://upos-sz-xxx.bilivideo.com/....mp4?....         ← 解析出的真实地址
proxy-id: 1                                                 ← 已注册到转发服务
```

看到 `proxy-id` 就说明走的是转发通道，播放应正常。
若显示 `proxy: service down -> direct url`，则是服务没启动。

---

## 七、已知限制

1. **画质上限 1080P** —— 受 `forceMuxed=true` 限制，不支持 4K/HDR/杜比视界
2. **弹幕不可用** —— 原弹幕服务器域名已失效，需自行部署替代服务
3. **长视频可能只播第一段** —— `durl` 模式下若 B站 把视频切成多段，插件只取第一段。
   实测 7 分钟左右的视频为单段，超长视频（如电影）可能受影响
4. **依赖转发服务** —— 服务未运行时无法播放（会自动回退到直连，但直连会 403）
5. **Cookie 会过期** —— SESSDATA 有效期约半年，过期后需重新获取

---

## 八、免责声明

本项目为 [chen310/BilibiliPotPlayer](https://github.com/chen310/BilibiliPotPlayer) 的兼容性修复分支，
仅用于个人学习与本地播放便利，不得用于任何商业用途或大规模抓取。
所有视频内容的版权归 B站 及原上传者所有。请遵守 B站 用户协议。
